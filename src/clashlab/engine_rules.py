"""Combined, explicitly declared Valkyrie and hidden-defense engine scope."""

from .teslas import RULES as TESLA_RULES
from .valkyries import RULES as VALKYRIE_RULES


RULESET = "spatial-valkyrie-tesla-hit-status-kernel-v13"
SCOPE = "valkyrie_tesla_hit_status_traps_heroes_sector_without_pets_or_defending_troops"
RULES = {**TESLA_RULES, **VALKYRIE_RULES}
