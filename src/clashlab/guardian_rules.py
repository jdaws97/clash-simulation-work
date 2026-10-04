"""Combined conditional engine with the weaponless TH18 Guardian lifecycle."""

from .guardians import GUARDIAN_RULES
from .trap_lifecycle_rules import RULES as TRAP_LIFECYCLE_RULES


RULESET = "spatial-th18-guardian-kernel-v23"
SCOPE = "guardian_skeleton_tornado_extended_sector_without_pets_or_siege"
RULES = {**TRAP_LIFECYCLE_RULES, **GUARDIAN_RULES}
