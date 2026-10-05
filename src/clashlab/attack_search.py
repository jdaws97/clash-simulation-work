"""Bounded joint attack candidates, using the paid compiler as admission authority.

Scheduled experiments and explicitly opted-in finite observation gates execute
through the same paid engine. Missing observation policies remain unscored.
"""

from copy import deepcopy
from collections import Counter
from hashlib import sha256
from itertools import islice, product
import json

from .common import InputError, identifier, integer, number, require
from .full_battle import compile_full_battle, simulate_full_battle, SUPPORTED_SPELLS


SCHEMA = "joint-attack-search-v1"
PAID_CONTROL_HOOK = "paid-observation-scheduler-v1"
CRAFTED_PROFILE_HOOK = "crafted-role-profile-model-scaling-v1"
SPELL_COLLECTIONS = set(SUPPORTED_SPELLS.values())
COLLECTIONS = {"entities", "effects"} | SPELL_COLLECTIONS
CONDITION_FIELDS = {"time_seconds", "alive", "active", "hp_fraction", "target_actor"}
ATTACK_CHANNELS = {"effects", "pets", "attacking_reinforcements"} | SPELL_COLLECTIONS


def digest(value):
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _shape(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional):
        raise InputError(
            f"Unexpected fields; expected {sorted(set(required) | set(optional))}"
        )
    if not set(required) <= set(value):
        raise InputError(f"Missing fields: {sorted(set(required) - set(value))}")


