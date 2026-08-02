"""Localisation des démos CS2 présentes sur la machine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cs2tracker.core.utils import ts_to_iso
from cs2tracker.gsi.locator import try_find_cs2
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Emplacements ou CS2 depose les demos telechargees ou enregistrees.
_RELATIVE_DIRS = ("game/csgo", "game/csgo/replays")


@dataclass(frozen=True, slots=True)
class DemoFile:
    path: Path
    size_bytes: int
    modified: float

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.path.name,
            "path": str(self.path),
            "size_mb": round(self.size_bytes / (1024 * 1024), 1),
            "modified": ts_to_iso(self.modified),
        }


def find_demos(cs2_path_override: str = "", limit: int = 50) -> list[DemoFile]:
    """Démos trouvées, de la plus récente à la plus ancienne."""
    installation = try_find_cs2(cs2_path_override)
    if installation is None:
        return []

    found: list[DemoFile] = []
    for relative in _RELATIVE_DIRS:
        directory = installation.game_path / relative
        if not directory.is_dir():
            continue
        try:
            for demo in directory.glob("*.dem"):
                stat = demo.stat()
                found.append(
                    DemoFile(path=demo, size_bytes=stat.st_size, modified=stat.st_mtime)
                )
        except OSError as exc:
            logger.warning("Lecture de %s impossible : %s", directory, exc)

    found.sort(key=lambda demo: demo.modified, reverse=True)
    return found[:limit]
