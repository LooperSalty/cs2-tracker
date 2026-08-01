# Améliorations envisagées

Classées par **rapport valeur / effort**. Chaque entrée dit ce que ça apporte
réellement, pas seulement ce que ça ajoute.

---

## ✅ Livré depuis la version 1.0

| Fonctionnalité | Ce que ça a apporté |
|---|---|
| **Percentiles** | Chaque statistique replacée dans la population, via la loi normale appliquée aux baselines existantes — aucune donnée supplémentaire nécessaire |
| **Dérive temporelle** | Détecteur de rupture de niveau entre deux relevés : le seul signal qu'un compte secondaire n'explique pas |
| **Import de lobby** | Contourne la limite du GSI en partie classique, où seul l'état du joueur local est transmis |
| **Courbes d'évolution** | Suivi K/D, HS %, précision dans le temps, en SVG sans dépendance |
| **Export CSV** | Historique ouvrable dans un tableur |
| **Overlay natif** | Panneau C++ par-dessus le jeu, sans injection ni hook ([`overlay/`](overlay/)) |

---

## 1. Ce qui rendrait la détection nettement meilleure

### 1.1 Analyse de démos `.dem` — *le plus gros gain possible*

**Le problème actuel** : le GSI ne donne ni les angles de visée, ni la
trajectoire du réticule. Toute détection d'aimbot « à la trame » est hors de
portée. Le moteur ne peut mesurer que le rythme et l'efficacité.

**Ce que les démos changent** : un fichier `.dem` contient les *ticks* du
serveur — position et angle de vue de chaque joueur, 64 fois par seconde. Ça
débloque les détections qui comptent vraiment :

| Détection | Signature recherchée |
|---|---|
| **Snap sur cible** | Accélération angulaire quasi instantanée juste avant le tir |
| **Correction post-tir** | Le réticule se recale *après* avoir dépassé la cible |
| **Suivi à travers un mur** | Angle de vue qui suit un adversaire non visible |
| **Prefire systématique** | Visée pré-positionnée sur des angles sans information |
| **Compensation de recul parfaite** | Contre-mouvement identique à la trame près |

**Comment** : `demoparser2` (Python, bindings Rust, rapide) ou `demoinfocs-golang`.
CS2 permet de télécharger ses propres démos matchmaking.

**Effort** : élevé — c'est un projet en soi. **Valeur** : transforme l'outil.

### 1.2 Calibration des références sur données réelles

Les valeurs de `baselines.py` sont des estimations documentées. Les recalibrer
sur un échantillon réel (quelques milliers de profils publics) rendrait les
z-scores exacts au lieu d'approximatifs.

Ajouter aussi des **références par rang** : un joueur Faceit 10 comparé à la
moyenne globale sera toujours signalé. Comparé à sa propre population, non.

**Effort** : moyen. **Valeur** : élevée — réduit directement les faux positifs.

### 1.3 Calibration adverse

Constituer deux jeux d'évaluation — profils VAC-bannis confirmés d'un côté,
profils de joueurs pros de l'autre — et mesurer le taux de vrais/faux positifs.
Sans ça, les poids restent des choix d'auteur plutôt que des paramètres validés.

**Effort** : moyen. **Valeur** : c'est la seule façon de *prouver* que le moteur
fonctionne.

---

## 2. Fonctionnalités attendues d'un tracker

| Idée | Détail | Effort |
|---|---|---|
| **FACEIT** | ELO, niveau, taux de victoire et matchs récents. L'API FACEIT est publique et gratuite (clé requise) — c'est le seul classement compétitif réellement accessible | moyen |
| **Comparaison de joueurs** | Deux profils côte à côte, écarts mis en évidence | faible |
| **Suivi de watchlist** | Alerte quand un joueur surveillé se fait bannir | faible |
| **Analyse de l'inventaire** | Valeur des skins : un compte jetable en est généralement dépourvu | faible |
| **Export d'un rapport** | PDF/PNG partageable en complément du CSV | faible |
| **Multi-langue** | L'interface est en français uniquement | faible |
| **Rang Premier / par carte** | Le classement CS2 n'est **pas** exposé par l'API Steam. Il faudrait dialoguer avec le Game Coordinator via un compte Steam connecté — lourd et fragile | élevé |
| **Overlay : ancrage sur la fenêtre CS2** | Aujourd'hui l'overlay se place par rapport à l'écran ; le suivre la fenêtre du jeu gérerait mieux le multi-écran | faible |

