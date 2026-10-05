"""Combined scope with explicit defending hero and attacker-response policies."""

from .sweeper_rules import RULES as SWEEPER_RULES
from .defending_heroes import DEFENDING_HERO_RULES


RULESET = "spatial-defending-heroes-kernel-v17"
SCOPE = "defending_heroes_extended_sector_without_pets_or_garrison"
RULES = {**SWEEPER_RULES, **DEFENDING_HERO_RULES}
