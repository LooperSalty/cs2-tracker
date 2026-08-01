"""Descripteurs des endpoints de la Steam Web API utilisés par l'application."""

from __future__ import annotations

from typing import Final

from cs2tracker.constants import STEAM_API_BASE

PLAYER_SUMMARIES: Final = f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v2/"
PLAYER_BANS: Final = f"{STEAM_API_BASE}/ISteamUser/GetPlayerBans/v1/"
FRIEND_LIST: Final = f"{STEAM_API_BASE}/ISteamUser/GetFriendList/v1/"
RESOLVE_VANITY: Final = f"{STEAM_API_BASE}/ISteamUser/ResolveVanityURL/v1/"

USER_STATS_FOR_GAME: Final = f"{STEAM_API_BASE}/ISteamUserStats/GetUserStatsForGame/v2/"
PLAYER_ACHIEVEMENTS: Final = f"{STEAM_API_BASE}/ISteamUserStats/GetPlayerAchievements/v1/"
SCHEMA_FOR_GAME: Final = f"{STEAM_API_BASE}/ISteamUserStats/GetSchemaForGame/v2/"
GLOBAL_STATS_FOR_GAME: Final = f"{STEAM_API_BASE}/ISteamUserStats/GetGlobalStatsForGame/v1/"
CURRENT_PLAYERS: Final = (
    f"{STEAM_API_BASE}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)

OWNED_GAMES: Final = f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/"
RECENTLY_PLAYED: Final = f"{STEAM_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v1/"
STEAM_LEVEL: Final = f"{STEAM_API_BASE}/IPlayerService/GetSteamLevel/v1/"
BADGES: Final = f"{STEAM_API_BASE}/IPlayerService/GetBadges/v1/"

CS2_SERVERS_STATUS: Final = (
    f"{STEAM_API_BASE}/ICSGOServers_730/GetGameServersStatus/v1/"
)

#: ``GetPlayerSummaries`` et ``GetPlayerBans`` acceptent des lots de 100 IDs.
MAX_STEAMIDS_PER_BATCH: Final = 100
