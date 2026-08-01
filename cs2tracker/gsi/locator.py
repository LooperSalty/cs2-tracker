"""Détection de l'installation Steam et de Counter-Strike 2 sur la machine.

Stratégie : registre Windows → ``libraryfolders.vdf`` → vérification de
``appmanifest_730.acf`` → chemin du dossier ``cfg`` du jeu.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cs2tracker.constants import CS2_APP_ID
from cs2tracker.core.errors import Cs2NotFoundError
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Dossier du jeu relatif à la racine d'une bibliothèque Steam.
_CS2_RELATIVE: Final = Path("steamapps/common/Counter-Strike Global Offensive")
#: Sous-chemin du dossier de configuration depuis la racine du jeu.
_CFG_RELATIVE: Final = Path("game/csgo/cfg")

_VDF_PATH_RE: Final = re.compile(r'"path"\s+"([^"]+)"')
_REGISTRY_KEYS: Final = (
    (r"SOFTWARE\Valve\Steam", "InstallPath"),
    (r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
)


@dataclass(frozen=True, slots=True)
class Cs2Installation:
    steam_path: Path
    game_path: Path
    cfg_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "steam_path": str(self.steam_path),
            "game_path": str(self.game_path),
            "cfg_path": str(self.cfg_path),
        }


def _steam_path_from_registry() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows uniquement
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            value, _ = winreg.QueryValueEx(key, "SteamPath")
            if value:
                return Path(str(value).replace("/", "\\"))
    except OSError:
        pass

    for subkey, value_name in _REGISTRY_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    return Path(str(value))
        except OSError:
            continue
    return None


def _fallback_steam_paths() -> list[Path]:
    candidates = [
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Program Files/Steam"),
        Path.home() / ".steam/steam",
        Path.home() / ".local/share/Steam",
        Path.home() / "Library/Application Support/Steam",
    ]
    return [path for path in candidates if path.is_dir()]


def find_steam_path() -> Path | None:
    from_registry = _steam_path_from_registry()
    if from_registry and from_registry.is_dir():
        return from_registry
    fallbacks = _fallback_steam_paths()
    return fallbacks[0] if fallbacks else None


def library_folders(steam_path: Path) -> list[Path]:
    """Toutes les racines de bibliothèque Steam déclarées (multi-disques)."""
    roots = [steam_path]
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return roots
    try:
        content = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.warning("libraryfolders.vdf illisible: %s", exc)
        return roots
    for match in _VDF_PATH_RE.finditer(content):
        candidate = Path(match.group(1).replace("\\\\", "\\"))
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def find_cs2(explicit_path: str = "") -> Cs2Installation:
    """Localise CS2 ou lève ``Cs2NotFoundError``.

    ``explicit_path`` (option ``CS2T_CS2_PATH``) court-circuite la détection et
    peut désigner soit la racine du jeu, soit directement le dossier ``cfg``.
    """
    if explicit_path:
        override = Path(explicit_path).expanduser()
        if override.name == "cfg" and override.is_dir():
            return Cs2Installation(
                steam_path=override.parents[3] if len(override.parents) > 3 else override,
                game_path=override.parents[2] if len(override.parents) > 2 else override,
                cfg_path=override,
            )
        cfg = override / _CFG_RELATIVE
        if cfg.is_dir():
            return Cs2Installation(steam_path=override, game_path=override, cfg_path=cfg)
        raise Cs2NotFoundError(f"Chemin force invalide: {explicit_path}")

    steam_path = find_steam_path()
    if steam_path is None:
        raise Cs2NotFoundError("Installation Steam introuvable")

    for root in library_folders(steam_path):
        manifest = root / "steamapps" / f"appmanifest_{CS2_APP_ID}.acf"
        game_path = root / _CS2_RELATIVE
        cfg_path = game_path / _CFG_RELATIVE
        if cfg_path.is_dir():
            return Cs2Installation(
                steam_path=steam_path, game_path=game_path, cfg_path=cfg_path
            )
        if manifest.is_file() and game_path.is_dir():
            # Le jeu est installé mais le dossier cfg n'existe pas encore.
            cfg_path.mkdir(parents=True, exist_ok=True)
            return Cs2Installation(
                steam_path=steam_path, game_path=game_path, cfg_path=cfg_path
            )

    raise Cs2NotFoundError(
        f"CS2 (app {CS2_APP_ID}) introuvable dans les bibliotheques Steam detectees"
    )


def try_find_cs2(explicit_path: str = "") -> Cs2Installation | None:
    """Variante non levante, pour les écrans de statut."""
    try:
        return find_cs2(explicit_path)
    except Cs2NotFoundError:
        return None
