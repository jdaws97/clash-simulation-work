"""Hero equipment, pets and siege machines with wiki-verified numbers.

All figures were read from the Clash of Clans Fandom wiki tables on
2026-10-15 (pages for each item; patch histories checked so the values include
the July/August 2026 changes). Levels used are the TH16-18 maxima: common
equipment 18, epic 27, pets at their max level.

Only the effects that matter for base evaluation are modelled; each item lists
what is approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Equipment:
    name: str
    hp: float = 0.0  # passive hero HP increase
    dps: float = 0.0  # passive hero DPS increase
    regen: float = 0.0  # passive self healing per second
    active: dict = field(default_factory=dict)  # ability effect description
    passive: dict = field(default_factory=dict)  # always-on special effects


# key: equipment name -> stats at the level noted
EQUIPMENT = {
    # Archer Queen
    "Giant Arrow": Equipment("Giant Arrow", hp=581, dps=132, active={"arrow": 1500, "arrow_ad_mult": 2.0}),  # L18; 2x vs AD since May 2026
    "Action Figure": Equipment("Action Figure", hp=713, dps=135, regen=40, active={"giant_giant": 10}),  # L27; summons Giant Giant L10
    "Healer Puppet": Equipment("Healer Puppet", hp=968, regen=35, active={"healers": 3, "healer_level": 8}),  # L18
    "Magic Mirror": Equipment("Magic Mirror", hp=861, active={"clones": 2, "clone_hp": 3216, "clone_dps": 765, "clone_time": 30}),  # L27
    "Invisibility Vial": Equipment("Invisibility Vial", hp=700, active={"invis": 7.8, "shot_bonus": 1740}),  # L18
    # Barbarian King
    "Spiky Ball": Equipment("Spiky Ball", hp=3290, dps=222, active={"spiky": 3250, "targets": 8}),  # L27
    "Earthquake Boots": Equipment("Earthquake Boots", hp=2500, dps=102, active={"quake_pct": 0.40, "radius": 8}),  # L18
    "Giant Gauntlet": Equipment("Giant Gauntlet", dps=160, regen=40, active={"reduction": 0.60, "duration": 19}),  # L27
    # Grand Warden
    "Eternal Tome": Equipment("Eternal Tome", active={"tome": 8.2}),  # L18 invulnerability seconds
    "Life Gem": Equipment("Life Gem", hp=500, dps=75, passive={"aura_hp_pct": 1.2, "aura_hp_cap": 1200}),  # L18
    "Rage Gem": Equipment("Rage Gem", dps=88, passive={"aura_damage": 0.50}),  # L18
    "Healing Tome": Equipment("Healing Tome", hp=685, active={"heal_aura": 150, "duration": 20}),  # L18
    "Fireball": Equipment("Fireball", dps=101, active={"fireball": 4100, "radius": 6}),  # L27
    # Royal Champion
    "Rocket Spear": Equipment("Rocket Spear", hp=700, dps=168, active={"spear_bonus": 980, "attacks": 10}),  # L27
    "Electro Boots": Equipment("Electro Boots", hp=700, regen=45, active={"aura_dps": 200, "duration": 10}),  # L27
    "Seeking Shield": Equipment("Seeking Shield", hp=380, active={"shield": 2500, "targets": 4}),  # L18
    # Minion Prince
    "Dark Orb": Equipment("Dark Orb", hp=1140, dps=73, active={"orb_slow": 0.5}),  # L18
    "Meteor Staff": Equipment("Meteor Staff", hp=1381, dps=125, passive={"meteor": 850, "cooldown": 5}),  # L27
    # Dragon Duke
    "Rocket Backpack": Equipment("Rocket Backpack", hp=3200, dps=86, active={"dash": 2150}),  # L27
    "Fire Heart": Equipment("Fire Heart", hp=5600, dps=23, regen=150, passive={"death_damage": 3000}),  # L18
    "Revenge Deck": Equipment("Revenge Deck", hp=3200, passive={"counter": 225, "counter_heal": 60}),  # L27
    "Electro Fangs": Equipment("Electro Fangs", hp=2400, passive={"fang_damage": 400, "fang_targets": 4}),  # L18
    "Flame Blower": Equipment("Flame Blower", hp=3100, active={"cone": 2500}),  # L18
}


@dataclass(frozen=True)
class Pet:
    name: str
    hp: float
    dps: float
    range: float
    speed: float
    flying: bool
    effect: dict = field(default_factory=dict)


# Max-level pets (wiki, 2026-10-15). Speeds are display values / 8 tiles/s.
PETS = {
    "Phoenix": Pet("Phoenix", 4200, 250, 2.5, 2.0, True, {"revive": 8.5}),
    "Unicorn": Pet("Unicorn", 2325, 0, 2.5, 2.0, False, {"heal_hero": 75}),
    "Spirit Fox": Pet("Spirit Fox", 2800, 180, 2.5, 3.0, False, {"invis": 4.0, "cooldown": 10.0}),
    "Diggy": Pet("Diggy", 5750, 175, 0.8, 4.0, False, {"stun": 3.5, "cooldown": 10.0}),
    "Frosty": Pet("Frosty", 3800, 150, 3.5, 3.0, False, {}),
    "L.A.S.S.I": Pet("L.A.S.S.I", 4500, 400, 0.6, 4.0, False, {}),
    "Electro Owl": Pet("Electro Owl", 3000, 170, 6.0, 2.5, True, {"chain": 2}),
    "Angry Jelly": Pet("Angry Jelly", 2125, 193, 1.5, 2.0, False, {}),
}

# Siege machines (wiki, max level available at TH16-18 workshop).
SIEGES = {
    # 690 per log, x4 vs walls (2,760), logs stop after 4 buildings, 37 s
    # lifetime, 5,800 HP, HP decays 156/s, heads for the Town Hall.
    "Log Launcher": {"hp": 5800, "log": 690, "wall_mult": 4, "pierce": 4, "lifetime": 37.0, "interval": 3.0},
    # Bombs on the way to the Town Hall: 450 per bomb every 1.5 s, 5,500 HP.
    "Battle Blimp": {"hp": 5500, "bomb": 450, "interval": 1.5, "death_damage": 1200},
    # Flies to the Town Hall launching 5 barrels (minions/balloon/baby dragon).
    "Sky Wagon": {"hp": 4200, "barrels": 5, "interval": 8.0},
}

# Apprentice Warden life aura (wiki L4): +26% max HP within 7 tiles.
APPRENTICE_AURA = {"pct": 0.26, "radius": 7.0}

# Revive Spell (wiki): hero heal % by TH-max level (L3 at TH16, L5 at TH18).
REVIVE_PCT = {16: 0.70, 17: 0.75, 18: 0.80}


@dataclass
class HeroLoadout:
    hero: str
    equipment: tuple
    pet: str | None = None


# The most common loadouts in real ranked attacks (decoded from the user's own
# defense log, 2026-10-10..14, and the TrophyCoach/Blueprint army pages).
COMMON_LOADOUTS = {
    "Archer Queen": HeroLoadout("Archer Queen", ("Giant Arrow", "Action Figure"), "Unicorn"),
    "Barbarian King": HeroLoadout("Barbarian King", ("Spiky Ball", "Earthquake Boots"), "Spirit Fox"),
    "Grand Warden": HeroLoadout("Grand Warden", ("Eternal Tome", "Rage Gem"), "Electro Owl"),
    "Royal Champion": HeroLoadout("Royal Champion", ("Rocket Spear", "Electro Boots"), "Phoenix"),
    "Minion Prince": HeroLoadout("Minion Prince", ("Dark Orb", "Meteor Staff"), "Angry Jelly"),
    "Dragon Duke": HeroLoadout("Dragon Duke", ("Rocket Backpack", "Fire Heart"), "Phoenix"),
}
