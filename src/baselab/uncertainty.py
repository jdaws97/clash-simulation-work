"""Paired uncertainty for expected ranked defender trophies.

Bootstrap draws resample seed replicates within fixed army/TH/modifier/skill/
scouting strata, preserving each stratum's mixture weight and pairing draws
across layouts. P(A > B) counts numerical ties as half, not a posterior probability.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .evaluate import defender_trophies, scouted, skill, summarise

# docs/GAP_ANALYSIS.md:50-53 calls for a minimum meaningful gain. This is an
# explicit reporting tolerance, not a threshold fitted to real-game defenses.
PRACTICAL_TIE_TROPHIES = 0.25
# review5 #6: roundoff in scouting sums must not decide trophy ties.
NUMERICAL_TIE_TROPHIES = 1e-9


def _tie_difference(value):
    return 0.0 if abs(value) <= NUMERICAL_TIE_TROPHIES else value


def practical_tie(interval: tuple[float, float]) -> bool:
    """True when the 95% interval intersects [-0.25, +0.25] trophies."""
    lower, upper = interval
    if lower > upper:
        raise ValueError("confidence interval bounds must be ordered")
    return (
        lower <= PRACTICAL_TIE_TROPHIES + NUMERICAL_TIE_TROPHIES
        and upper >= -PRACTICAL_TIE_TROPHIES - NUMERICAL_TIE_TROPHIES
    )


@dataclass(frozen=True)
class PairedComparison:
    difference: float
    ci95: tuple[float, float]
    probability_a_better: float
    groups: int
    bootstrap_samples: int
    seed: int

    @property
    def practical_tie(self) -> bool:
        return practical_tie(self.ci95)

    def summary(self) -> str:
        verdict = "practical tie" if self.practical_tie else "outside practical tie"
        return (
            f"delta trophies {self.difference:+.2f}, "
            f"95% CI [{self.ci95[0]:+.2f}, {self.ci95[1]:+.2f}], "
            f"bootstrap P(A>B) {self.probability_a_better:.1%}; {verdict}"
        )


def group_trophies(scenarios, results, *, scout=None, with_strata=False):
    """Normalized weights and trophies, in scouting-group insertion order."""
    if len(scenarios) != len(results) or not scenarios:
        raise ValueError("one result is required for every scenario")
    if any(not math.isfinite(sc.weight) or sc.weight < 0 for sc in scenarios):
        raise ValueError("scenario weights must be finite and nonnegative")
    groups = {}
    # evaluate.py:650-686: overlapping side combinations are not independent.
    for sc, result, weight in scouted(scenarios, results, scout):
        key = (sc.army, sc.town_hall, sc.modifier, sc.group, sc.full_scout)
        # evaluate._assign_skill: quantiles are fixed strata, seeds are replicates.
        stratum = (sc.army, sc.town_hall, sc.modifier, skill(sc.seed), sc.full_scout)
        row = groups.setdefault(key, [0.0, 0.0, stratum])
        row[0] += weight
        row[1] += weight * defender_trophies(int(result[0]), result[1])
    rows = [row for row in groups.values() if row[0] > 0]
    total = sum(row[0] for row in rows)
    if total <= 0:
        raise ValueError("scenario weights must have a positive total")
    weights = [row[0] / total for row in rows]
    trophies = [row[1] / row[0] for row in rows]
    if with_strata:
        return weights, trophies, [row[2] for row in rows]
    return weights, trophies


def _percentile(ordered, fraction):
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def paired_comparison(
    scenarios,
    results_a,
    results_b,
    *,
    bootstrap_samples=10_000,
    seed=0,
    scout=None,
) -> PairedComparison:
    """Compare A minus B from results on the exact same ordered scenarios.

    Each replicate resamples scouting groups (seed replicates) within each
    fixed army, TH, modifier, skill quantile and scouting rule. Original group
    weights are normalized within the stratum, then multiplied by its fixed
    mixture weight. Sides and techniques stay together. The point
    estimate follows evaluate.summarise(), including its scouting rules.
    These intervals describe scenario sampling, not real-game model accuracy.
    """
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    scenarios = list(scenarios)
    results_a, results_b = list(results_a), list(results_b)
    weights, trophies_a, strata = group_trophies(
        scenarios, results_a, scout=scout, with_strata=True
    )
    _, trophies_b = group_trophies(scenarios, results_b, scout=scout)
    difference = _tie_difference(
        summarise(scenarios, results_a, scout).ranked_trophies
        - summarise(scenarios, results_b, scout).ranked_trophies
    )
    deltas = [_tie_difference(a - b) for a, b in zip(trophies_a, trophies_b)]
    weighted = [w * d for w, d in zip(weights, deltas)]
    rng = random.Random(seed)
    count = len(weights)
    fixed = {}
    for index, stratum in enumerate(strata):
        fixed.setdefault(stratum, []).append(index)
    strata_weights = [
        (indices, math.fsum(weights[i] for i in indices)) for indices in fixed.values()
    ]
    draws = []
    # review5 #5: strata keep their prescribed mixture mass. RNG order is
    # first-seen stratum, then one index draw per seed replicate in that stratum.
    for _ in range(bootstrap_samples):
        contributions = []
        for indices, mass in strata_weights:
            selected = [indices[rng.randrange(len(indices))] for _ in indices]
            numerator = math.fsum(weighted[i] for i in selected)
            denominator = math.fsum(weights[i] for i in selected)
            contributions.append(mass * numerator / denominator)
        draws.append(_tie_difference(math.fsum(contributions)))
    draws.sort()
    return PairedComparison(
        difference=difference,
        ci95=(_percentile(draws, 0.025), _percentile(draws, 0.975)),
        probability_a_better=sum(0.5 if d == 0.0 else float(d > 0.0) for d in draws)
        / bootstrap_samples,
        groups=count,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
