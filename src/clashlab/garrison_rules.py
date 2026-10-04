"""Combined conditional combat scope with defending Clan Castle reserves."""

from .builder_rules import RULES as BUILDER_RULES
from .garrisons import GARRISON_RULES


RULESET = "spatial-defending-garrison-kernel-v20"
SCOPE = "defending_garrison_extended_sector_without_pets_or_siege"
RULES = {**BUILDER_RULES, **GARRISON_RULES}
