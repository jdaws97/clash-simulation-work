"""Combined rules for conditional attacking reinforcements and siege carriers."""

from .guardian_rules import RULES as GUARDIAN_RULES
from .reinforcements import REINFORCEMENT_RULES
from .siege_machines import SIEGE_RULES


RULESET = "spatial-attacking-reinforcement-siege-kernel-v24"
SCOPE = "attacking_reinforcement_siege_guardian_extended_sector_without_pets"
RULES = {**GUARDIAN_RULES, **REINFORCEMENT_RULES, **SIEGE_RULES}
