"""Routes temps réel : ingestion GSI, état courant, flux d'événements."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from cs2tracker.api.deps import ContextDep, SteamIdDep
from cs2tracker.api.schemas import ok
from cs2tracker.core.errors import GsiAuthError
from cs2tracker.gsi.parser import extract_token, parse_payload
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["temps-reel"])

#: Taille maximale acceptée pour un payload GSI (garde-fou anti-abus).
MAX_GSI_BODY_BYTES = 1_500_000
#: Délai maximal d'attente d'un message WebSocket avant envoi d'un ping.
WS_HEARTBEAT_SECONDS = 20.0


@router.post("/gsi", include_in_schema=False)
async def ingest_gsi(request: Request, context: ContextDep) -> dict[str, Any]:
    """Point de collecte appelé directement par CS2.

    Le jeton d'authentification déclaré dans le ``.cfg`` est vérifié à chaque
    requête : sans lui, n'importe quel processus local pourrait injecter un
    faux état de jeu.
    """
    body = await request.body()
    if len(body) > MAX_GSI_BODY_BYTES:
        raise GsiAuthError("Payload GSI anormalement volumineux")

    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise GsiAuthError("Payload GSI illisible") from exc

    if not isinstance(payload, dict):
        raise GsiAuthError("Payload GSI de forme inattendue")

    expected = context.settings.gsi_token
    if expected and extract_token(payload) != expected:
        logger.warning("Payload GSI rejete : jeton invalide")
        raise GsiAuthError()

    state = parse_payload(payload)
    events = await context.live.update(state)
    context.recorder.handle(state, events, await context.live.all_raw_metrics())
    return {"ok": True}


@router.get("/api/live/state", summary="Etat de jeu courant", tags=["temps-reel"])
async def live_state(context: ContextDep) -> dict:
    return ok((await context.live.snapshot()).as_dict())


@router.get("/api/live/scoreboard", summary="Tableau des scores", tags=["temps-reel"])
async def scoreboard(context: ContextDep) -> dict:
    return ok(await context.live.scoreboard())


@router.get("/api/live/players", summary="Metriques temps reel par joueur", tags=["temps-reel"])
async def live_players(context: ContextDep) -> dict:
    return ok(await context.live.tracker_snapshot())


@router.get(
    "/api/live/players/{steamid}",
    summary="Metriques temps reel d'un joueur",
    tags=["temps-reel"],
)
async def live_player(steamid: SteamIdDep, context: ContextDep) -> dict:
    metrics = await context.live.live_metrics(steamid)
    return ok(metrics)


@router.get("/api/live/events", summary="Flux d'evenements", tags=["temps-reel"])
async def live_events(
    context: ContextDep,
    since: Annotated[int, Query(ge=0, description="Dernier numero de sequence recu")] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict:
    latest, events = await context.live.recent_events(since=since, limit=limit)
    return ok({"latest_sequence": latest, "events": events})


@router.post("/api/live/reset", summary="Reinitialiser l'etat temps reel", tags=["temps-reel"])
async def live_reset(context: ContextDep) -> dict:
    await context.live.reset()
    return ok({"reset": True})


@router.websocket("/ws/live")
async def live_websocket(websocket: WebSocket) -> None:
    """Diffusion en continu de l'état et des événements."""
    context = websocket.app.state.context
    await websocket.accept()
    queue = await context.live.subscribe()

    try:
        snapshot = await context.live.snapshot()
        await websocket.send_json({"type": "snapshot", "data": snapshot.as_dict()})
        while True:
            try:
                message = await asyncio.wait_for(
                    queue.get(), timeout=WS_HEARTBEAT_SECONDS
                )
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.debug("Client WebSocket deconnecte")
    except Exception as exc:  # noqa: BLE001 - on ferme proprement quoi qu'il arrive
        logger.warning("WebSocket interrompu: %s", exc)
    finally:
        await context.live.unsubscribe(queue)
