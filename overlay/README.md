# Overlay CS2 Tracker

Affichage natif Win32 posé **par-dessus** Counter-Strike 2 : score, état de la
manche, tableau des joueurs et score de suspicion, sans quitter la partie.

```
┌──────────────────────────────────────────────┐
│ CS2 TRACKER              F8 masquer · F9 ↻   │
│ ──────────────────────────────────────────── │
│ 8 : 6   de_mirage           Manche 14 · live │
│ BOMBE 23.7 s                                 │
│ Alpha  25/8 · 78 PV · 3200 $                 │
│ ──────────────────────────────────────────── │
│ JOUEUR              K/D    ADR        RISQUE │
│ Alpha              25/8     60         12 OK │
│ Charlie            23/10    94    87 CRITIQUE│
│ Foxtrot            20/13   145         34 OK │
└──────────────────────────────────────────────┘
```

---

## Ce qu'il ne fait pas

C'est le point le plus important de ce composant.

| | |
|---|---|
| ❌ | lire la mémoire de CS2 |
| ❌ | injecter une DLL dans le processus du jeu |
| ❌ | intercepter Direct3D, OpenGL ou Vulkan |
| ❌ | poser le moindre hook sur le jeu |

L'overlay est un **processus séparé** qui crée sa propre fenêtre Win32
transparente et non cliquable, puis interroge l'API locale de CS2 Tracker en
HTTP. CS2 ignore totalement son existence — au même titre que Discord, Steam ou
n'importe quelle fenêtre de bureau.

Un overlay qui hookerait Direct3D serait techniquement plus souple, mais il
serait indiscernable d'un logiciel de triche du point de vue d'un anti-cheat.
Ce compromis a été refusé.

---

## Limite à connaître

**CS2 doit être en « Plein écran fenêtre »** (*fullscreen windowed*).

Une fenêtre superposée ne peut pas s'afficher au-dessus d'une application en
plein écran **exclusif** : dans ce mode, le jeu possède la sortie graphique et
le compositeur de Windows est court-circuité. C'est une contrainte du système,
pas un défaut de l'overlay — toutes les surcouches non injectées la partagent.

Dans CS2 : `Options` → `Vidéo` → `Mode d'affichage` → `Plein écran fenêtre`.

---

## Construction

Prérequis : Visual Studio 2019 ou plus récent avec la charge de travail
**Développement Desktop en C++** (fournit MSVC et CMake).

```powershell
powershell -ExecutionPolicy Bypass -File overlay\build.ps1
```

Le script localise CMake et le générateur adapté à ta version de Visual Studio.
Résultat : `overlay\build\Release\CS2TrackerOverlay.exe`, environ 210 Ko, sans
dépendance — la runtime C++ est liée statiquement.

Construction manuelle :

```powershell
cmake -S overlay -B overlay/build -G "Visual Studio 17 2022" -A x64
cmake --build overlay/build --config Release
```

---

## Utilisation

1. Lance **CS2 Tracker** (l'overlay a besoin de son API locale).
2. Lance `CS2TrackerOverlay.exe`.
3. Lance CS2 en plein écran fenêtre.

| Raccourci | Effet |
|---|---|
| `F8` | Masquer / afficher |
| `F9` | Déplacer d'un coin à l'autre de l'écran |
| `Ctrl+Maj+F8` | Fermer l'overlay |

Options en ligne de commande :

```powershell
CS2TrackerOverlay.exe --port 8642 --width 460 --height 560 --refresh 700
```

| Option | Défaut | Rôle |
|---|---|---|
| `--port` | 8642 | Port de l'API locale |
| `--width` / `--height` | 460 × 560 | Taille du panneau |
| `--refresh` | 700 | Intervalle de rafraîchissement (ms) |

---

## Architecture

| Fichier | Rôle |
|---|---|
| `src/main.cpp` | Point d'entrée, instance unique, arguments |
| `src/overlay_window.cpp` | Fenêtre en couche, rendu GDI+, raccourcis |
| `src/api_client.cpp` | Client WinHTTP, remplissage du modèle |
| `src/json.cpp` | Analyseur JSON minimal (~230 lignes) |
| `src/model.h` | Structures affichées |

### Comment la transparence fonctionne

La fenêtre est créée avec :

```cpp
WS_EX_LAYERED     // composition avec canal alpha par pixel
WS_EX_TRANSPARENT // les clics traversent vers le jeu
WS_EX_TOPMOST     // reste au-dessus
WS_EX_NOACTIVATE  // ne vole jamais le focus clavier
WS_EX_TOOLWINDOW  // absente d'Alt+Tab et de la barre des tâches
```

Le contenu est dessiné avec GDI+ dans un DIB 32 bits, puis présenté par
`UpdateLayeredWindow`.

**Le piège** : `UpdateLayeredWindow` attend un alpha **prémultiplié**. Dessiner
via un simple `Graphics(hdc)` produit de l'ARGB brut, que Windows interprète
alors comme des couleurs sur-lumineuses avec des franges sur le texte clair. Le
DIB est donc enveloppé dans un `Gdiplus::Bitmap` déclaré `PixelFormat32bppPARGB`,
et le rendu de texte utilise l'anticrénelage classique — ClearType suppose un
fond opaque et produit des franges colorées sur une surface à canal alpha.

### Pas de dépendances

Tout provient de Windows : WinHTTP, GDI+, User32, GDI32. Aucun gestionnaire de
paquets, aucun `vcpkg`, aucune bibliothèque tierce. L'analyseur JSON est écrit
à la main précisément pour cette raison.
