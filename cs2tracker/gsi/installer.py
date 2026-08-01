"""Génération et installation du fichier de configuration GSI de CS2.

CS2 lit tout fichier ``gamestate_integration_*.cfg`` présent dans
``game/csgo/cfg`` au démarrage et pousse ensuite l'état du jeu en HTTP POST
vers l'URI déclarée. C'est le mécanisme officiel Valve — aucune lecture
mémoire, aucune injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cs2tracker.constants import GSI_CONFIG_FILENAME
from cs2tracker.gsi.locator import Cs2Installation, find_cs2
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Blocs de données demandés au jeu. Les entrées ``allplayers_*`` et
#: ``*_position`` ne sont renseignées qu'en spectateur / GOTV (règle Valve).
_DATA_BLOCKS: tuple[str, ...] = (
    "provider",
    "map",
    "map_round_wins",
    "round",
    "player_id",
    "player_state",
    "player_weapons",
    "player_match_stats",
    "player_position",
    "allplayers_id",
    "allplayers_state",
    "allplayers_match_stats",
    "allplayers_weapons",
    "allplayers_position",
    "allgrenades",
    "bomb",
    "phase_countdowns",
)


@dataclass(frozen=True, slots=True)
class InstallResult:
    installed: bool
    config_path: Path
    endpoint: str
    message: str

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "installed": self.installed,
            "config_path": str(self.config_path),
            "endpoint": self.endpoint,
            "message": self.message,
        }


def render_config(endpoint: str, token: str, *, throttle: float = 0.1) -> str:
    """Produit le contenu VDF du fichier de configuration GSI."""
    data_lines = "\n".join(f'        "{block}"  "1"' for block in _DATA_BLOCKS)
    return (
        '"CS2 Tracker"\n'
        "{\n"
        f'    "uri"       "{endpoint}"\n'
        '    "timeout"   "5.0"\n'
        '    "buffer"    "0.1"\n'
        f'    "throttle"  "{throttle}"\n'
        '    "heartbeat" "10.0"\n'
        '    "auth"\n'
        "    {\n"
        f'        "token" "{token}"\n'
        "    }\n"
        '    "data"\n'
        "    {\n"
        f"{data_lines}\n"
        "    }\n"
        "}\n"
    )


def config_path_for(installation: Cs2Installation) -> Path:
    return installation.cfg_path / GSI_CONFIG_FILENAME


def install_config(
    endpoint: str,
    token: str,
    *,
    cs2_path_override: str = "",
    throttle: float = 0.1,
) -> InstallResult:
    """Écrit (ou met à jour) le ``.cfg`` GSI dans le dossier de CS2."""
    installation = find_cs2(cs2_path_override)
    target = config_path_for(installation)
    content = render_config(endpoint, token, throttle=throttle)

    if target.is_file():
        try:
            if target.read_text(encoding="utf-8") == content:
                return InstallResult(
                    installed=True,
                    config_path=target,
                    endpoint=endpoint,
                    message="Configuration GSI deja a jour.",
                )
        except OSError:
            pass

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Ecriture du cfg GSI impossible: %s", exc)
        return InstallResult(
            installed=False,
            config_path=target,
            endpoint=endpoint,
            message=(
                "Ecriture refusee. Lance l'application en administrateur ou copie "
                "le fichier manuellement."
            ),
        )

    logger.info("Configuration GSI installee: %s", target)
    return InstallResult(
        installed=True,
        config_path=target,
        endpoint=endpoint,
        message="Configuration GSI installee. Redemarre CS2 pour l'activer.",
    )


def uninstall_config(cs2_path_override: str = "") -> bool:
    installation = find_cs2(cs2_path_override)
    target = config_path_for(installation)
    if not target.is_file():
        return False
    try:
        target.unlink()
    except OSError as exc:
        logger.error("Suppression du cfg GSI impossible: %s", exc)
        return False
    return True


def is_installed(cs2_path_override: str = "") -> bool:
    from cs2tracker.gsi.locator import try_find_cs2

    installation = try_find_cs2(cs2_path_override)
    if installation is None:
        return False
    return config_path_for(installation).is_file()
