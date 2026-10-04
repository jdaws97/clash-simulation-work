"""Build balanced practice trials and report scenarios without invented weights."""

from copy import deepcopy
from random import Random

from .common import InputError, identifier, integer, require, stable_id
from .evaluation import evaluate_candidates


def design_campaign(specification):
    """Randomize complete comparison blocks using an explicitly supplied budget."""
    campaign_id = identifier(require(specification, "id"), "campaign id")
    seed = integer(require(specification, "seed"), "seed", 0)
    repeats = integer(require(specification, "repeats_per_case"), "repeats", 1)
    maximum = integer(require(specification, "maximum_trials"), "maximum trials", 1)
    mode = require(specification, "mode")
    if mode not in {"ranked", "war", "cwl", "friendly"}:
        raise InputError("Campaign mode must be explicit")
    patch_id = identifier(require(specification, "patch_id"), "patch id")
    modifier_id = identifier(require(specification, "modifier_id"), "modifier id")
    arms = require(specification, "arms")
    cases = require(specification, "cases")
    if len(arms) < 2 or not cases:
        raise InputError("A comparison needs at least two arms and one case")
    arm_ids = set()
    for arm in arms:
        arm_id = identifier(require(arm, "id"), "arm id")
        if arm_id in arm_ids:
            raise InputError("Comparison arm identifiers must be unique")
        arm_ids.add(arm_id)
        for field in ("army_id", "plan_id", "human_profile_id"):
            identifier(require(arm, field), field)
    case_ids = set()
    base_folds = {}
    for case in cases:
        case_id = identifier(require(case, "id"), "case id")
        if case_id in case_ids:
            raise InputError("Case identifiers must be unique")
        case_ids.add(case_id)
        for field in ("base_id", "scenario_id"):
            identifier(require(case, field), field)
        for field in ("attacker_town_hall", "defender_town_hall"):
            integer(require(case, field), field, 1)
        fold = require(case, "fold")
        if fold not in {"train", "validation", "test"}:
            raise InputError("Each case needs an explicit evidence fold")
        prior_fold = base_folds.setdefault(case["base_id"], fold)
        if prior_fold != fold:
            raise InputError("The same base cannot be a practice and held-out case")
    requested = len(arms) * len(cases) * repeats
    if requested > maximum:
        raise InputError(
            f"Complete comparison requires {requested} trials, above budget {maximum}"
        )
    random = Random(seed)
    blocks = [(case, repeat) for case in cases for repeat in range(1, repeats + 1)]
    random.shuffle(blocks)
    trials = []
    for case, repeat in blocks:
        block_id = f"{campaign_id}:{case['id']}:{repeat}"
        ordered_arms = list(arms)
        random.shuffle(ordered_arms)
        for arm in ordered_arms:
            trials.append(
                {
                    "id": stable_id({"block": block_id, "arm": arm["id"]}),
                    "order": len(trials) + 1,
                    "arm_id": arm["id"],
                    "army_id": arm["army_id"],
                    "plan_id": arm["plan_id"],
                    "human_profile_id": arm["human_profile_id"],
                    "base_id": case["base_id"],
                    "scenario_id": case["scenario_id"],
                    "attacker_town_hall": case["attacker_town_hall"],
                    "defender_town_hall": case["defender_town_hall"],
                    "session_id": block_id,
                    "encounter_id": block_id,
                    "pair_id": block_id,
                    "fold": case["fold"],
                    "mode": mode,
                    "patch_id": patch_id,
                    "modifier_id": modifier_id,
                    "source": None,
                    "stars": None,
                    "destruction": None,
                    "town_hall_destroyed": None,
                }
            )
    return {
        "id": campaign_id,
        "status": "PRACTICE_SCHEDULE_WITH_UNMEASURED_OUTCOMES",
        "trial_count": len(trials),
        "specification": specification,
        "trials": trials,
        "instructions": [
            "Record a real replay source and outcomes for each trial before evaluation",
            "Keep each comparison block together when clustering repeated practice",
            "Leave held-out bases unseen while choosing armies and plans",
            "Record failures and missed actions, including failed setup attempts",
            "Friendly challenge outcomes require explicit mode and modifier equivalence before transferring to ranked/war/CWL",
            "War/CWL defense encounters must contain actual incoming attempts; schedule blocks alone are not best-incoming evidence",
        ],
    }


def evaluate_strata(rows, configuration):
    """Evaluate each requested scenario independently without a population mix."""
    scenarios = require(configuration, "scenario_ids")
    if not scenarios or len(scenarios) != len(set(scenarios)):
        raise InputError("Scenario identifiers must be a nonempty unique list")
    reports = []
    for scenario in scenarios:
        identifier(scenario, "scenario id")
        individual = deepcopy(configuration)
        individual.pop("scenario_ids")
        individual["scenario_weights"] = {scenario: 1.0}
        reports.append(
            {
                "scenario_id": scenario,
                "evaluation": evaluate_candidates(rows, individual),
            }
        )
    return {
        "method": "SEPARATE_SCENARIO_EVALUATIONS",
        "reports": reports,
        "overall_ranking": None,
        "population_mixture_assumed": False,
        "warning": "A within-scenario ranking does not establish an overall best army or base",
    }
