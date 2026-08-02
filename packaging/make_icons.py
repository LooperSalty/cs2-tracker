"""Décline le logo source en toutes les tailles dont l'application a besoin.

Source unique : ``img/logo.png``. Chaque cible en est dérivée, pour qu'un
changement de logo se propage partout d'une seule commande :

    python packaging/make_icons.py

Cibles produites :
  packaging/icon.ico              icône de CS2Tracker.exe
  overlay/icon.ico                icône de CS2TrackerOverlay.exe
  cs2tracker/web/icon.png         logo de la barre latérale
  cs2tracker/web/favicon.png      onglet du navigateur
  cs2tracker/desktop/tray_icon.png  zone de notification
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "img"

#: Tailles embarquées dans les .ico. Windows pioche celle qui lui convient
#: selon le contexte : 16 px dans la barre des tâches, 256 px en grandes icônes.
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def find_source() -> Path:
    """Repère le logo : ``logo.png`` en priorité, sinon la seule image du dossier."""
    preferred = SOURCE_DIR / "logo.png"
    if preferred.is_file():
        return preferred

    candidates = sorted(
        path
        for path in SOURCE_DIR.glob("*")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not candidates:
        raise SystemExit(
            f"Aucune image trouvee dans {SOURCE_DIR}. "
            "Depose le logo sous img/logo.png."
        )
    return candidates[0]


def prepare(source: Path) -> Image.Image:
    """Recadre sur le contenu réel puis rend l'image carrée.

    Un détourage laisse souvent une large marge transparente : sans recadrage,
    le logo apparaîtrait minuscule une fois réduit à 16 px.
    """
    image = Image.open(source).convert("RGBA")
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)

    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2), image)
    return square


def main() -> int:
    source = find_source()
    print(f"Source : {source.relative_to(PROJECT_ROOT)}")

    square = prepare(source)
    print(f"Normalise : {square.size[0]}x{square.size[1]}")

    for target in (PROJECT_ROOT / "packaging" / "icon.ico",
                   PROJECT_ROOT / "overlay" / "icon.ico"):
        target.parent.mkdir(parents=True, exist_ok=True)
        square.save(target, format="ICO", sizes=ICO_SIZES)
        print(f"  {target.relative_to(PROJECT_ROOT)}  {target.stat().st_size / 1024:.0f} Ko")

    web = PROJECT_ROOT / "cs2tracker" / "web"
    for name, size in (("icon.png", 256), ("favicon.png", 64)):
        square.resize((size, size), Image.LANCZOS).save(web / name, optimize=True)
        print(f"  {(web / name).relative_to(PROJECT_ROOT)}")

    tray = PROJECT_ROOT / "cs2tracker" / "desktop" / "tray_icon.png"
    square.resize((128, 128), Image.LANCZOS).save(tray, optimize=True)
    print(f"  {tray.relative_to(PROJECT_ROOT)}")

    print("Termine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
