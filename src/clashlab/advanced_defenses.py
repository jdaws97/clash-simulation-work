"""Declared Multi-Gear shot streams and primary-centered Super Wizard fanout.

Catalog per-hit quantities remain distinct from displayed DPS. Burst-gap and
fanout geometry, selection and release policies are explicit hypotheses; neither
compiler claims that these policies have been calibrated against game replays.
"""

from copy import deepcopy
from math import hypot

from .spell_visibility import untargetable_until
from .common import InputError, identifier, integer, number, require
from .rates import attack_rate
from .spatial import EPSILON, _active, _eligible, center, target_distance
from .sweepers import EXTRACTION_SOURCE


MULTI_GEAR_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/news/"
    "get-geared-up-for-the-latest-update--3/"
)
SUPER_WIZARD_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/release-notes/"
    "town-hall-18-crash-lands-update/"
)
BALANCE_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/news/balance-changes-4/"
)
FANOUT_PATTERN = "primary_centered_fanout"
MULTI_GEAR_TARGETING = "retain_primary_else_nearest_footprint_then_instance_id"
MULTI_GEAR_READINESS = (
    "shared_attack_work_freeze_and_rate_changes_preserve_unreleased_burst"
)
MULTI_GEAR_GAPS = {
    "snapshot_timeBetweenBursts_is_post_last_shot_gap",
    "snapshot_timeBetweenBursts_is_extra_after_one_inter_shot_interval",
}
MULTI_GEAR_PARAMETERS = {
    "source",
    "damage_basis",
    "burst_timing",
    "targeting",
    "readiness_policy",
}
FANOUT_FIELDS = {
    "anchor",
    "radius_tiles",
    "distance_metric",
    "target_count_basis",
    "selection",
    "target_layer_policy",
    "primary_protection",
    "secondary_protection",
    "visibility",
    "delay_seconds",
    "selection_time",
    "released_links",
    "secondary_destination",
    "inactive_secondary_policy",
}
ADVANCED_DEFENSE_RULES = {
    "multi_gear_cadence": "catalog_per_hit_and_explicit_post_burst_gap_mapping",
    "multi_gear_target": "retain_eligible_primary_then_nearest_footprint_and_id",
    "multi_gear_work": "shared_freeze_and_rate_clock_preserves_unreleased_shots",
    "super_wizard_fanout": "one_primary_then_declared_primary_centered_neighbors",
    "super_wizard_selection": "explicit_anchor_metric_count_order_layers_and_protection",
    "super_wizard_release": "select_at_primary_impact_then_independent_delayed_links",
    "advanced_defense_verification": "declared_hypotheses_not_replay_calibrated",
}
REVENGE_GAPS = {
    "publisher_sources": [SUPER_WIZARD_SOURCE, BALANCE_SOURCE],
    "latest_publisher_destroyed_building_thresholds": [5, 25, 50],
    "publisher_phase_count": 4,
    "catalog_attack_mode_count": 3,
    "pinned_extraction_base_damage_by_level": {1: 50, 2: 60},
    "missing": [
        "mapping of four lifecycle phases to three named catalog attack modes",
        "per-stage maximum HP and HP-preservation or healing rule on transition",
        "source reconciliation for extraction base damage 50/60 and empty normal stats",
        "destruction eligibility, transition timing and attack-work preservation",
        "per-stage ricochet selection, link timing, geometry and release policy",
    ],
}


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise InputError(f"{label} needs every explicit supported field")


def _choice(value, choices, label):
    if value not in choices:
        raise InputError(f"Unsupported {label}")


def _defense_identity(instance, entity, row, entity_id, modes):
    if (
        instance["entity"] != entity_id
        or entity["id"] != entity_id
        or instance["mode"] not in modes
        or instance["statistics_mode"] != instance["mode"]
        or instance["team"] != "defense"
        or instance["counts_for_destruction"] is not True
        or instance["spawn_seconds"] != 0
        or instance["supercharge"] is not False
        or "wall_parameters" in instance
    ):
        raise InputError(f"{entity_id} requires a counted, non-supercharged defense")
    if row["townHallRequired"] > instance["town_hall"]:
        raise InputError(f"{entity_id} level is unavailable at the declared Town Hall")


