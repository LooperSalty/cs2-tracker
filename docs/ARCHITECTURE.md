# Architecture

## Vue d'ensemble

L'application est une **API locale** entourée de deux clients. Aucune logique
métier ne vit dans les interfaces : elles consomment l'API exactement comme le
ferait un outil tiers, ce qui garantit que l'API est réellement utilisable.

```
             ┌──────────────────┐   ┌──────────────────┐
             │  Interface web   │   │   Fenêtre Qt     │
             │  (cs2tracker/web)│   │  (cs2tracker/ui) │
             └────────┬─────────┘   └────────┬─────────┘
                      │      HTTP / WebSocket │
                      └───────────┬───────────┘
                                  ▼
                   ┌────────────────────────────┐
                   │      API  (FastAPI)        │
                   │      cs2tracker/api        │
                   └──┬────────┬────────┬───────┘
                      │        │        │
        ┌─────────────▼──┐  ┌──▼─────┐  ├──────────────┐
        │  steam/        │  │  gsi/  │  │  anticheat/  │
        │  Steam Web API │  │  Temps │  │  Détecteurs  │
        │                │  │  réel  │  │  + moteur    │
        └────────────────┘  └───┬────┘  └──────┬───────┘
                                │              │
                          ┌─────▼──────────────▼─────┐
                          │  storage/  (SQLite)      │
                          └──────────────────────────┘
```

## Paquets

| Paquet | Rôle | Dépend de |
|---|---|---|
| `core/` | Modèles de domaine, SteamID, utilitaires, erreurs | — |
| `steam/` | Client HTTP, parseurs, service d'agrégation | `core` |
| `gsi/` | Détection de CS2, parsing, diff d'états, agrégation | `core` |
| `anticheat/` | Extraction de variables, détecteurs, moteur, rapports | `core`, `gsi` |
| `storage/` | Schéma SQLite et dépôts | `core`, `anticheat`, `gsi` |
| `api/` | Routes, validation, contexte applicatif | tous |
| `ui/`, `web/` | Clients de l'API | `api` (par HTTP seulement) |

Les dépendances sont **acycliques** et orientées vers `core`.

## Principes appliqués

### Immuabilité

Tous les modèles sont des `dataclass(frozen=True, slots=True)`. Une évolution
d'état produit une copie via `dataclasses.replace`, jamais une mutation.

```python
# gsi/tracker.py — fin de manche
self._players[steamid] = replace(
    metrics, rounds=metrics.rounds + (record,), current_kills=0, ...
)
```

Ce choix élimine une classe entière de bugs : le `MatchTracker` est lu par les
routes REST pendant que l'endpoint GSI l'alimente, sans risque de lecture d'un
état à moitié écrit.

### Échecs partiels isolés

`SteamService.get_full_profile` lance huit appels en parallèle et collecte les
échecs au lieu de les propager :

```python
gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
```

Un profil dont seuls les amis sont privés reste entièrement analysable ; les
sources manquantes remontent dans `partial_errors`.

### Validation aux frontières

- **SteamID** : `deps.validate_steamid` impose 17 chiffres avant toute requête.
- **Corps JSON** : modèles Pydantic avec bornes explicites (`max_length=10` sur
  un lot de joueurs, taille et forme d'une clé Steam).
- **Payload GSI** : jeton vérifié à chaque requête, taille plafonnée.
- **Réponses Steam** : parseurs défensifs, une donnée absente vaut 0.

### Enveloppe de réponse unique

Toute réponse suit la même forme, succès comme échec :

```json
{ "success": true, "data": { }, "error": null, "meta": null }
```

Les erreurs métier portent un `user_message` distinct du message technique : le
détail reste dans les logs, jamais dans la réponse HTTP.

## Flux de données

### Consultation d'un profil

```
UI ──POST /api/players/search──▶ SteamService.get_full_profile
                                        │
                          8 appels Steam en parallèle
                                        ▼
                                 PlayerProfile (immuable)
                                        │
                            ┌───────────┴───────────┐
                            ▼                       ▼
                    PlayerRepository        SnapshotRepository
                    (upsert joueur)         (relevé horodaté)
```

### Partie en direct

```
CS2 ──POST /gsi (10×/s)──▶ vérification du jeton
                                  │
                           parse_payload → GameState
                                  │
                    diff_states(précédent, courant) → événements
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
             LiveStateStore  MatchTracker  MatchRecorder
             (état + flux)   (métriques)   (archivage)
```

Le GSI n'émet que des **états**. Toute la sémantique (« kill », « bombe posée »,
« manche gagnée ») est déduite des transitions par `gsi/events.py`.

### Analyse anti-triche

```
PlayerProfile + LivePlayerMetrics
              │
              ▼
   build_features()          lissage bayésien, confiances, agrégats par arme
              │
              ▼
   7 familles de détecteurs   → ~30 Signal(score, confiance, poids, explication)
              │
              ▼
   engine.analyse()           moyenne pondérée → exposant → corroboration
              │               → planchers (ban, signal critique)
              ▼
   AnalysisResult             score, verdict, catégories, signaux, features
```

## Persistance

SQLite en mode WAL, connexion unique protégée par un `RLock` (l'API est async
mais les écritures sont brèves et sérialisées).

| Table | Contenu |
|---|---|
| `players` | Joueurs connus, favoris, notes |
| `stat_snapshots` | Relevés horodatés — permettent de calculer la progression |
| `analyses` | Historique des rapports anti-triche |
| `matches`, `match_players`, `match_rounds` | Parties observées via GSI |

Toutes les requêtes sont paramétrées ; aucune valeur utilisateur n'est
concaténée dans du SQL.

## Configuration

`config.py` lit l'environnement puis un `.env` optionnel, sans jamais écraser
une variable déjà définie. Les données utilisateur vont dans
`%LOCALAPPDATA%\CS2Tracker` :

| Fichier | Contenu |
|---|---|
| `cs2tracker.db` | Base SQLite |
| `gsi_token.txt` | Jeton partagé entre le `.cfg` de CS2 et le serveur |
| `cs2tracker.log` | Journal rotatif, secrets masqués |

## Tests

97 tests répartis en cinq fichiers :

| Fichier | Couvre |
|---|---|
| `test_steamid.py` | Conversions et parsing de tous les formats d'identifiant |
| `test_parsers.py` | Transformation des payloads Steam |
| `test_gsi.py` | Parsing GSI, moteur de diff, agrégation, dépôt d'état |
| `test_anticheat.py` | Comportement du moteur, y compris sa **prudence** |
| `test_api.py` | Enveloppe, validation, ingestion GSI, persistance, WebSocket |

Les tests du moteur vérifient autant ce qu'il détecte que ce qu'il **refuse** de
détecter : micro-échantillon, profil privé, signature de smurf.
