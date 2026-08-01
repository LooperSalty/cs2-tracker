"""Tests du pipeline Game State Integration : parsing, diff, agrégation."""

from __future__ import annotations

import pytest

from cs2tracker.gsi.events import EventType, diff_states
from cs2tracker.gsi.installer import render_config
from cs2tracker.gsi.parser import extract_token, parse_payload
from cs2tracker.gsi.state import LiveStateStore
from cs2tracker.gsi.tracker import MatchTracker

TOKEN = "jeton-de-test"


def payload(
    *,
    round_number: int = 5,
    round_phase: str = "live",
    kills: int = 10,
    deaths: int = 6,
    round_kills: int = 1,
    round_hs: int = 0,
    health: int = 100,
    bomb: str = "carried",
) -> dict:
    return {
        "provider": {
            "name": "Counter-Strike: Global Offensive",
            "appid": 730,
            "version": 14000,
            "steamid": "76561198000000001",
            "timestamp": 1_700_000_000,
        },
        "map": {
            "mode": "competitive",
            "name": "de_mirage",
            "phase": "live",
            "round": round_number,
            "team_ct": {"score": 7, "consecutive_round_losses": 1, "timeouts_remaining": 1},
            "team_t": {"score": 4, "consecutive_round_losses": 0, "timeouts_remaining": 1},
            "round_wins": {"1": "ct_win_elimination"},
        },
        "round": {"phase": round_phase, "bomb": "", "win_team": ""},
        "player": {
            "steamid": "76561198000000001",
            "name": "TestPlayer",
            "clan": "",
            "team": "CT",
            "activity": "playing",
            "observer_slot": 0,
            "state": {
                "health": health,
                "armor": 100,
                "helmet": True,
                "defusekit": True,
                "flashed": 0,
                "smoked": 0,
                "burning": 0,
                "money": 3_500,
                "round_kills": round_kills,
                "round_killhs": round_hs,
                "round_totaldmg": 145,
                "equip_value": 4_700,
            },
            "match_stats": {
                "kills": kills,
                "assists": 3,
                "deaths": deaths,
                "mvps": 2,
                "score": 30,
            },
            "weapons": {
                "weapon_0": {
                    "name": "weapon_knife",
                    "paintkit": "default",
                    "type": "Knife",
                    "state": "holstered",
                },
                "weapon_1": {
                    "name": "weapon_ak47",
                    "paintkit": "cu_ak47",
                    "type": "Rifle",
                    "ammo_clip": 25,
                    "ammo_clip_max": 30,
                    "ammo_reserve": 90,
                    "state": "active",
                },
            },
            "position": "120.50, -430.25, 64.00",
            "forward": "0.50, -0.80, 0.10",
        },
        "bomb": {"state": bomb, "countdown": "0.0", "player": ""},
        "phase_countdowns": {"phase": round_phase, "phase_ends_in": "42.3"},
        "auth": {"token": TOKEN},
    }


# --- Parsing ------------------------------------------------------------------
def test_parse_full_payload():
    state = parse_payload(payload())
    assert state.provider is not None
    assert state.provider.appid == 730
    assert state.map_state is not None
    assert state.map_state.name == "de_mirage"
    assert state.map_state.team_ct.score == 7
    assert state.player is not None
    assert state.player.state.health == 100
    assert state.player.match_stats.kills == 10
    assert state.player.active_weapon.clean_name == "ak47"
    assert state.player.position.x == pytest.approx(120.5)


def test_parse_tolerates_missing_blocks():
    state = parse_payload({"provider": {"appid": 730}})
    assert state.map_state is None
    assert state.player is None
    assert state.allplayers == ()
    assert state.as_dict()["map"] is None


def test_parse_empty_payload_is_safe():
    state = parse_payload({})
    assert state.provider is None
    assert not state.in_match


def test_extract_token():
    assert extract_token(payload()) == TOKEN
    assert extract_token({}) == ""


def test_workshop_map_name_is_normalised():
    raw = payload()
    raw["map"]["name"] = "workshop/1234567/de_custom"
    state = parse_payload(raw)
    assert state.map_state.name == "de_custom"


# --- Diff / événements --------------------------------------------------------
def test_first_state_emits_connection_event():
    events = diff_states(None, parse_payload(payload()))
    assert len(events) == 1
    assert events[0].type is EventType.CONNECTION


def test_kill_is_detected():
    before = parse_payload(payload(kills=10, round_kills=1))
    after = parse_payload(payload(kills=12, round_kills=3, round_hs=1))
    events = diff_states(before, after)
    kill_events = [e for e in events if e.type in {EventType.KILL, EventType.HEADSHOT_KILL}]
    assert kill_events
    assert kill_events[0].detail["count"] == 2


