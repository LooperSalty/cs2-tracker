"""Extraction des variables d'entrée des détecteurs.

On isole ici tout le travail de préparation (lissage bayésien, calcul
d'ancienneté, agrégats par catégorie d'arme) afin que chaque détecteur reste
une fonction courte et lisible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from cs2tracker.anticheat import baselines
from cs2tracker.core.models import PlayerProfile
from cs2tracker.core.utils import (
    now_ts,
    safe_div,
    sample_confidence,
    shrunk_rate,
)
from cs2tracker.gsi.tracker import LivePlayerMetrics
from cs2tracker.steam.weapons import (
    AIM_RELEVANT_CATEGORIES,
    SPRAY_WEAPON_KEYS,
    WEAPON_BY_KEY,
)

SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True, slots=True)
class CategoryAim:
    """Agrégat de visée pour une catégorie d'armes."""

    category: str
    kills: int
    shots: int
    hits: int
    accuracy: float

    @property
    def has_sample(self) -> bool:
        return self.shots >= 2_000 and self.kills >= 100


@dataclass(frozen=True, slots=True)
class PlayerFeatures:
    """Toutes les variables dérivées nécessaires aux détecteurs."""

    steamid: str
    name: str

    # --- disponibilité des sources ------------------------------------------
    has_stats: bool
    has_live: bool
    profile_public: bool

    # --- volumétrie ----------------------------------------------------------
    total_kills: int
    total_deaths: int
    total_rounds: int
    total_shots: int
    total_hits: int
    hours_played: float
    account_age_days: float

    # --- taux lissés ---------------------------------------------------------
    headshot_rate: float
    accuracy: float
    kd_ratio: float
    kills_per_round: float
    damage_per_round: float
    damage_per_kill: float
    kills_per_hour: float
    hits_per_kill: float
    shots_per_kill: float
    mvp_rate: float
    round_win_rate: float

    # --- confiances ----------------------------------------------------------
    kill_confidence: float
    shot_confidence: float
    round_confidence: float

    # --- armes ---------------------------------------------------------------
    category_aim: Mapping[str, CategoryAim] = field(default_factory=dict)
    spray_accuracy: float = 0.0
    spray_shots: int = 0
    weapon_headshot_rates: Mapping[str, float] = field(default_factory=dict)

    # --- compte --------------------------------------------------------------
    steam_level: int = 0
    games_owned: int = 0
    friends_count: int = 0
    badges_count: int = 0
    cs2_share_of_playtime: float = 0.0
    achievements_rate: float = 0.0

    # --- sanctions -----------------------------------------------------------
    vac_bans: int = 0
    game_bans: int = 0
    days_since_last_ban: int = 0
    community_banned: bool = False
    economy_banned: bool = False

    # --- temps réel ----------------------------------------------------------
    live_rounds: int = 0
    live_headshot_rate: float = 0.0
    live_adr: float = 0.0
    live_adr_variability: float = 0.0
    live_kills_per_round: float = 0.0
    live_multi_kill_rate: float = 0.0
    live_kill_interval_stdev: float = 0.0
    live_fast_chain_rate: float = 0.0
    live_utility_per_round: float = 0.0
    live_survival_rate: float = 0.0
    live_kill_intervals: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "steamid": self.steamid,
            "name": self.name,
            "sources": {
                "lifetime_stats": self.has_stats,
                "live_gsi": self.has_live,
                "public_profile": self.profile_public,
            },
            "volume": {
                "kills": self.total_kills,
                "deaths": self.total_deaths,
                "rounds": self.total_rounds,
                "shots_fired": self.total_shots,
                "hours": round(self.hours_played, 1),
                "account_age_days": round(self.account_age_days, 1),
            },
            "rates": {
                "headshot_rate": round(self.headshot_rate, 4),
                "accuracy": round(self.accuracy, 4),
                "kd": round(self.kd_ratio, 3),
                "kills_per_round": round(self.kills_per_round, 3),
                "damage_per_round": round(self.damage_per_round, 1),
                "kills_per_hour": round(self.kills_per_hour, 2),
                "hits_per_kill": round(self.hits_per_kill, 2),
                "mvp_rate": round(self.mvp_rate, 4),
            },
            "confidence": {
                "kills": round(self.kill_confidence, 3),
                "shots": round(self.shot_confidence, 3),
                "rounds": round(self.round_confidence, 3),
            },
            "live": {
                "rounds": self.live_rounds,
                "headshot_rate": round(self.live_headshot_rate, 3),
                "adr": round(self.live_adr, 1),
                "adr_variability": round(self.live_adr_variability, 3),
                "multi_kill_rate": round(self.live_multi_kill_rate, 3),
                "kill_interval_stdev": round(self.live_kill_interval_stdev, 3),
            },
            "bans": {
                "vac": self.vac_bans,
                "game": self.game_bans,
                "days_since_last": self.days_since_last_ban,
            },
        }


