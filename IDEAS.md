# Dix améliorations majeures

Chaque entrée dit **ce que ça change réellement**, pas ce que ça ajoute au
catalogue. Elles sont classées par rapport valeur / effort, et chacune indique
honnêtement ce qui la bloque.

Pour les petites évolutions incrémentales, voir [`ROADMAP.md`](ROADMAP.md).

---

## 1. Analyse des démos `.dem` — *le seul vrai saut qualitatif*

**Le plafond actuel.** Le GSI ne donne ni les angles de visée, ni la position du
réticule. Le moteur ne peut donc mesurer que le rythme et l'efficacité. Aucune
détection d'aimbot « à la trame » n'est possible — c'est une limite de nature,
pas de qualité d'implémentation.

**Ce que les démos débloquent.** Un `.dem` contient les *ticks* du serveur :
position et angle de vue de chaque joueur, 64 fois par seconde.

| Détection | Signature recherchée |
|---|---|
| Snap sur cible | Accélération angulaire quasi instantanée juste avant le tir |
| Correction post-tir | Le réticule se recale *après* avoir dépassé la cible |
| Suivi à travers un mur | L'angle suit un adversaire hors de la ligne de vue |
| Prefire systématique | Visée pré-positionnée sur des angles sans information |
| Recul parfait | Contre-mouvement identique à la trame près |
| **Zones d'impact réelles** | Torse, bras, jambes — ce que Steam ne donne pas |

Ce dernier point règle aussi la limite de la silhouette à deux zones.

**Comment.** `demoparser2` (Python, cœur Rust, rapide). CS2 permet de
télécharger ses propres démos matchmaking.

**Effort** : élevé, c'est un projet en soi. **Valeur** : transforme l'outil.

---

## 2. Calibration adverse — *prouver que le moteur fonctionne*

Aujourd'hui les poids et les références sont des **choix d'auteur**. Rien ne
démontre que le moteur sépare correctement.

**Le protocole.** Constituer deux corpus — profils VAC-bannis confirmés d'un
côté, joueurs professionnels et smurfs connus de l'autre — puis mesurer taux de
vrais positifs et de faux positifs. Ajuster les poids par descente de gradient
plutôt qu'à l'estime.

Sans cette étape, le score reste une opinion structurée. Avec elle, il devient
un instrument mesuré, avec une précision annonçable.

**Effort** : moyen. **Valeur** : c'est la seule façon de sortir de l'arbitraire.

---

## 3. Références par rang — *arrêter de signaler les bons joueurs*

Le moteur compare tout le monde à la moyenne globale. Un joueur Faceit niveau 10
sera donc **toujours** signalé : ses statistiques sont réellement extrêmes par
rapport à la population entière.

**La correction.** Segmenter les distributions de référence par niveau (rang
Premier, niveau Faceit, ou à défaut par tranche d'heures de jeu) et comparer
chaque joueur à *ses pairs*.

C'est la cause n° 1 de faux positifs restante.

**Effort** : moyen. **Valeur** : élevée, directement sur la précision.

---

## 4. Intégration FACEIT — *le seul classement réellement accessible*

Le rang Premier de CS2 n'est **pas** exposé par l'API Steam ; il faudrait
dialoguer avec le Game Coordinator via un compte connecté, ce qui est lourd et
fragile.

FACEIT, en revanche, a une API publique et gratuite : ELO, niveau, taux de
victoire, historique de matchs, et surtout des statistiques **par match** —
ce que Steam ne fournit jamais.

Cela alimente aussi l'idée n° 3 : le niveau FACEIT est un excellent segment de
comparaison.

**Effort** : moyen. **Valeur** : élevée.

---

## 5. Analyse de match par match — *sortir de la moyenne à vie*

Steam ne donne que des cumuls depuis la création du compte, plus le dernier
match. Un joueur avec 8 000 manches a une moyenne que rien ne fait bouger.

Le tracker construit déjà un historique via les relevés et le GSI. En
enregistrant chaque match individuellement — via GSI, démos ou FACEIT — on
obtient une **distribution** de performances au lieu d'un point.

Cela permet des détections impossibles aujourd'hui : régularité anormale entre
matchs, matchs isolés aberrants, corrélation entre pics de performance et
heures de la journée.

**Effort** : moyen. **Valeur** : élevée, et prérequis de plusieurs autres idées.

---

## 6. Détection de groupe — *les tricheurs jouent rarement seuls*

L'analyse est aujourd'hui strictement individuelle. Or un compte suspect qui
joue systématiquement avec les mêmes comptes, eux aussi suspects, est un signal
bien plus fort que chacun pris isolément.

**Ce qu'il faut.** Enregistrer les co-occurrences de joueurs entre matchs (les
données sont déjà collectées), construire le graphe, puis repérer les
composantes où le score moyen est anormalement haut.

