"""Combined scope with controlled Skeleton reserves and finite Tornado motion."""

from .firespitter_rules import RULES as FIRESPITTER_RULES
from .skeleton_traps import SKELETON_RULES
from .tornado_traps import TORNADO_RULES


RULESET = "spatial-skeleton-tornado-trap-kernel-v22"
SCOPE = "skeleton_tornado_firespitter_extended_sector_without_pets_or_siege"
RULES = {**FIRESPITTER_RULES, **SKELETON_RULES, **TORNADO_RULES}
