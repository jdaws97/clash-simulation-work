"""Use verified scoring ranges until exact trophies are observed."""

from .common import InputError, integer, number


TROPHY_BANDS = {0: (0, 4), 1: (5, 15), 2: (16, 32), 3: (40, 40)}


def validate_outcome(outcome):
    stars = integer(outcome["stars"], "stars", 0, 3)
    destruction = number(outcome["destruction"], "destruction", 0, 100)
    town_hall_destroyed = outcome["town_hall_destroyed"]
    if not isinstance(town_hall_destroyed, bool):
        raise InputError("town_hall_destroyed must be explicitly true or false")
    calculated = int(destruction >= 50) + int(town_hall_destroyed)
    if destruction == 100:
        if not town_hall_destroyed:
            raise InputError("100% destruction must include the Town Hall")
        calculated += 1
    if stars != calculated:
        raise InputError("Stars conflict with destruction and Town Hall survival")
    trophies = outcome.get("attacker_trophies")
    if trophies is not None:
        integer(trophies, "attacker_trophies", 0, 40)
        lower, upper = TROPHY_BANDS[stars]
        if not lower <= trophies <= upper:
            raise InputError("Observed trophies conflict with the verified star band")
    return outcome


def outcome_metrics(outcome):
    validate_outcome(outcome)
    lower, upper = TROPHY_BANDS[outcome["stars"]]
    trophies = outcome.get("attacker_trophies")
    if trophies is not None:
        lower = upper = trophies
    return {
        "triple_rate": float(outcome["stars"] == 3),
        "stars": float(outcome["stars"]),
        "destruction": float(outcome["destruction"]),
        "town_hall_survival": float(not outcome["town_hall_destroyed"]),
        "attacker_trophies_lower": float(lower),
        "attacker_trophies_upper": float(upper),
        "defender_trophies_lower": float(40 - upper),
        "defender_trophies_upper": float(40 - lower),
    }


def strongest_attack(outcomes):
    for outcome in outcomes:
        validate_outcome(outcome)
    if not outcomes:
        raise InputError("Cannot score an empty war encounter")
    return max(outcomes, key=lambda row: (row["stars"], row["destruction"]))
