<div align="right">

[English](README.md) · **Français**

</div>

# CS2 Tracker

<img src="img/logo.png" alt="" width="96" align="right">

Application Windows de suivi statistique pour **Counter-Strike 2**, avec une API
REST locale, un suivi de partie en temps réel et un moteur d'analyse anti-triche
heuristique et explicable.

```
┌─ Steam Web API ─────┐      ┌─ CS2 (Game State Integration) ─┐
│ profils · stats     │      │ état de la partie, 10×/seconde │
│ sanctions VAC       │      └────────────┬───────────────────┘
└──────────┬──────────┘                   │
           └─────────────┬────────────────┘
                         ▼
              ┌──── API locale ────┐
              │ FastAPI · SQLite   │──▶ fenêtre native (défaut)
              │ moteur anti-triche │──▶ overlay en jeu
              └────────────────────┘──▶ vos propres outils
```

---

## Ce que fait l'application

| | |
|---|---|
| **Profil complet** | Identité (SteamID64/2/3), ancienneté, niveau, amis, bibliothèque, succès |
| **Statistiques à vie** | Kills, précision, headshots, dégâts, MVP, manches — par arme et par carte |
| **Classement** | Chaque statistique replacée dans la population : « top 8 % », « Excellent » |
| **Temps réel** | Score, manche, phase, bombe, tableau des scores, flux d'événements |
| **Overlay en jeu** | Panneau natif par-dessus CS2, sans injection ([`overlay/`](overlay/)) |
| **Sanctions** | Bannissements VAC et éditeur, ancienneté, restrictions communautaires |
| **Anti-triche** | Score de suspicion 0–100 avec le détail de chaque indicateur |
| **Import de lobby** | Colle un `status` de la console CS2 pour analyser les 10 joueurs |
| **Historique** | Relevés horodatés, courbes d'évolution, détection de rupture de niveau |
| **API REST** | ~40 endpoints documentés, ouverts à vos propres outils |

---

## Installation

### Option A — l'exécutable (recommandé)

1. Télécharge `CS2Tracker.exe` depuis la page [Releases](../../releases).
2. Double-clique.

Une **fenêtre d'application** s'ouvre. Pas de terminal, pas de navigateur :
l'interface est rendue par WebView2, le moteur intégré à Windows.

Fermer la fenêtre ne quitte pas le programme — il continue en arrière-plan dans
la zone de notification, pour que l'API reçoive les données du jeu pendant ta
partie. Clique sur l'icône pour rouvrir la fenêtre, ou choisis **Quitter**.

Télécharge aussi `CS2TrackerOverlay.exe` et place-le **à côté** si tu veux
l'affichage par-dessus le jeu.

Aucun Python à installer, aucune dépendance. Un dossier de données est créé dans
`%LOCALAPPDATA%\CS2Tracker`.

### Option B — depuis les sources

```powershell
git clone https://github.com/LooperSalty/cs2-tracker.git
cd cs2-tracker
python -m pip install -r requirements.txt
python run.py
```

Python 3.11 ou supérieur.

---

## Configuration en deux étapes

### 1. Clé API Steam

Indispensable pour lire les profils. Elle est **gratuite** et s'obtient en une
minute sur [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey).

Renseigne-la dans l'onglet **Configuration** de l'application, ou crée un fichier
`.env` à la racine :

```ini
STEAM_API_KEY=TA_CLE_ICI
```

La clé n'est écrite que dans ce fichier local et n'est envoyée qu'à Steam. Elle
prend effet immédiatement — aucun redémarrage nécessaire.

> Si plusieurs comptes Steam existent sur ton PC, l'application **demande**
> lequel est le tien au lieu de deviner. La clé API appartient au compte
> connecté sur le *site* Steam, alors que la détection automatique ne voit que
> le *client* Steam — et rien ne relie les deux.

### 2. Liaison temps réel avec CS2

Onglet **Configuration** → **Installer**. L'application écrit
`gamestate_integration_cs2tracker.cfg` dans le dossier de configuration de CS2,
puis **redémarre CS2**.

C'est le mécanisme officiel de Valve : le jeu pousse lui-même son état vers
l'application. Rien n'est lu en mémoire, rien n'est injecté.

> En partie classique, CS2 ne transmet que **ton propre** état. Les données de
> tous les joueurs n'arrivent qu'en mode spectateur ou sur une retransmission
> GOTV — c'est une limite volontaire de Valve, pas un défaut de l'application.
> Utilise l'import de lobby pour analyser les adversaires en partie classique.

---

## Utilisation

```powershell
CS2Tracker.exe                      # fenêtre native + API (défaut)
CS2Tracker.exe --overlay            # lance aussi l'overlay par-dessus le jeu
CS2Tracker.exe --browser            # interface dans le navigateur
CS2Tracker.exe --api-only           # API seule, pour un client tiers
CS2Tracker.exe --analyse <steamid>  # rapport d'analyse en console
CS2Tracker.exe --install-gsi        # écrit la configuration GSI puis quitte
```

Documentation interactive de l'API : `http://127.0.0.1:8642/docs`.

### L'overlay en jeu

Onglet **Configuration** → **Lancer l'overlay**, ou via l'icône de la zone de
notification. Il affiche score, manche, bombe et risque de chaque joueur
par-dessus CS2.

