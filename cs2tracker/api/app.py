"""Fabrique de l'application FastAPI.

Sécurité : l'API n'écoute que sur la boucle locale par défaut, le CORS est
restreint aux origines locales, et toutes les erreurs sont converties en
réponses normalisées qui ne divulguent aucun détail interne.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from cs2tracker import __app_name__, __version__
from cs2tracker.api.context import AppContext, build_context, shutdown_context
from cs2tracker.api.routes import ALL_ROUTERS
from cs2tracker.api.schemas import fail, ok
from cs2tracker.config import Settings, get_settings
from cs2tracker.core.errors import Cs2TrackerError
from cs2tracker.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)

_DESCRIPTION = """
API locale de suivi CS2.

* **Profils & statistiques** : Steam Web API (donnees publiques uniquement).
* **Temps reel** : Game State Integration officiel de Valve.
* **Anti-triche** : moteur heuristique produisant un *score de suspicion*
  explicable — jamais une preuve.

Aucune lecture memoire, aucune injection, aucune modification du jeu hors du
fichier `.cfg` GSI prevu par Valve.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    setup_logging(resolved.log_level, resolved.data_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        context = build_context(resolved)
        app.state.context = context
        logger.info("API prete sur %s", resolved.api_base_url)
        try:
            yield
        finally:
            await shutdown_context(context)
            logger.info("API arretee proprement")

    app = FastAPI(
        title=f"{__app_name__} API",
        version=__version__,
        description=_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://127.0.0.1:{resolved.api_port}",
            f"http://localhost:{resolved.api_port}",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    for router in ALL_ROUTERS:
        app.include_router(router)

    _register_error_handlers(app)
    _register_root_routes(app)
    _mount_web_interface(app)
    return app


def _mount_web_interface(app: FastAPI) -> None:
    """Sert l'interface web locale sur ``/app``.

    Les fichiers sont entierement autonomes (aucun CDN) : l'application reste
    utilisable sans connexion Internet.
    """
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if not web_dir.is_dir():
        logger.warning("Interface web absente (%s) — API seule.", web_dir)
        return

    app.mount("/app", StaticFiles(directory=web_dir, html=True), name="web")

    @app.get("/ui", include_in_schema=False)
    async def ui_alias() -> RedirectResponse:
        return RedirectResponse("/app/")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        icon = web_dir / "favicon.ico"
        if icon.is_file():
            return FileResponse(icon)
        # L'icone est integree en SVG dans la page ; ce chemin ne sert qu'aux
        # requetes automatiques du navigateur.
        return Response(status_code=204)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Cs2TrackerError)
    async def handle_domain_error(_: Request, exc: Cs2TrackerError) -> JSONResponse:
        logger.info("Erreur metier (%s): %s", exc.__class__.__name__, exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.user_message, {"type": exc.__class__.__name__}),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"champ": ".".join(str(p) for p in err.get("loc", [])), "message": err.get("msg")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=fail("Requete invalide.", {"details": details}),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Le detail technique reste dans les logs, jamais dans la reponse.
        logger.exception("Erreur non geree: %s", exc)
        return JSONResponse(
            status_code=500,
            content=fail("Une erreur interne est survenue."),
        )


def _register_root_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["systeme"], summary="Sonde de sante")
    async def health() -> dict:
        return ok({"status": "ok", "version": __version__})

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return ok(
            {
                "name": __app_name__,
                "version": __version__,
                "docs": "/docs",
                "interface": "/app/",
                "endpoints": {
                    "systeme": "/api/system/status",
                    "joueurs": "/api/players/{steamid}",
                    "anti_triche": "/api/anticheat/{steamid}",
                    "temps_reel": "/api/live/state",
                    "matchs": "/api/matches",
                    "websocket": "/ws/live",
                },
            }
        )


def get_context(app: FastAPI) -> AppContext:
    return app.state.context
