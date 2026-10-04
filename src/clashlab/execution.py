"""Keep observation, interpretation, and testable interventions separate."""

from .common import InputError, identifier, number, require


DIMENSIONS = {
    "funnel",
    "entry",
    "target_selection",
    "troop_protection",
    "healer_safety",
    "spell_coverage",
    "ability_timing",
    "deployment_order",
    "cleanup",
    "adaptation",
}


def review_execution(review):
    observations = require(review, "observations")
    seen = set()
    for observation in observations:
        evidence_id = identifier(require(observation, "id"), "evidence id")
        if evidence_id in seen:
            raise InputError("Duplicate execution evidence")
        seen.add(evidence_id)
        number(require(observation, "video_seconds"), "video time", 0)
        identifier(require(observation, "source"), "evidence source")
        identifier(require(observation, "description"), "observation description")
    for hypothesis in require(review, "hypotheses"):
        if require(hypothesis, "dimension") not in DIMENSIONS:
            raise InputError("Unknown execution-review dimension")
        evidence = require(hypothesis, "evidence_ids")
        if not evidence or not set(evidence) <= seen:
            raise InputError("An execution hypothesis needs linked observations")
        for field in (
            "interpretation",
            "alternative_explanations",
            "intervention",
            "measurement",
        ):
            require(hypothesis, field)
        if require(hypothesis, "causal_status") != "UNTESTED_HYPOTHESIS":
            raise InputError("A replay alone cannot establish a counterfactual cause")
    return {
        "replay_id": require(review, "replay_id"),
        "review": review,
        "status": "EXECUTION_REVIEW_WITH_TESTABLE_HYPOTHESES",
        "experimental_design": [
            "Keep army, gear, pets, levels, base, and patch fixed while varying one plan decision",
            "Alternate plan order across practice sessions; do not always test the new plan after learning the base",
            "Record actual targeting and protection windows as well as final stars",
            "Then vary composition under both plans to reveal composition-by-execution interactions",
            "Reserve unseen bases and sessions for the final recommendation",
        ],
    }