def _category_aim(stats_weapons: Any) -> dict[str, CategoryAim]:
    buckets: dict[str, list[int]] = {}
    for weapon in stats_weapons:
        if weapon.category not in AIM_RELEVANT_CATEGORIES and weapon.category not in {
            "Sniper",
            "Fusil a pompe",
            "Mitrailleuse",
        }:
            continue
        bucket = buckets.setdefault(weapon.category, [0, 0, 0])
        bucket[0] += weapon.kills
        bucket[1] += weapon.shots_fired
        bucket[2] += weapon.shots_hit
    return {
        category: CategoryAim(
            category=category,
            kills=values[0],
            shots=values[1],
            hits=values[2],
            accuracy=safe_div(values[2], values[1]),
        )
        for category, values in buckets.items()
    }


def _spray_aggregate(stats_weapons: Any) -> tuple[float, int]:
    shots = sum(w.shots_fired for w in stats_weapons if w.key in SPRAY_WEAPON_KEYS)
    hits = sum(w.shots_hit for w in stats_weapons if w.key in SPRAY_WEAPON_KEYS)
    return safe_div(hits, shots), shots


def _weapon_headshot_rates(raw: Mapping[str, int]) -> dict[str, float]:
    """Le schéma Steam ne détaille pas les HS par arme : on approxime.

    À défaut de ``total_kills_headshot_<arme>``, on ne renvoie que les armes
    pour lesquelles Steam expose effectivement une statistique dédiée.
    """
    rates: dict[str, float] = {}
    for key in WEAPON_BY_KEY:
        headshots = raw.get(f"total_kills_headshot_{key}")
        kills = raw.get(f"total_kills_{key}")
        if headshots and kills:
            rates[key] = safe_div(headshots, kills)
    return rates


def _account_age_days(profile: PlayerProfile) -> float:
    if profile.summary and profile.summary.time_created:
        return max(0.0, (now_ts() - profile.summary.time_created) / SECONDS_PER_DAY)
    return 0.0


