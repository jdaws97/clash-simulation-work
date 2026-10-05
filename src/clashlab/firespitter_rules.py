"""Combined conditional scope with oriented Firespitter shot streams."""

from .garrison_rules import RULES as GARRISON_RULES
from .firespitters import FIRESPITTER_RULES


RULESET = "spatial-firespitter-shot-stream-kernel-v21"
SCOPE = "firespitter_garrison_extended_sector_without_pets_or_siege"
RULES = {**GARRISON_RULES, **FIRESPITTER_RULES}
