"""Client HTTP synchrone de l'interface vers l'API locale.

L'UI ne connaît que l'API : aucune logique métier n'est dupliquée côté Qt.
Cela garantit que l'API est réellement utilisable de l'extérieur.
"""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 30.0


class ApiError(Exception):
    """Erreur remontée par l'API, déjà formulée pour l'utilisateur."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Enveloppe fine autour de ``httpx.Client`` respectant l'enveloppe API."""

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    @property
    def base_url(self) -> str:
        return self._base_url

    # --- primitives ----------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(
                method, path, params=params, json=json_body
            )
        except httpx.ConnectError as exc:
            raise ApiError(
                "Impossible de joindre l'API locale. Le service est-il demarre ?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiError("L'API locale ne repond pas (delai depasse).") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"Erreur reseau locale: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                f"Reponse illisible de l'API (HTTP {response.status_code})."
            ) from exc

        if not isinstance(payload, Mapping):
            raise ApiError("Format de reponse inattendu.")

        if payload.get("success") is False or response.status_code >= 400:
            raise ApiError(
                str(payload.get("error") or f"Erreur HTTP {response.status_code}"),
                response.status_code,
            )
        return payload.get("data")

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Mapping[str, Any] | None = None, **params: Any) -> Any:
        return self._request(
            "POST", path, params=params or None, json_body=body
        )

    def put(self, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return self._request("PUT", path, json_body=body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # --- appels metier -------------------------------------------------------
    def health(self) -> Any:
        return self.get("/health")

    def system_status(self) -> Any:
        return self.get("/api/system/status")

    def install_gsi(self, throttle: float = 0.1) -> Any:
        return self.post("/api/system/gsi/install", {"throttle": throttle})

    def uninstall_gsi(self) -> Any:
        return self.delete("/api/system/gsi/install")

    def gsi_preview(self) -> Any:
        return self.get("/api/system/gsi/preview")

    def clear_cache(self) -> Any:
        return self.post("/api/system/cache/clear")

    def search_player(self, query: str) -> Any:
        return self.post("/api/players/search", {"query": query})

    def player_profile(self, steamid: str) -> Any:
        return self.get(f"/api/players/{steamid}")

    def player_weapons(self, steamid: str) -> Any:
        return self.get(f"/api/players/{steamid}/weapons")

    def player_maps(self, steamid: str) -> Any:
        return self.get(f"/api/players/{steamid}/maps")

    def player_games(self, steamid: str, limit: int = 25) -> Any:
        return self.get(f"/api/players/{steamid}/games", limit=limit)

    def player_history(self, steamid: str) -> Any:
        return self.get(f"/api/players/{steamid}/history")

    def tracked_players(self, favourites_only: bool = False) -> Any:
        return self.get("/api/players/tracked", favourites_only=favourites_only)

    def set_favourite(self, steamid: str, favourite: bool) -> Any:
        return self.put(f"/api/players/{steamid}/favourite", {"favourite": favourite})

    def analyse(self, steamid: str, use_live: bool = True) -> Any:
        return self.get(f"/api/anticheat/{steamid}", use_live=use_live)

    def analyse_report(self, steamid: str) -> Any:
        return self.get(f"/api/anticheat/{steamid}/report")

    def analyse_batch(self, players: list[str], use_live: bool = True) -> Any:
        return self.post(
            "/api/anticheat/batch",
            {"players": players, "use_live_data": use_live, "persist": True},
        )

    def analyse_live_lobby(self) -> Any:
        return self.post("/api/anticheat/lobby/live")

    def anticheat_disclaimer(self) -> Any:
        return self.get("/api/anticheat/disclaimer")

    def suspicious_leaderboard(self, limit: int = 25) -> Any:
        return self.get("/api/anticheat/leaderboard/suspicious", limit=limit)

    def live_state(self) -> Any:
        return self.get("/api/live/state")

    def live_scoreboard(self) -> Any:
        return self.get("/api/live/scoreboard")

    def live_players(self) -> Any:
        return self.get("/api/live/players")

    def live_events(self, since: int = 0, limit: int = 100) -> Any:
        return self.get("/api/live/events", since=since, limit=limit)

    def matches(self, limit: int = 50) -> Any:
        return self.get("/api/matches", limit=limit)

    def match_detail(self, match_id: int) -> Any:
        return self.get(f"/api/matches/{match_id}")
