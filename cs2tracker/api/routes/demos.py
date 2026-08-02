"""Routes d'analyse de démos."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from cs2tracker.api.deps import ContextDep
from cs2tracker.api.schemas import DemoAnalyseRequest, ok
from cs2tracker.demos import analyse_demo, find_demos, parser_available
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/demos", tags=["demos"])


@router.get("", summary="Demos disponibles sur cette machine")
async def list_demos(
    context: ContextDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict:
    demos = find_demos(context.settings.cs2_path_override, limit=limit)
    return ok(
        {
            "parser_installed": parser_available(),
            "count": len(demos),
            "demos": [demo.as_dict() for demo in demos],
            "hint": (
                ""
                if parser_available()
                else "Installe demoparser2 pour activer l'analyse : "
                     "pip install demoparser2"
            ),
        }
    )


@router.post("/analyse", summary="Analyser une demo")
async def analyse(payload: DemoAnalyseRequest) -> dict:
    """Analyse la trajectoire angulaire des tirs.

    Le parsing est lourd (plusieurs secondes) et purement CPU : il tourne dans
    un thread pour ne pas bloquer la boucle asynchrone, et donc l'ingestion GSI
    qui continue pendant ce temps.
    """
    result = await run_in_threadpool(analyse_demo, payload.path, payload.steamid64)
    return ok(result.as_dict())
