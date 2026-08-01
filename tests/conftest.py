"""Fixtures partagées : profils synthétiques et environnement isolé."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cs2tracker.core.models import (  # noqa: E402
    AccountOverview,
    BanStatus,
    Cs2Stats,
    MapStats,
    PlayerProfile,
    PlayerSummary,
    WeaponStats,
)
from cs2tracker.core.steamid import from_steamid64  # noqa: E402
from cs2tracker.core.utils import now_ts  # noqa: E402

DAY_SECONDS = 86_400

#: Sentinelle distinguant « argument non fourni » de « explicitement None ».
UNSET = object()


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Empêche les tests d'écrire dans le dossier de données réel."""
    monkeypatch.setenv("CS2T_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CS2T_STEAM_API_KEY", "test-key-0000000000000000000000")
    from cs2tracker import config

    config.set_settings(config.load_settings())
    yield
    config.set_settings(config.load_settings())


def make_summary(
    steamid: str = "76561198000000001",
    *,
    public: bool = True,
    age_days: float = 3_000,
) -> PlayerSummary:
    return PlayerSummary(
        steamid64=steamid,
        persona_name="TestPlayer",
        profile_url=f"https://steamcommunity.com/profiles/{steamid}",
        avatar="a.jpg",
        avatar_medium="m.jpg",
        avatar_full="f.jpg",
        visibility_state=3 if public else 1,
        profile_state=1,
        last_logoff=int(now_ts()),
        time_created=int(now_ts() - age_days * DAY_SECONDS),
        persona_state=1,
        country_code="FR",
        state_code=None,
        real_name=None,
        primary_clan_id=None,
        game_id=None,
        game_extra_info=None,
    )


def make_stats(
    steamid: str = "76561198000000001",
    *,
    kills: int = 50_000,
    deaths: int = 50_000,
    headshot_kills: int = 22_500,
    shots_fired: int = 951_000,
    shots_hit: int = 195_000,
    rounds: int = 80_000,
    hours: float = 1_800.0,
    damage: int = 5_800_000,
) -> Cs2Stats:
    """Joueur strictement moyen, avec des chiffres **mutuellement coherents**.

    Les valeurs par defaut respectent les identites du jeu : 20,5 % de precision,
    3,9 impacts par kill, 19 balles par kill, 0,62 kill/manche, 72,5 de degats
    par manche, 45 % de headshots. Toute incoherence ici produirait de faux
    signaux et fausserait les tests.
    """
    weapons = (
        WeaponStats("ak47", "AK-47", "Fusil", kills // 3, shots_fired // 3, shots_hit // 3),
        WeaponStats("m4a1", "M4A4", "Fusil", kills // 4, shots_fired // 4, shots_hit // 4),
        WeaponStats("awp", "AWP", "Sniper", kills // 8, shots_fired // 20, shots_hit // 12),
        WeaponStats("deagle", "Desert Eagle", "Pistolet", kills // 10, shots_fired // 15, shots_hit // 20),
    )
    maps = (
        MapStats("de_dust2", "Dust II", rounds // 3, rounds // 6),
        MapStats("de_mirage", "Mirage", rounds // 4, rounds // 8),
    )
    return Cs2Stats(
        steamid64=steamid,
        total_kills=kills,
        total_deaths=deaths,
        total_time_played=int(hours * 3600),
        total_planted_bombs=rounds // 20,
        total_defused_bombs=rounds // 60,
        total_wins=rounds // 2,
        total_damage_done=damage,
        total_money_earned=rounds * 3_000,
        total_rescued_hostages=10,
        total_kills_headshot=headshot_kills,
        total_shots_fired=shots_fired,
        total_shots_hit=shots_hit,
        total_rounds_played=rounds,
        total_matches_played=rounds // 25,
        total_matches_won=rounds // 50,
        total_mvps=int(rounds * 0.105),
        total_contribution_score=rounds * 2,
        total_wins_pistolround=rounds // 30,
        last_match_kills=20,
        last_match_deaths=15,
        last_match_mvps=3,
        last_match_damage=2_100,
        last_match_rounds=25,
        last_match_wins=13,
        last_match_max_players=10,
        last_match_money_spent=60_000,
        last_match_favweapon_id=7,
        weapons=weapons,
        maps=maps,
        raw={"total_kills": kills, "total_deaths": deaths},
    )


def make_bans(vac: int = 0, game: int = 0, days_since: int = 0) -> BanStatus:
    return BanStatus(
        steamid64="76561198000000001",
        community_banned=False,
        vac_banned=vac > 0,
        number_of_vac_bans=vac,
        days_since_last_ban=days_since,
        number_of_game_bans=game,
        economy_ban="none",
    )


def make_account(
    *, hours: float = 1_800.0, level: int = 25, friends: int = 80, games: int = 40
) -> AccountOverview:
    return AccountOverview(
        steam_level=level,
        games_owned=games,
        cs2_hours=hours,
        cs2_hours_2weeks=12.0,
        cs2_last_played=int(now_ts()),
        friends_count=friends,
        friends_oldest_since=int(now_ts() - 2_000 * DAY_SECONDS),
        badges_count=12,
        total_playtime_hours=hours * 2,
    )


def make_profile(
    *,
    stats: Cs2Stats | None | object = UNSET,
    bans: BanStatus | None | object = UNSET,
    account: AccountOverview | None | object = UNSET,
    summary: PlayerSummary | None | object = UNSET,
    steamid: str = "76561198000000001",
) -> PlayerProfile:
    """Construit un profil ; passer ``None`` rend explicitement la source absente."""
    identity = from_steamid64(steamid)
    return PlayerProfile(
        identity=identity.as_dict(),
        summary=make_summary(steamid) if summary is UNSET else summary,
        bans=make_bans() if bans is UNSET else bans,
        stats=make_stats(steamid) if stats is UNSET else stats,
        account=make_account() if account is UNSET else account,
        achievements_unlocked=90,
        achievements_total=167,
    )


@pytest.fixture
def average_profile() -> PlayerProfile:
    """Joueur parfaitement moyen : le moteur doit le classer CLEAN."""
    return make_profile()


@pytest.fixture
def blatant_profile() -> PlayerProfile:
    """Profil aux statistiques physiquement improbables sur tous les axes."""
    return make_profile(
        stats=make_stats(
            kills=60_000,
            deaths=12_000,
            headshot_kills=52_000,
            shots_fired=140_000,
            shots_hit=88_000,
            rounds=40_000,
            hours=180.0,
            damage=7_400_000,
        ),
        account=make_account(hours=180.0, level=2, friends=2, games=2),
        summary=make_summary(age_days=60),
    )
