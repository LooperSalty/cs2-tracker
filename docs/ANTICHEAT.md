# Le moteur anti-triche

> **Avertissement préalable.** Ce moteur produit une *estimation statistique*, pas
> une preuve. Il ne peut ni observer la mémoire du client, ni les angles de visée,
> ni la télémétrie serveur. Seul Valve dispose de ces éléments. Un score élevé
> justifie un signalement en jeu — jamais une accusation publique.

---

## 1. Ce sur quoi il travaille

| Source | Fournit | Limite |
|---|---|---|
| Steam Web API | Statistiques à vie, sanctions, méta-compte | Profil privé = rien |
| Game State Integration | État de partie 10×/seconde | Pas d'angles ni de trajectoire de réticule |

Ce que le GSI **ne donne pas**, et qu'aucune détection ne peut donc utiliser
ici : position du réticule, vitesse angulaire, snap sur cible, visibilité de
l'adversaire, tirs à travers la fumée. Une détection d'aimbot « à la trame »
est hors de portée par construction.

Ce que le GSI **donne** et qu'un logiciel de triche altère de façon mesurable :
le rythme, la régularité et l'efficacité.

---

## 2. Les trois garde-fous

Le moteur est conçu pour se tromper **dans le sens de l'innocence**.

### 2.1 La confiance module tout

Chaque signal porte trois grandeurs distinctes, jamais confondues :

