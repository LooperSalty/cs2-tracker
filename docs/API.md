# Référence de l'API

Base : `http://127.0.0.1:8642`
Documentation interactive : [`/docs`](http://127.0.0.1:8642/docs) · Schéma : `/openapi.json`

L'API n'écoute que sur la boucle locale. Le CORS est restreint aux origines
locales et aucune authentification n'est requise — c'est un service personnel.

## Enveloppe

Toute réponse, succès comme échec, suit la même forme :

```json
{ "success": true,  "data": { }, "error": null, "meta": null }
{ "success": false, "data": null, "error": "Message lisible.", "meta": { } }
```

| Code | Signification |
|---|---|
| 400 | Identifiant Steam mal formé |
| 401 | Jeton GSI invalide, ou clé Steam refusée |
| 403 | Profil Steam privé |
| 404 | Joueur, match ou statistique introuvable |
| 422 | Corps de requête invalide (détail dans `meta.details`) |
| 429 | Limite de requêtes Steam atteinte |
| 503 | Clé API Steam absente |

---

## Système

| Méthode | Chemin | Description |
|---|---|---|
| `GET` | `/health` | Sonde de santé |
| `GET` | `/api/system/status` | État complet : Steam, CS2, GSI, base, cache |
| `GET` | `/api/system/cs2` | Chemins d'installation détectés |
| `POST` | `/api/system/steam-key` | Enregistre la clé Steam dans `.env` |
| `POST` | `/api/system/gsi/install` | Écrit le `.cfg` GSI dans CS2 |
| `DELETE` | `/api/system/gsi/install` | Retire le `.cfg` |
| `GET` | `/api/system/gsi/preview` | Aperçu du fichier généré |
| `GET` | `/api/system/servers` | État des serveurs CS2 et joueurs en ligne |
| `POST` | `/api/system/cache/clear` | Vide le cache Steam |

```bash
curl http://127.0.0.1:8642/api/system/status
```

---

## Joueurs

| Méthode | Chemin | Description |
|---|---|---|
| `POST` | `/api/players/search` | Recherche + profil complet (`{"query": "..."}`) |
| `GET` | `/api/players/resolve/{query}` | Résout une identité (appel Steam si vanity) |
| `GET` | `/api/players/parse/{query}` | Analyse une saisie **sans réseau** |
| `GET` | `/api/players/tracked` | Joueurs suivis localement |
| `GET` | `/api/players/{steamid}` | Profil complet |
| `GET` | `/api/players/{steamid}/summary` | Résumé Steam |
| `GET` | `/api/players/{steamid}/bans` | Sanctions |
| `GET` | `/api/players/{steamid}/stats` | Statistiques CS2 à vie |
| `GET` | `/api/players/{steamid}/weapons` | Détail par arme + agrégat |
| `GET` | `/api/players/{steamid}/maps` | Détail par carte |
| `GET` | `/api/players/{steamid}/games` | Bibliothèque et temps de jeu |
| `GET` | `/api/players/{steamid}/friends` | Liste d'amis (`?with_profiles=true`) |
| `GET` | `/api/players/{steamid}/achievements` | Succès CS2 |
| `GET` | `/api/players/{steamid}/recent` | Jeux joués récemment |
| `GET` | `/api/players/{steamid}/history` | Relevés locaux + progression + matchs |
| `POST` | `/api/players/{steamid}/snapshot` | Force un relevé |
| `PUT` | `/api/players/{steamid}/favourite` | Marque comme favori |
| `PUT` | `/api/players/{steamid}/notes` | Note personnelle |
| `DELETE` | `/api/players/{steamid}` | Retire du suivi local |

`{steamid}` doit être un SteamID64 (17 chiffres). Les autres formats passent par
`/resolve`.

```bash
curl -X POST http://127.0.0.1:8642/api/players/search \
     -H "Content-Type: application/json" \
     -d '{"query": "https://steamcommunity.com/id/pseudo"}'
```

<details>
<summary>Extrait de réponse (<code>data</code>)</summary>

```json
{
  "identity": { "steamid64": "7656...", "steamid3": "[U:1:...]", "steamid2": "STEAM_1:..." },
  "summary":  { "persona_name": "...", "is_public": true, "playing_cs2": false },
  "bans":     { "vac_banned": false, "total_bans": 0, "has_any_ban": false },
  "stats": {
    "totals": { "kills": 12345, "rounds_played": 20000, "shots_fired": 90000 },
    "ratios": { "kd": 1.12, "headshot_rate": 0.47, "accuracy": 0.211,
                "damage_per_round": 75.0, "hits_per_kill": 3.9 },
    "last_match": { "kd": 1.29, "adr": 92.3, "favourite_weapon": "AK-47" },
    "weapons": [ { "name": "AK-47", "kills": 4000, "accuracy": 0.22 } ],
    "maps":    [ { "name": "Dust II", "rounds_played": 6100, "win_rate": 0.49 } ]
  },
  "account": { "cs2_hours": 1000.0, "steam_level": 20, "friends_count": 48 },
  "partial_errors": []
}
```
</details>

---

## Anti-triche

| Méthode | Chemin | Description |
|---|---|---|
| `GET` | `/api/anticheat/disclaimer` | Portée, méthodologie, faux positifs connus |
| `GET` | `/api/anticheat/weights` | Pondération courante des détecteurs |
| `GET` | `/api/anticheat/{steamid}` | Analyse complète |
| `GET` | `/api/anticheat/{steamid}/report` | Rapport texte lisible |
| `GET` | `/api/anticheat/{steamid}/history` | Analyses précédentes |
| `POST` | `/api/anticheat/batch` | Jusqu'à 10 joueurs d'un coup |
| `POST` | `/api/anticheat/lobby/live` | Tous les joueurs vus en direct |
| `GET` | `/api/anticheat/leaderboard/suspicious` | Profils les plus suspects analysés |

Paramètres de `/api/anticheat/{steamid}` : `use_live` (défaut `true`),
`persist` (défaut `true`), `include_features` (défaut `true`).

```bash
curl "http://127.0.0.1:8642/api/anticheat/76561198000000001?use_live=true"
```

<details>
<summary>Extrait de réponse</summary>

```json
{
  "suspicion_score": 91.0,
  "verdict": "CRITICAL",
  "verdict_label": "Faisceau d'indices tres lourd",
  "global_confidence": 0.86,
  "has_confirmed_ban": false,
  "data_sources": { "lifetime_stats": true, "live_gsi": true, "public_profile": true },
  "categories": [ { "category": "visee", "score": 96.4, "confidence": 1.0, "signals": 5 } ],
  "signals": [
    {
      "key": "aim.headshot_rate",
      "label": "Taux de tirs a la tete",
      "category": "visee",
      "score": 0.91, "confidence": 1.0, "weight": 2.6,
      "severity": "critique",
      "explanation": "86.5 % des eliminations sont des headshots, contre 45.0 % ...",
      "observed": 0.865, "expected": 0.45, "z_score": 4.37,
      "sample_size": 60000, "contribution": 2.37
    }
  ],
  "disclaimer": "Ce score est une estimation statistique ..."
}
```
</details>

---

## Temps réel

| Méthode | Chemin | Description |
|---|---|---|
| `POST` | `/gsi` | **Appelé par CS2**, pas par toi. Jeton obligatoire |
| `GET` | `/api/live/state` | Instantané complet de l'état de jeu |
| `GET` | `/api/live/scoreboard` | Tableau des scores |
| `GET` | `/api/live/players` | Métriques accumulées par joueur |
| `GET` | `/api/live/players/{steamid}` | Métriques d'un joueur |
| `GET` | `/api/live/events` | Flux d'événements (`?since=<seq>`) |
| `POST` | `/api/live/reset` | Réinitialise l'état |
| `WS` | `/ws/live` | Diffusion continue |

Le flux d'événements est **incrémental** : conserve `latest_sequence` et
repasse-le en `since` pour ne recevoir que les nouveautés.

```javascript
const socket = new WebSocket("ws://127.0.0.1:8642/ws/live");
socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") console.log(message.state, message.events);
};
```

Types d'événements : `kill`, `headshot_kill`, `multi_kill`, `death`, `assist`,
`mvp`, `round_start`, `round_freeze`, `round_end`, `bomb_planted`,
`bomb_defused`, `bomb_exploded`, `match_start`, `match_end`, `map_change`,
`weapon_switch`, `damage_taken`, `flashed`, `low_health`, `connection`.

---

## Matchs

| Méthode | Chemin | Description |
|---|---|---|
| `GET` | `/api/matches` | Matchs récents |
| `GET` | `/api/matches/current` | Match en cours d'enregistrement |
| `GET` | `/api/matches/{id}` | Détail (joueurs + manches) |
| `GET` | `/api/matches/{id}/rounds` | Manches |
| `GET` | `/api/matches/{id}/players` | Joueurs |

---

## Limites

- **Débit Steam** : le client s'auto-limite à 8 requêtes/seconde et met en cache
  (profils 5 min, statistiques 2 min, sanctions 10 min). Vider le cache force
  un rafraîchissement.
- **Profils privés** : `403` avec un message explicite.
- **Données `allplayers`** : uniquement en spectateur ou GOTV — limite de Valve.
