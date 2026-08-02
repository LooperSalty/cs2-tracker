"""Tests de l'API : enveloppe de réponse, validation, ingestion GSI, stockage."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cs2tracker.api.app import create_app
from cs2tracker.config import get_settings
from tests.test_gsi import payload


@pytest.fixture
def client():
    with TestClient(create_app(get_settings())) as test_client:
        yield test_client


@pytest.fixture
def gsi_token():
    return get_settings().gsi_token


# --- Enveloppe et routes de base ---------------------------------------------
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


def test_root_lists_endpoints(client):
    body = client.get("/").json()
    assert "endpoints" in body["data"]


def test_system_status(client):
    body = client.get("/api/system/status").json()
    assert body["success"] is True
    assert "database" in body["data"]
    assert "gsi_endpoint" in body["data"]


def test_openapi_schema_is_generated(client):
    assert client.get("/openapi.json").status_code == 200


# --- Validation ---------------------------------------------------------------
def test_invalid_steamid_is_rejected(client):
    response = client.get("/api/players/not-a-steamid/stats")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert "invalide" in body["error"].lower()


def test_offline_identity_parsing(client):
    body = client.get("/api/players/parse/76561198043717815").json()
    assert body["data"]["resolved"] is True
    assert body["data"]["steamid2"].startswith("STEAM_1:")


def test_offline_parsing_detects_vanity(client):
    body = client.get("/api/players/parse/gabelogannewell").json()
    assert body["data"]["resolved"] is False
    assert body["data"]["vanity"] == "gabelogannewell"


def test_batch_request_rejects_empty_list(client):
    response = client.post("/api/anticheat/batch", json={"players": []})
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_batch_request_caps_player_count(client):
    response = client.post(
        "/api/anticheat/batch", json={"players": [str(i) for i in range(20)]}
    )
    assert response.status_code == 422


# --- Anti-triche : routes hors réseau ----------------------------------------
def test_disclaimer_route(client):
    data = client.get("/api/anticheat/disclaimer").json()["data"]
    assert "preuve" in data["disclaimer"].lower()
    assert "smurfs" in " ".join(data["methodology"]["known_false_positives"])
    assert "lecture de la memoire du jeu" in data["methodology"]["never_used"]


def test_weights_route(client):
    data = client.get("/api/anticheat/weights").json()["data"]
    assert data["weights"]["aim.headshot_rate"] > 0
    assert data["engine"]["confirmed_ban_floor"] >= 70


# --- Ingestion GSI ------------------------------------------------------------
def test_gsi_rejects_bad_token(client):
    response = client.post("/gsi", json={**payload(), "auth": {"token": "faux"}})
    assert response.status_code == 401


def test_gsi_accepts_valid_token_and_updates_state(client, gsi_token):
    body = {**payload(), "auth": {"token": gsi_token}}
    assert client.post("/gsi", json=body).status_code == 200

    state = client.get("/api/live/state").json()["data"]
    assert state["connected"] is True
    assert state["state"]["map"]["name"] == "de_mirage"

    scoreboard = client.get("/api/live/scoreboard").json()["data"]
    assert scoreboard[0]["name"] == "TestPlayer"


def test_gsi_events_are_exposed(client, gsi_token):
    client.post("/gsi", json={**payload(kills=10), "auth": {"token": gsi_token}})
    client.post(
        "/gsi",
        json={**payload(kills=13, round_kills=3), "auth": {"token": gsi_token}},
    )
    data = client.get("/api/live/events").json()["data"]
    assert data["latest_sequence"] > 0
    assert any(event["type"] in {"kill", "headshot_kill"} for event in data["events"])


def test_gsi_rejects_malformed_body(client):
    response = client.post(
        "/gsi", content=b"pas du json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401


def test_live_reset(client, gsi_token):
    client.post("/gsi", json={**payload(), "auth": {"token": gsi_token}})
    assert client.post("/api/live/reset").json()["data"]["reset"] is True
    state = client.get("/api/live/state").json()["data"]
    assert state["state"] is None


def test_live_player_metrics_route(client, gsi_token):
    client.post("/gsi", json={**payload(), "auth": {"token": gsi_token}})
    body = client.get("/api/live/players/76561198000000001").json()
    assert body["success"] is True


# --- Persistance --------------------------------------------------------------
def test_tracked_players_empty_at_start(client):
    assert client.get("/api/players/tracked").json()["data"] == []


def test_favourite_and_notes_roundtrip(client):
    steamid = "76561198000000001"
    client.put(f"/api/players/{steamid}/favourite", json={"favourite": True})
    client.put(f"/api/players/{steamid}/notes", json={"notes": "a surveiller"})

    players = client.get("/api/players/tracked", params={"favourites_only": True}).json()
    assert players["data"][0]["steamid64"] == steamid
    assert players["data"][0]["notes"] == "a surveiller"


def test_delete_player(client):
    steamid = "76561198000000001"
    client.put(f"/api/players/{steamid}/favourite", json={"favourite": True})
    client.delete(f"/api/players/{steamid}")
    assert client.get("/api/players/tracked").json()["data"] == []


def test_matches_routes(client):
    assert client.get("/api/matches").json()["data"] == []
    current = client.get("/api/matches/current").json()["data"]
    assert current["match"] is None
    assert client.get("/api/matches/999").status_code == 404


def test_gsi_preview_route(client):
    data = client.get("/api/system/gsi/preview").json()["data"]
    assert "gamestate_integration" in data["filename"]
    assert data["endpoint"].endswith("/gsi")


# --- Identite de l'utilisateur ------------------------------------------------
def test_identity_reports_local_accounts(client):
    """La detection ne doit jamais lever, meme sans Steam installe."""
    data = client.get("/api/me/identity").json()["data"]
    assert "steamid64" in data
    assert isinstance(data["candidates"], list)
    assert data["confirmed"] is False


def test_set_and_clear_me(client):
    steamid = "76561198043717815"
    saved = client.put("/api/me", json={"steamid64": steamid}).json()["data"]
    assert saved["steamid64"] == steamid
    assert saved["confirmed"] is True

    identity = client.get("/api/me/identity").json()["data"]
    assert identity["steamid64"] == steamid
    assert identity["confirmed"] is True
    assert identity["source"] == "choix enregistre"

    cleared = client.delete("/api/me").json()["data"]
    assert cleared["cleared"] is True
    assert client.get("/api/me/identity").json()["data"]["confirmed"] is False


def test_set_me_rejects_malformed_steamid(client):
    assert client.put("/api/me", json={"steamid64": "123"}).status_code == 422
    assert client.put("/api/me", json={"steamid64": "abcdefghijklmnopq"}).status_code == 422


# --- Enregistrement de la cle Steam -------------------------------------------
def test_steam_key_is_applied_without_restart(client):
    """La cle doit devenir utilisable sans relancer l'application.

    ``verify: False`` evite un appel reel a Steam : la suite de tests ne doit
    dependre ni du reseau ni de la disponibilite de leurs serveurs.
    """
    body = client.post(
        "/api/system/steam-key", json={"key": "B" * 32, "verify": False}
    ).json()["data"]

    assert body["saved"] is True
    assert body["applied"] is True
    assert body["restart_required"] is False

    # Le client Steam a bien ete reconstruit dans le contexte en cours.
    status = client.get("/api/system/status").json()["data"]
    assert status["steam_api_configured"] is True


def test_steam_key_rejects_short_input(client):
    assert client.post("/api/system/steam-key", json={"key": "trop-court"}).status_code == 422


def test_steam_key_rejects_non_alphanumeric(client):
    response = client.post("/api/system/steam-key", json={"key": "!" * 32})
    assert response.status_code == 422


# --- Import de lobby ----------------------------------------------------------
STATUS_PASTE = """
 id   name             steamid
 2    "Alpha"          [U:1:123456789]
 3    "Bravo"          STEAM_1:1:44444
 4    "Charlie"        76561198043717815