| Grandeur | Sens |
|---|---|
| `score` | Intensité de l'anomalie, 0 à 1 |
| `confidence` | Fiabilité de la mesure (taille d'échantillon, données présentes) |
| `weight` | Importance intrinsèque du détecteur |

La contribution au score final est `score × weight × confidence`. Un signal
maximal avec une confiance nulle ne pèse **rien**.

Les taux sont en outre lissés bayésiennement (`shrunk_rate`) :

```
taux_lissé = (succès + moyenne_population × poids_prior) / (essais + poids_prior)
```

Un joueur avec 2 kills dont 2 headshots n'a pas « 100 % de HS » : l'estimation
est tirée vers la moyenne tant que l'échantillon est mince.

### 2.2 La corroboration prime sur l'intensité

```python
strong_categories = {s.category for s in signals
                     if s.severity in {HIGH, CRITICAL} and s.category != BAN}
if len(strong_categories) >= 3:
    facteur = 1.12 + 0.04 × (len(strong_categories) - 3)   # plafonné à 1.35
```

Trois signaux forts issus d'une **même** famille peuvent partager une cause
unique (un style de jeu). Trois signaux forts issus de familles **distinctes**
sont beaucoup plus difficiles à expliquer autrement.

Le score agrégé passe par un exposant `1.15` : il faut plusieurs anomalies
marquées pour approcher du haut de l'échelle.

### 2.3 La couverture des sources

```python
coverage = 0.55 × a_des_stats + 0.25 × a_du_temps_réel + 0.20   # sanctions
confiance_globale = confiance_des_signaux × coverage
```

Sans statistiques de jeu, la confiance plafonne à 0,20 — sous le seuil de
`min_global_confidence`. Le verdict devient `INDÉTERMINÉ` au lieu de se
prononcer à l'aveugle. Un signal `CRITICAL` ne relève le score que si la
couverture est suffisante.

---

## 3. Les sept familles

### Visée — poids le plus élevé

Le marqueur le plus discriminant accessible hors du client.

| Détecteur | Référence | Lecture |
|---|---|---|
| `aim.headshot_rate` | 45 % ± 9,5 | Un triggerbot gonfle ce taux sans toucher au reste |
| `aim.accuracy` | 20,5 % ± 4,5 | Le recul plafonne naturellement ce taux |
| `aim.hits_per_kill` | 3,9 ± 1,0 | *Inversé* : moins d'impacts = dégâts concentrés sur les zones létales |
| `aim.shots_per_kill` | 19 ± 5,5 | *Inversé* : économie incompatible avec des duels disputés |
| `aim.damage_per_kill` | 122 ± 15 | *Inversé* : peu de dégâts « perdus » sur des survivants |

### Armes

| Détecteur | Idée |
|---|---|
| `weapon.spray_accuracy` | La précision au spray est la plus dure à truquer manuellement |
| `weapon.category_headshots` | Un HS à l'AWP n'a pas le sens d'un HS à l'AK — chaque catégorie a sa propre référence |
| `weapon.uniformity` | Un joueur humain est **irrégulier** : excellent à une arme, moyen à une autre. Une excellence uniforme est atypique |

`weapon.uniformity` combine `excellence × homogénéité` : il ne se déclenche que
si la moyenne est haute **et** la dispersion faible.

### Niveau (progression)

Modèle logarithmique saturant : forte progression au début, plateau ensuite.

```python
attendu = 0.48 + (0.82 - 0.48) × (heures / 1500) ** 0.45
```

L'écart est pondéré par l'inexpérience : moins il y a d'heures, plus l'écart
est parlant. **Ce signal est explicitement marqué ambigu** — un smurf produit
exactement la même signature.

### Compte

Poids volontairement **faibles**. Un compte neuf et privé est parfaitement
légitime ; ces indicateurs ne servent qu'à contextualiser des anomalies de jeu.

`account.smurf_profile` combine jeunesse + peu d'heures + niveau élevé, et
porte `metadata.ambiguous_with_smurf = True`. Son explication le dit
explicitement : « signature typique d'un smurf **autant** que d'un tricheur ».

### Temps réel

| Détecteur | Ce qu'il capte |
|---|---|
| `live.kill_rhythm` | *Inversé* : dispersion des délais entre kills. Un humain alterne duels instantanés et affrontements longs ; une cadence métronomique ne s'obtient pas manuellement |
| `live.fast_chains` | Enchaînements sous 1,2 s — bascule de cible assistée |
| `live.multi_kills` | Conversion trop fréquente des situations d'infériorité |
| `live.utility_neglect` | *Inversé* : gagner sans avoir besoin d'information ni de couverture |
| `live.headshot_rate`, `live.adr`, `live.survival` | Efficacité observée |

Minimum 5 manches, pleine confiance à 30.

### Régularité

| Détecteur | Ce qu'il capte |
|---|---|
| `consistency.adr_variability` | *Inversé* : coefficient de variation des dégâts par manche. Les manches faibles, normales chez un humain, disparaissent |
| `consistency.stats_vs_live` | Rupture entre le niveau historique du compte et le niveau observé maintenant |

### Sanctions — factuel

Seule famille non statistique : elle constate une décision déjà prise par Valve.
Un ban VAC ou éditeur impose un plancher de 80/100 et une confiance de 0,9.
Le poids de la sanction décroît avec son ancienneté (`ban.recency`).

---

## 4. Agrégation

```python
brut     = Σ(score × poids × confiance) / Σ(poids × confiance)
façonné  = brut ** 1.15
façonné  = façonné × facteur_corroboration          # 1.0 à 1.35
score    = façonné × 100

if ban_avéré:                    score = max(score, 80)
elif signal_critique et couverture_suffisante:  score = max(score, 62)
```

| Score | Verdict |
|---|---|
| 0–29 | `CLEAN` |
| 30–49 | `LOW` |
| 50–69 | `MODERATE` |
| 70–84 | `HIGH` |
| 85–100 | `CRITICAL` |
| confiance < 0,25 | `INDÉTERMINÉ` |

---

## 5. Les références de population

Elles vivent isolées dans [`anticheat/baselines.py`](../cs2tracker/anticheat/baselines.py),
précisément pour être ajustables sans toucher aux détecteurs.

**Ce sont des estimations calibrées, pas des mesures officielles Valve.** Elles
sont mutuellement cohérentes : ADR 72 et 0,62 kill/manche impliquent bien
72 / 0,62 ≈ 116 dégâts par kill, valeur retenue pour `DAMAGE_PER_KILL`.

Pour recalibrer sur ta propre population, remplace les couples
`(mean, stdev)` — la logique des détecteurs est inchangée.

---

## 6. Faux positifs connus

| Cas | Pourquoi le moteur se trompe | Ce qu'il fait |
|---|---|---|
| **Smurf** | Signature identique : compte jeune, peu d'heures, niveau élevé | Le signale explicitement dans l'explication et les métadonnées |
| **Joueur pro** | Ses statistiques *sont* extrêmes | Exige la corroboration de plusieurs familles |
| **AWPeur** | HS bas, précision haute — profil déformé | Références par catégorie d'arme |
| **Petit échantillon** | Un ratio extrême sur 10 kills | Lissage bayésien + confiance |
| **Profil privé** | Aucune donnée de jeu | Verdict `INDÉTERMINÉ` |

---

## 7. Ce qui n'est pas fait, et pourquoi

| Technique | Raison de l'exclusion |
|---|---|
| Lecture mémoire du client | Intrusif, détecté par VAC, éthiquement indéfendable |
| Injection / hook | Idem, et casserait le jeu |
| Analyse de démos (`.dem`) | Techniquement légitime — voir [ROADMAP](../ROADMAP.md) |
| Interception réseau | Chiffré et hors de propos |
| Vérification croisée avec des listes tierces | Fiabilité invérifiable, risque de diffamation |

---

## 8. Utiliser un résultat correctement

1. **Un score n'accuse personne.** Il classe un profil par rapport à une
   population.
2. **Regarde les indicateurs, pas le chiffre.** L'interface affiche pour chaque
   signal sa mesure, sa référence et son échantillon — c'est là qu'est
   l'information.
3. **En cas de doute, utilise le signalement en jeu.** Overwatch et VAC ont
   accès à ce que ce moteur n'aura jamais.
4. **N'accuse jamais publiquement sur la base de ce score.**
