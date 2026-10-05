"""Conditional rolling logs, incendiary bursts, generated troops and burrowing.

The selected catalog supplies named quantities. Geometry, timing and field
composition remain explicit hypotheses. This module does not certify current
client behavior or change the ordinary siege payload's single owner.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from heapq import heappop
from math import hypot

from .common import InputError, identifier, integer, number, require
from .rates import attack_rate
from .reinforcements import ReinforcementCombat
from .siege_machines import (
    SiegeCombat,
    _along,
    _range_entry,
    _segment_rectangle_entry,
    siege_time_after,
)
from .spatial import EPSILON, _active, _eligible, center, target_distance


EXTENDED_SIEGES = {"log-launcher", "flame-flinger", "siege-barracks", "battle-drill"}
BOUND_RECIPE_SIEGES = {"log-launcher"}


def recipe_siege_runtime(actors, select_target, reinforcements, width, height):
    """Select one complete carrier runtime; orphan extensions stay unavailable."""
    entities = {
        actor["siege_model"]["entity"]
        for actor in actors.values()
        if "siege_model" in actor
    }
    if entities & BOUND_RECIPE_SIEGES:
        if not entities <= BOUND_RECIPE_SIEGES:
            raise InputError("A recipe battle owns only one selected siege carrier")
        return ExtendedSiegeCombat(actors, select_target, reinforcements, width, height)
    return SiegeCombat(actors, select_target, reinforcements, width, height)


EXTENDED_SIEGE_RULES = {
    "extended_siege_statistics": "named_catalog_roles_with_explicit_geometry_and_timing",
    "log_contacts": "captured_structure_footprints_distance_ordered_with_explicit_hit_limit",
    "flinger_fields": "independent_impacts_and_source_attributed_fields_survive_carrier_loss",
    "barracks_generation": "separate_owned_reserves_mature_then_wait_for_a_legal_release_point",
    "barracks_termination": "cancel_unproduced_reserves_preserve_already_produced_releases",
    "drill_travel": "ground_burrow_direct_route_then_surface_and_stun_before_weapon_phase",
    "drill_underground_effects": "explicit_exclusion_requires_shared_damage_status_and_trap_gates",
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires its complete explicit parameters")


def _choice(value, expected, label):
    if value != expected:
        raise InputError(f"Unsupported {label}: expected {expected}")


def _validate_behavior(entity_id, behavior):
    if entity_id == "log-launcher":
        _fields(
            behavior,
            {
                "kind",
                "travel_tiles",
                "half_width_tiles",
                "speed_tiles_per_second",
                "launch_delay_seconds",
                "maximum_structure_hits",
                "wall_hit_limit",
                "contact_geometry",
                "point_blank_range_tiles",
                "point_blank_composition",
                "source_loss",
                "hit_limit_policy",
            },
            "Rolling log behavior",
        )
        _choice(behavior["kind"], "rolling_log", "Log Launcher behavior")
        for field in ("travel_tiles", "speed_tiles_per_second"):
            number(behavior[field], field, EPSILON)
        for field in (
            "half_width_tiles",
            "launch_delay_seconds",
            "point_blank_range_tiles",
        ):
            number(behavior[field], field, 0)
        integer(behavior["maximum_structure_hits"], "log structure hit limit", 1)
        for field, value in {
            "wall_hit_limit": "walls_do_not_consume_structure_hits",
            "contact_geometry": "launch_snapshot_axis_aligned_expanded_footprints",
            "point_blank_composition": "strongest_named_role_per_recipient",
            "source_loss": "launched_logs_continue",
            "hit_limit_policy": "eligible_structure_contacts_including_protected",
        }.items():
            _choice(behavior[field], value, field)
    elif entity_id == "flame-flinger":
        _fields(
            behavior,
            {
                "kind",
                "shot_offsets_seconds",
                "impact_delay_seconds",
                "projectile_speed_tiles_per_second",
                "impact_radius_tiles",
                "flame_radius_tiles",
                "flame_duration_seconds",
                "flame_interval_seconds",
                "flame_dps_fractions",
                "flame_composition",
                "source_loss",
                "burst_cancellation",
                "membership",
                "statistics_mapping",
            },
            "Flame Flinger behavior",
        )
        _choice(behavior["kind"], "incendiary_burst", "Flame Flinger behavior")
        offsets = behavior["shot_offsets_seconds"]
        if not isinstance(offsets, list) or not offsets or offsets[0] != 0:
            raise InputError("Flinger burst must explicitly begin with its first shot")
        for offset in offsets:
            number(offset, "Flinger shot offset", 0)
        if offsets != sorted(set(offsets)):
            raise InputError("Flinger shot offsets must be strictly increasing")
        for field in (
            "projectile_speed_tiles_per_second",
            "flame_duration_seconds",
            "flame_interval_seconds",
        ):
            number(behavior[field], field, EPSILON)
        for field in (
            "impact_delay_seconds",
            "impact_radius_tiles",
            "flame_radius_tiles",
        ):
            number(behavior[field], field, 0)
        fractions = behavior["flame_dps_fractions"]
        if not isinstance(fractions, list) or not fractions:
            raise InputError(
                "Flinger flame ramp requires explicit source-DPS fractions"
            )
        for fraction in fractions:
            number(fraction, "flame DPS fraction", 0, 1)
        for field, value in {
            "flame_composition": "strongest_per_source_sum_between_sources",
            "source_loss": "launched_impacts_and_flames_continue",
            "burst_cancellation": "cancel_unlaunched_on_death_or_freeze",
            "membership": "pulse_time_minimum_point_to_footprint_distance",
            "statistics_mapping": "damagePerHit_per_spirit_flameMaxDps_per_source",
        }.items():
            _choice(behavior[field], value, field)
    elif entity_id == "siege-barracks":
        _fields(
            behavior,
            {
                "kind",
                "schedule",
                "release",
                "generation_clock",
                "termination",
                "simultaneous_boundary",
                "level_basis",
            },
            "Siege Barracks behavior",
        )
        _choice(behavior["kind"], "stationary_generation", "Siege Barracks behavior")
        schedule = behavior["schedule"]
        if not isinstance(schedule, list) or not schedule:
            raise InputError(
                "Barracks require every generated actor in an explicit schedule"
            )
        seen = set()
        last_delay = -1
        for row in schedule:
            _fields(
                row,
                {"actor_id", "entity", "level", "delay_seconds"},
                "Barracks schedule row",
            )
            identifier(row["actor_id"], "Barracks generated actor")
            if row["entity"] not in {"pekka", "wizard"} or row["actor_id"] in seen:
                raise InputError(
                    "Barracks generated members must be unique PEKKAs or Wizards"
                )
            seen.add(row["actor_id"])
            integer(row["level"], "generated troop level", 1)
            last_delay = number(
                row["delay_seconds"], "generation delay", max(last_delay, 0)
            )
        release = behavior["release"]
        _fields(
            release,
            {
                "offsets",
                "maximum_displacement_tiles",
                "position_policy",
                "blocked_position",
            },
            "Barracks release policy",
        )
        if not isinstance(release["offsets"], dict) or set(release["offsets"]) != seen:
            raise InputError(
                "Every generated troop needs its own explicit release offset"
            )
        for offset in release["offsets"].values():
            _fields(offset, {"x", "y"}, "Generated troop offset")
            for value in offset.values():
                number(value, "generated offset")
        number(
            release["maximum_displacement_tiles"], "generated release displacement", 0
        )
        for field, value in {
            "position_policy": "explicit_offset_then_nearest_clear_ground_cell",
            "blocked_position": "hold_member_until_legal_point_exists",
        }.items():
            _choice(release[field], value, field)
        for field, value in {
            "generation_clock": "continues_during_freeze",
            "termination": "cancel_unproduced_preserve_produced",
            "simultaneous_boundary": "carrier_termination_precedes_generation",
            "level_basis": "attacker_confirmed_troop_level",
        }.items():
            _choice(behavior[field], value, field)
    else:
        _fields(
            behavior,
            {
                "kind",
                "stun_seconds",
                "stun_radius_tiles",
                "stun_source",
                "stun_composition",
                "travel",
                "underground_effects",
                "retarget",
            },
            "Battle Drill behavior",
        )
        _choice(behavior["kind"], "burrow_surface_stun", "Battle Drill behavior")
        number(behavior["stun_seconds"], "Drill stun duration", EPSILON)
        number(behavior["stun_radius_tiles"], "Drill stun radius hypothesis", 0)
        identifier(behavior["stun_source"], "Drill stun evidence")
        for field, value in {
            "stun_composition": "maximum_remaining_duration_defenses_only",
            "travel": "direct_burrow_ignoring_blocking_footprints",
            "underground_effects": "exclude_direct_splash_status_hazard_and_trap_effects",
            "retarget": "retained_eligible_defense_then_other_structure",
        }.items():
            _choice(behavior[field], value, field)


def _validate_parameters(parameters, entity_id):
    _fields(
        parameters,
        {
            "source",
            "origin",
            "donor_town_hall",
            "payload_group_id",
            "range_tiles",
            "minimum_range_tiles",
            "targeting",
            "termination",
            "spell_response",
            "behavior",
        },
        "Extended siege parameters",
    )
    identifier(parameters["source"], "extended siege evidence")
    identifier(parameters["payload_group_id"], "extended siege payload group")
    if parameters["origin"] == "own":
        if parameters["donor_town_hall"] is not None:
            raise InputError("Owned siege cannot declare a donor technology override")
    elif parameters["origin"] == "donated":
        integer(parameters["donor_town_hall"], "siege donor Town Hall", 1)
    else:
        raise InputError("Siege origin must be own or donated")
    maximum = number(parameters["range_tiles"], "siege range", 0)
    number(parameters["minimum_range_tiles"], "siege minimum range", 0, maximum)
    if entity_id == "siege-barracks" and maximum != 0:
        raise InputError("Siege Barracks cannot have an ordinary weapon range")
    if entity_id != "siege-barracks" and maximum <= EPSILON:
        raise InputError("Armed siege requires a positive explicit weapon range")
    targeting = parameters["targeting"]
    _fields(
        targeting,
        {"hall_actor_id", "arrival_radius_tiles", "hall_loss"},
        "Extended siege targeting",
    )
    if entity_id == "log-launcher":
        identifier(targeting["hall_actor_id"], "Log Launcher Town Hall")
        number(targeting["arrival_radius_tiles"], "Hall arrival radius", 0)
        _choice(targeting["hall_loss"], "continue_to_captured_anchor", "Hall loss")
    elif targeting != {
        "hall_actor_id": None,
        "arrival_radius_tiles": None,
        "hall_loss": "not_applicable",
    }:
        raise InputError("Only Log Launcher uses a captured Town Hall destination")
    termination = parameters["termination"]
    _fields(
        termination,
        {"decay_basis", "decay_interval_seconds", "lifetime_basis"},
        "Extended siege termination",
    )
    number(termination["decay_interval_seconds"], "siege decay cadence", EPSILON)
    expected = {
        "log-launcher": "snapshot_hpDecayPerSecond",
        "flame-flinger": "snapshot_hpDecayPerSecond",
        "siege-barracks": "snapshot_hitpoints_over_entity_lifetime",
        "battle-drill": "none",
    }
    _choice(termination["decay_basis"], expected[entity_id], "siege decay basis")
    _choice(
        termination["lifetime_basis"],
        "none" if entity_id == "battle-drill" else "snapshot_lifetime",
        "siege lifetime basis",
    )
    if parameters["spell_response"] != {
        "beneficial_fields": "immune_to_healing_rage_and_haste",
        "hostile_effects": "explicit_shared_status_and_hazard_policies",
    }:
        raise InputError(
            "Extended siege requires explicit beneficial and hostile spell policies"
        )
    _validate_behavior(entity_id, parameters["behavior"])


def validate_extended_siege_pattern(pattern):
    if "defending_unit_collateral_policy" in pattern:
        if pattern["defending_unit_collateral_policy"] != "ignore":
            raise InputError(
                "Rolling logs require the explicit structure-only collateral hypothesis"
            )
        pattern = {
            key: value
            for key, value in pattern.items()
            if key != "defending_unit_collateral_policy"
        }
    _fields(
        pattern,
        {
            "kind",
            "source",
            "entity",
            "target_kinds",
            "target_layers",
            "maximum_hp_fraction",
        },
        "Extended siege weapon marker",
    )
    if (
        pattern["kind"]
        != ("none" if pattern["entity"] == "siege-barracks" else "siege_extended")
        or pattern["entity"] not in EXTENDED_SIEGES
        or pattern["target_kinds"] != ["defense", "building", "wall"]
        or pattern["target_layers"] != ["ground"]
        or pattern["maximum_hp_fraction"] != 0
    ):
        raise InputError("Extended siege weapons require their dedicated lifecycle")
    identifier(pattern["source"], "extended siege weapon evidence")


def compile_extended_siege(
    actor, instance, entity, row, modifiers, catalog, movement_units_per_tile
):
    """Compile named quantities without deriving burst damage from reported DPS."""
    entity_id = entity["id"]
    if entity_id not in EXTENDED_SIEGES or entity["category"] != "siege-machine":
        raise InputError("Unsupported extended siege machine")
    if (
        actor["team"] != "attack"
        or actor["counts_for_destruction"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or require(instance, "attack_parameters") != {}
        or any(
            field in instance
            for field in (
                "wall_parameters",
                "hero_parameters",
                "payload_member_parameters",
                "garrison_member_parameters",
                "barracks_member_parameters",
            )
        )
    ):
        raise InputError(
            "Extended siege requires its independent attacking carrier role"
        )
    parameters = deepcopy(require(instance, "siege_parameters"))
    _validate_parameters(parameters, entity_id)
    technology = (
        instance["town_hall"]
        if parameters["origin"] == "own"
        else parameters["donor_town_hall"]
    )
    if not catalog.available(entity_id, instance["level"], technology):
        raise InputError("Extended siege is unavailable to its declared source")
    behavior = parameters["behavior"]
    scale = modifiers["damage_multiplier"]
    stationary = entity_id == "siege-barracks"
    hit = (
        0
        if stationary
        else number(require(row, "damagePerHit"), "named siege hit", EPSILON)
    )
    interval = (
        1
        if stationary
        else number(
            require(
                entity,
                "timeBetweenBursts" if entity_id == "flame-flinger" else "attackSpeed",
            ),
            "siege attack cadence",
            EPSILON,
        )
    )
    statistics = {"hit": hit * scale}
    if entity_id == "log-launcher":
        statistics.update(
            wall_hit=number(
                require(row, "damageVsWalls"), "named log wall hit", EPSILON
            )
            * scale,
            point_blank_hit=number(
                require(row, "pointBlankDamage"), "named log point-blank hit", EPSILON
            )
            * scale,
        )
    elif entity_id == "flame-flinger":
        shots = integer(
            require(entity, "shotsPerBurst"), "named Flinger shots per burst", 1
        )
        if (
            len(behavior["shot_offsets_seconds"]) != shots
            or behavior["shot_offsets_seconds"][-1] >= interval
        ):
            raise InputError(
                "Flinger offsets must cover the named burst inside its source cycle"
            )
        statistics["flame_max_dps"] = (
            number(require(row, "flameMaxDps"), "named maximum flame DPS", EPSILON)
            * scale
        )
    elif stationary:
        expected = {
            "pekka": integer(require(row, "pekkasSpawned"), "source PEKKA count", 0),
            "wizard": integer(require(row, "wizardsSpawned"), "source Wizard count", 0),
        }
        if Counter(item["entity"] for item in behavior["schedule"]) != Counter(
            expected
        ):
            raise InputError(
                "Generated troop schedule differs from named Barracks source counts"
            )
        statistics["generated_counts"] = expected
    lifetime = None
    decay_rate = 0
    if entity_id != "battle-drill":
        lifetime = number(
            require(entity if stationary else row, "lifetime"),
            "named siege lifetime",
            EPSILON,
        )
        decay_rate = (
            number(require(row, "hitpoints"), "source Barracks HP", EPSILON) / lifetime
            if stationary
            else number(
                require(entity, "hpDecayPerSecond"), "named siege HP decay", EPSILON
            )
        )
    termination = parameters["termination"]
    compiled_termination = {
        "manual_release": "destroy_and_release",
        "maximum_lifetime_seconds": lifetime,
        "decay": {
            "interval_seconds": termination["decay_interval_seconds"],
            "maximum_hp_fraction_per_pulse": decay_rate
            * termination["decay_interval_seconds"]
            / row["hitpoints"],
            "protection": "bypass_damage_immunity",
            "freeze": "clock_continues",
        },
    }
    if compiled_termination["decay"]["maximum_hp_fraction_per_pulse"] > 1:
        raise InputError("Siege decay interval would conceal its death boundary")
    if stationary and any(
        item["delay_seconds"] >= lifetime for item in behavior["schedule"]
    ):
        raise InputError(
            "Barracks generation must mature strictly before source lifetime expiry"
        )
    priorities = (
        []
        if stationary
        else (
            ["defense", "building", "wall"]
            if entity_id == "log-launcher"
            else ["defense", "building"]
        )
    )
    actor.update(
        kind="unit",
        layer="ground",
        movement="stationary" if stationary else "ground",
        speed=number(require(entity, "movementSpeed"), "source siege movement", 0)
        / movement_units_per_tile
        * modifiers["movement_speed_multiplier"],
        damage=hit * scale,
        attack_interval_seconds=interval * modifiers["attack_interval_multiplier"],
        range=parameters["range_tiles"] * modifiers["range_multiplier"],
        minimum_range=parameters["minimum_range_tiles"] * modifiers["range_multiplier"],
        blocking=False,
        width=0,
        height=0,
        target_priorities=priorities,
        target_priority_tiers=(
            (
                [list(priorities)]
                if entity_id == "log-launcher"
                else [["defense"], ["building"]]
            )
            if priorities
            else []
        ),
        target_layers=["ground"],
        healing_class="siege",
        buff_class="siege",
        hazard_class="siege",
        spring_class="siege",
        beneficial_field_immunity=True,
        attack_model={
            "kind": "none" if stationary else "siege_extended",
            "source": actor["source"],
            "entity": entity_id,
            "target_kinds": ["defense", "building", "wall"],
            "target_layers": ["ground"],
            "maximum_hp_fraction": 0,
        },
        siege_model={
            "entity": entity_id,
            "parameters": {
                **parameters,
                "termination": compiled_termination,
                "death": {
                    "triggers": "hp_death_only",
                    "overlap": "sum_explicit_effects",
                    "effects": [],
                },
            },
            "extension_parameters": parameters,
            "statistics": statistics,
            "reported_snapshot_dps": (
                None
                if stationary
                else number(require(row, "damagePerSecond"), "reported siege DPS", 0)
            ),
            "unmodified_hit_damage": hit,
            "death_effects": [],
        },
    )
    if not stationary:
        actor["wall_behavior"] = {"kind": "avoid", "source": parameters["source"]}
    else:
        actor.pop("target_priority_tiers", None)
    actor["entity_adapter"].update(
        siege_parameters=deepcopy(parameters),
        behavior_verification="explicit_extended_siege_hypotheses_not_replay_validated",
    )
    validate_extended_siege_pattern(actor["attack_model"])
    return actor


def attach_barracks_member(actor, instance, entity, row, catalog):
    """Mark a generated reserve; the carrier validates counts and exact ownership."""
    parameters = require(instance, "barracks_member_parameters")
    _fields(
        parameters, {"source", "carrier_id", "level_basis"}, "Barracks generated member"
    )
    identifier(parameters["source"], "Barracks member evidence")
    identifier(parameters["carrier_id"], "Barracks member carrier")
    _choice(
        parameters["level_basis"],
        "attacker_confirmed_troop_level",
        "Barracks troop level",
    )
    if (
        entity["id"] not in {"pekka", "wizard"}
        or actor["team"] != "attack"
        or actor["kind"] != "unit"
        or actor["spawn_seconds"] != "controlled"
        or actor["counts_for_destruction"]
        or any(
            field in actor
            for field in (
                "payload_member_model",
                "garrison_member_model",
                "hero_model",
                "siege_model",
            )
        )
        or not catalog.available(entity["id"], instance["level"], instance["town_hall"])
    ):
        raise InputError(
            "Barracks units must be independent, available generated reserves"
        )
    actor["barracks_member_model"] = {
        "entity": entity["id"],
        "level": instance["level"],
        "parameters": deepcopy(parameters),
    }
    return actor


def validate_barracks_inventory(actors, account):
    """Generated actors consume no camp/CC space, but require confirmed levels."""
    for actor in actors.values():
        member = actor.get("barracks_member_model")
        if member is None:
            continue
        owned = account.get("levels", {}).get(member["entity"])
        if owned != member["level"]:
            raise InputError(
                "Barracks generated troop level differs from confirmed attacker research"
            )


def siege_effect_eligible(actor):
    """Shared damage/status/trap paths must call this for underground Drill."""
    return not actor.get("_siege_underground", False)


class _GeneratedRelease:
    """Use the existing deterministic blocked-payload placement policy exactly."""

    _blocked_cells = ReinforcementCombat._blocked_cells
    _release_point = ReinforcementCombat._release_point

    def __init__(self, actors, release, width, height):
        self.actors = actors
        self.parameters = {"release": deepcopy(release)}
        self.width = width
        self.height = height
        self.state = {"delivery_point": None}


class ExtendedSiegeCombat(SiegeCombat):
    """The same external lifecycle interface as SiegeCombat, with separate weapons."""

    def __init__(self, actors, select_target, reinforcements, width, height):
        self.actors = actors
        self.ordinary_select_target = select_target
        self.reinforcements = reinforcements
        self.width = width
        self.height = height
        self.models = {}
        self.states = {}
        self.pending = []
        self.serial = 0
        self.fields = []
        self.flame_clocks = {}
        self.logs = {}
        self.generated = {}
        for actor_id, actor in actors.items():
            model = actor.get("siege_model")
            if model is None or model["entity"] not in EXTENDED_SIEGES:
                continue
            _fields(
                model,
                {
                    "entity",
                    "parameters",
                    "extension_parameters",
                    "statistics",
                    "reported_snapshot_dps",
                    "unmodified_hit_damage",
                    "death_effects",
                },
                "Extended siege runtime model",
            )
            entity_id = model["entity"]
            _validate_parameters(model["extension_parameters"], entity_id)
            validate_extended_siege_pattern(actor["attack_model"])
            if (
                actor["team"] != "attack"
                or actor["kind"] != "unit"
                or actor["layer"] != "ground"
                or actor["counts_for_destruction"]
                or actor["blocking"]
                or actor.get("healing_class") != "siege"
                or actor.get("buff_class") != "siege"
                or not actor.get("beneficial_field_immunity")
                or actor.get("defending_unit_response", {}).get("primary", "ignore")
                != "ignore"
                or model["parameters"]["payload_group_id"]
                != reinforcements.parameters["id"]
                or reinforcements.parameters["delivery"]
                != {"kind": "siege", "carrier_id": actor_id}
                or model["death_effects"]
            ):
                raise InputError(
                    "Extended siege role or payload single ownership is inconsistent"
                )
            for value in model["statistics"].values():
                if not isinstance(value, dict):
                    number(value, "compiled extended siege statistic", 0)
            anchor = None
            if entity_id == "log-launcher":
                hall = actors.get(model["parameters"]["targeting"]["hall_actor_id"])
                if (
                    hall is None
                    or hall.get("entity_adapter", {}).get("entity") != "town-hall"
                    or hall["team"] != "defense"
                ):
                    raise InputError(
                        "Log Launcher needs its declared defending Town Hall"
                    )
                anchor = center(hall)
            self.models[actor_id] = deepcopy(model)
            self.states[actor_id] = {
                "phase": "undeployed",
                "deployed_at": None,
                "terminated_at": None,
                "termination_reason": None,
                "anchor": anchor,
                "next_decay": None,
                "expires_at": None,
                "route_arrival": None,
                "blocker": None,
                "weapon_launches": 0,
                "drill_phase": "surface",
                "drill_target": None,
            }
            if actor["spawn_seconds"] != "controlled":
                reinforcements.validate_deployment_point(
                    {"x": actor["x"], "y": actor["y"]}
                )
            if entity_id == "siege-barracks":
                self._bind_generated(actor_id)
        bound = {
            member_id
            for group in self.generated.values()
            for member_id in group["members"]
        }
        declared = {
            actor_id
            for actor_id, actor in actors.items()
            if "barracks_member_model" in actor
        }
        if bound != declared:
            raise InputError(
                "Every Barracks generated reserve must have exactly one carrier"
            )

    def _bind_generated(self, carrier_id):
        behavior = self.models[carrier_id]["parameters"]["behavior"]
        members = {}
        for entry in behavior["schedule"]:
            actor = self.actors.get(entry["actor_id"])
            member = None if actor is None else actor.get("barracks_member_model")
            if (
                member is None
                or member["entity"] != entry["entity"]
                or member["level"] != entry["level"]
                or member["parameters"]["carrier_id"] != carrier_id
                or member["parameters"]["level_basis"] != behavior["level_basis"]
                or actor["spawn_seconds"] != "controlled"
                or actor["team"] != "attack"
                or actor["counts_for_destruction"]
                or any(
                    key in actor
                    for key in (
                        "payload_member_model",
                        "garrison_member_model",
                        "siege_model",
                        "hero_model",
                    )
                )
            ):
                raise InputError(
                    "Barracks generated member ownership or source level is inconsistent"
                )
            members[entry["actor_id"]] = {
                "phase": "unproduced",
                "delay_seconds": entry["delay_seconds"],
                "produced_at": None,
                "released_at": None,
            }
        self.generated[carrier_id] = {
            "members": members,
            "placement": _GeneratedRelease(
                self.actors, behavior["release"], self.width, self.height
            ),
        }

    def validate_command(self, command, time=None):
        if command.get("kind") == "deploy":
            generated = {
                member
                for group in self.generated.values()
                for member in group["members"]
            }
            if set(command.get("targets", [])) & generated:
                raise InputError(
                    "Generated Barracks reserves cannot be externally deployed"
                )
        return super().validate_command(command, time)

    def apply_commands(self, commands, time, trace):
        for command in commands:
            self.validate_command(command, time)
        return super().apply_commands(commands, time, trace)

    def _terminate(self, actor_id, time, reason, trace):
        changed = super()._terminate(actor_id, time, reason, trace)
        self.actors[actor_id]["_siege_underground"] = False
        if changed and actor_id in self.generated:
            for member_id, state in self.generated[actor_id]["members"].items():
                if state["phase"] == "unproduced":
                    state["phase"] = "cancelled"
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "barracks_generation_cancelled",
                            "source": actor_id,
                            "member": member_id,
                        }
                    )
        return changed

    def prepare(self, actors, time, trace, allow_release=True):
        changed = super().prepare(actors, time, trace, allow_release=allow_release)
        for actor_id, model in self.models.items():
            if model["entity"] == "battle-drill" and _active(actors[actor_id], time):
                self._drill_target(actors[actor_id], time, trace)
            if actor_id in self.generated:
                changed |= self._prepare_generated(actor_id, time, trace, allow_release)
        return changed

    def _prepare_generated(self, carrier_id, time, trace, allow_release):
        group = self.generated[carrier_id]
        state = self.states[carrier_id]
        if state["deployed_at"] is None:
            return False
        placement = group["placement"]
        if placement.state["delivery_point"] is None:
            point = center(self.actors[carrier_id])
            placement.state["delivery_point"] = {"x": point[0], "y": point[1]}
        changed = False
        for member_id, member in group["members"].items():
            actor = self.actors[member_id]
            if (
                member["phase"] in {"unproduced", "produced", "cancelled"}
                and actor["spawn_seconds"] != "controlled"
            ):
                raise InputError("Barracks reserve was externally deployed")
            due = state["deployed_at"] + member["delay_seconds"]
            if (
                member["phase"] == "unproduced"
                and due <= time
                and state["phase"] == "active"
            ):
                member.update(phase="produced", produced_at=due)
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "barracks_generated",
                        "source": carrier_id,
                        "member": member_id,
                    }
                )
                changed = True
            if member["phase"] != "produced" or not allow_release:
                continue
            point = placement._release_point(member_id, time)
            if point is None:
                continue
            if actor["hp"] != actor["maximum_hp"]:
                raise InputError(
                    "An undeployed generated reserve cannot carry unexplained damage"
                )
            actor.update(spawn_seconds=time, x=point[0], y=point[1], target=None)
            actor["next_attack"] = time + actor["first_attack_seconds"]
            member.update(phase="released", released_at=time)
            trace.append(
                {
                    "time_seconds": time,
                    "event": "barracks_released",
                    "source": carrier_id,
                    "member": member_id,
                    "x": point[0],
                    "y": point[1],
                }
            )
            changed = True
        return changed

    def _drill_target(self, actor, time, trace=None):
        state = self.states[actor["id"]]
        target = self.actors.get(actor["target"])
        if target is None or not _eligible(actor, target, time):
            choices = [
                (
                    0 if candidate["kind"] == "defense" else 1,
                    target_distance(center(actor), candidate),
                    candidate["id"],
                    candidate,
                )
                for candidate in self.actors.values()
                if _eligible(actor, candidate, time)
            ]
            target = min(choices, key=lambda entry: entry[:3])[3] if choices else None
        actor["target"] = None if target is None else target["id"]
        if target is None:
            actor["_siege_underground"] = False
            state.update(drill_phase="surface", drill_target=None)
            return None, []
        distance = target_distance(center(actor), target)
        if distance > actor["range"] + EPSILON:
            actor["_siege_underground"] = True
            state.update(drill_phase="burrowed", drill_target=target["id"])
            destination = center(target)
            contact = _range_entry(center(actor), destination, target, actor["range"])
            route = [_along(center(actor), destination, contact)]
            return target, self._remember_arrival(actor, route, time)
        changed = (
            state["drill_phase"] != "surface" or state["drill_target"] != target["id"]
        )
        actor["_siege_underground"] = False
        state.update(
            drill_phase="surface", drill_target=target["id"], route_arrival=None
        )
        if changed:
            behavior = self.models[actor["id"]]["parameters"]["behavior"]
            for recipient in self.actors.values():
                if (
                    recipient["team"] == actor["team"]
                    or recipient["kind"] != "defense"
                    or not _active(recipient, time)
                    or recipient.get("_tesla_hidden", False)
                ):
                    continue
                if (
                    recipient["id"] != target["id"]
                    and target_distance(center(target), recipient)
                    > behavior["stun_radius_tiles"] + EPSILON
                ):
                    continue
                recipient["frozen_until"] = max(
                    recipient["frozen_until"], time + behavior["stun_seconds"]
                )
                if trace is not None:
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "drill_surface_stun",
                            "source": actor["id"],
                            "target": recipient["id"],
                            "until": recipient["frozen_until"],
                        }
                    )
        return target, []

    def select_target(self, actor, actors, time, blocked, width, height):
        model = self.models.get(actor["id"])
        if model is None:
            return self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
        if self.states[actor["id"]]["phase"] != "active" or not _active(actor, time):
            return None, None
        if model["entity"] == "siege-barracks":
            return None, []
        if model["entity"] == "battle-drill":
            return self._drill_target(actor, time)
        if model["entity"] == "flame-flinger":
            target, route = self.ordinary_select_target(
                actor, actors, time, blocked, width, height
            )
            return target, self._remember_arrival(actor, route, time)
        # The log carrier follows the captured Hall line and waits at the first
        # physical obstruction, while its weapon continues through the line.
        return super().select_target(actor, actors, time, blocked, width, height)

    def launch(self, actor, target, actors, time, trace):
        state = self.states.get(actor["id"])
        if (
            state is None
            or state["phase"] != "active"
            or not _active(actor, time)
            or actor["frozen_until"] > time + EPSILON
        ):
            raise InputError("Inactive, frozen or unowned extended siege cannot fire")
        distance = target_distance(center(actor), target)
        if (
            not _eligible(actor, target, time)
            or distance > actor["range"] + EPSILON
            or distance < actor.get("minimum_range", 0) - EPSILON
        ):
            raise InputError(
                "Extended siege weapon target is outside its explicit range"
            )
        model = self.models[actor["id"]]
        behavior = model["parameters"]["behavior"]
        if model["entity"] == "log-launcher":
            self._launch_log(actor, time, trace)
        elif model["entity"] == "flame-flinger":
            for offset in behavior["shot_offsets_seconds"]:
                self._queue(
                    time + offset,
                    {
                        "kind": "flinger_shot",
                        "source": actor["id"],
                        "position": center(target),
                        "target": target["id"],
                    },
                )
        elif model["entity"] == "battle-drill":
            if actor.get("_siege_underground", False):
                raise InputError(
                    "An underground Drill cannot launch its surface weapon"
                )
            self._queue(
                time,
                {
                    "kind": "drill_hit",
                    "source": actor["id"],
                    "source_team": actor["team"],
                    "target": target["id"],
                    "amount": actor["damage"],
                },
            )
        else:
            raise InputError("Siege Barracks has no ordinary weapon")
        actor["next_attack"] = time + actor["attack_interval_seconds"] / attack_rate(
            actor
        )
        state["weapon_launches"] += 1
        trace.append(
            {
                "time_seconds": time,
                "event": "extended_siege_launch",
                "source": actor["id"],
                "target": target["id"],
                "entity": model["entity"],
            }
        )

    def _launch_log(self, actor, time, trace):
        model = self.models[actor["id"]]
        behavior = model["parameters"]["behavior"]
        start = center(actor)
        anchor = self.states[actor["id"]]["anchor"]
        end = _along(start, anchor, behavior["travel_tiles"])
        width = behavior["half_width_tiles"]
        self.serial += 1
        log_id = self.serial
        self.logs[log_id] = {"structure_hits": 0}
        contacts = []
        for target in self.actors.values():
            if (
                target["team"] == actor["team"]
                or target["kind"] not in {"defense", "building", "wall"}
                or target["layer"] != "ground"
                or not _active(target, time)
            ):
                continue
            rectangle = (
                target["x"] - width,
                target["y"] - width,
                target["x"] + target["width"] + width,
                target["y"] + target["height"] + width,
            )
            contact = _segment_rectangle_entry(start, end, rectangle)
            if contact is not None:
                contacts.append((contact, target["id"], target))
        for distance, _, target in sorted(contacts, key=lambda item: item[:2]):
            amount = model["statistics"][
                "wall_hit" if target["kind"] == "wall" else "hit"
            ]
            if (
                target_distance(start, target)
                <= behavior["point_blank_range_tiles"] + EPSILON
            ):
                amount = max(amount, model["statistics"]["point_blank_hit"])
            self._queue(
                time
                + behavior["launch_delay_seconds"]
                + distance / behavior["speed_tiles_per_second"],
                {
                    "kind": "log_contact",
                    "source": actor["id"],
                    "source_team": actor["team"],
                    "target": target["id"],
                    "amount": amount,
                    "log_id": log_id,
                    "maximum_structure_hits": behavior["maximum_structure_hits"],
                },
            )

    @staticmethod
    def _recipient(packet, target, time):
        return (
            _active(target, time)
            and not target.get("_tesla_hidden", False)
            and target["team"] != packet["source_team"]
            and target["kind"] in {"defense", "building", "wall"}
            and target["layer"] == "ground"
        )

    def _hit(self, packet, target, amount, time, trace, damage):
        from .damage_receipts import record_damage

        protected = target["immune_until"] > time + EPSILON
        actual = record_damage(
            self,
            target,
            amount,
            time,
            source_id=packet["source"],
            source_actor_id=packet["source"],
            source_team=packet["source_team"],
            origin="weapon",
        )
        damage[target["id"]] += actual
        trace.append(
            {
                "time_seconds": time,
                "event": "extended_siege_impact",
                "source": packet["source"],
                "target": target["id"],
                "packet_kind": packet["kind"],
                "damage": amount,
                "protected": protected,
                **(
                    {"flame_interval": deepcopy(packet["flame_interval"])}
                    if "flame_interval" in packet
                    else {}
                ),
            }
        )

    def resolve(self, actors, time, trace):
        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time:
            due, _, packet = heappop(self.pending)
            source = actors[packet["source"]]
            model = self.models[source["id"]]
            behavior = model["parameters"]["behavior"]
            kind = packet["kind"]
            if kind == "flinger_shot":
                if not _active(source, time) or source["frozen_until"] > time + EPSILON:
                    trace.append(
                        {
                            "time_seconds": time,
                            "event": "flinger_unlaunched_shot_cancelled",
                            "source": source["id"],
                            "target": packet["target"],
                        }
                    )
                    continue
                distance = hypot(
                    packet["position"][0] - source["x"],
                    packet["position"][1] - source["y"],
                )
                arrival = (
                    due
                    + behavior["impact_delay_seconds"]
                    + distance / behavior["projectile_speed_tiles_per_second"]
                )
                self._queue(
                    arrival,
                    {
                        **packet,
                        "kind": "flinger_impact",
                        "source_team": source["team"],
                        "amount": model["statistics"]["hit"],
                    },
                )
                trace.append(
                    {
                        "time_seconds": time,
                        "event": "flinger_spirit_launched",
                        "source": source["id"],
                        "target": packet["target"],
                        "arrival_seconds": arrival,
                    }
                )
                continue
            if kind == "flinger_impact":
                for target in actors.values():
                    if (
                        self._recipient(packet, target, time)
                        and target_distance(packet["position"], target)
                        <= behavior["impact_radius_tiles"] + EPSILON
                    ):
                        self._hit(packet, target, packet["amount"], time, trace, damage)
                self.fields.append(
                    {
                        "source": source["id"],
                        "source_team": packet["source_team"],
                        "position": packet["position"],
                        "created_at": due,
                        "expires_at": siege_time_after(
                            due, behavior["flame_duration_seconds"]
                        ),
                    }
                )
                if source["id"] not in self.flame_clocks:
                    self.flame_clocks[source["id"]] = {
                        "settled_at": due,
                        "next_pulse": siege_time_after(
                            due, behavior["flame_interval_seconds"]
                        ),
                    }
                continue
            target = actors[packet["target"]]
            if not self._recipient(packet, target, time):
                continue
            if kind == "log_contact":
                log = self.logs[packet["log_id"]]
                if log["structure_hits"] >= packet["maximum_structure_hits"]:
                    continue
                if target["kind"] != "wall":
                    log["structure_hits"] += 1
            self._hit(packet, target, packet["amount"], time, trace, damage)
        self._resolve_flames(actors, time, trace, damage)
        return damage

    def _resolve_flames(self, actors, time, trace, damage):
        # Fields carry absolute ramp ages, but only their source owns a damage
        # clock. Independent staggered field clocks would multiply source DPS.
        for source in sorted(list(self.flame_clocks)):
            clock = self.flame_clocks[source]
            behavior = self.models[source]["parameters"]["behavior"]
            while source in self.flame_clocks:
                due = self._flame_boundary(source)
                if due is None or due > time:
                    break
                start = clock["settled_at"]
                if due <= start:
                    raise InputError(
                        "Flame damage clock must advance before settlement"
                    )
                fields = [field for field in self.fields if field["source"] == source]
                for target in sorted(actors.values(), key=lambda actor: actor["id"]):
                    matching = [
                        field
                        for field in fields
                        if self._recipient(field, target, time)
                        and target_distance(field["position"], target)
                        <= behavior["flame_radius_tiles"] + EPSILON
                    ]
                    amount = self._flame_integral(source, matching, start, due)
                    if amount <= 0:
                        continue
                    self._hit(
                        {
                            "source": source,
                            "source_team": self.actors[source]["team"],
                            "kind": "flame_pulse",
                            "flame_interval": {"start": start, "end": due},
                        },
                        target,
                        amount,
                        time,
                        trace,
                        damage,
                    )
                clock["settled_at"] = due
                self.fields = [
                    field
                    for field in self.fields
                    if field["source"] != source or field["expires_at"] > due
                ]
                if not any(field["source"] == source for field in self.fields):
                    del self.flame_clocks[source]
                    break
                clock["next_pulse"] = siege_time_after(
                    due, behavior["flame_interval_seconds"]
                )

    def _flame_boundary(self, source):
        fields = [field for field in self.fields if field["source"] == source]
        if not fields:
            return None
        # The last partial interval settles at final field expiry rather than
        # paying a full pulse after the source no longer has a damage field.
        return min(
            self.flame_clocks[source]["next_pulse"],
            max(field["expires_at"] for field in fields),
        )

    def _flame_integral(self, source, fields, start, end):
        """Integrate the strongest matching field's DPS over one source interval."""
        if not fields:
            return 0
        behavior = self.models[source]["parameters"]["behavior"]
        interval = behavior["flame_interval_seconds"]
        fractions = behavior["flame_dps_fractions"]
        boundaries = {start, end}
        profiles = []
        for field in fields:
            ramp_times = [
                siege_time_after(field["created_at"], index * interval)
                for index in range(1, len(fractions))
            ]
            profiles.append((field, ramp_times))
            boundaries.update(
                boundary
                for boundary in (field["created_at"], field["expires_at"], *ramp_times)
                if start < boundary < end
            )
        boundaries = sorted(boundaries)
        weighted_duration = 0
        for left, right in zip(boundaries, boundaries[1:]):
            # Every discontinuity is a boundary: the rate is constant on
            # [left, right). A midpoint may round to right for a one-ULP tail.
            strongest = max(
                (
                    fractions[sum(boundary <= left for boundary in ramp_times)]
                    for field, ramp_times in profiles
                    if field["created_at"] <= left < field["expires_at"]
                ),
                default=0,
            )
            weighted_duration += (right - left) * strongest
        return self.models[source]["statistics"]["flame_max_dps"] * weighted_duration

    def next_boundary(self, time):
        boundaries = []
        inherited = super().next_boundary(time)
        if inherited is not None:
            boundaries.append(inherited)
        for source in self.flame_clocks:
            boundary = self._flame_boundary(source)
            if boundary is not None and boundary > time:
                boundaries.append(boundary)
        for carrier_id, group in self.generated.items():
            state = self.states[carrier_id]
            if state["phase"] != "active":
                continue
            boundaries.extend(
                state["deployed_at"] + member["delay_seconds"]
                for member in group["members"].values()
                if member["phase"] == "unproduced"
                and state["deployed_at"] + member["delay_seconds"] > time
            )
        return min(boundaries) if boundaries else None

    def release_ready(self, time):
        return any(
            member["phase"] == "produced"
            and group["placement"]._release_point(member_id, time) is not None
            for group in self.generated.values()
            for member_id, member in group["members"].items()
        )

    def frame(self, actor):
        frame = super().frame(actor)
        if actor["id"] in self.states:
            frame["siege_underground"] = actor.get("_siege_underground", False)
        for carrier_id, group in self.generated.items():
            member = group["members"].get(actor["id"])
            if member is not None:
                frame.update(
                    barracks_carrier=carrier_id, barracks_member_phase=member["phase"]
                )
        return frame

    def result(self):
        return {
            **super().result(),
            "active_flame_fields": len(self.fields),
            "flame_damage_clocks": deepcopy(self.flame_clocks),
            "generated": {
                carrier: deepcopy(group["members"])
                for carrier, group in self.generated.items()
            },
            "shared_drill_effect_gates_required": True,
        }

    def continuation_reasons(self, time):
        """Opaque pending intents become typed facts, not generic damage packets.

        A flinger_shot is cancellable future launch work; it has neither a
        released projectile's damage receipt nor its source-loss persistence.
        Shared consumers must use this provider instead of indexing pending.
        """
        from .battle_termination import continuation_fact

        facts = []
        for arrival, serial, packet in self.pending:
            source = self.actors[packet["source"]]
            if packet["kind"] == "flinger_shot" and not _active(source, time):
                continue
            facts.append(
                continuation_fact(
                    "pending_damage",
                    f"siege:{serial}",
                    [packet["source"]],
                    source_team=source["team"],
                    not_before_seconds=arrival,
                )
            )
        for source in sorted(self.flame_clocks):
            boundary = self._flame_boundary(source)
            if boundary is not None:
                facts.append(
                    continuation_fact(
                        "pending_damage",
                        f"flinger-source:{source}",
                        [source],
                        source_team=self.actors[source]["team"],
                        not_before_seconds=boundary,
                        expires_at_seconds=max(
                            field["expires_at"]
                            for field in self.fields
                            if field["source"] == source
                        ),
                    )
                )
        for carrier_id, group in self.generated.items():
            carrier = self.states[carrier_id]
            for member_id, state in group["members"].items():
                if state["phase"] == "produced" or (
                    state["phase"] == "unproduced" and carrier["phase"] == "active"
                ):
                    due = carrier["deployed_at"] + state["delay_seconds"]
                    facts.append(
                        continuation_fact(
                            "pending_release",
                            f"barracks:{member_id}",
                            [member_id],
                            not_before_seconds=due,
                        )
                    )
        return facts