**FACEIT** est le meilleur prochain ajout côté données : c'est la seule source
de classement compétitif accessible sans bricolage, et elle apporte un contexte
que les statistiques Steam à vie ne donnent pas (niveau réel de l'adversaire).

---

## 3. Technique

### 3.1 Interface

- **WebSocket au lieu du polling.** Le front interroge trois endpoints chaque
  seconde ; `/ws/live` existe déjà et n'est pas utilisé. Gain : latence et charge.
- **Virtualisation des tableaux** au-delà de quelques centaines de lignes.
- **Raccourcis clavier** — `Ctrl+K` pour la recherche, chiffres pour la navigation.
- **Accessibilité** : les tableaux mériteraient une vraie navigation clavier.

### 3.2 Backend

- **Migrations de schéma.** `DB_SCHEMA_VERSION` existe mais aucun mécanisme de
  migration n'est branché. À faire avant toute évolution du schéma.
- **Cache persistant.** Le cache Steam est en mémoire : tout redémarrage le vide.
- **Purge automatique** des vieux relevés et matchs.
- **Reprise du recorder** après un redémarrage en cours de match.

### 3.3 Qualité

- **Couverture mesurée.** 97 tests, mais `pytest-cov` n'est pas branché — le
  chiffre réel est inconnu.
- **Tests de l'interface web.** Playwright a servi à la revue visuelle, pas en
  tests automatisés.
- **CI GitHub Actions** : tests + build de l'exe + publication de release.
- **Typage strict** : `mypy --strict` n'a jamais été passé sur le code.

### 3.4 Distribution

- **Signature de l'exécutable.** Sans certificat, SmartScreen affiche un
  avertissement au premier lancement. Un certificat de signature de code le
  supprime.
- **Installeur Inno Setup** : raccourci menu Démarrer, désinstallation propre.
- **Mise à jour automatique** depuis les releases GitHub.

---

## 4. La part de C++ — décision prise

Le besoin initial était « un exe facile à installer ». Il est réglé sans C++ :
`CS2Tracker.exe` fait 26 Mo, ne demande ni Python ni dépendance.

Comparaison honnête d'une réécriture complète :

| Aspect | Python actuel | C++ |
|---|---|---|
| Taille | 26 Mo | ~5–10 Mo |
| Démarrage | ~1,5 s | ~0,2 s |
| Mémoire | ~80 Mo | ~20 Mo |
| Coût | — | **plusieurs semaines**, et perte des 126 tests |

Aucun de ces gains n'est perceptible à côté d'un jeu qui consomme 4 Go.

**Ce qui a été retenu** : garder le cœur en Python et n'écrire en C++ que le
composant qui en tire un bénéfice réel — l'**overlay**, seule chose que Python
ne pouvait pas faire correctement. Il est livré : 219 Ko, sans dépendance, et il
consomme l'API existante.

Point de conception non négociable : l'overlay **n'injecte rien** dans CS2.
Hooker Direct3D aurait donné plus de souplesse (affichage en plein écran
exclusif, notamment) mais aurait rendu le programme indiscernable d'un logiciel
de triche du point de vue d'un anti-cheat. Le compromis retenu est une fenêtre
Win32 superposée, avec sa contrainte assumée : CS2 doit tourner en plein écran
fenêtre.

---

## 5. Priorités suggérées

1. ~~Import de lobby~~ — **fait**
2. ~~Dérive temporelle~~ — **fait**
3. ~~Overlay~~ — **fait**
4. **WebSocket dans l'interface** — le code serveur existe déjà, le front continue de sonder
5. **CI + signature de l'exe** — supprime l'avertissement SmartScreen
6. **FACEIT** — le seul classement compétitif réellement accessible
7. **Calibration des références** — réduit les faux positifs
8. **Analyse de démos** — le vrai saut qualitatif, et un projet en soi
