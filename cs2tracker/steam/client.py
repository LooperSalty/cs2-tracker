"""Client HTTP asynchrone pour la Steam Web API.

Responsabilités : limitation de débit, retries exponentiels, cache TTL,
traduction des codes HTTP en erreurs de domaine. La clé API n'est jamais
journalisée ni renvoyée dans une exception.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import httpx

from cs2tracker.constants import (
    HTTP_BACKOFF_BASE_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT_SECONDS,
    STEAM_RATE_LIMIT_PER_SECOND,
)
from cs2tracker.core.errors import (
    ProfilePrivateError,
    SteamApiError,
    SteamRateLimitError,
    SteamUnauthorizedError,
)
from cs2tracker.core.utils import now_ts
from cs2tracker.logging_setup import get_logger
from cs2tracker.steam.cache import TtlCache

logger = get_logger(__name__)

#: Codes qui justifient une nouvelle tentative (transitoires côté Steam).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class RateLimiter:
    """Limiteur à jetons simple : espace les requêtes dans le temps."""

    def __init__(self, per_second: float) -> None:
        self._min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            elapsed = now_ts() - self._last_call
            wait_for = self._min_interval - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_call = now_ts()


class SteamClient:
    """Façade bas niveau : ``get_json`` + gestion d'erreurs et de cache."""

    def __init__(self, api_key: str, *, cache: TtlCache | None = None) -> None:
        self._api_key = api_key
        self._cache = cache or TtlCache()
        self._limiter = RateLimiter(STEAM_RATE_LIMIT_PER_SECOND)
        self._client: httpx.AsyncClient | None = None
        self._request_count = 0

    # --- cycle de vie --------------------------------------------------------
    async def __aenter__(self) -> "SteamClient":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
                headers={"User-Agent": "CS2Tracker/1.0 (+local)"},
                follow_redirects=True,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- accès ---------------------------------------------------------------
    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def cache(self) -> TtlCache:
        return self._cache

    def _cache_key(self, url: str, params: Mapping[str, Any]) -> str:
        # La clé API est exclue de la clé de cache : elle ne varie pas.
        relevant = sorted((k, str(v)) for k, v in params.items() if k != "key")
        return f"{url}?{'&'.join(f'{k}={v}' for k, v in relevant)}"

    async def get_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        ttl_seconds: float = 0.0,
        allow_private: bool = False,
    ) -> dict[str, Any]:
        """Effectue un GET JSON avec cache, limitation et retries.

        ``allow_private`` : si vrai, un 403 renvoie ``{}`` au lieu de lever —
        pratique pour les endpoints facultatifs (amis, jeux possédés).
        """
        request_params: dict[str, Any] = dict(params or {})
        request_params["key"] = self._api_key

        cache_key = self._cache_key(url, request_params)
        if ttl_seconds > 0:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached

        payload = await self._request_with_retries(url, request_params, allow_private)

        if ttl_seconds > 0:
            await self._cache.set(cache_key, payload, ttl_seconds)
        return payload

    async def _request_with_retries(
        self, url: str, params: Mapping[str, Any], allow_private: bool
    ) -> dict[str, Any]:
        await self.start()
        assert self._client is not None

        last_error: Exception | None = None
        for attempt in range(HTTP_MAX_RETRIES):
            await self._limiter.acquire()
            try:
                self._request_count += 1
                response = await self._client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("Timeout Steam (essai %d) sur %s", attempt + 1, _safe(url))
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Erreur reseau Steam (essai %d): %s", attempt + 1, exc)
            else:
                terminal = self._handle_status(response, allow_private)
                if terminal is not None:
                    return terminal
                if response.status_code not in _RETRYABLE_STATUS:
                    raise SteamApiError(
                        f"Reponse inattendue {response.status_code}",
                        http_status=response.status_code,
                    )
                last_error = SteamApiError(
                    f"HTTP {response.status_code}", http_status=response.status_code
                )
                if response.status_code == 429:
                    logger.warning("Steam limite le debit, backoff...")

            if attempt < HTTP_MAX_RETRIES - 1:
                await asyncio.sleep(HTTP_BACKOFF_BASE_SECONDS * (2**attempt))

        if isinstance(last_error, SteamApiError) and last_error.http_status == 429:
            raise SteamRateLimitError(str(last_error))
        raise SteamApiError(f"Echec apres {HTTP_MAX_RETRIES} tentatives: {last_error}")

    def _handle_status(
        self, response: httpx.Response, allow_private: bool
    ) -> dict[str, Any] | None:
        """Renvoie le payload si la requête est terminée, ``None`` pour réessayer."""
        status = response.status_code

        if status == 200:
            try:
                data = response.json()
            except ValueError as exc:
                raise SteamApiError("Reponse Steam non-JSON") from exc
            return data if isinstance(data, dict) else {"data": data}

        if status in {401, 403}:
            # 403 = profil privé sur les endpoints de stats ; 401 = clé invalide.
            if status == 403:
                if allow_private:
                    return {}
                raise ProfilePrivateError()
            raise SteamUnauthorizedError("Cle API refusee", http_status=status)

        if status == 404:
            # Steam renvoie 404 quand le joueur n'a aucune stat pour l'appid.
            return {}

        return None


def _safe(url: str) -> str:
    """Retire tout paramètre de requête d'une URL avant journalisation."""
    return url.split("?", 1)[0]
