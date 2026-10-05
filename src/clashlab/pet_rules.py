"""Combined rules for explicitly assigned attacking hero pets."""

from .hero_pets import PET_RULES
from .siege_rules import RULES as SIEGE_RULES


RULESET = "spatial-paired-hero-pet-kernel-v25"
SCOPE = "paired_hero_pet_reinforcement_siege_guardian_extended_sector"
RULES = {**SIEGE_RULES, **PET_RULES}