def _weapon(actor, instance, entity, row, modifiers, pattern):
    mode = entity["modes"][instance["mode"]]
    stats = row["stats"][instance["statistics_mode"]]
    actor.update(
        kind="defense",
        movement="stationary",
        layer="ground",
        speed=0,
        blocking=True,
        width=3,
        height=3,
        minimum_range=0,
        range=number(mode["range"], "advanced defense range", EPSILON)
        * modifiers["range_multiplier"],
        damage=number(
            stats["damagePerShot"], "advanced defense per-hit damage", EPSILON
        )
        * modifiers["damage_multiplier"],
        attack_interval_seconds=number(
            mode["attackSpeed"], "advanced defense shot interval", EPSILON
        )
        * modifiers["attack_interval_multiplier"],
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground", "air"],
        attack_model=pattern,
    )
    for field in ("range", "damage", "attack_interval_seconds"):
        number(actor[field], f"modified advanced defense {field}", EPSILON)


def _projectile(parameters):
    from .combat import validate_pattern

    _exact(parameters, {"projectile"}, "Advanced defense attack parameters")
    projectile = deepcopy(parameters["projectile"])
    if require(projectile, "inactive_primary_policy") != "fizzle":
        raise InputError("Advanced defense primary projectiles require explicit fizzle")
    pattern = {
        "kind": "single",
        "source": "advanced-defense-projectile-validation",
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": projectile,
    }
    validate_pattern(pattern)
    return projectile


def _validate_multi_gear_parameters(parameters, mode):
    _exact(
        parameters,
        MULTI_GEAR_PARAMETERS,
        "Multi-Gear parameters",
    )
    identifier(parameters["source"], "Multi-Gear behavior evidence")
    if parameters["damage_basis"] != "snapshot_damagePerShot_is_one_projectile":
        raise InputError("Multi-Gear damage must select catalog damage per projectile")
    timing = (
        {"snapshot_attackSpeed_is_one_shot_interval"}
        if mode == "normal"
        else MULTI_GEAR_GAPS
    )
    _choice(parameters["burst_timing"], timing, "Multi-Gear burst timing")
    if parameters["targeting"] != MULTI_GEAR_TARGETING:
        raise InputError(
            "Multi-Gear target retention and reacquisition must be explicit"
        )
    if parameters["readiness_policy"] != MULTI_GEAR_READINESS:
        raise InputError("Multi-Gear readiness and burst preservation must be explicit")


def compile_multi_gear(actor, instance, entity, row, modifiers):
    _defense_identity(
        instance, entity, row, "multi-gear-tower", {"normal", "fastAttack"}
    )
    parameters = require(instance, "multi_gear_parameters")
    mode_name = instance["mode"]
    _validate_multi_gear_parameters(parameters, mode_name)
    mode = entity["modes"][mode_name]
    pattern = {
        "kind": "single",
        "source": actor["source"],
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": _projectile(instance["attack_parameters"]),
    }
    _weapon(actor, instance, entity, row, modifiers, pattern)
    interval = actor["attack_interval_seconds"]
    shots = 1
    gap = interval
    if mode_name == "fastAttack":
        shots = integer(require(mode, "shotsPerBurst"), "Multi-Gear burst count", 1)
        gap = (
            number(require(mode, "timeBetweenBursts"), "Multi-Gear burst gap", EPSILON)
            * modifiers["attack_interval_multiplier"]
        )
        if parameters["burst_timing"] == (
            "snapshot_timeBetweenBursts_is_extra_after_one_inter_shot_interval"
        ):
            gap += interval
    actor["multi_gear_model"] = {
        "kind": "multi_gear_shot_stream",
        "mode": mode_name,
        **deepcopy(parameters),
        "shots_per_burst": shots,
        "inter_shot_seconds": interval,
        "post_burst_seconds": gap,
    }
    cycle = (shots - 1) * interval + gap
    actor["entity_adapter"].update(
        multi_gear_parameters=deepcopy(parameters),
        behavior_verification="declared_shot_stream_not_replay_calibrated",
        source_audit={
            "publisher_source": MULTI_GEAR_SOURCE,
            "balance_source": BALANCE_SOURCE,
            "extraction_source": EXTRACTION_SOURCE,
            "catalog_damage_statistic": "damagePerShot",
            "catalog_displayed_dps": row["stats"][mode_name]["dps"],
            "extraction_attack_speed_raw": 1000 if mode_name == "normal" else 350,
            "selected_inter_shot_seconds": interval,
            "selected_post_last_shot_gap_seconds": gap,
            "selected_uninterrupted_cycle_seconds": cycle,
            "derived_full_hit_dps_before_runtime_buffs": shots
            * actor["damage"]
            / cycle,
            "resolution": "explicit_catalog_per_hit_burst_mapping_preserves_extraction_conflict",
        },
    )
    validate_multi_gear_model(actor)
    return actor