**Règle CS2 sur « Plein écran fenêtre »** : une fenêtre superposée ne peut pas
s'afficher au-dessus d'une application en plein écran exclusif.

`F8` masque · `F9` déplace · `Ctrl+Maj+F8` ferme.

---

## Le moteur anti-triche

**Ce qu'il produit** : un score de suspicion de 0 à 100, un verdict, et surtout
**la liste des indicateurs qui l'ont fait monter**, chacun avec sa mesure, sa
référence de population et sa taille d'échantillon.

**Ce qu'il n'est pas** : une preuve. Seul Valve dispose des éléments (mémoire du
client, télémétrie serveur) permettant de conclure.

### Principe

Une trentaine de détecteurs répartis en huit familles comparent le joueur à des
distributions de référence. Trois garde-fous rendent le moteur conservateur :

1. **La confiance module tout.** Un taux de 100 % de headshots sur 3 kills ne
   déclenche rien : les taux sont lissés bayésiennement et pondérés par la
   taille de l'échantillon.
2. **La corroboration prime sur l'intensité.** Il faut que plusieurs familles
   *indépendantes* concordent pour approcher le haut de l'échelle. Un seul écart,
   même extrême, ne suffit pas.
3. **La couverture est prise en compte.** Sans statistiques de jeu, le verdict
   devient `INDÉTERMINÉ` plutôt que de se prononcer à l'aveugle.

### Familles d'indicateurs

| Famille | Ce qu'elle mesure |
|---|---|
| **Visée** | Taux de HS, précision, impacts et balles par kill, dégâts par kill |
| **Armes** | Précision au spray, profil par catégorie, homogénéité entre armes |
| **Niveau** | Performance rapportée aux heures de jeu, K/D, taux de MVP et de victoire |
| **Compte** | Ancienneté, confidentialité, bibliothèque, empreinte sociale |
| **Temps réel** | HS observés, ADR, multi-kills, rythme des éliminations, utilitaires |
| **Régularité** | Variabilité des dégâts, cohérence historique vs partie en cours |
| **Évolution** | Rupture de niveau entre deux relevés — le signal le plus spécifique |
| **Sanctions** | Bannissements VAC et éditeur (factuel, non statistique) |

> **Pourquoi l'évolution compte.** Un joueur avec 80 000 manches au compteur peut
> doubler son taux de headshots sur ses 500 manches suivantes sans que sa moyenne
> à vie bouge d'un point. Comparer deux relevés isole la période récente — et
> contrairement à tous les autres signaux, un bond soudain ne s'explique **pas**
> par un compte secondaire : un smurf est bon dès le premier relevé.

### Échelle

| Score | Verdict | Lecture |
|---|---|---|
| 0–29 | `CLEAN` | Rien ne distingue ce joueur de la population |
| 30–49 | `LOW` | Quelques écarts mineurs |
| 50–69 | `MODERATE` | Plusieurs signaux inhabituels |
| 70–84 | `HIGH` | Comportement fortement atypique |
| 85–100 | `CRITICAL` | Faisceau d'indices très lourd |
| — | `INDÉTERMINÉ` | Données insuffisantes pour se prononcer |

### Faux positifs connus

Le moteur les signale explicitement plutôt que de les masquer :

- **comptes secondaires (smurfs)** — signature statistiquement identique à celle
  d'un tricheur : compte jeune, peu d'heures, niveau élevé ;
- **joueurs de niveau compétitif** — leurs statistiques sont réellement extrêmes ;
- **styles atypiques** — AWP exclusif, entry fragger, joueur de soutien ;
- **échantillons faibles** — d'où le lissage bayésien.

Détail complet : [`docs/ANTICHEAT.md`](docs/ANTICHEAT.md).

---

## Ce que l'application ne fait jamais

- ❌ lire la mémoire du jeu
- ❌ injecter du code dans le processus
- ❌ modifier un fichier de CS2 autre que le `.cfg` GSI prévu par Valve
- ❌ intercepter le trafic réseau du jeu
- ❌ envoyer tes données ailleurs qu'à Steam

Tout repose sur des données **publiques** et sur un mécanisme **officiel**.

---

## Développement

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest                                                # 137 tests
powershell -ExecutionPolicy Bypass -File packaging\build.ps1     # construit l'exe
powershell -ExecutionPolicy Bypass -File overlay\build.ps1       # construit l'overlay
python packaging\make_icons.py                                   # régénère les icônes
```

Documentation technique :

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — structure du code et flux de données
- [`docs/API.md`](docs/API.md) — référence des endpoints
- [`docs/ANTICHEAT.md`](docs/ANTICHEAT.md) — modèle de détection en détail
- [`docs/GSI.md`](docs/GSI.md) — Game State Integration, portée et limites
- [`overlay/README.md`](overlay/README.md) — l'overlay natif
- [`ROADMAP.md`](ROADMAP.md) — améliorations incrémentales
- [`IDEAS.md`](IDEAS.md) — dix améliorations majeures, et ce qui bloque chacune

---

## Licence

MIT — voir [`LICENSE`](LICENSE).

Non affilié à Valve Corporation. Counter-Strike et Steam sont des marques de
Valve Corporation.

L'analyse anti-triche est une estimation statistique fondée sur des données
publiques. Elle ne constitue pas une preuve de triche et ne doit pas servir à
accuser publiquement un joueur.
