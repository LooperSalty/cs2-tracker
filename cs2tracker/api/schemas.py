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


class SteamKeyRequest(BaseModel):
    """Une clé Steam est une chaîne hexadécimale de 32 caractères."""

    key: str = Field(..., min_length=16, max_length=64)

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