def build_features(
    profile: PlayerProfile, live: LivePlayerMetrics | None = None
) -> PlayerFeatures:
    """Assemble les variables d'analyse depuis le profil Steam et le live."""
    stats = profile.stats
    account = profile.account
    bans = profile.bans
    summary = profile.summary

    steamid = str(profile.identity.get("steamid64", ""))
    name = summary.persona_name if summary else (live.name if live else steamid)

    total_kills = stats.total_kills if stats else 0
    total_shots = stats.total_shots_fired if stats else 0
    total_rounds = stats.total_rounds_played if stats else 0

    kill_confidence = sample_confidence(
        total_kills, baselines.PRIOR_WEIGHT_KILLS * 20, 100
    )
    shot_confidence = sample_confidence(
        total_shots, baselines.PRIOR_WEIGHT_SHOTS * 15, 3_000
    )
    round_confidence = sample_confidence(
        total_rounds, baselines.PRIOR_WEIGHT_ROUNDS * 40, 100
    )

    # Les taux sont lissés vers la moyenne de population : un petit échantillon
    # ne peut pas produire un score extrême.
    headshot_rate = shrunk_rate(
        stats.total_kills_headshot if stats else 0,
        total_kills,
        baselines.HEADSHOT_RATE.mean,
        baselines.PRIOR_WEIGHT_KILLS,
    )
    accuracy = shrunk_rate(
        stats.total_shots_hit if stats else 0,
        total_shots,
        baselines.ACCURACY.mean,
        baselines.PRIOR_WEIGHT_SHOTS,
    )

    spray_accuracy, spray_shots = (
        _spray_aggregate(stats.weapons) if stats else (0.0, 0)
    )

    return PlayerFeatures(
        steamid=steamid,
        name=name,
        has_stats=stats is not None and stats.total_rounds_played > 0,
        has_live=live is not None and live.rounds_observed > 0,
        profile_public=bool(summary and summary.is_public),
        total_kills=total_kills,
        total_deaths=stats.total_deaths if stats else 0,
        total_rounds=total_rounds,
        total_shots=total_shots,
        total_hits=stats.total_shots_hit if stats else 0,
        hours_played=(
            account.cs2_hours
            if account and account.cs2_hours > 0
            else (stats.hours_played if stats else 0.0)
        ),
        account_age_days=_account_age_days(profile),
        headshot_rate=headshot_rate,
        accuracy=accuracy,
        kd_ratio=stats.kd_ratio if stats else 0.0,
        kills_per_round=stats.kills_per_round if stats else 0.0,
        damage_per_round=stats.damage_per_round if stats else 0.0,
        damage_per_kill=stats.damage_per_kill if stats else 0.0,
        kills_per_hour=stats.kills_per_hour if stats else 0.0,
        hits_per_kill=stats.hits_per_kill if stats else 0.0,
        shots_per_kill=stats.shots_per_kill if stats else 0.0,
        mvp_rate=stats.mvp_rate if stats else 0.0,
        round_win_rate=stats.round_win_rate if stats else 0.0,
        kill_confidence=kill_confidence,
        shot_confidence=shot_confidence,
        round_confidence=round_confidence,
        category_aim=_category_aim(stats.weapons) if stats else {},
        spray_accuracy=spray_accuracy,
        spray_shots=spray_shots,
        weapon_headshot_rates=_weapon_headshot_rates(stats.raw) if stats else {},
        steam_level=account.steam_level if account else 0,
        games_owned=account.games_owned if account else 0,
        friends_count=account.friends_count if account else 0,
        badges_count=account.badges_count if account else 0,
        cs2_share_of_playtime=account.cs2_share_of_playtime if account else 0.0,
        achievements_rate=profile.achievement_rate,
        vac_bans=bans.number_of_vac_bans if bans else 0,
        game_bans=bans.number_of_game_bans if bans else 0,
        days_since_last_ban=bans.days_since_last_ban if bans else 0,
        community_banned=bool(bans and bans.community_banned),
        economy_banned=bool(
            bans and bans.economy_ban and bans.economy_ban.lower() not in {"none", ""}
        ),
        live_rounds=live.rounds_observed if live else 0,
        live_headshot_rate=live.live_headshot_rate if live else 0.0,
        live_adr=live.adr if live else 0.0,
        live_adr_variability=live.adr_variability if live else 0.0,
        live_kills_per_round=live.kills_per_round if live else 0.0,
        live_multi_kill_rate=live.multi_kill_rate if live else 0.0,
        live_kill_interval_stdev=live.kill_interval_stdev if live else 0.0,
        live_fast_chain_rate=live.fast_chain_rate if live else 0.0,
        live_utility_per_round=live.utility_per_round if live else 0.0,
        live_survival_rate=live.survival_rate if live else 0.0,
        live_kill_intervals=len(live.all_kill_intervals) if live else 0,
    )