def validate_multi_gear_model(actor):
    from .combat import validate_pattern

    model = require(actor, "multi_gear_model")
    fields = {
        "kind",
        "mode",
        "source",
        "damage_basis",
        "burst_timing",
        "targeting",
        "readiness_policy",
        "shots_per_burst",
        "inter_shot_seconds",
        "post_burst_seconds",
    }
    _exact(model, fields, "Multi-Gear model")
    _choice(model["mode"], {"normal", "fastAttack"}, "Multi-Gear mode")
    parameters = {key: model[key] for key in MULTI_GEAR_PARAMETERS}
    _validate_multi_gear_parameters(parameters, model["mode"])
    shots = integer(model["shots_per_burst"], "Multi-Gear shots", 1)
    if shots != (1 if model["mode"] == "normal" else 4):
        raise InputError(
            "Multi-Gear modes require their one- or four-shot catalog count"
        )
    for field in ("inter_shot_seconds", "post_burst_seconds"):
        number(model[field], f"Multi-Gear {field}", EPSILON)
    if (
        model["kind"] != "multi_gear_shot_stream"
        or actor["kind"] != "defense"
        or actor["team"] != "defense"
        or actor["movement"] != "stationary"
        or actor["target_layers"] != ["ground", "air"]
        or actor["attack_model"]["kind"] != "single"
        or actor["attack_interval_seconds"] != model["inter_shot_seconds"]
        or not actor["counts_for_destruction"]
    ):
        raise InputError(
            "Multi-Gear model and stationary single-target weapon disagree"
        )
    if (
        model["mode"] == "normal"
        and model["post_burst_seconds"] != model["inter_shot_seconds"]
    ):
        raise InputError("Normal Multi-Gear mode cannot select a separate burst gap")
    validate_pattern(actor["attack_model"])
    return model


class MultiGearCombat:
    """Own only shot order/readiness; shared PatternCombat owns released hits."""

    def __init__(self, actors, ordinary_select_target, combat):
        self.ordinary_select_target = ordinary_select_target
        self.combat = combat
        self.models = {
            key: deepcopy(validate_multi_gear_model(actor))
            for key, actor in actors.items()
            if "multi_gear_model" in actor
        }
        self.states = {
            key: {
                "next_shot_index": 0,
                "burst_number": 0,
                "launched_shots": 0,
                "cancelled_unreleased_shots": 0,
                "destroyed": False,
            }
            for key in self.models
        }

    def prepare(self, actors, time, trace):
        for key, model in self.models.items():
            state = self.states[key]
            if actors[key]["hp"] > 0 or state["destroyed"]:
                continue
            index = state["next_shot_index"]
            remaining = model["shots_per_burst"] - index if index else 0
            state["cancelled_unreleased_shots"] += remaining
            state["next_shot_index"] = 0
            state["destroyed"] = True
            actors[key]["target"] = None
            trace.append(
                {
                    "event": "multi_gear_destroyed",
                    "time_seconds": time,
                    "source": key,
                    "cancelled_unreleased_shots": remaining,
                }
            )

    @staticmethod
    def _acquirable(actor, target, time):
        return (
            _eligible(actor, target, time)
            and target_distance(center(actor), target) <= actor["range"] + EPSILON
        )

    def select_target(self, actor, actors, time, blocked, width, height):
        if actor["id"] not in self.models:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        if not _active(actor, time):
            actor["target"] = None
            return None, None
        target = actors.get(actor["target"])
        if target is None or not self._acquirable(actor, target, time):
            candidates = [
                candidate
                for candidate in actors.values()
                if self._acquirable(actor, candidate, time)
            ]
            target = min(
                candidates,
                key=lambda value: (target_distance(center(actor), value), value["id"]),
                default=None,
            )
        actor["target"] = target["id"] if target is not None else None
        return (target, []) if target is not None else (None, None)

    def launch(self, actor, primary, actors, time, trace):
        if (
            not _active(actor, time)
            or actor["frozen_until"] > time + EPSILON
            or actor.get("_displacement_pause_until", 0) > time + EPSILON
            or actor["next_attack"] > time + EPSILON
            or primary is None
            or not self._acquirable(actor, primary, time)
        ):
            return False
        model = self.models[actor["id"]]
        state = self.states[actor["id"]]
        index = state["next_shot_index"]
        if index == 0:
            state["burst_number"] += 1
        weapon_state = {
            "kind": "multi_gear",
            "burst_number": state["burst_number"],
            "shot_number": index + 1,
        }
        self.combat.launch(
            actor, primary, actors, time, trace, weapon_state=weapon_state
        )
        state["launched_shots"] += 1
        state["next_shot_index"] = (index + 1) % model["shots_per_burst"]
        interval = (
            model["inter_shot_seconds"]
            if state["next_shot_index"]
            else model["post_burst_seconds"]
        )
        actor["next_attack"] = time + interval / attack_rate(actor)
        return True

    def frame(self, actor):
        state = self.states.get(actor["id"])
        return {"multi_gear_state": deepcopy(state)} if state is not None else {}

    def result(self):
        return {"states": deepcopy(self.states)}


