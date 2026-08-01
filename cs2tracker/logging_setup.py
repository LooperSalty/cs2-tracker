"""Configuration du logging : console + fichier rotatif, secrets masqués."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

_SECRET_PATTERNS: Final = (
    re.compile(r"(key=)[A-Za-z0-9]{8,}", re.IGNORECASE),
    re.compile(r"(token[\"'=:\s]+)[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
)

_LOG_FORMAT: Final = "%(asctime)s %(levelname)-8s %(name)-28s %(message)s"
_MAX_BYTES: Final = 2_000_000
_BACKUP_COUNT: Final = 3


class SecretMaskingFilter(logging.Filter):
    """Empêche toute clé API ou jeton d'atterrir dans les logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = message
        for pattern in _SECRET_PATTERNS:
            masked = pattern.sub(r"\1***", masked)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    root = logging.getLogger()
    if getattr(root, "_cs2tracker_configured", False):
        return

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(_LOG_FORMAT, datefmt="%H:%M:%S")
    secret_filter = SecretMaskingFilter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(secret_filter)
    root.addHandler(console)

    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "cs2tracker.log",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(secret_filter)
            root.addHandler(file_handler)
        except OSError:
            root.warning("Impossible d'ouvrir le fichier de log, console uniquement.")

    for noisy in ("httpx", "httpcore", "uvicorn.access", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._cs2tracker_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
