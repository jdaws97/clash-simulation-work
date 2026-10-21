"""The outcome of one battle (Battle.result)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Result:
    stars: int
    destruction: float
    th_destroyed: bool
    time: float
    destroyed_keys: dict
    surviving_defenses: list
    units_left: int
    log: list

    @property
    def score(self) -> float:
        """Attacker-side score: stars dominate, destruction breaks ties."""
        return self.stars + self.destruction / 100.0
