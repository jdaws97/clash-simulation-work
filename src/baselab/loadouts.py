"""A hero's loadout: its equipment and pet.

The engine (src/baselab/engine/heroes.py) takes every equipment and pet
number from data/registry.json; this module only names what a hero brings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HeroLoadout:
    hero: str
    equipment: tuple
    pet: str | None = None