def validate_fanout(parameters):
    _exact(parameters, FANOUT_FIELDS, "Super Wizard fanout")
    choices = {
        "anchor": {"primary_center_at_launch", "primary_center_at_primary_impact"},
        "distance_metric": {"center_distance", "point_to_target_footprint"},
        "target_count_basis": {
            "snapshot_count_includes_primary",
            "snapshot_count_is_secondary_count",
        },
        "selection": {
            "nearest_then_instance_id",
            "highest_current_hp_then_distance_then_instance_id",
        },
        "target_layer_policy": {"both_declared_layers", "primary_target_layer_only"},
        "primary_protection": {"continue_fanout", "stop_fanout"},
        "secondary_protection": {
            "protected_targets_consume_slots",
            "skip_protected_targets",
        },
        "visibility": {
            "exclude_currently_untargetable",
            "ignore_acquisition_visibility",
        },
        "selection_time": {"live_candidates_at_primary_impact"},
        "released_links": {"independent_of_source_and_primary_after_selection"},
        "secondary_destination": {
            "locked_actor_center_at_impact",
            "fixed_target_center_at_selection",
        },
        "inactive_secondary_policy": {"fizzle"},
    }
    for field, values in choices.items():
        _choice(parameters[field], values, f"Super Wizard {field}")
    number(parameters["radius_tiles"], "Super Wizard fanout radius", 0)
    number(parameters["delay_seconds"], "Super Wizard fanout delay", 0)


def compile_super_wizard(actor, instance, entity, row, modifiers):
    _defense_identity(instance, entity, row, "super-wizard-tower", {"normal"})
    parameters = require(instance, "super_wizard_parameters")
    _exact(parameters, {"source", "damage_basis", "fanout"}, "Super Wizard parameters")
    identifier(parameters["source"], "Super Wizard behavior evidence")
    if (
        parameters["damage_basis"]
        != "snapshot_primary_and_each_secondary_damagePerShot"
    ):
        raise InputError(
            "Super Wizard requires separate primary and secondary per-hit quantities"
        )
    validate_fanout(parameters["fanout"])
    mode = entity["modes"]["normal"]
    stats = row["stats"]["normal"]
    primary = number(stats["damagePerShot"], "Super Wizard primary damage", EPSILON)
    secondary = number(
        stats["secondaryChainDamagePerShot"], "Super Wizard secondary damage", 0
    )
    count = integer(mode["maxChainTargets"], "Super Wizard catalog target count", 1)
    includes_primary = (
        parameters["fanout"]["target_count_basis"] == "snapshot_count_includes_primary"
    )
    pattern = {
        "kind": FANOUT_PATTERN,
        "source": actor["source"],
        "behavior_source": parameters["source"],
        "target_kinds": ["unit"],
        "target_layers": ["ground", "air"],
        "maximum_hp_fraction": 0,
        "projectile": _projectile(instance["attack_parameters"]),
        "fanout": deepcopy(parameters["fanout"]),
        "maximum_secondary_targets": count - int(includes_primary),
        "secondary_damage_multiplier": secondary / primary,
    }
    validate_fanout_pattern(pattern)
    _weapon(actor, instance, entity, row, modifiers, pattern)
    actor["entity_adapter"].update(
        super_wizard_parameters=deepcopy(parameters),
        behavior_verification="declared_primary_centered_fanout_not_replay_calibrated",
        source_audit={
            "publisher_source": SUPER_WIZARD_SOURCE,
            "extraction_source": EXTRACTION_SOURCE,
            "catalog_primary_damage": primary,
            "catalog_each_secondary_damage": secondary,
            "catalog_target_count": count,
            "selected_secondary_target_count": pattern["maximum_secondary_targets"],
            "unresolved_geometry_and_count_interpretation": deepcopy(
                parameters["fanout"]
            ),
        },
    )
    return actor