def test_headshot_kill_is_distinguished():
    before = parse_payload(payload(kills=10, round_kills=1, round_hs=0))
    after = parse_payload(payload(kills=11, round_kills=2, round_hs=1))
    events = diff_states(before, after)
    assert any(e.type is EventType.HEADSHOT_KILL for e in events)


def test_multi_kill_event():
    before = parse_payload(payload(kills=10, round_kills=2))
    after = parse_payload(payload(kills=11, round_kills=3))
    events = diff_states(before, after)
    assert any(e.type is EventType.MULTI_KILL for e in events)


def test_death_is_detected():
    before = parse_payload(payload(deaths=6))
    after = parse_payload(payload(deaths=7))
    assert any(e.type is EventType.DEATH for e in diff_states(before, after))


def test_damage_taken_is_detected():
    before = parse_payload(payload(health=100))
    after = parse_payload(payload(health=45))
    events = diff_states(before, after)
    damage = [e for e in events if e.type is EventType.DAMAGE_TAKEN]
    assert damage and damage[0].detail["amount"] == 55


def test_low_health_event_below_threshold():
    before = parse_payload(payload(health=100))
    after = parse_payload(payload(health=15))
    assert any(e.type is EventType.LOW_HEALTH for e in diff_states(before, after))


def test_round_phase_transitions():
    live = parse_payload(payload(round_phase="live"))
    over = parse_payload(payload(round_phase="over"))
    assert any(e.type is EventType.ROUND_END for e in diff_states(live, over))
    freeze = parse_payload(payload(round_phase="freezetime"))
    assert any(e.type is EventType.ROUND_FREEZE for e in diff_states(over, freeze))


def test_bomb_planted_event():
    before = parse_payload(payload(bomb="carried"))
    after = parse_payload(payload(bomb="planted"))
    assert any(e.type is EventType.BOMB_PLANTED for e in diff_states(before, after))


def test_map_change_event():
    before = parse_payload(payload())
    changed = payload()
    changed["map"]["name"] = "de_nuke"
    assert any(e.type is EventType.MAP_CHANGE for e in diff_states(before, parse_payload(changed)))


# --- Agrégation ---------------------------------------------------------------
def test_tracker_accumulates_rounds():
    tracker = MatchTracker()
    previous = None
    for round_number in range(1, 8):
        for phase in ("freezetime", "live"):
            state = parse_payload(
                payload(round_number=round_number, round_phase=phase, round_kills=2, round_hs=1)
            )
            tracker.ingest(state, diff_states(previous, state))
            previous = state

    metrics = tracker.metrics_for("76561198000000001")
    assert metrics is not None
    assert metrics.rounds_observed >= 5
    assert metrics.has_enough_rounds
    assert 0.0 <= metrics.live_headshot_rate <= 1.0


def test_tracker_resets_on_map_change():
    tracker = MatchTracker()
    first = parse_payload(payload())
    tracker.ingest(first, diff_states(None, first))

    changed = payload()
    changed["map"]["name"] = "de_nuke"
    second = parse_payload(changed)
    tracker.ingest(second, diff_states(first, second))
    assert tracker.map_name == "de_nuke"


# --- Store --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_store_update_and_snapshot():
    store = LiveStateStore()
    events = await store.update(parse_payload(payload()))
    assert events
    snapshot = await store.snapshot()
    assert snapshot.connected
    assert snapshot.payload_count == 1
    assert snapshot.state is not None


@pytest.mark.asyncio
async def test_live_store_event_sequence():
    store = LiveStateStore()
    await store.update(parse_payload(payload(kills=10)))
    await store.update(parse_payload(payload(kills=13, round_kills=3)))
    latest, events = await store.recent_events(since=0)
    assert latest >= len(events) >= 1
    _, none_left = await store.recent_events(since=latest)
    assert none_left == []


@pytest.mark.asyncio
async def test_live_store_scoreboard():
    store = LiveStateStore()
    await store.update(parse_payload(payload()))
    rows = await store.scoreboard()
    assert len(rows) == 1
    assert rows[0]["name"] == "TestPlayer"


@pytest.mark.asyncio
async def test_live_store_reset():
    store = LiveStateStore()
    await store.update(parse_payload(payload()))
    await store.reset()
    snapshot = await store.snapshot()
    assert snapshot.payload_count == 0
    assert snapshot.state is None


# --- Configuration ------------------------------------------------------------
def test_render_config_contains_endpoint_and_token():
    content = render_config("http://127.0.0.1:8642/gsi", TOKEN)
    assert '"uri"       "http://127.0.0.1:8642/gsi"' in content
    assert f'"token" "{TOKEN}"' in content
    assert '"player_state"  "1"' in content
    assert content.count("{") == content.count("}")
