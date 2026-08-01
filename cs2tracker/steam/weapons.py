"""Table de référence des armes CS2/CS:GO.

Les clés correspondent au suffixe des statistiques Steam :
``total_kills_<key>``, ``total_shots_<key>``, ``total_hits_<key>``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class WeaponMeta:
    key: str
    name: str
    category: str
    #: True si l'arme permet un tir à la tête « naturel » (pertinent anti-triche).
    headshot_relevant: bool
    #: Précision moyenne observée en population (utilisée comme baseline).
    baseline_accuracy: float


PISTOL: Final = "Pistolet"
SMG: Final = "SMG"
RIFLE: Final = "Fusil"
SNIPER: Final = "Sniper"
SHOTGUN: Final = "Fusil a pompe"
HEAVY: Final = "Mitrailleuse"
MELEE: Final = "Corps a corps"
GRENADE: Final = "Grenade"

WEAPONS: Final[tuple[WeaponMeta, ...]] = (
    # --- Pistolets -----------------------------------------------------------
    WeaponMeta("glock", "Glock-18", PISTOL, True, 0.21),
    WeaponMeta("hkp2000", "P2000", PISTOL, True, 0.24),
    WeaponMeta("usp_silencer", "USP-S", PISTOL, True, 0.26),
    WeaponMeta("p250", "P250", PISTOL, True, 0.25),
    WeaponMeta("fiveseven", "Five-SeveN", PISTOL, True, 0.26),
    WeaponMeta("tec9", "Tec-9", PISTOL, True, 0.21),
    WeaponMeta("cz75a", "CZ75-Auto", PISTOL, True, 0.22),
    WeaponMeta("elite", "Dual Berettas", PISTOL, True, 0.20),
    WeaponMeta("deagle", "Desert Eagle", PISTOL, True, 0.22),
    WeaponMeta("revolver", "R8 Revolver", PISTOL, True, 0.23),
    # --- SMG -----------------------------------------------------------------
    WeaponMeta("mac10", "MAC-10", SMG, True, 0.20),
    WeaponMeta("mp9", "MP9", SMG, True, 0.21),
    WeaponMeta("mp7", "MP7", SMG, True, 0.21),
    WeaponMeta("mp5sd", "MP5-SD", SMG, True, 0.22),
    WeaponMeta("ump45", "UMP-45", SMG, True, 0.22),
    WeaponMeta("p90", "P90", SMG, True, 0.20),
    WeaponMeta("bizon", "PP-Bizon", SMG, True, 0.19),
    # --- Fusils --------------------------------------------------------------
    WeaponMeta("ak47", "AK-47", RIFLE, True, 0.22),
    WeaponMeta("m4a1", "M4A4", RIFLE, True, 0.23),
    WeaponMeta("m4a1_silencer", "M4A1-S", RIFLE, True, 0.25),
    WeaponMeta("famas", "FAMAS", RIFLE, True, 0.21),
    WeaponMeta("galilar", "Galil AR", RIFLE, True, 0.20),
    WeaponMeta("aug", "AUG", RIFLE, True, 0.24),
    WeaponMeta("sg556", "SG 553", RIFLE, True, 0.24),
    # --- Snipers -------------------------------------------------------------
    WeaponMeta("awp", "AWP", SNIPER, False, 0.35),
    WeaponMeta("ssg08", "SSG 08", SNIPER, True, 0.33),
    WeaponMeta("scar20", "SCAR-20", SNIPER, False, 0.36),
    WeaponMeta("g3sg1", "G3SG1", SNIPER, False, 0.34),
    # --- Fusils a pompe ------------------------------------------------------
    WeaponMeta("nova", "Nova", SHOTGUN, False, 0.30),
    WeaponMeta("xm1014", "XM1014", SHOTGUN, False, 0.28),
    WeaponMeta("mag7", "MAG-7", SHOTGUN, False, 0.30),
    WeaponMeta("sawedoff", "Sawed-Off", SHOTGUN, False, 0.29),
    # --- Lourdes -------------------------------------------------------------
    WeaponMeta("m249", "M249", HEAVY, False, 0.18),
    WeaponMeta("negev", "Negev", HEAVY, False, 0.17),
    # --- Sans munitions comptabilisees --------------------------------------
    WeaponMeta("knife", "Couteau", MELEE, False, 0.0),
    WeaponMeta("taser", "Zeus x27", MELEE, False, 0.0),
    WeaponMeta("hegrenade", "Grenade HE", GRENADE, False, 0.0),
    WeaponMeta("molotov", "Cocktail Molotov", GRENADE, False, 0.0),
    WeaponMeta("decoy", "Leurre", GRENADE, False, 0.0),
    WeaponMeta("flashbang", "Flashbang", GRENADE, False, 0.0),
    WeaponMeta("smokegrenade", "Fumigene", GRENADE, False, 0.0),
)

WEAPON_BY_KEY: Final[dict[str, WeaponMeta]] = {w.key: w for w in WEAPONS}

#: Catégories dont la précision et le taux de HS sont analysables sérieusement.
AIM_RELEVANT_CATEGORIES: Final = frozenset({PISTOL, SMG, RIFLE})

#: Armes "spray" : une précision très élevée y est bien plus improbable.
SPRAY_WEAPON_KEYS: Final = frozenset(
    {"ak47", "m4a1", "m4a1_silencer", "famas", "galilar", "sg556", "aug",
     "mac10", "mp9", "mp7", "ump45", "p90", "bizon", "mp5sd", "m249", "negev"}
)

#: Armes "one-tap" : le HS y est structurellement plus fréquent.
ONE_TAP_WEAPON_KEYS: Final = frozenset({"deagle", "revolver", "ssg08", "usp_silencer"})


def weapon_display_name(key: str) -> str:
    meta = WEAPON_BY_KEY.get(key)
    return meta.name if meta else key.replace("_", " ").upper()


def weapon_category(key: str) -> str:
    meta = WEAPON_BY_KEY.get(key)
    return meta.category if meta else "Autre"


#: Correspondance des identifiants d'arme favorite renvoyés par ``last_match_favweapon_id``.
FAV_WEAPON_IDS: Final[dict[int, str]] = {
    1: "Desert Eagle", 2: "Dual Berettas", 3: "Five-SeveN", 4: "Glock-18",
    7: "AK-47", 8: "AUG", 9: "AWP", 10: "FAMAS", 11: "G3SG1",
    13: "Galil AR", 14: "M249", 16: "M4A4", 17: "MAC-10", 19: "P90",
    23: "MP5-SD", 24: "UMP-45", 25: "XM1014", 26: "PP-Bizon", 27: "MAG-7",
    28: "Negev", 29: "Sawed-Off", 30: "Tec-9", 31: "Zeus x27", 32: "P2000",
    33: "MP7", 34: "MP9", 35: "Nova", 36: "P250", 38: "SCAR-20",
    39: "SG 553", 40: "SSG 08", 42: "Couteau", 43: "Flashbang",
    44: "Grenade HE", 45: "Fumigene", 46: "Molotov", 47: "Leurre",
    48: "Incendiaire", 49: "C4", 60: "M4A1-S", 61: "USP-S", 63: "CZ75-Auto",
    64: "R8 Revolver",
}


def favourite_weapon_name(weapon_id: int) -> str:
    return FAV_WEAPON_IDS.get(weapon_id, f"Arme #{weapon_id}")
