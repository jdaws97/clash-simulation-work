"""Combined combat scope with paid, persistent Rage and Haste fields."""

from .buffs import BUFF_RULES
from .engine_rules import RULES as EXTENDED_RULES


RULESET = "spatial-area-buffs-kernel-v14"
SCOPE = "area_buffs_extended_sector_without_pets_or_defending_troops"
RULES = {**EXTENDED_RULES, **BUFF_RULES}
