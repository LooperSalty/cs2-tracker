"""Tests de conversion des identifiants Steam."""

from __future__ import annotations

import pytest

from cs2tracker.core.errors import InvalidSteamIdError
from cs2tracker.core.steamid import (
    from_account_id,
    from_steamid64,
    is_valid_steamid64,
    parse,
)

KNOWN_STEAMID64 = 76561198043717815
KNOWN_ACCOUNT_ID = KNOWN_STEAMID64 - 76561197960265728


def test_steamid64_roundtrip():
    identity = from_steamid64(KNOWN_STEAMID64)
    assert identity.account_id == KNOWN_ACCOUNT_ID
    assert from_account_id(identity.account_id).steamid64 == KNOWN_STEAMID64


def test_steamid2_format():
    identity = from_steamid64(KNOWN_STEAMID64)
    parity = KNOWN_ACCOUNT_ID & 1
    half = KNOWN_ACCOUNT_ID >> 1
    assert identity.steamid2 == f"STEAM_1:{parity}:{half}"


def test_steamid3_format():
    identity = from_steamid64(KNOWN_STEAMID64)
    assert identity.steamid3 == f"[U:1:{KNOWN_ACCOUNT_ID}]"


@pytest.mark.parametrize(
    "raw",
    [
        str(KNOWN_STEAMID64),
        f"https://steamcommunity.com/profiles/{KNOWN_STEAMID64}",
        f"[U:1:{KNOWN_ACCOUNT_ID}]",
        f"U:1:{KNOWN_ACCOUNT_ID}",
        f"STEAM_1:{KNOWN_ACCOUNT_ID & 1}:{KNOWN_ACCOUNT_ID >> 1}",
        f"  {KNOWN_STEAMID64}  ",
    ],
)
def test_parse_resolves_all_id_formats(raw):
    request = parse(raw)
    assert request.identity is not None
    assert request.identity.steamid64 == KNOWN_STEAMID64


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://steamcommunity.com/id/gabelogannewell", "gabelogannewell"),
        ("gabelogannewell", "gabelogannewell"),
        ("steamcommunity.com/id/mon-pseudo_42", "mon-pseudo_42"),
    ],
)
def test_parse_detects_vanity(raw, expected):
    request = parse(raw)
    assert request.identity is None
    assert request.vanity == expected
    assert request.needs_remote_lookup


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "STEAM_9:9:9"])
def test_parse_rejects_garbage(raw):
    with pytest.raises(InvalidSteamIdError):
        parse(raw)


def test_out_of_range_steamid64_rejected():
    with pytest.raises(InvalidSteamIdError):
        from_steamid64(123)
    assert not is_valid_steamid64(123)


def test_identity_dict_is_serialisable():
    payload = from_steamid64(KNOWN_STEAMID64).as_dict()
    assert payload["steamid64"] == str(KNOWN_STEAMID64)
    assert payload["profile_url"].endswith(str(KNOWN_STEAMID64))
