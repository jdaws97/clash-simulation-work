"""Combined combat scope with finite Air Sweeper displacement."""

from .indirect_rules import RULES as INDIRECT_RULES
from .sweepers import SWEEPER_RULES


RULESET = "spatial-air-sweeper-kernel-v16"
SCOPE = "air_sweeper_extended_sector_without_pets_or_defending_troops"
RULES = {**INDIRECT_RULES, **SWEEPER_RULES}
