"""Explicit attacking spells layered on complete battle-exhaustion rules."""

from .attack_spell_models import ATTACK_SPELL_RULES
from .termination_rules import RULES as TERMINATION_RULES


RULESET = "spatial-attack-spells-kernel-v29"
SCOPE = "attack_spells_battle_exhaustion_extended_hero_roster_sector"
RULES = {**TERMINATION_RULES, **ATTACK_SPELL_RULES}
