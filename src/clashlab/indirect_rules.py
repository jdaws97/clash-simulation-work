"""Combined combat scope with separately timed Mortar and Eagle shells."""

from .buff_rules import RULES as BUFF_RULES
from .indirect_defenses import INDIRECT_RULES


RULESET = "spatial-indirect-defenses-kernel-v15"
SCOPE = "indirect_defenses_extended_sector_without_pets_or_defending_troops"
RULES = {**BUFF_RULES, **INDIRECT_RULES}
