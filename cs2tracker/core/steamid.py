"""Conversion et normalisation des identifiants Steam.

Formats supportés en entrée :
  - SteamID64        : ``76561198000000000``
  - SteamID2 (legacy): ``STEAM_1:0:20000000``
  - SteamID3         : ``[U:1:40000000]`` ou ``U:1:40000000``
  - AccountID brut   : ``40000000``
  - URL profil       : ``https://steamcommunity.com/profiles/765...``
  - URL vanity       : ``https://steamcommunity.com/id/monpseudo`` (→ à résoudre)
  - Vanity nu        : ``monpseudo``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from cs2tracker.constants import STEAMID64_BASE
from cs2tracker.core.errors import InvalidSteamIdError

_STEAMID2_RE: Final = re.compile(r"^STEAM_([0-5]):([01]):(\d+)$", re.IGNORECASE)
_STEAMID3_RE: Final = re.compile(r"^\[?U:1:(\d+)\]?$", re.IGNORECASE)
_PROFILE_URL_RE: Final = re.compile(
    r"steamcommunity\.com/profiles/(\d{17})", re.IGNORECASE
)
_VANITY_URL_RE: Final = re.compile(
    r"steamcommunity\.com/id/([A-Za-z0-9_.-]+)", re.IGNORECASE
)
_VANITY_RE: Final = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")

#: Un SteamID64 individuel valide est borné : 2^32 comptes possibles.
_MAX_ACCOUNT_ID: Final = 2**32 - 1


@dataclass(frozen=True, slots=True)
class SteamIdentity:
    """Représentation immuable et complète d'une identité Steam."""

    steamid64: int
    account_id: int

    @property
    def steamid2(self) -> str:
        return f"STEAM_1:{self.account_id & 1}:{self.account_id >> 1}"

    @property
    def steamid3(self) -> str:
        return f"[U:1:{self.account_id}]"

    @property
    def profile_url(self) -> str:
        return f"https://steamcommunity.com/profiles/{self.steamid64}"

    def as_dict(self) -> dict[str, str | int]:
        return {
            "steamid64": str(self.steamid64),
            "steamid3": self.steamid3,
            "steamid2": self.steamid2,
            "account_id": self.account_id,
            "profile_url": self.profile_url,
        }


@dataclass(frozen=True, slots=True)
class ResolveRequest:
    """Résultat d'une analyse locale : soit résolu, soit un vanity à résoudre."""

    identity: SteamIdentity | None
    vanity: str | None

    @property
    def needs_remote_lookup(self) -> bool:
        return self.identity is None and self.vanity is not None


def is_valid_steamid64(value: int) -> bool:
    return STEAMID64_BASE <= value <= STEAMID64_BASE + _MAX_ACCOUNT_ID


def from_steamid64(value: int | str) -> SteamIdentity:
    try:
        steamid64 = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise InvalidSteamIdError(f"SteamID64 illisible: {value!r}") from exc
    if not is_valid_steamid64(steamid64):
        raise InvalidSteamIdError(f"SteamID64 hors plage: {steamid64}")
    return SteamIdentity(steamid64=steamid64, account_id=steamid64 - STEAMID64_BASE)


def from_account_id(account_id: int) -> SteamIdentity:
    if not 0 < account_id <= _MAX_ACCOUNT_ID:
        raise InvalidSteamIdError(f"AccountID hors plage: {account_id}")
    return SteamIdentity(steamid64=STEAMID64_BASE + account_id, account_id=account_id)


def parse(raw: str) -> ResolveRequest:
    """Analyse une saisie utilisateur sans aucun appel réseau.

    Renvoie une identité complète quand le format est auto-suffisant, sinon le
    vanity name à résoudre via l'API Steam.
    """
    if not raw or not raw.strip():
        raise InvalidSteamIdError("Saisie vide")

    text = raw.strip()

    profile_match = _PROFILE_URL_RE.search(text)
    if profile_match:
        return ResolveRequest(from_steamid64(profile_match.group(1)), None)

    vanity_url_match = _VANITY_URL_RE.search(text)
    if vanity_url_match:
        return ResolveRequest(None, vanity_url_match.group(1))

    steamid2_match = _STEAMID2_RE.match(text)
    if steamid2_match:
        parity = int(steamid2_match.group(2))
        half = int(steamid2_match.group(3))
        return ResolveRequest(from_account_id(half * 2 + parity), None)

    steamid3_match = _STEAMID3_RE.match(text)
    if steamid3_match:
        return ResolveRequest(from_account_id(int(steamid3_match.group(1))), None)

    if text.isdigit():
        number = int(text)
        if number >= STEAMID64_BASE:
            return ResolveRequest(from_steamid64(number), None)
        if 0 < number <= _MAX_ACCOUNT_ID:
            return ResolveRequest(from_account_id(number), None)
        raise InvalidSteamIdError(f"Nombre non interpretable comme SteamID: {number}")

    if _VANITY_RE.match(text):
        return ResolveRequest(None, text)

    raise InvalidSteamIdError(f"Format non reconnu: {raw!r}")


#: Motifs d'identifiants reperables dans un texte libre (sortie de `status`,
#: liste collee depuis un site tiers, journal de partie…).
_SCAN_PATTERNS: Final = (
    re.compile(r"\[?U:1:(\d{1,10})\]?", re.IGNORECASE),
    re.compile(r"STEAM_[0-5]:([01]):(\d{1,10})", re.IGNORECASE),
    re.compile(r"\b(7656119\d{10})\b"),
)


def extract_all(text: str, *, limit: int = 64) -> tuple[SteamIdentity, ...]:
    """Repere tous les identifiants Steam presents dans un texte quelconque.

    Concu pour la sortie de la commande `status` de la console CS2, dont le
    format a change entre CS:GO et CS2. Plutot que de coller a une mise en page
    precise — qui casserait a la prochaine mise a jour du jeu — on balaie le
    texte a la recherche des motifs d'identifiants eux-memes.

    Les doublons sont ecartes en conservant l'ordre d'apparition, qui reflete
    l'ordre du tableau des scores.
    """
    if not text:
        return ()

    found: list[SteamIdentity] = []
    seen: set[int] = set()

    def remember(identity: SteamIdentity) -> None:
        if identity.steamid64 not in seen:
            seen.add(identity.steamid64)
            found.append(identity)

    for match in _SCAN_PATTERNS[0].finditer(text):
        try:
            remember(from_account_id(int(match.group(1))))
        except InvalidSteamIdError:
            continue

    for match in _SCAN_PATTERNS[1].finditer(text):
        try:
            account_id = int(match.group(2)) * 2 + int(match.group(1))
            remember(from_account_id(account_id))
        except InvalidSteamIdError:
            continue

    for match in _SCAN_PATTERNS[2].finditer(text):
        try:
            remember(from_steamid64(match.group(1)))
        except InvalidSteamIdError:
            continue

    return tuple(found[:limit])


def account_creation_hint(account_id: int) -> str:
    """Indice grossier d'ancienneté déduit de la séquence d'AccountID.

    Les AccountID sont attribués séquentiellement : un ID très élevé implique
    un compte récent. Ce n'est qu'un *indice* — ``timecreated`` du profil reste
    la source de vérité quand le profil est public.
    """
    if account_id < 50_000_000:
        return "compte anterieur a ~2012"
    if account_id < 200_000_000:
        return "compte ~2012-2015"
    if account_id < 500_000_000:
        return "compte ~2015-2018"
    if account_id < 900_000_000:
        return "compte ~2018-2021"
    if account_id < 1_400_000_000:
        return "compte ~2021-2024"
    return "compte tres recent (>2024)"
