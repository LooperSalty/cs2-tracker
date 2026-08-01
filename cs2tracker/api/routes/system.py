"""Routes système : santé, statut, configuration GSI, diagnostic."""

from __future__ import annotations

from fastapi import APIRouter

from cs2tracker import __version__
from cs2tracker.api.deps import ContextDep
from cs2tracker.api.schemas import GsiInstallRequest, SteamKeyRequest, ok
from cs2tracker.config import persist_steam_key
from cs2tracker.core.errors import ConfigError, Cs2NotFoundError
from cs2tracker.gsi.installer import install_config, render_config, uninstall_config
from cs2tracker.gsi.locator import try_find_cs2

router = APIRouter(prefix="/api/system", tags=["systeme"])


@router.get("/status", summary="Etat complet de l'application")
async def status(context: ContextDep) -> dict:
    snapshot = await context.live.snapshot()
    return ok(
        {
            "version": __version__,
            **context.system_status(),
            "live": {
                "connected": snapshot.connected,
                "payloads_received": snapshot.payload_count,
                "seconds_since_update": snapshot.seconds_since_update,
                "websocket_subscribers": context.live.subscriber_count,
            },
        }
    )


@router.get("/cs2", summary="Chemins d'installation de CS2")
async def cs2_paths(context: ContextDep) -> dict:
    installation = try_find_cs2(context.settings.cs2_path_override)
    if installation is None:
        raise Cs2NotFoundError()
    return ok(installation.as_dict())


@router.post("/gsi/install", summary="Installer la configuration GSI dans CS2")
async def gsi_install(context: ContextDep, payload: GsiInstallRequest) -> dict:
    result = install_config(
        context.settings.gsi_endpoint,
        context.settings.gsi_token,
        cs2_path_override=context.settings.cs2_path_override,
        throttle=payload.throttle,
    )
    return ok(result.as_dict())


@router.delete("/gsi/install", summary="Retirer la configuration GSI")
async def gsi_uninstall(context: ContextDep) -> dict:
    removed = uninstall_config(context.settings.cs2_path_override)
    return ok({"removed": removed})


@router.get("/gsi/preview", summary="Apercu du fichier .cfg genere")
async def gsi_preview(context: ContextDep) -> dict:
    content = render_config(
        context.settings.gsi_endpoint, context.settings.gsi_token
    )
    return ok(
        {
            "filename": "gamestate_integration_cs2tracker.cfg",
            "content": content,
            "endpoint": context.settings.gsi_endpoint,
        }
    )


@router.get("/servers", summary="Etat des serveurs officiels CS2")
async def servers(context: ContextDep) -> dict:
    status_payload = await context.steam.get_servers_status()
    player_count = await context.steam.get_current_players()
    return ok({"servers": status_payload, "players_online": player_count})


@router.get("/overlay", summary="Etat de l'overlay en jeu")
async def overlay_status(context: ContextDep) -> dict:
    from cs2tracker.desktop import overlay_launcher

    executable = overlay_launcher.find_overlay()
    return ok(
        {
            "available": executable is not None,
            "running": overlay_launcher.is_running(),
            "path": str(executable) if executable else None,
        }
    )


@router.post("/overlay", summary="Lancer l'overlay en jeu")
async def overlay_start(context: ContextDep) -> dict:
    """Demarre l'executable natif affiche par-dessus CS2.

    L'overlay est un processus distinct qui n'injecte rien dans le jeu : il
    interroge cette meme API en HTTP.
    """
    from cs2tracker.desktop import overlay_launcher

    started, message = overlay_launcher.launch(context.settings.api_port)
    return ok({"started": started, "message": message})


@router.post("/steam-key", summary="Enregistrer la cle API Steam")
async def save_steam_key(payload: SteamKeyRequest) -> dict:
    """Écrit la clé dans le ``.env`` local.

    La clé n'est jamais renvoyée : la réponse ne confirme que l'écriture.
    Le redémarrage est nécessaire car le client Steam est construit au
    démarrage de l'API.
    """
    try:
        persist_steam_key(payload.key)
    except OSError as exc:
        raise ConfigError(
            str(exc),
            user_message="Ecriture du fichier .env impossible (droits insuffisants ?).",
        ) from exc
    return ok(
        {
            "saved": True,
            "restart_required": True,
            "message": "Cle enregistree. Redemarre l'application pour l'activer.",
        }
    )


@router.post("/cache/clear", summary="Vider le cache Steam")
async def clear_cache(context: ContextDep) -> dict:
    if context.steam_client is None:
        return ok({"cleared": 0})
    cleared = await context.steam_client.cache.invalidate()
    return ok({"cleared": cleared})
