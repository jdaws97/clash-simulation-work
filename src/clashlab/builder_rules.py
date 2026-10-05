"""Combined combat scope with travelling defensive Builder repair workers."""

from .spell_tower_rules import RULES as SPELL_TOWER_RULES
from .builder_huts import BUILDER_RULES


RULESET = "spatial-builder-hut-kernel-v19"
SCOPE = "builder_hut_extended_sector_without_pets_or_defending_troops"
RULES = {**SPELL_TOWER_RULES, **BUILDER_RULES}