C'est aussi ce qui permettrait de détecter les **boosting lobbies**.

**Effort** : moyen. **Valeur** : élevée — un angle qu'aucun signal individuel ne
couvre.

---

## 7. Journal d'audit des verdicts — *pouvoir se relire*

Les analyses sont stockées, mais rien ne permet de vérifier après coup si un
verdict était juste : les joueurs signalés « HIGH » finissent-ils bannis ?

**Le mécanisme.** Revérifier périodiquement le statut VAC des profils analysés
et confronter au verdict rendu. Cela produit une **courbe de calibration
réelle** — le taux de bannissement effectif par palier de score.

C'est la boucle de rétroaction qui manque : sans elle, le moteur ne peut jamais
apprendre de ses erreurs.

**Effort** : faible — le stockage existe déjà. **Valeur** : très élevée.

---

## 8. Comparaison directe entre joueurs — *le mode le plus demandé d'un tracker*

Deux profils côte à côte, métrique par métrique, avec les écarts mis en
évidence. Utile pour se comparer à un ami, à un adversaire, ou à soi-même à six
mois d'intervalle.

Toute la donnée et tous les composants visuels existent : c'est presque
exclusivement du travail d'interface.

**Effort** : faible. **Valeur** : forte en usage quotidien.

---

## 9. WebSocket et overlay réactif — *supprimer la latence*

L'interface interroge trois endpoints chaque seconde alors que `/ws/live`
existe déjà côté serveur et n'est pas utilisé. L'overlay fait de même en HTTP.

Basculer sur le WebSocket supprime la latence d'affichage et la charge inutile.
Pour l'overlay, cela permettrait un affichage réellement instantané des kills.

**Effort** : faible, le serveur est prêt. **Valeur** : moyenne, mais c'est de la
dette technique déjà provisionnée.

---

## 10. Distribution professionnelle — *supprimer la friction d'installation*

Trois obstacles subsistent avant que quelqu'un d'autre que toi puisse
l'installer sereinement :

1. **Signature de code.** Sans certificat, SmartScreen affiche un avertissement
   au premier lancement. C'est la barrière n° 1 à l'adoption.
2. **Installeur** (Inno Setup) : raccourci menu Démarrer, désinstallation
   propre, association du lancement au démarrage de Windows.
3. **Mise à jour automatique** depuis les releases GitHub, avec vérification de
   signature.

S'y ajoute la **CI GitHub Actions** — déjà écrite mais jamais exécutée —, qui
construirait et publierait les binaires automatiquement.

**Effort** : faible à moyen (le certificat a un coût annuel). **Valeur** : c'est
la différence entre un projet personnel et un logiciel distribuable.

---

## Bonus — trois idées plus légères

| Idée | Pourquoi |
|---|---|
| **Watchlist avec alerte** | Être notifié quand un joueur surveillé se fait bannir : validation directe du verdict rendu |
| **Valeur d'inventaire** | Un compte jetable en est dépourvu ; signal faible mais gratuit à calculer |
| **Interface multilingue** | L'application est en français seulement, alors que le dépôt est public |

---

## Ordre suggéré

Si l'objectif est **la précision du moteur** :
7 (audit) → 3 (références par rang) → 2 (calibration) → 5 (par match) → 1 (démos)

Si l'objectif est **l'usage quotidien** :
8 (comparaison) → 4 (FACEIT) → 9 (WebSocket) → 10 (distribution)

L'idée n° 7 est le meilleur premier pas dans les deux cas : effort faible,
données déjà là, et c'est elle qui rend toutes les autres mesurables.
