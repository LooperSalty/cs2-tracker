# Améliorations envisagées

Classées par **rapport valeur / effort**. Chaque entrée dit ce que ça apporte
réellement, pas seulement ce que ça ajoute.

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

### 1.3 Détection de dérive temporelle

Aujourd'hui les relevés sont stockés mais peu exploités. Un joueur qui passe de
45 % à 70 % de headshots **entre deux relevés** est un signal bien plus fort
qu'un taux élevé constant (qui peut n'être qu'un bon joueur).

Le différentiel entre deux `stat_snapshots` isole la performance *récente*, là
où les statistiques à vie la noient dans des milliers d'heures.

**Effort** : faible — les données sont déjà là. **Valeur** : élevée.

### 1.4 Calibration adverse

Constituer deux jeux d'évaluation — profils VAC-bannis confirmés d'un côté,
profils de joueurs pros de l'autre — et mesurer le taux de vrais/faux positifs.
Sans ça, les poids restent des choix d'auteur plutôt que des paramètres validés.

**Effort** : moyen. **Valeur** : c'est la seule façon de *prouver* que le moteur
fonctionne.

---

## 2. Fonctionnalités attendues d'un tracker

| Idée | Détail | Effort |
|---|---|---|
| **Overlay en jeu** | Fenêtre transparente toujours au-dessus avec le HUD et les scores de suspicion du lobby | moyen |
| **Import de lobby** | Coller le résultat de `status` depuis la console CS2 pour analyser les 10 joueurs d'un coup | **faible** |
| **Comparaison de joueurs** | Deux profils côte à côte, écarts mis en évidence | faible |
| **Graphiques d'évolution** | Courbes K/D, HS%, précision dans le temps (SVG, sans dépendance) | faible |
| **Export** | Rapport PDF/PNG partageable, export CSV des relevés | faible |
| **Suivi de watchlist** | Alerte quand un joueur surveillé se fait bannir | faible |
| **Statistiques Premier / rang** | Le classement CS2 n'est pas exposé par l'API Steam — nécessiterait le protocole GC | élevé |
| **Multi-langue** | L'interface est en français uniquement | faible |

L'**import de lobby** est le meilleur premier ajout : effort minimal, et il
contourne exactement la limite du GSI en partie classique.

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

## 4. Sur la réécriture en C++

Le besoin exprimé était « un exe facile à installer ». **C'est déjà le cas** :
`CS2Tracker.exe` fait 26 Mo, ne demande ni Python ni dépendance, et démarre
directement.

Ce qu'une réécriture C++ apporterait réellement :

| Aspect | Python actuel | C++ |
|---|---|---|
| Taille | 26 Mo | ~5–10 Mo |
| Démarrage | ~1,5 s | ~0,2 s |
| Mémoire | ~80 Mo | ~20 Mo |
| Overlay en jeu | difficile | natif (Direct3D) |
| Parsing de démos | correct | nettement plus rapide |
| Coût de développement | — | **plusieurs semaines** |

Aucun de ces gains n'est perceptible pour un outil qui tourne à côté d'un jeu
consommant 4 Go. Les deux seuls arguments sérieux sont **l'overlay Direct3D** et
le **parsing de démos à grande échelle**.

**Chemin intermédiaire recommandé** : garder le cœur en Python et n'écrire en
C++ que le composant qui en tire un bénéfice réel — un overlay Direct3D qui
consomme l'API existante. On garde toute la logique déjà testée, on gagne la
seule chose que le C++ apporte vraiment.

---

## 5. Priorités suggérées

1. **Import de lobby** — contourne la limite du GSI, effort minimal
2. **WebSocket dans l'interface** — le code serveur existe déjà
3. **Dérive temporelle** — les données sont déjà stockées
4. **CI + signature de l'exe** — supprime la friction d'installation
5. **Calibration des références** — réduit les faux positifs
6. **Analyse de démos** — le vrai saut qualitatif
7. **Overlay** — en C++ si l'ambition est là
