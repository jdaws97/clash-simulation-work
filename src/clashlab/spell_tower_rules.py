"""Combined scope with explicit reactive defensive spell field policies."""

from .defending_hero_rules import RULES as DEFENDING_HERO_RULES
from .spell_towers import SPELL_TOWER_RULES


RULESET = "spatial-reactive-spell-towers-kernel-v18"
SCOPE = "reactive_spell_towers_extended_sector_without_pets_or_garrison"
RULES = {**DEFENDING_HERO_RULES, **SPELL_TOWER_RULES}