def _rows(value, label, maximum=128, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise InputError(f"{label} needs {minimum}..{maximum} explicit entries")
    return value


def _provenance(value):
    _shape(value, {"kind", "source"})
    if value["kind"] not in {"original_generated", "external_baseline"}:
        raise InputError(
            "Candidate provenance must distinguish originals from baselines"
        )
    identifier(value["source"], "candidate provenance source")


def scenario_environment(scene):
    """Project the fixed opponent and simulation policies, not an inferred roster.

    Only paid attack entities and explicitly attack-owned channels can vary.
    Unknown/future scene fields remain frozen by default, including traps,
    hazards, target selection, defender reactions and shared binding policies.
    """
    if not isinstance(scene, dict):
        raise InputError("Scenario scene must be an object")
    environment = deepcopy(scene)
    for channel in ATTACK_CHANNELS:
        environment.pop(channel, None)
    environment["entities"] = [
        deepcopy(actor)
        for actor in _rows(require(scene, "entities"), "scene entities", maximum=4096)
        if require(actor, "team") != "attack"
    ]
    return environment


def scenario_fingerprint(value):
    return digest(
        {
            key: require(value, key)
            for key in (
                "scenario_environment",
                "context",
                "layout",
                "opponent_inventory",
                "battle",
                "mechanics",
            )
        }
    )


def validate_candidate_scenario(candidate):
    """Reject unauthorized environment drift before any cache or battle use."""
    if require(candidate, "scenario_sha256") != scenario_fingerprint(candidate):
        raise InputError(
            "Candidate scenario fingerprint differs from its pinned context"
        )
    if scenario_environment(candidate["roster"]["entity_scene"]) != require(
        candidate, "scenario_environment"
    ):
        raise InputError(
            "Roster changes the pinned scenario environment; use a separate scenario manifest"
        )
    return candidate["scenario_sha256"]


def validate_manifest(manifest, mode_rules):
    _shape(
        manifest,
        {
            "schema",
            "id",
            "context",
            "account",
            "layout",
            "opponent_inventory",
            "scenario_environment",
            "battle",
            "mechanics",
            "budget",
            "army_options",
            "plan_options",
        },
    )
    if manifest["schema"] != SCHEMA:
        raise InputError("Unsupported attack search schema")
    environment = manifest["scenario_environment"]
    if environment != scenario_environment(environment):
        raise InputError(
            "Scenario environment must contain only the immutable scene projection"
        )
    identifier(manifest["id"], "search id")
    context = manifest["context"]
    _shape(context, {"mode", "league", "profile_id", "scenario_id"})
    mode = context["mode"]
    if mode not in {"ranked", "war", "cwl", "friendly"}:
        raise InputError("Search mode must be explicit")
    identifier(context["scenario_id"], "scenario id")
    profile = context["profile_id"]
    if profile not in mode_rules["battle_modifier_profiles"]:
        raise InputError("Unknown explicit battle profile")
    if mode == "ranked":
        if context["league"] != "Legend I" or profile != "legend_i":
            raise InputError(
                "This ranked search contract requires explicit Legend I / legend_i"
            )
    elif mode in {"war", "cwl"}:
        if profile != "none" or context["league"] is not None:
            raise InputError(
                "War/CWL are separate unmodified contexts; league must be null"
            )
    elif context["league"] is not None:
        raise InputError("Friendly profile experiments use a null league")
    battle = manifest["battle"]
    _shape(
        battle,
        {"id", "source", "time_limit_seconds", "battle_modifier_policy"},
        {"termination_policy"},
    )
    if battle["battle_modifier_policy"]["profile_id"] != profile:
        raise InputError("Context and applied battle modifier profile disagree")
    number(battle["time_limit_seconds"], "battle duration", 0.001, 180)
    mechanics = manifest["mechanics"]
    _shape(mechanics, {"allow_experimental", "assumptions", "evidence_gaps"})
    if not isinstance(mechanics["allow_experimental"], bool):
        raise InputError("Experimental model opt-in must be boolean")
    for field in ("assumptions", "evidence_gaps"):
        for item in _rows(mechanics[field], field, minimum=1):
            identifier(item, field)
    budget = manifest["budget"]
    _shape(budget, {"maximum_candidates", "timeout_seconds"})
    limit = integer(budget["maximum_candidates"], "candidate budget", 1, 32)
    timeout = number(budget["timeout_seconds"], "worker timeout", 0.001, 60)
    if limit * timeout > 120:
        raise InputError(
            "This small-budget harness allows at most 120 worker wall seconds"
        )
    for field in ("army_options", "plan_options"):
        options = _rows(manifest[field], field, maximum=32, minimum=1)
        ids = set()
        for option in options:
            option_id = identifier(require(option, "id"), field)
            if option_id in ids:
                raise InputError("Joint option identifiers must be unique per axis")
            ids.add(option_id)
            _provenance(require(option, "provenance"))
    return manifest


def enumerate_joint_candidates(manifest, mode_rules):
    """A stable, declared-order product prefix; rejected pairs consume the budget.

    Army options are complete legal-loadout proposals, including hero/equipment
    pairs, pets, spells and siege/CC. Their paired entity scenes avoid guessing
    missing adapters. Plan options jointly vary placements, times and conditions.
    """
    validate_manifest(manifest, mode_rules)
    scenario_sha256 = scenario_fingerprint(manifest)
    pairs = product(manifest["army_options"], manifest["plan_options"])
    result = []
    for roster, plan in islice(pairs, manifest["budget"]["maximum_candidates"]):
        candidate = {
            "schema": SCHEMA,
            "context": deepcopy(manifest["context"]),
            "account": deepcopy(manifest["account"]),
            "layout": deepcopy(manifest["layout"]),
            "opponent_inventory": deepcopy(manifest["opponent_inventory"]),
            "scenario_environment": deepcopy(manifest["scenario_environment"]),
            "scenario_sha256": scenario_sha256,
            "battle": deepcopy(manifest["battle"]),
            "mechanics": deepcopy(manifest["mechanics"]),
            "roster": deepcopy(roster),
            "plan": deepcopy(plan),
        }
        candidate["id"] = digest(candidate)
        result.append(candidate)
    return {
        "candidates": result,
        "enumeration": "declared_roster_then_plan_product_prefix",
        "total_pairs": len(manifest["army_options"]) * len(manifest["plan_options"]),
        "complete": len(result)
        == len(manifest["army_options"]) * len(manifest["plan_options"]),
    }


def _condition(condition, actors, duration):
    field = require(condition, "field")
    if field not in CONDITION_FIELDS:
        raise InputError("Cue needs an existing explicit observation field")
    _shape(
        condition,
        {"field", "operator", "value"},
        {"actor_id"} if field != "time_seconds" else (),
    )
    if field != "time_seconds" and require(condition, "actor_id") not in actors:
        raise InputError("Cue actor is not declared in this scene")
    operator = condition["operator"]
    if operator not in {"equals", "at_least", "at_most"}:
        raise InputError("Unknown cue comparison")
    value = condition["value"]
    if field in {"alive", "active"}:
        if operator != "equals" or not isinstance(value, bool):
            raise InputError("Boolean cues need boolean equality")
    elif field == "target_actor":
        if operator != "equals" or value not in actors:
            raise InputError("Target cue needs a declared actor identity")
    else:
        number(value, "cue value", 0, duration if field == "time_seconds" else 1)


def _conditions(conditions, actors, duration):
    for condition in _rows(conditions, "conditions", maximum=16, minimum=1):
        _condition(condition, actors, duration)


def _funnel(funnel, events, actors, layout, duration):
    _shape(
        funnel,
        {"required"},
        {
            "reason",
            "prerequisites",
            "commit_event_ids",
            "deadline_seconds",
            "contingencies",
        },
    )
    if not isinstance(funnel["required"], bool):
        raise InputError("Funnel requirement must be explicit")
    if not funnel["required"]:
        if set(funnel) != {"required", "reason"}:
            raise InputError("Non-funnel controls need exactly an explicit reason")
        identifier(funnel["reason"], "non-funnel fixture reason")
        if layout["town_hall"] == 18:
            raise InputError(
                "TH18 candidates need explicit funnel prerequisites and bait contingencies"
            )
        return []
    if set(funnel) != {
        "required",
        "prerequisites",
        "commit_event_ids",
        "deadline_seconds",
        "contingencies",
    }:
        raise InputError(
            "Funnel needs prerequisites, commit events, deadline and contingencies"
        )
    _conditions(funnel["prerequisites"], actors, duration)
    if all(item["field"] == "time_seconds" for item in funnel["prerequisites"]):
        raise InputError("Funnel readiness cannot be a guessed time alone")
    commits = _rows(funnel["commit_event_ids"], "commit events", minimum=1)
    if len(set(commits)) != len(commits) or not set(commits) <= events:
        raise InputError("Funnel commits must reference unique declared events")
    number(funnel["deadline_seconds"], "funnel deadline", 0, duration)
    covered = set()
    for branch in _rows(funnel["contingencies"], "funnel contingencies", minimum=1):
        _shape(branch, {"trigger", "all_conditions", "response", "event_ids"})
        trigger = branch["trigger"]
        if trigger not in {"funnel_failed", "hall_bait_detected"} or trigger in covered:
            raise InputError(
                "Funnel contingency triggers must be distinct supported labels"
            )
        covered.add(trigger)
        _conditions(branch["all_conditions"], actors, duration)
        if all(item["field"] == "time_seconds" for item in branch["all_conditions"]):
            raise InputError("Funnel contingencies need a battlefield-state cue")
        targets = _rows(branch["event_ids"], "contingency events")
        if len(set(targets)) != len(targets) or not set(targets) <= events:
            raise InputError("Contingency events must reference unique declared events")
        if branch["response"] == "hold_commit":
            if targets:
                raise InputError("hold_commit consumes no alternate events")
        elif branch["response"] == "alternate_events":
            if not targets or set(targets) & set(commits):
                raise InputError(
                    "An alternate branch needs events distinct from main commit"
                )
        else:
            raise InputError("Unsupported contingency response")
    if covered != {"funnel_failed", "hall_bait_detected"}:
        raise InputError("Funnel needs both failure and Hall-bait contingencies")
    return [PAID_CONTROL_HOOK]


def prepare_candidate(candidate, catalog, mode_rules):
    """Return an admitted paid specification and unmet runtime-hook dependencies."""
    validate_candidate_scenario(candidate)
    roster, plan = candidate["roster"], candidate["plan"]
    _shape(roster, {"id", "army", "entity_scene", "provenance"})
    _shape(plan, {"id", "events", "funnel", "provenance"}, {"observation_policy"})
    specification = deepcopy(candidate["battle"])
    specification["entity_scene"] = scene = deepcopy(roster["entity_scene"])
    if scene["statistics_policy"]["kind"] != "conditional_pinned_snapshot":
        raise InputError(
            "Search v1 requires local pinned catalog statistics; external branches need a hash-resolved adapter"
        )
    if candidate["mechanics"]["allow_experimental"] is not True:
        raise InputError(
            "Current engine conventions require explicit experimental-model opt-in"
        )
    duration = specification["time_limit_seconds"]
    actors = {row["id"] for row in scene["entities"]}
    targets = {}
    for collection in sorted(COLLECTIONS):
        for row in scene.get(collection, []):
            if collection == "entities" and (
                row["team"] != "attack" or row["spawn_seconds"] == "controlled"
            ):
                continue
            key = (collection, row["id"])
            if key in targets:
                raise InputError("Ambiguous scheduled actor/command/cast identity")
            targets[key] = row
    seen, event_ids, dependencies = set(), set(), set()
    for event in _rows(plan["events"], "plan events", maximum=512, minimum=1):
        _shape(
            event,
            {"id", "selector", "at_seconds", "all_conditions"},
            {"position", "positions"},
        )
        event_id = identifier(event["id"], "plan event id")
        if event_id in event_ids:
            raise InputError("Plan event IDs must be unique")
        event_ids.add(event_id)
        _shape(event["selector"], {"collection", "id"})
        key = (event["selector"]["collection"], event["selector"]["id"])
        if key not in targets or key in seen:
            raise InputError("Plan event must bind one unique scheduled paid action")
        seen.add(key)
        time = number(event["at_seconds"], "event time", 0, duration)
        _conditions(event["all_conditions"], actors, duration)
        for condition in event["all_conditions"]:
            if condition["field"] != "time_seconds":
                dependencies.add(PAID_CONTROL_HOOK)
                continue
            expected = condition["value"]
            matches = {
                "equals": time == expected,
                "at_least": time >= expected,
                "at_most": time <= expected,
            }
            if not matches[condition["operator"]]:
                raise InputError(
                    "Scheduled event time contradicts its declared clock condition"
                )
        row = targets[key]
        row["spawn_seconds" if key[0] == "entities" else "time_seconds"] = time
        if "position" in event:
            if key[0] == "effects" and row["kind"] != "clan_castle_deploy":
                raise InputError("This command does not support a single placement")
            _position(event["position"], scene)
            if key[0] == "effects":
                row["position"] = deepcopy(event["position"])
            else:
                row.update(event["position"])
        if "positions" in event:
            if key[0] != "effects" or row["kind"] != "deploy" or "position" in event:
                raise InputError("Multi-placement applies only to a deploy command")
            if set(event["positions"]) != set(row["targets"]):
                raise InputError("Deployment positions must exactly cover paid targets")
            for position in event["positions"].values():
                _position(position, scene)
            row["positions"] = deepcopy(event["positions"])
    if seen != set(targets):
        raise InputError(
            "Plan must cover every scheduled deployment, ability, CC action and cast"
        )
    dependencies.update(
        _funnel(plan["funnel"], event_ids, actors, candidate["layout"], duration)
    )
    dependencies.update(
        _crafted_inventory(candidate["opponent_inventory"], candidate["layout"])
    )
    defense_profile = mode_rules["battle_modifier_profiles"][
        candidate["context"]["profile_id"]
    ]["roles"]["defense"]
    if candidate["opponent_inventory"]["crafted_status"] == "selected" and any(
        defense_profile[field] != 1
        for field in ("damage_multiplier", "hitpoints_multiplier")
    ):
        # Require the compiler's reviewed actual-model scaling capability before
        # admitting a non-neutral crafted profile to scored search.
        dependencies.add(CRAFTED_PROFILE_HOOK)
    if "observation_policy" in plan:
        from .paid_control import POLICIES

        policy = plan["observation_policy"]
        _shape(policy, {"source", "observation_interval_seconds", *POLICIES})
        specification["paid_observation_plan"] = {
            **deepcopy(policy),
            "events": [
                {
                    key: deepcopy(event[key])
                    for key in ("id", "selector", "at_seconds", "all_conditions")
                }
                for event in plan["events"]
            ],
            "funnel": deepcopy(plan["funnel"]),
        }
    compiled = compile_full_battle(
        specification,
        candidate["account"],
        roster["army"],
        candidate["layout"],
        catalog,
        mode_rules,
    )
    if (
        compiled.get("paid_observation_admission", {}).get("capability")
        == PAID_CONTROL_HOOK
    ):
        dependencies.discard(PAID_CONTROL_HOOK)
    if CRAFTED_PROFILE_HOOK in compiled.get("battle_modifier_audit", {}).get(
        "application", {}
    ).get("capabilities", []):
        dependencies.discard(CRAFTED_PROFILE_HOOK)
    return specification, compiled, sorted(dependencies)


def _crafted_inventory(inventory, layout):
    _shape(inventory, {"kind", "crafted_status", "source"})
    identifier(inventory["source"], "opponent inventory evidence")
    if inventory["kind"] not in {"synthetic_declared", "current_opponent"}:
        raise InputError("Opponent inventory kind must be explicit")
    status = inventory["crafted_status"]
    stations = [row for row in layout["buildings"] if row["id"] == "crafting-station"]
    if status == "unknown":
        return ["opponent-crafted-identity-and-module-levels"]
    if status == "synthetic_omitted":
        if inventory["kind"] != "synthetic_declared" or stations:
            raise InputError(
                "Only an explicitly synthetic inventory may omit crafted coverage"
            )
    elif status == "selected":
        if len(stations) != 1 or not stations[0].get("settings", {}).get("crafted"):
            raise InputError(
                "Selected crafted coverage needs an active selected Station, not an empty placeholder"
            )
    else:
        raise InputError(
            "Crafted coverage must be selected, unknown or synthetic_omitted"
        )
    return []


def _position(position, scene):
    _shape(position, {"x", "y"})
    for axis, size in (("x", "width"), ("y", "height")):
        value = number(position[axis], f"deployment {axis}", 0)
        if value >= scene[size]:
            raise InputError("Deployment position lies outside the declared board")


def evaluate_candidate(candidate, catalog, mode_rules):
    specification, compiled, dependencies = prepare_candidate(
        candidate, catalog, mode_rules
    )
    admission = {
        "army": compiled["validation"]["army"],
        "scope": specification["entity_scene"]["scope"],
    }
    if dependencies:
        return {
            "status": "blocked_dependency",
            "objective": None,
            "dependencies": dependencies,
            "admission": admission,
        }
    battle = simulate_full_battle(
        specification,
        candidate["account"],
        candidate["roster"]["army"],
        candidate["layout"],
        catalog,
        mode_rules,
    )
    outcome = battle["outcome"]
    return {
        "status": "completed",
        "scenario_sha256": candidate["scenario_sha256"],
        "objective": {
            field: outcome[field]
            for field in (
                "stars",
                "destruction",
                "elapsed_seconds",
                "completion_time_seconds",
            )
        },
        "outcome": outcome,
        "resource_use": battle["resource_use"],
        "paid_observation": battle.get("paid_observation"),
        "modifier_audit": battle["battle_modifier_audit"],
        "crafted_runtime": battle["combat"].get("crafted_defenses"),
        "crafted_event_counts": dict(
            Counter(
                event["event"]
                for event in battle["combat"]["trace"]
                if event.get("event", "").startswith("crafted_")
            )
        ),
        "admission": admission,
        "limitations": battle["limitations"],
        "full_game_prediction": False,
    }


def comparison(rows):
    """Separate objectives; incomplete attacks never benefit from early death.

    Elapsed time is always reported, but a speed advantage is asserted only for
    two complete destructions. No probability, weighted score or recommendation.
    """
    completed = [row for row in rows if row["result"]["status"] == "completed"]
    for row in completed:
        if require(row["result"], "scenario_sha256") != require(row, "scenario_sha256"):
            raise InputError(
                "Comparison row and completed receipt disagree on scenario"
            )
    relations = []
    for index, left in enumerate(completed):
        for right in completed[index + 1 :]:
            if require(left, "scenario_sha256") != require(right, "scenario_sha256"):
                continue
            a, b = left["result"]["objective"], right["result"]["objective"]
            both_complete = (
                a["completion_time_seconds"] is not None
                and b["completion_time_seconds"] is not None
            )
            relations.append(
                {
                    "left": left["candidate_id"],
                    "right": right["candidate_id"],
                    "stars_delta": a["stars"] - b["stars"],
                    "destruction_delta": a["destruction"] - b["destruction"],
                    "elapsed_seconds_delta": a["elapsed_seconds"]
                    - b["elapsed_seconds"],
                    "completion_seconds_delta": (
                        a["completion_time_seconds"] - b["completion_time_seconds"]
                        if both_complete
                        else None
                    ),
                    "time_comparable": both_complete,
                }
            )
    return relations
