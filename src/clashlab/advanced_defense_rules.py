"""Combined declared sector rules with advanced TH17/18 defensive weapons."""

from .advanced_defenses import ADVANCED_DEFENSE_RULES
from .giga_bombs import GIGA_BOMB_RULES
from .pet_rules import RULES as PET_RULES


RULESET = "spatial-advanced-th18-defenses-kernel-v26"
SCOPE = "advanced_th18_defenses_pets_siege_guardian_sector"
RULES = {**PET_RULES, **ADVANCED_DEFENSE_RULES, **GIGA_BOMB_RULES}
