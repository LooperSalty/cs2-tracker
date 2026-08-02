"""Vérification des mises à jour depuis les releases GitHub.

L'application **ne se met jamais à jour toute seule** : elle signale qu'une
version existe et laisse l'utilisateur décider. Télécharger et exécuter un
binaire sans accord explicite serait exactement le comportement qu'on reproche
aux logiciels indésirables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

import httpx

from cs2tracker import __version__
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

RELEASES_API: Final = (
    "https://api.github.com/repos/LooperSalty/cs2-tracker/releases/latest"
)
RELEASES_PAGE: Final = "https://github.com/LooperSalty/cs2-tracker/releases/latest"

_VERSION_RE: Final = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_TIMEOUT: Final = 8.0


def parse_version(text: str) -> tuple[int, int, int]:
    """Extrait un triplet depuis « v1.8.0 », « 1.8.0 » ou « CS2 Tracker 1.8.0 »."""
    match = _VERSION_RE.search(text or "")
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    checked: bool
    current: str
    latest: str = ""
    update_available: bool = False
    url: str = RELEASES_PAGE
    notes: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "current": self.current,
            "latest": self.latest,
            "update_available": self.update_available,
            "url": self.url,
            "notes": self.notes[:2000],
            "reason": self.reason,
        }


async def check_for_update(timeout: float = _TIMEOUT) -> UpdateStatus:
    """Interroge GitHub. Une panne réseau n'est pas une erreur applicative."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                RELEASES_API,
                headers={"Accept": "application/vnd.github+json"},
            )
    except httpx.HTTPError as exc:
        return UpdateStatus(
            checked=False, current=__version__,
            reason=f"GitHub injoignable : {exc}",
        )

    if response.status_code != 200:
        return UpdateStatus(
            checked=False, current=__version__,
            reason=f"GitHub a repondu {response.status_code}.",
        )

    try:
        payload = response.json()
    except ValueError:
        return UpdateStatus(
            checked=False, current=__version__, reason="Reponse GitHub illisible."
        )

    latest_tag = str(payload.get("tag_name") or "")
    latest = parse_version(latest_tag)
    current = parse_version(__version__)

    return UpdateStatus(
        checked=True,
        current=__version__,
        latest=latest_tag.lstrip("v"),
        update_available=latest > current,
        url=str(payload.get("html_url") or RELEASES_PAGE),
        notes=str(payload.get("body") or ""),
    )
