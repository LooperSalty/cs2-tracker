"""Chargement de la configuration (env + .env), sans dépendance externe.

Toutes les valeurs sensibles proviennent de variables d'environnement ; aucun
secret n'est écrit en dur dans le code source.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from cs2tracker.constants import (
    DB_FILENAME,
    GSI_DEFAULT_HOST,
    GSI_DEFAULT_PORT,
)
from cs2tracker.core.errors import MissingApiKeyError

_ENV_PREFIX: Final = "CS2T_"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Dossier de données utilisateur (``%LOCALAPPDATA%\\CS2Tracker`` sur Windows)."""
    override = os.getenv(f"{_ENV_PREFIX}DATA_DIR")
    if override:
        path = Path(override).expanduser()
    else:
        base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_DATA_HOME")
        path = Path(base).joinpath("CS2Tracker") if base else Path.home() / ".cs2tracker"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_dotenv(path: Path | None = None) -> None:
    """Charge un ``.env`` minimaliste sans écraser l'environnement existant."""
    env_path = path or (project_root() / ".env")
    if not env_path.is_file():
        return
    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.getenv(f"{_ENV_PREFIX}{name}", os.getenv(name, default)).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on", "oui"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration applicative immuable."""

    steam_api_key: str
    #: Cle FACEIT, distincte de celle de Steam. Facultative.
    faceit_api_key: str
    api_host: str
    api_port: int
    gsi_token: str
    db_path: Path
    data_path: Path
    cs2_path_override: str
    log_level: str
    record_matches: bool
    auto_snapshot: bool
    open_ui: bool

    @property
    def has_steam_key(self) -> bool:
        return bool(self.steam_api_key)

    @property
    def api_base_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"

    @property
    def gsi_endpoint(self) -> str:
        return f"{self.api_base_url}/gsi"

    def require_steam_key(self) -> str:
        if not self.steam_api_key:
            raise MissingApiKeyError()
        return self.steam_api_key

    @property
    def has_faceit_key(self) -> bool:
        return bool(self.faceit_api_key)

    def with_steam_key(self, key: str) -> "Settings":
        """Renvoie une *nouvelle* configuration (jamais de mutation en place)."""
        return replace(self, steam_api_key=key.strip())

    def with_faceit_key(self, key: str) -> "Settings":
        return replace(self, faceit_api_key=key.strip())


def _load_or_create_gsi_token(store: Path) -> str:
    """Jeton partagé entre le .cfg CS2 et le serveur ; généré une seule fois."""
    from_env = _env("GSI_TOKEN")
    if from_env:
        return from_env
    token_file = store / "gsi_token.txt"
    if token_file.is_file():
        existing = token_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(24)
    token_file.write_text(token, encoding="utf-8")
    return token


def load_settings() -> Settings:
    load_dotenv()
    store = data_dir()
    return Settings(
        steam_api_key=_env("STEAM_API_KEY"),
        faceit_api_key=_env("FACEIT_API_KEY"),
        api_host=_env("API_HOST", GSI_DEFAULT_HOST),
        api_port=_env_int("API_PORT", GSI_DEFAULT_PORT),
        gsi_token=_load_or_create_gsi_token(store),
        db_path=store / DB_FILENAME,
        data_path=store,
        cs2_path_override=_env("CS2_PATH"),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        record_matches=_env_bool("RECORD_MATCHES", True),
        auto_snapshot=_env_bool("AUTO_SNAPSHOT", True),
        open_ui=_env_bool("OPEN_UI", True),
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton paresseux — la configuration est lue une fois par process."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Remplace la configuration courante (utilisé par l'UI et les tests)."""
    global _settings
    _settings = settings


def persist_env_value(name: str, value: str) -> None:
    """Écrit une valeur dans le ``.env`` du projet, en remplaçant l'ancienne.

    Les variantes préfixées sont retirées elles aussi : deux définitions de la
    même clé donneraient un comportement dépendant de l'ordre de lecture.
    """
    env_path = project_root() / ".env"
    prefixes = (f"{name}=", f"{_ENV_PREFIX}{name}=")

    lines: list[str] = []
    if env_path.is_file():
        lines = [
            line
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith(prefixes)
        ]
    lines.append(f"{name}={value.strip()}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value.strip()


def persist_steam_key(key: str) -> None:
    """Écrit la clé Steam dans le ``.env`` et rafraîchit la configuration."""
    persist_env_value("STEAM_API_KEY", key)
    set_settings(get_settings().with_steam_key(key))