"""


def test_extract_finds_all_formats(client):
    data = client.post(
        "/api/players/extract", json={"text": STATUS_PASTE, "analyse": False}
    ).json()["data"]
    assert data["found"] == 3
    assert all(len(p["steamid64"]) == 17 for p in data["players"])


def test_extract_rejects_empty_text(client):
    assert client.post("/api/players/extract", json={"text": "   "}).status_code == 422


def test_extract_rejects_oversized_paste(client):
    response = client.post("/api/players/extract", json={"text": "x" * 25_000})
    assert response.status_code == 422


def test_pasted_lobby_without_identifiers_explains_how(client):
    data = client.post(
        "/api/anticheat/lobby/paste", json={"text": "rien d'utile ici"}
    ).json()["data"]
    assert data["found"] == 0
    assert "status" in data["message"]


def test_pasted_lobby_extract_only_needs_no_steam_key(client):
    data = client.post(
        "/api/anticheat/lobby/paste", json={"text": STATUS_PASTE, "analyse": False}
    ).json()["data"]
    assert data["found"] == 3
    assert len(data["players"]) == 3


# --- Export -------------------------------------------------------------------
def test_csv_export_has_header_even_when_empty(client):
    response = client.get("/api/players/76561198000000001/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0].startswith("captured_at;")


# --- WebSocket ----------------------------------------------------------------
def test_websocket_sends_initial_snapshot(client):
    with client.websocket_connect("/ws/live") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "snapshot"
        assert "connected" in message["data"]