def validate_fanout_pattern(pattern):
    _exact(
        pattern,
        {
            "kind",
            "source",
            "behavior_source",
            "target_kinds",
            "target_layers",
            "maximum_hp_fraction",
            "projectile",
            "fanout",
            "maximum_secondary_targets",
            "secondary_damage_multiplier",
        },
        "Super Wizard pattern",
    )
    if (
        pattern["kind"] != FANOUT_PATTERN
        or pattern["target_kinds"] != ["unit"]
        or pattern["target_layers"] != ["ground", "air"]
        or pattern["maximum_hp_fraction"] != 0
    ):
        raise InputError(
            "Super Wizard fanout needs a dedicated ground-and-air unit pattern"
        )
    identifier(pattern["source"], "Super Wizard statistic source")
    identifier(pattern["behavior_source"], "Super Wizard behavior source")
    _projectile({"projectile": pattern["projectile"]})
    validate_fanout(pattern["fanout"])
    integer(pattern["maximum_secondary_targets"], "Super Wizard secondary limit", 0, 15)
    expected = (
        14
        if pattern["fanout"]["target_count_basis"] == "snapshot_count_includes_primary"
        else 15
    )
    if pattern["maximum_secondary_targets"] != expected:
        raise InputError(
            "Super Wizard target limit disagrees with the declared count basis"
        )
    number(
        pattern["secondary_damage_multiplier"],
        "Super Wizard secondary multiplier",
        0,
        1,
    )


def release_fanout_packets(packet, primary, actors, time, damage_eligible):
    """Capture secondary recipients once; returned ordinary packets never recurse.

    The caller first establishes that the primary hit landed. Selected links use
    captured damage and survive later source/primary death. Each own recipient's
    live status and protection are resolved by the shared projectile queue.
    """
    pattern = packet["pattern"]
    fanout = pattern["fanout"]
    if (
        primary["immune_until"] > time + EPSILON
        and fanout["primary_protection"] == "stop_fanout"
    ):
        return []
    point = (
        packet["position"]
        if fanout["anchor"] == "primary_center_at_launch"
        else center(primary)
    )
    candidates = []
    for target in actors.values():
        if target["id"] == primary["id"] or not damage_eligible(packet, target, time):
            continue
        if (
            fanout["target_layer_policy"] == "primary_target_layer_only"
            and target["layer"] != packet["primary_layer"]
        ):
            continue
        if (
            fanout["secondary_protection"] == "skip_protected_targets"
            and target["immune_until"] > time + EPSILON
        ):
            continue
        if (
            fanout["visibility"] == "exclude_currently_untargetable"
            and untargetable_until(target) > time + EPSILON
        ):
            continue
        if fanout["distance_metric"] == "point_to_target_footprint":
            distance = target_distance(point, target)
        else:
            destination = center(target)
            distance = hypot(destination[0] - point[0], destination[1] - point[1])
        if distance > fanout["radius_tiles"] + EPSILON:
            continue
        priority = (
            -target["hp"]
            if fanout["selection"]
            == "highest_current_hp_then_distance_then_instance_id"
            else 0
        )
        candidates.append((priority, distance, target["id"], target))
    selected = sorted(candidates, key=lambda value: value[:3])[
        : pattern["maximum_secondary_targets"]
    ]
    released = []
    for ordinal, (_, _, _, target) in enumerate(selected, 1):
        following = deepcopy(packet)
        following.update(
            target=target["id"],
            position=center(target),
            flat_damage=packet["flat_damage"] * pattern["secondary_damage_multiplier"],
            chain_index=1,
            visited=[primary["id"], target["id"]],
            fanout_link={
                "primary": primary["id"],
                "ordinal": ordinal,
                "anchor": point,
                "selected_seconds": time,
            },
        )
        destination = (
            "fixed_target_center_at_launch"
            if fanout["secondary_destination"] == "fixed_target_center_at_selection"
            else "locked_actor_center_at_impact"
        )
        following["pattern"] = {
            "kind": "single",
            "source": pattern["source"],
            "target_kinds": ["unit"],
            "target_layers": list(pattern["target_layers"]),
            "maximum_hp_fraction": 0,
            "projectile": {
                "timing": "instant",
                "delay_seconds": 0,
                "destination": destination,
                "hit_radius": pattern["projectile"]["hit_radius"],
                "inactive_primary_policy": fanout["inactive_secondary_policy"],
            },
        }
        released.append((time + fanout["delay_seconds"], following))
    return released
