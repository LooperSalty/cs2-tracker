"""Identification du compte Steam utilisé sur cette machine.

Objectif : ne pas obliger l'utilisateur à ressaisir son SteamID pour consulter
ses propres statistiques.

Trois sources, de la plus fiable à la moins fiable :

1. le flux GSI, quand CS2 tourne — ``provider.steamid`` désigne sans ambiguïté
   le joueur local ;
2. le registre Windows, quand le client Steam est lancé — ``ActiveUser`` porte
   l'AccountID de la session ouverte ;
3. ``config/loginusers.vdf``, toujours présent — on y retient le compte marqué
   ``AutoLogin``, sinon le plus récemment utilisé.

Aucune de ces sources ne fait de requête réseau.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cs2tracker.core.steamid import from_account_id, from_steamid64
from cs2tracker.core.utils import to_int
from cs2tracker.gsi.locator import find_steam_path
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Bloc `"7656119..." { ... }` du fichier loginusers.vdf.
_USER_BLOCK_RE: Final = re.compile(
    r'"(7656119\d{10})"\s*\{(.*?)\}', re.DOTALL
)
_FIELD_RE: Final = re.compile(r'"([^"]+)"\s+"([^"]*)"')


@dataclass(frozen=True, slots=True)
class LocalAccount:
    """Compte Steam connu de cette machine."""

    steamid64: str
    account_name: str
    persona_name: str
    auto_login: bool
    last_used: int
    #: Comment ce compte a été repéré, pour l'expliquer à l'utilisateur.
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "steamid64": self.steamid64,
            "account_name": self.account_name,
            "persona_name": self.persona_name,
            "auto_login": self.auto_login,
            "last_used": self.last_used,
            "source": self.source,
        }


def _login_users_file() -> Path | None:
    steam_path = find_steam_path()
    if steam_path is None:
        return None
    candidate = steam_path / "config" / "loginusers.vdf"
    return candidate if candidate.is_file() else None


def read_known_accounts() -> tuple[LocalAccount, ...]:
    """Tous les comptes ayant ouvert une session sur cette machine."""
    path = _login_users_file()
    if path is None:
        return ()

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.warning("loginusers.vdf illisible : %s", exc)
        return ()

    accounts: list[LocalAccount] = []
    for match in _USER_BLOCK_RE.finditer(content):
        steamid = match.group(1)
        fields = {k.lower(): v for k, v in _FIELD_RE.findall(match.group(2))}
        accounts.append(
            LocalAccount(
                steamid64=steamid,
                account_name=fields.get("accountname", ""),
                persona_name=fields.get("personaname", ""),
                auto_login=fields.get("autologin", "0") == "1",
                last_used=to_int(fields.get("timestamp")),
                source="loginusers.vdf",
            )
        )

    # Le plus recemment utilise en tete : c'est le choix par defaut le plus sur.
    return tuple(sorted(accounts, key=lambda a: a.last_used, reverse=True))


def active_account_id() -> int:
    """AccountID de la session Steam ouverte, 0 si le client est fermé."""
    if sys.platform != "win32":
        return 0
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ActiveUser")
            return to_int(value)
    except OSError:
        return 0


def is_ambiguous() -> bool:
    """Vrai si plusieurs comptes Steam cohabitent sur cette machine.

    Dans ce cas, deviner est risqué : la clé API appartient au compte connecté
    sur le **site** Steam, alors que la détection observe le **client**. Les
    deux diffèrent régulièrement, et rien ne permet de les relier. Mieux vaut
    alors demander qu'imposer un mauvais profil.
    """
    return len(read_known_accounts()) > 1


def detect_local_account() -> LocalAccount | None:
    """Meilleure hypothèse sur l'identité de l'utilisateur."""
    accounts = read_known_accounts()

    # 1. Session Steam ouverte : verite du moment.
    active_id = active_account_id()
    if active_id:
        try:
            steamid = str(from_account_id(active_id).steamid64)
        except Exception:  # noqa: BLE001 - un registre incoherent ne doit rien casser
            steamid = ""
        if steamid:
            for account in accounts:
                if account.steamid64 == steamid:
                    return LocalAccount(
                        steamid64=account.steamid64,
                        account_name=account.account_name,
                        persona_name=account.persona_name,
                        auto_login=account.auto_login,
                        last_used=account.last_used,
                        source="session Steam en cours",
                    )
            return LocalAccount(
                steamid64=steamid, account_name="", persona_name="",
                auto_login=False, last_used=0, source="session Steam en cours",
            )

    if not accounts:
        return None

    # 2. Compte marque pour la connexion automatique.
    for account in accounts:
        if account.auto_login:
            return LocalAccount(
                steamid64=account.steamid64,
                account_name=account.account_name,
                persona_name=account.persona_name,
                auto_login=True,
                last_used=account.last_used,
                source="connexion automatique Steam",
            )

    # 3. A defaut, le dernier compte utilise.
    newest = accounts[0]
    return LocalAccount(
        steamid64=newest.steamid64,
        account_name=newest.account_name,
        persona_name=newest.persona_name,
        auto_login=False,
        last_used=newest.last_used,
        source="dernier compte connecte",
    )


def account_from_gsi(provider_steamid: str) -> LocalAccount | None:
    """Identité issue du flux GSI — la plus fiable quand CS2 tourne."""
    if not provider_steamid:
        return None
    try:
        identity = from_steamid64(provider_steamid)
    except Exception:  # noqa: BLE001 - payload GSI inattendu
        return None
    return LocalAccount(
        steamid64=str(identity.steamid64),
        account_name="",
        persona_name="",
        auto_login=False,
        last_used=0,
        source="partie CS2 en cours",
    )
