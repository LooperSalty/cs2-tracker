"""Hiérarchie d'erreurs de l'application.

Chaque erreur porte un message *utilisateur* (``user_message``) distinct du
message technique, pour ne jamais fuiter de détail sensible dans l'UI ou l'API.
"""

from __future__ import annotations


class Cs2TrackerError(Exception):
    """Racine de toutes les erreurs applicatives."""

    status_code: int = 500
    user_message: str = "Une erreur interne est survenue."

    def __init__(self, message: str = "", *, user_message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        if user_message is not None:
            self.user_message = user_message


class ConfigError(Cs2TrackerError):
    status_code = 500
    user_message = "Configuration invalide."


class MissingApiKeyError(ConfigError):
    status_code = 503
    user_message = (
        "Cle API Steam absente. Renseigne STEAM_API_KEY dans le fichier .env "
        "(obtenue sur https://steamcommunity.com/dev/apikey)."
    )


class SteamApiError(Cs2TrackerError):
    status_code = 502
    user_message = "L'API Steam a repondu une erreur."

    def __init__(self, message: str = "", *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class SteamRateLimitError(SteamApiError):
    status_code = 429
    user_message = "Limite de requetes Steam atteinte, reessaie dans un instant."


class SteamUnauthorizedError(SteamApiError):
    status_code = 401
    user_message = "Cle API Steam refusee (invalide ou revoquee)."


class ProfilePrivateError(Cs2TrackerError):
    status_code = 403
    user_message = (
        "Le profil Steam est prive : les statistiques de jeu ne sont pas accessibles."
    )


class PlayerNotFoundError(Cs2TrackerError):
    status_code = 404
    user_message = "Joueur introuvable."


class InvalidSteamIdError(Cs2TrackerError):
    status_code = 400
    user_message = "Identifiant Steam invalide."


class GsiAuthError(Cs2TrackerError):
    status_code = 401
    user_message = "Jeton GSI invalide."


class Cs2NotFoundError(Cs2TrackerError):
    status_code = 404
    user_message = "Installation de Counter-Strike 2 introuvable sur ce PC."


class StorageError(Cs2TrackerError):
    status_code = 500
    user_message = "Erreur d'acces a la base locale."
