"""Table de référence des cartes CS2/CS:GO.

Clés Steam associées : ``total_wins_map_<key>`` et ``total_rounds_map_<key>``.
"""

from __future__ import annotations

from typing import Final

ACTIVE_DUTY: Final = "Active Duty"
RESERVE: Final = "Reserve"
HOSTAGE: Final = "Otages"
ARMS_RACE: Final = "Arms Race"
LEGACY: Final = "Legacy"

MAPS: Final[dict[str, tuple[str, str]]] = {
    "de_dust2": ("Dust II", ACTIVE_DUTY),
    "de_mirage": ("Mirage", ACTIVE_DUTY),
    "de_inferno": ("Inferno", ACTIVE_DUTY),
    "de_nuke": ("Nuke", ACTIVE_DUTY),
    "de_overpass": ("Overpass", ACTIVE_DUTY),
    "de_ancient": ("Ancient", ACTIVE_DUTY),
    "de_anubis": ("Anubis", ACTIVE_DUTY),
    "de_vertigo": ("Vertigo", ACTIVE_DUTY),
    "de_train": ("Train", ACTIVE_DUTY),
    "de_cache": ("Cache", RESERVE),
    "de_cbble": ("Cobblestone", RESERVE),
    "de_canals": ("Canals", RESERVE),
    "de_biome": ("Biome", RESERVE),
    "de_breach": ("Breach", RESERVE),
    "de_studio": ("Studio", RESERVE),
    "de_thera": ("Thera", RESERVE),
    "de_mills": ("Mills", RESERVE),
    "de_dogtown": ("Dogtown", RESERVE),
    "de_basalt": ("Basalt", RESERVE),
    "de_edin": ("Edin", RESERVE),
    "de_palais": ("Palais", RESERVE),
    "de_whistle": ("Whistle", RESERVE),
    "cs_office": ("Office", HOSTAGE),
    "cs_italy": ("Italy", HOSTAGE),
    "cs_agency": ("Agency", HOSTAGE),
    "cs_assault": ("Assault", HOSTAGE),
    "cs_militia": ("Militia", HOSTAGE),
    "ar_baggage": ("Baggage", ARMS_RACE),
    "ar_shoots": ("Shoots", ARMS_RACE),
    "ar_monastery": ("Monastery", ARMS_RACE),
    "ar_dizzy": ("Dizzy", ARMS_RACE),
    "de_lake": ("Lake", LEGACY),
    "de_bank": ("Bank", LEGACY),
    "de_safehouse": ("Safehouse", LEGACY),
    "de_sugarcane": ("Sugarcane", LEGACY),
    "de_stmarc": ("St. Marc", LEGACY),
    "de_shorttrain": ("Shortdust Train", LEGACY),
    "de_shortdust": ("Short Dust", LEGACY),
    "de_house": ("House", LEGACY),
    "de_shoots": ("Shoots", LEGACY),
    "de_boyard": ("Boyard", LEGACY),
}


def map_display_name(key: str) -> str:
    entry = MAPS.get(key)
    if entry:
        return entry[0]
    return key.replace("de_", "").replace("cs_", "").replace("ar_", "").replace("_", " ").title()


def map_pool(key: str) -> str:
    entry = MAPS.get(key)
    return entry[1] if entry else "Autre"


def normalize_map_name(raw: str) -> str:
    """Nettoie un nom de carte issu du GSI (``de_dust2`` ou ``workshop/…/x``)."""
    if not raw:
        return ""
    cleaned = raw.strip().lower()
    if "/" in cleaned:
        cleaned = cleaned.rsplit("/", 1)[-1]
    return cleaned
