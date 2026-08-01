# Game State Integration

## Ce que c'est

Un mécanisme **officiel de Valve** : on dépose un fichier de configuration dans
le dossier de CS2, et le jeu se met à envoyer son état par HTTP POST vers
l'adresse qu'on lui indique.

Rien n'est lu en mémoire, rien n'est injecté, aucun fichier du jeu n'est modifié
en dehors de ce `.cfg` prévu à cet effet. C'est la même mécanique qu'utilisent
les overlays de tournoi et les outils de streaming.

## Installation

**Depuis l'application** : onglet *Configuration* → *Installer*, puis redémarre CS2.

**En ligne de commande** :

```powershell
CS2Tracker.exe --install-gsi
```

**Manuellement** : copie le contenu de `/api/system/gsi/preview` dans

```
<Steam>\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\gamestate_integration_cs2tracker.cfg
```

L'application détecte le dossier via le registre Windows puis
`steamapps/libraryfolders.vdf` — les installations sur un second disque sont
gérées. Un chemin peut être forcé avec `CS2T_CS2_PATH`.

## Le fichier généré

```vdf
"CS2 Tracker"
{
    "uri"       "http://127.0.0.1:8642/gsi"
    "timeout"   "5.0"
    "buffer"    "0.1"
    "throttle"  "0.1"
    "heartbeat" "10.0"
    "auth"
    {
        "token" "<jeton généré à la première exécution>"
    }
    "data"
    {
        "provider"  "1"   "map"                   "1"
        "round"     "1"   "player_state"          "1"
        "bomb"      "1"   "player_match_stats"    "1"
        ...
    }
}
```

Le **jeton** est généré une seule fois dans
`%LOCALAPPDATA%\CS2Tracker\gsi_token.txt` et vérifié à chaque requête. Sans lui,
n'importe quel processus local pourrait injecter un faux état de jeu.

`throttle` fixe l'intervalle minimal entre deux envois. 0,1 s donne un suivi
fluide sans charge notable ; monte à 0,5 s si tu tiens à économiser des cycles.

## Ce que le jeu transmet

| Bloc | Contenu | Toujours disponible |
|---|---|---|
| `provider` | Version du jeu, SteamID du joueur local | oui |
| `map` | Carte, mode, phase, manche, scores, historique des manches | oui |
| `round` | Phase (`freezetime` / `live` / `over`), état de la bombe, vainqueur | oui |
| `player` | **Ton** état : PV, armure, argent, kills de la manche, arme active | oui |
| `player_match_stats` | Tes kills, morts, assistances, MVP, score | oui |
| `bomb` | État, décompte, porteur | oui |
| `phase_countdowns` | Phase en cours et temps restant | oui |
| `allplayers_*` | Même chose **pour tous les joueurs** | **spectateur / GOTV uniquement** |
| `*_position` | Coordonnées et orientation | **spectateur / GOTV uniquement** |
| `grenades` | Grenades actives sur la carte | spectateur / GOTV |

> ### La limite importante
>
> En partie classique, CS2 ne transmet **que ton propre état**. C'est une
> restriction délibérée de Valve : sinon le GSI serait lui-même un wallhack.
>
> Conséquence directe : le tableau des scores complet et l'analyse temps réel
> des adversaires ne fonctionnent qu'en **mode spectateur**, sur une
> **retransmission GOTV**, ou en **replay de démo**. L'analyse d'un joueur à
> partir de ses statistiques Steam reste possible en toutes circonstances.

## Des états, pas des événements

Le GSI n'émet aucun événement. Il envoie des instantanés, et toute la sémantique
se déduit des transitions — c'est le rôle de
[`gsi/events.py`](../cs2tracker/gsi/events.py) :

| Transition observée | Événement déduit |
|---|---|
| `match_stats.kills` augmente | `kill` (ou `headshot_kill` si `round_killhs` augmente aussi) |
| `state.round_kills` atteint 3 | `multi_kill` |
| `state.health` diminue | `damage_taken`, puis `low_health` sous 25 PV |
| `round.phase` : `live` → `over` | `round_end` avec le camp vainqueur |
| `bomb.state` : `carried` → `planted` | `bomb_planted` |
| `map.name` change | `map_change`, remise à zéro des métriques |

Chaque événement est horodaté et numéroté. `/api/live/events?since=<seq>` ne
renvoie que les nouveautés.

## Diagnostic

| Symptôme | Cause probable |
|---|---|
| *Flux temps réel* rouge alors que CS2 tourne | CS2 n'a pas été redémarré depuis l'installation du `.cfg` |
| Écriture du `.cfg` refusée | Dossier protégé — lance l'application en administrateur, ou copie le fichier à la main |
| Aucun joueur dans le tableau des scores | Normal en partie classique — voir la limite ci-dessus |
| État figé sur une ancienne partie | `POST /api/live/reset` |
| CS2 introuvable | Renseigne `CS2T_CS2_PATH` dans le `.env` |

Vérifier que le jeu émet bien :

```powershell
curl http://127.0.0.1:8642/api/live/state
```

`connected: true` et un `payload_count` qui augmente signifient que la liaison
fonctionne.
