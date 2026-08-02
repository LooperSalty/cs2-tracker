"""Enveloppe de réponse commune et modèles d'entrée validés."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")

#: Nombre maximal de joueurs analysables en une requête (taille d'un lobby CS2).
MAX_BATCH_PLAYERS = 10


class ApiResponse(BaseModel, Generic[T]):
    """Enveloppe uniforme : ``success`` + ``data`` + ``error``."""

    success: bool = True
    data: T | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None, "meta": meta}


def fail(message: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": False, "data": None, "error": message, "meta": meta}


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=256, description="SteamID, URL ou vanity")

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("La recherche ne peut pas etre vide")
        return cleaned


class BatchAnalyseRequest(BaseModel):
    players: list[str] = Field(
        ..., min_length=1, max_length=MAX_BATCH_PLAYERS,
        description="SteamIDs, URLs ou vanity names (10 maximum)",
    )
    use_live_data: bool = Field(
        default=True, description="Croiser avec les metriques temps reel disponibles"
    )
    persist: bool = Field(default=True, description="Enregistrer les analyses en base")

    @field_validator("players")
    @classmethod
    def clean_players(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v and v.strip()]
        if not cleaned:
            raise ValueError("Aucun joueur valide fourni")
        return cleaned


class NotesRequest(BaseModel):
    notes: str = Field(default="", max_length=4_000)


class FavouriteRequest(BaseModel):
    favourite: bool = True


#: Un collage de console CS2 tient largement dans cette limite.
MAX_PASTE_LENGTH = 20_000


class LobbyPasteRequest(BaseModel):
    """Texte libre collé depuis la console CS2 (commande ``status``)."""

    text: str = Field(..., min_length=1, max_length=MAX_PASTE_LENGTH)
    analyse: bool = Field(
        default=True, description="Analyser les joueurs trouves, pas seulement les extraire"
    )

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le texte colle est vide")
        return cleaned


class CompareRequest(BaseModel):
    """Deux joueurs à confronter."""

    left: str = Field(..., min_length=1, max_length=256)
    right: str = Field(..., min_length=1, max_length=256)

    @field_validator("left", "right")
    @classmethod
    def strip_side(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Identifiant vide")
        return cleaned


class CalibrationRequest(BaseModel):
    """Corpus étiquetés servant à mesurer le moteur."""

    #: Comptes portant une sanction confirmee.
    cheaters: list[str] = Field(default_factory=list, max_length=200)
    #: Joueurs de confiance : professionnels, streamers, comptes verifies.
    legit: list[str] = Field(default_factory=list, max_length=200)
    #: Signaler un joueur honnete coute plus cher que manquer un tricheur.
    max_false_positive_rate: float = Field(default=0.02, ge=0.0, le=0.5)

    @field_validator("cheaters", "legit")
    @classmethod
    def clean_corpus(cls, values: list[str]) -> list[str]:
        return [v.strip() for v in values if v and v.strip()]


class DemoAnalyseRequest(BaseModel):
    """Démo à analyser, avec le joueur à isoler."""

    path: str = Field(..., min_length=1, max_length=1024)
    #: Vide = tous les joueurs de la demo.
    steamid64: str = Field(default="", max_length=17)

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.lower().endswith(".dem"):
            raise ValueError("Le fichier doit etre une demo .dem")
        return cleaned


class FaceitKeyRequest(BaseModel):
    key: str = Field(..., min_length=8, max_length=128)

    @field_validator("key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        return value.strip()


class SetMeRequest(BaseModel):
    """Désignation manuelle du compte de l'utilisateur."""

    steamid64: str = Field(..., min_length=17, max_length=17)

    @field_validator("steamid64")
    @classmethod
    def check_steamid(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError("Un SteamID64 ne contient que des chiffres")
        return cleaned


class SteamKeyRequest(BaseModel):
    """Une clé Steam est une chaîne hexadécimale de 32 caractères."""

    key: str = Field(..., min_length=16, max_length=64)
    verify: bool = Field(
        default=True,
        description=(
            "Interroger Steam pour confirmer que la cle est acceptee. "
            "Desactivable si Steam est momentanement injoignable."
        ),
    )

    @field_validator("key")
    @classmethod
    def clean_key(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isalnum():
            raise ValueError("Une cle Steam ne contient que des lettres et des chiffres")
        return cleaned


class GsiInstallRequest(BaseModel):
    throttle: float = Field(
        default=0.1, ge=0.01, le=5.0,
        description="Intervalle minimal entre deux envois du jeu (secondes)",
    )
