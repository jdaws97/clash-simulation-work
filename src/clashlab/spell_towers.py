"""Reactive Rage, Poison and Invisibility towers with declared timing policies.

The catalog supplies effect quantities; trigger attribution, cast timing, death
release and recipient geometry remain explicit hypotheses. Invisibility changes
acquisition only. It never grants damage immunity or deletes released attacks.
"""

from copy import deepcopy
from heapq import heappop, heappush
from math import hypot

from .buffs import _circle_events
from .spell_visibility import untargetable_until
from .common import InputError, identifier, number, require
from .hazards import HAZARD_CLASSES, PROTECTION_POLICIES, validate_hazard
from .spatial import EPSILON, _active, center, target_distance


SUPPORTED_MODES = {"rage": 1, "poison": 2, "invisibility": 3}
UNSUPPORTED_MODES = {"earthquake": "maximum-HP earthquake pulse adapter missing"}
UNIT_CLASSES = {"troop", "hero", "pet", "siege", "other", "guardian"}
RAGE_COMPOSITION = {"multiply_with_other_sources", "strongest_with_other_sources"}
SPELL_TOWER_RULES = {
    "spell_tower_weapon": "reactive_fields_without_ordinary_weapon_launches",
    "spell_tower_trigger": "declared_presence_or_new_aggregate_allied_structure_damage",
    "spell_tower_cast": "cancel_unlaunched_cast_on_freeze_or_lost_presence_trigger",
    "spell_tower_recharge": "explicit_launch_or_field_release_origin_wall_clock",
    "spell_tower_death": "one_explicit_ready_only_or_unconditional_death_release",
    "spell_tower_payload": "fixed_launch_aim_persists_after_source_or_target_death",
    "spell_tower_rage": "strongest_tower_flat_weapon_bonus_explicit_other_source_composition",
    "spell_tower_invisibility": "blocks_primary_and_chain_acquisition_without_damage_immunity",
    "spell_tower_poison": "shared_pulsed_hazard_scheduler_additive_damage_strongest_status",
    "spell_tower_membership": "explicit_center_or_footprint_geometry_exact_moving_center_crossings",
}
PARAMETERS = {
    "source",
    "arming_seconds",
    "trigger",
    "cast",
    "recharge",
    "death",
    "recipients",
    "effect",
}
TRIGGER_FIELDS = {
    "policy",
    "radius_multiplier",
    "unit_classes",
    "target_layers",
    "excluded_entities",
    "damage_scope",
    "visibility_policy",
}
CAST_FIELDS = {
    "delay_seconds",
    "targeting_policy",
    "aim_policy",
    "projectile_speed_tiles_per_second",
    "impact_delay_seconds",
    "freeze_policy",
    "pending_trigger_policy",
}
RECHARGE_FIELDS = {"clock", "duration_multiplier"}
DEATH_FIELDS = {
    "policy",
    "delay_seconds",
    "frozen_policy",
    "aim_policy",
    "pending_cast_policy",
    "released_payload_policy",
}
RECIPIENT_FIELDS = {
    "target_kinds",
    "target_layers",
    "unit_classes",
    "excluded_entities",
    "geometry",
    "include_source",
}
COMMON_EFFECT_FIELDS = {"radius_multiplier", "duration_multiplier", "membership_policy"}
EFFECT_FIELDS = {
    "rage": COMMON_EFFECT_FIELDS
    | {
        "damage_bonus_multiplier",
        "stacking_policy",
        "other_rage_policy",
        "statistic_basis",
    },
    "poison": COMMON_EFFECT_FIELDS
    | {
        "statistic_basis",
        "damage_multiplier",
        "pulse_interval_seconds",
        "first_pulse_offset_seconds",
        "growth_by_field_age",
        "exit_linger_seconds",
        "protection_policy",
        "excluded_classes",
        "stacking_policy",
    },
    "invisibility": COMMON_EFFECT_FIELDS
    | {"acquisition_policy", "stacking_policy", "immunity_policy"},
}


def _exact(mapping, expected, label):
    if not isinstance(mapping, dict) or set(mapping) != expected:
        raise InputError(f"Spell Tower {label} needs every explicit supported field")


def _choice(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        raise InputError(f"Unsupported Spell Tower {label}")


def _values(value, allowed, label, empty=False):
    if (
        not isinstance(value, list)
        or (not value and not empty)
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(set(value))
        or not set(value) <= allowed
    ):
        raise InputError(f"Spell Tower {label} needs explicit unique supported values")


def _entity_exclusions(value):
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(set(value))
    ):
        raise InputError(
            "Spell Tower entity exclusions must be an explicit unique list"
        )
    for entity in value:
        identifier(entity, "excluded Spell Tower entity")


def _validate_parameters(parameters, mode):
    _exact(parameters, PARAMETERS, "parameters")
    identifier(parameters["source"], "Spell Tower behavior evidence")
    number(parameters["arming_seconds"], "Spell Tower initial arming", 0)
    trigger = parameters["trigger"]
    _exact(trigger, TRIGGER_FIELDS, "trigger")
    expected_trigger = (
        "new_positive_allied_structure_damage"
        if mode == "invisibility"
        else "continuous_enemy_presence"
    )
    _choice(trigger["policy"], {expected_trigger}, "mode trigger")
    number(
        trigger["radius_multiplier"], "Spell Tower trigger radius multiplier", EPSILON
    )
    _values(trigger["unit_classes"], UNIT_CLASSES, "trigger unit classes")
    _values(trigger["target_layers"], {"ground", "air"}, "trigger layers")
    _entity_exclusions(trigger["excluded_entities"])
    _choice(
        trigger["damage_scope"],
        (
            {"aggregate_actual_damage_without_source_attribution"}
            if mode == "invisibility"
            else {"not_applicable"}
        ),
        "damage attribution",
    )
    _choice(
        trigger["visibility_policy"],
        {"exclude_untargetable_enemies", "include_untargetable_enemies"},
        "trigger visibility",
    )
    cast = parameters["cast"]
    _exact(cast, CAST_FIELDS, "cast")
    number(cast["delay_seconds"], "Spell Tower cast delay", 0)
    number(cast["impact_delay_seconds"], "Spell Tower impact delay", 0)
    speed = cast["projectile_speed_tiles_per_second"]
    if speed is not None:
        number(speed, "Spell Tower flask speed", EPSILON)
    _choice(
        cast["targeting_policy"],
        (
            {"nearest_damaged_structure_then_id"}
            if mode == "invisibility"
            else {"nearest_enemy_center_then_id"}
        ),
        "target selection",
    )
    _choice(
        cast["aim_policy"],
        {"trigger_center_at_launch"} if mode == "poison" else {"source_center"},
        "cast aim",
    )
    _choice(
        cast["freeze_policy"], {"cancel_cast_and_retain_charge"}, "Freeze interaction"
    )
    _choice(
        cast["pending_trigger_policy"],
        (
            {"latched_damage_event"}
            if mode == "invisibility"
            else {"same_enemy_alive_visible_in_range"}
        ),
        "pending trigger",
    )
    recharge = parameters["recharge"]
    _exact(recharge, RECHARGE_FIELDS, "recharge")
    _choice(recharge["clock"], {"launch", "field_release"}, "recharge clock")
    number(recharge["duration_multiplier"], "Spell Tower recharge multiplier", EPSILON)
    death = parameters["death"]
    _exact(death, DEATH_FIELDS, "death release")
    _choice(
        death["policy"],
        {"none", "release_if_ready_at_death", "release_once_regardless_of_recharge"},
        "death release",
    )
    number(death["delay_seconds"], "Spell Tower death release delay", 0)
    _choice(death["frozen_policy"], {"release", "suppress"}, "frozen death")
    _choice(death["aim_policy"], {"source_center"}, "death aim")
    _choice(
        death["pending_cast_policy"],
        {"cancel_unlaunched_cast"},
        "pending cast on death",
    )
    _choice(
        death["released_payload_policy"],
        {"persist_independent_of_source"},
        "released payload lifetime",
    )
    recipients = parameters["recipients"]
    _exact(recipients, RECIPIENT_FIELDS, "recipients")
    _values(
        recipients["target_kinds"],
        {"unit"} if mode == "poison" else {"defense", "building", "unit"},
        "recipient kinds",
    )
    _values(recipients["target_layers"], {"ground", "air"}, "recipient layers")
    _values(recipients["unit_classes"], UNIT_CLASSES, "recipient unit classes")
    _entity_exclusions(recipients["excluded_entities"])
    _choice(
        recipients["geometry"],
        {"center_in_radius", "footprint_intersects_radius"},
        "recipient geometry",
    )
    if not isinstance(recipients["include_source"], bool):
        raise InputError("Spell Tower source membership must be boolean")
    if mode == "poison" and (
        recipients["target_kinds"] != ["unit"]
        or recipients["excluded_entities"]
        or set(recipients["unit_classes"])
        not in (UNIT_CLASSES, UNIT_CLASSES - {"guardian"})
    ):
        raise InputError(
            "Poison uses the shared hazard class exclusions; entity-specific exclusions are unsupported"
        )
    effect = parameters["effect"]
    _exact(effect, EFFECT_FIELDS[mode], "effect")
    number(effect["radius_multiplier"], "Spell Tower effect radius multiplier", EPSILON)
    number(
        effect["duration_multiplier"], "Spell Tower effect duration multiplier", EPSILON
    )
    _choice(
        effect["membership_policy"],
        (
            {"pulsed_damage_continuous_status_with_explicit_linger"}
            if mode == "poison"
            else {"continuous_inside_field_no_linger"}
        ),
        "effect membership",
    )
    if mode == "rage":
        number(
            effect["damage_bonus_multiplier"], "Spell Tower Rage bonus multiplier", 0
        )
        _choice(
            effect["statistic_basis"],
            {"snapshot_damageIncrease_is_bonus_percent_flat_weapons_only"},
            "Rage statistic basis",
        )
        _choice(effect["stacking_policy"], {"strongest_tower_bonus"}, "Rage stacking")
        _choice(effect["other_rage_policy"], RAGE_COMPOSITION, "other Rage composition")
    elif mode == "invisibility":
        _choice(
            effect["acquisition_policy"],
            {"block_primary_and_chain_acquisition_released_damage_continues"},
            "invisibility acquisition",
        )
        _choice(
            effect["stacking_policy"], {"union_of_live_fields"}, "invisibility stacking"
        )
        _choice(
            effect["immunity_policy"],
            {"does_not_grant_damage_immunity"},
            "invisibility damage immunity",
        )
    else:
        _choice(
            effect["statistic_basis"],
            {"snapshot_maxDps_and_slow_percentages"},
            "Poison statistic basis",
        )
        number(effect["damage_multiplier"], "Spell Tower poison damage multiplier", 0)
        number(effect["pulse_interval_seconds"], "Spell Tower poison pulse", EPSILON)
        number(
            effect["first_pulse_offset_seconds"], "Spell Tower first poison pulse", 0
        )
        number(effect["exit_linger_seconds"], "Spell Tower poison linger", 0)
        _choice(effect["protection_policy"], PROTECTION_POLICIES, "poison protection")
        _values(
            effect["excluded_classes"],
            HAZARD_CLASSES,
            "poison class exclusions",
            empty=True,
        )
        _choice(
            effect["stacking_policy"],
            {"additive_damage_strongest_slow"},
            "poison stacking",
        )


def compile_spell_tower(actor, instance, entity, row, modifiers):
    """Attach one explicitly selected supported mode to the shared catalog actor."""
    mode = require(instance, "mode")
    if mode not in SUPPORTED_MODES:
        raise InputError(
            "Spell Tower supports explicit Rage, Poison or Invisibility; Earthquake remains unsupported"
        )
    if (
        instance["entity"] != "spell-tower"
        or instance["team"] != "defense"
        or not instance["counts_for_destruction"]
    ):
        raise InputError("Spell Tower must be a counted defending catalog structure")
    if row["level"] < SUPPORTED_MODES[mode]:
        raise InputError("Selected Spell Tower mode is locked at this tower level")
    if instance["statistics_mode"] != "mode" or instance["attack_parameters"] != {}:
        raise InputError(
            "Spell Towers require mode statistics and no ordinary attack parameters"
        )
    for field in (
        "damage_multiplier",
        "maximum_hp_damage_multiplier",
        "attack_interval_multiplier",
        "range_multiplier",
        "movement_speed_multiplier",
    ):
        if modifiers[field] != 1:
            raise InputError(
                "Spell Tower non-HP actor modifiers must be neutral; effect scaling is explicit"
            )
    parameters = require(instance, "spell_tower_parameters")
    _validate_parameters(parameters, mode)
    snapshot = require(require(entity, "modes"), mode)
    effect = deepcopy(parameters["effect"])
    effect["radius"] = number(
        snapshot["spellRadius"], "Spell Tower catalog spell radius", EPSILON
    ) * effect.pop("radius_multiplier")
    effect["duration_seconds"] = number(
        snapshot["spellDuration"], "Spell Tower catalog spell duration", EPSILON
    ) * effect.pop("duration_multiplier")
    if mode == "rage":
        effect["damage_bonus_fraction"] = (
            number(snapshot["damageIncrease"], "Spell Tower Rage bonus percent", 0)
            / 100
            * effect.pop("damage_bonus_multiplier")
        )
    elif mode == "poison":
        effect["maximum_dps"] = number(
            snapshot["maxDps"], "Spell Tower poison DPS", 0
        ) * effect.pop("damage_multiplier")
        effect["movement_multiplier"] = (
            1
            - number(
                snapshot["speedDecrease"],
                "Spell Tower poison movement reduction",
                0,
                100 - EPSILON,
            )
            / 100
        )
        effect["attack_rate_multiplier"] = (
            1
            - number(
                snapshot["attackRateDecrease"],
                "Spell Tower poison attack reduction",
                0,
                100 - EPSILON,
            )
            / 100
        )
    trigger = deepcopy(parameters["trigger"])
    trigger["radius"] = number(
        snapshot["range"], "Spell Tower catalog trigger range", EPSILON
    ) * trigger.pop("radius_multiplier")
    recharge = parameters["recharge"]
    model = {
        "kind": "reactive_spell_tower",
        "mode": mode,
        "source": parameters["source"],
        "arming_seconds": parameters["arming_seconds"],
        "trigger": trigger,
        "cast": deepcopy(parameters["cast"]),
        "recharge": {
            "clock": recharge["clock"],
            "duration_seconds": number(
                snapshot["rechargeTime"], "Spell Tower catalog recharge", EPSILON
            )
            * recharge["duration_multiplier"],
        },
        "death": deepcopy(parameters["death"]),
        "recipients": deepcopy(parameters["recipients"]),
        "effect": effect,
    }
    actor.update(
        kind="defense",
        layer="ground",
        movement="stationary",
        speed=0,
        width=2,
        height=2,
        blocking=True,
        damage=0,
        attack_interval_seconds=model["recharge"]["duration_seconds"],
        range=0,
        target_priorities=[],
        target_priority_tiers=[],
        target_layers=[],
        attack_model={
            "kind": "none",
            "source": actor["source"],
            "maximum_hp_fraction": 0,
        },
        spell_tower_model=model,
    )
    # Empty target-priority tiers are not a valid partition in the spatial loader.
    actor.pop("target_priority_tiers")
    actor["entity_adapter"].update(
        spell_tower_parameters=deepcopy(parameters),
        selected_statistic=f"modes.{mode}; mode effect quantities do not grow with tower HP level",
        behavior_verification="explicit_reactive_tower_hypotheses_not_replay_validated",
    )
    validate_spell_tower_model(actor)
    return actor


def _parameter_view(model):
    """Reuse policy validation while keeping runtime statistics independently scaled."""
    parameters = {field: deepcopy(model[field]) for field in PARAMETERS}
    parameters["trigger"]["radius_multiplier"] = parameters["trigger"].pop("radius")
    parameters["recharge"]["duration_multiplier"] = parameters["recharge"].pop(
        "duration_seconds"
    )
    effect = parameters["effect"]
    effect["radius_multiplier"] = effect.pop("radius")
    effect["duration_multiplier"] = effect.pop("duration_seconds")
    if model["mode"] == "rage":
        effect["damage_bonus_multiplier"] = effect.pop("damage_bonus_fraction")
    elif model["mode"] == "poison":
        effect["damage_multiplier"] = effect.pop("maximum_dps")
        for field in ("movement_multiplier", "attack_rate_multiplier"):
            number(effect.pop(field), f"Spell Tower {field}", EPSILON, 1)
    return parameters


def validate_spell_tower_model(actor):
    model = require(actor, "spell_tower_model")
    _exact(model, PARAMETERS | {"kind", "mode"}, "runtime model")
    if model["kind"] != "reactive_spell_tower" or model["mode"] not in SUPPORTED_MODES:
        raise InputError("Unsupported Spell Tower runtime mode")
    _validate_parameters(_parameter_view(model), model["mode"])
    if (
        actor["team"] != "defense"
        or actor["kind"] != "defense"
        or actor["movement"] != "stationary"
        or actor["layer"] != "ground"
        or actor["width"] != 2
        or actor["height"] != 2
        or not actor["blocking"]
        or not actor["counts_for_destruction"]
        or actor["spawn_seconds"] != 0
        or actor["first_attack_seconds"] != 0
        or actor["damage"] != 0
        or actor["attack_model"]["kind"] != "none"
        or actor["target_priorities"]
    ):
        raise InputError(
            "Spell Tower runtime requires a stationary counted 2x2 defense without a weapon"
        )
    return model


def _unit_class(actor):
    return actor.get("buff_class", actor.get("hazard_class"))


class SpellTowerCombat:
    """Own reactive tower charges and fields; share poison with the hazard runtime.

    Call prepare after commands and after health settlement. A true return value
    means new fields were released; settle shared hazards at the same timestamp.
    The core must skip ordinary weapon launches for these actors, honor the
    separate acquisition flag, and include both temporal and spatial boundaries.
    """

    def __init__(self, actors, hazards):
        self.actors = actors
        self.models = {
            key: deepcopy(validate_spell_tower_model(actor))
            for key, actor in actors.items()
            if "spell_tower_model" in actor
        }
        self.hazards = hazards
        self.states = {}
        self.pending = []
        self.fields = {}
        self.sequence = 0
        self.last_time = None
        self.boundary_sides = {}
        self.crossing_hints = {}
        self.received_damage = {
            key: actor.get("_received_damage", 0) for key, actor in actors.items()
        }
        compositions = {
            model["effect"]["other_rage_policy"]
            for model in self.models.values()
            if model["mode"] == "rage"
        }
        if len(compositions) > 1:
            raise InputError(
                "All Rage towers must select the same other-source composition policy"
            )
        self.rage_composition = next(iter(compositions), "multiply_with_other_sources")
        for key, model in self.models.items():
            self.states[key] = {
                "phase": "armed",
                "ready_at": model["arming_seconds"],
                "cast_started_at": None,
                "launch_at": None,
                "trigger_id": None,
                "launched_count": 0,
                "released_count": 0,
                "death_processed": False,
                "death_release_queued": False,
            }
            if model["mode"] == "poison":
                if hazards is None:
                    raise InputError(
                        "Poison towers require the shared hazard scheduler"
                    )
                validate_hazard(
                    self._poison_field(key, "validation", center(actors[key]), 0),
                    actors,
                )
        if self.models:
            for actor in actors.values():
                if actor["kind"] == "unit" and _unit_class(actor) not in UNIT_CLASSES:
                    raise InputError(
                        "Spell Tower unit membership needs an explicit supported class"
                    )

    def _circle_inside(self, key, actor, origin, radius):
        point = center(actor)
        side = self.boundary_sides.get(key)
        if side is not None:
            if (
                hypot(point[0] - side["position"][0], point[1] - side["position"][1])
                <= EPSILON * 128
            ):
                return side["inside_after"]
            self.boundary_sides.pop(key)
        return hypot(point[0] - origin[0], point[1] - origin[1]) <= radius + EPSILON

    def _trigger_eligible(self, source, actor, time, check_range=True):
        model = self.models[source]
        trigger = model["trigger"]
        eligible = (
            _active(actor, time)
            and actor["kind"] == "unit"
            and actor["team"] != self.actors[source]["team"]
            and actor["layer"] in trigger["target_layers"]
            and _unit_class(actor) in trigger["unit_classes"]
            and actor.get("entity_adapter", {}).get("entity")
            not in trigger["excluded_entities"]
        )
        if trigger["visibility_policy"] == "exclude_untargetable_enemies":
            eligible = eligible and untargetable_until(actor) <= time + EPSILON
        return eligible and (
            not check_range
            or self._circle_inside(
                ("trigger", source, actor["id"]),
                actor,
                center(self.actors[source]),
                trigger["radius"],
            )
        )

    def _select_trigger(self, source, actors, time, damaged):
        model = self.models[source]
        tower = actors[source]
        origin = center(tower)
        choices = []
        for key, actor in actors.items():
            if model["mode"] == "invisibility":
                if (
                    key not in damaged
                    or actor["team"] != tower["team"]
                    or actor["kind"] not in {"defense", "building"}
                    or target_distance(origin, actor)
                    > model["trigger"]["radius"] + EPSILON
                ):
                    continue
            elif not self._trigger_eligible(source, actor, time):
                continue
            point = center(actor)
            choices.append((hypot(point[0] - origin[0], point[1] - origin[1]), key))
        return min(choices)[1] if choices else None

    def _poison_field(self, source, field_id, position, start):
        model = self.models[source]
        effect = model["effect"]
        return {
            "id": field_id,
            "source": model["source"],
            "start_seconds": start,
            **{
                field: deepcopy(effect[field])
                for field in (
                    "duration_seconds",
                    "pulse_interval_seconds",
                    "first_pulse_offset_seconds",
                    "maximum_dps",
                    "growth_by_field_age",
                    "movement_multiplier",
                    "attack_rate_multiplier",
                    "exit_linger_seconds",
                    "protection_policy",
                    "excluded_classes",
                )
            },
            "area": {
                "x": position[0],
                "y": position[1],
                "radius": effect["radius"],
                "target_team": "attack",
                "target_kinds": ["unit"],
                "target_layers": deepcopy(model["recipients"]["target_layers"]),
            },
        }

    def _queue_release(self, source, position, launch, arrival, reason, trace):
        self.sequence += 1
        model = self.models[source]
        packet = {
            "id": f"{source}:tower-field:{self.sequence}",
            "source": source,
            "mode": model["mode"],
            "position": position,
            "start_seconds": arrival,
            "reason": reason,
        }
        heappush(self.pending, (arrival, self.sequence, packet))
        state = self.states[source]
        state["launched_count"] += 1
        trace.append(
            {
                "event": "spell_tower_launch",
                "time_seconds": launch,
                "source": source,
                "mode": model["mode"],
                "field_id": packet["id"],
                "reason": reason,
                "position": position,
                "release_at": arrival,
            }
        )

    def _cancel_cast(self, source, time, reason, trace):
        state = self.states[source]
        if state["phase"] != "casting":
            return
        trace.append(
            {
                "event": "spell_tower_cast_cancelled",
                "time_seconds": time,
                "source": source,
                "reason": reason,
            }
        )
        state.update(
            phase="armed", cast_started_at=None, launch_at=None, trigger_id=None
        )

    def _death(self, source, actor, time, trace):
        state = self.states[source]
        if state["death_processed"] or actor["death_time"] is None:
            return
        model = self.models[source]
        death = model["death"]
        charged = actor["death_time"] >= state["ready_at"] - EPSILON
        self._cancel_cast(source, time, "source_destroyed", trace)
        eligible = death["policy"] == "release_once_regardless_of_recharge" or (
            death["policy"] == "release_if_ready_at_death" and charged
        )
        if (
            death["frozen_policy"] == "suppress"
            and actor["frozen_until"] > actor["death_time"] + EPSILON
        ):
            eligible = False
        state.update(phase="destroyed", death_processed=True)
        if eligible:
            arrival = actor["death_time"] + death["delay_seconds"]
            self._queue_release(
                source, center(actor), actor["death_time"], arrival, "death", trace
            )
            state["death_release_queued"] = True
        trace.append(
            {
                "event": "spell_tower_death_policy",
                "time_seconds": time,
                "source": source,
                "charged": charged,
                "release_queued": eligible,
            }
        )

    def _advance_tower(self, source, actors, time, damaged, trace):
        actor = actors[source]
        state = self.states[source]
        model = self.models[source]
        self._death(source, actor, time, trace)
        if not _active(actor, time):
            return
        if actor["frozen_until"] > time + EPSILON:
            self._cancel_cast(source, time, "source_frozen", trace)
            return
        if state["ready_at"] > time + EPSILON:
            return
        if state["phase"] == "recharging":
            state["phase"] = "armed"
            trace.append(
                {"event": "spell_tower_rearmed", "time_seconds": time, "source": source}
            )
        if state["phase"] == "casting" and model["mode"] != "invisibility":
            if not self._trigger_eligible(source, actors[state["trigger_id"]], time):
                self._cancel_cast(source, time, "trigger_no_longer_eligible", trace)
        if state["phase"] == "armed":
            trigger = self._select_trigger(source, actors, time, damaged)
            if trigger is None:
                return
            state.update(
                phase="casting",
                trigger_id=trigger,
                cast_started_at=time,
                launch_at=time + model["cast"]["delay_seconds"],
            )
            trace.append(
                {
                    "event": "spell_tower_cast_start",
                    "time_seconds": time,
                    "source": source,
                    "trigger": trigger,
                    "launch_at": state["launch_at"],
                }
            )
        if state["launch_at"] > time + EPSILON:
            return
        position = (
            center(actors[state["trigger_id"]])
            if model["mode"] == "poison"
            else center(actor)
        )
        cast = model["cast"]
        travel = 0
        if cast["projectile_speed_tiles_per_second"] is not None:
            origin = center(actor)
            travel = (
                hypot(position[0] - origin[0], position[1] - origin[1])
                / cast["projectile_speed_tiles_per_second"]
            )
        arrival = time + cast["impact_delay_seconds"] + travel
        self._queue_release(source, position, time, arrival, "trigger", trace)
        recharge_origin = (
            arrival if model["recharge"]["clock"] == "field_release" else time
        )
        state.update(
            phase="recharging",
            ready_at=recharge_origin + model["recharge"]["duration_seconds"],
            cast_started_at=None,
            launch_at=None,
            trigger_id=None,
        )

    def _release_due(self, actors, time, trace):
        released = False
        while self.pending and self.pending[0][0] <= time + EPSILON:
            _, _, packet = heappop(self.pending)
            model = self.models[packet["source"]]
            field = {
                **packet,
                "end_seconds": packet["start_seconds"]
                + model["effect"]["duration_seconds"],
                "radius": model["effect"]["radius"],
                "recipients": deepcopy(model["recipients"]),
            }
            if packet["mode"] == "poison":
                self.hazards.schedule(
                    self._poison_field(
                        packet["source"],
                        packet["id"],
                        packet["position"],
                        packet["start_seconds"],
                    ),
                    actors,
                    source_actor_id=packet["source"],
                )
            else:
                field["effect"] = deepcopy(model["effect"])
            self.fields[packet["id"]] = field
            self.states[packet["source"]]["released_count"] += 1
            trace.append(
                {
                    "event": "spell_tower_field_release",
                    "time_seconds": time,
                    "source": packet["source"],
                    "field_id": packet["id"],
                    "mode": packet["mode"],
                    "reason": packet["reason"],
                    "position": packet["position"],
                    "end_seconds": field["end_seconds"],
                }
            )
            released = True
        return released

    def _recipient_eligible(self, field, actor, time):
        recipients = field["recipients"]
        team = "attack" if field["mode"] == "poison" else "defense"
        return (
            _active(actor, time)
            and actor["team"] == team
            and actor["kind"] in recipients["target_kinds"]
            and actor["layer"] in recipients["target_layers"]
            and (recipients["include_source"] or actor["id"] != field["source"])
            and actor.get("entity_adapter", {}).get("entity")
            not in recipients["excluded_entities"]
            and (
                actor["kind"] != "unit"
                or _unit_class(actor) in recipients["unit_classes"]
            )
        )

    def _inside_field(self, field, actor):
        if (
            actor["movement"] != "stationary"
            or field["recipients"]["geometry"] == "center_in_radius"
        ):
            return self._circle_inside(
                ("field", field["id"], actor["id"]),
                actor,
                field["position"],
                field["radius"],
            )
        return target_distance(field["position"], actor) <= field["radius"] + EPSILON

    def _prepare_fields(self, actors, time, trace):
        for actor in actors.values():
            factor, untargetable = 1, 0
            fields = []
            for field_id, field in sorted(self.fields.items()):
                if (
                    field["mode"] == "poison"
                    or field["start_seconds"] > time + EPSILON
                    or field["end_seconds"] <= time + EPSILON
                    or not self._recipient_eligible(field, actor, time)
                    or not self._inside_field(field, actor)
                ):
                    continue
                fields.append(field_id)
                if field["mode"] == "rage":
                    factor = max(factor, 1 + field["effect"]["damage_bonus_fraction"])
                else:
                    untargetable = max(untargetable, field["end_seconds"])
            previous = (
                actor.get("_spell_tower_damage_multiplier", 1),
                actor.get("_spell_tower_untargetable_until", 0),
                actor.get("_spell_tower_fields", []),
            )
            current = (factor, untargetable, fields)
            if previous != current:
                trace.append(
                    {
                        "event": "spell_tower_membership",
                        "time_seconds": time,
                        "target": actor["id"],
                        "damage_multiplier": factor,
                        "untargetable_until": untargetable,
                        "fields": fields,
                    }
                )
            actor["_spell_tower_damage_multiplier"] = factor
            actor["_spell_tower_untargetable_until"] = untargetable
            actor["_spell_tower_rage_composition"] = self.rage_composition
            actor["_spell_tower_fields"] = fields

    def prepare(self, actors, time, trace):
        number(time, "Spell Tower preparation time", 0)
        if self.last_time is not None and time < self.last_time - EPSILON:
            raise InputError("Spell Tower runtime cannot move backward in time")
        for key, hint in list(self.crossing_hints.items()):
            if hint["time_seconds"] > time + EPSILON:
                continue
            point = center(actors[key[-1]])
            if (
                abs(hint["time_seconds"] - time) <= EPSILON
                and hypot(
                    point[0] - hint["position"][0], point[1] - hint["position"][1]
                )
                <= EPSILON * 128
            ):
                self.boundary_sides[key] = hint
            self.crossing_hints.pop(key)
        self.last_time = time
        damaged = set()
        for key, actor in actors.items():
            current = actor.get("_received_damage", 0)
            if current > self.received_damage.get(key, 0) + EPSILON:
                damaged.add(key)
            self.received_damage[key] = current
        for source in sorted(self.models):
            self._advance_tower(source, actors, time, damaged, trace)
        released = self._release_due(actors, time, trace)
        self._prepare_fields(actors, time, trace)
        return released

    def next_boundary(self, time):
        values = [arrival for arrival, _, _ in self.pending]
        for state in self.states.values():
            if state["phase"] != "destroyed":
                values.extend((state["ready_at"], state["launch_at"]))
        values.extend(field["end_seconds"] for field in self.fields.values())
        future = [
            value for value in values if value is not None and value > time + EPSILON
        ]
        return min(future) if future else None

    def first_crossing_delay(self, actor, route, time, horizon, effective_speed):
        """Split trigger/field entry and exit along ordinary or forced polyline motion."""
        speed = number(effective_speed, "Spell Tower crossing speed", 0)
        if speed <= EPSILON:
            return None
        zones = []
        for source, model in self.models.items():
            if (
                model["mode"] == "invisibility"
                or not _active(self.actors[source], time)
                or self.states[source]["phase"] not in {"armed", "casting"}
            ):
                continue
            if self._trigger_eligible(source, actor, time, check_range=False):
                zones.append(
                    (
                        ("trigger", source, actor["id"]),
                        center(self.actors[source]),
                        model["trigger"]["radius"],
                    )
                )
        for field_id, field in self.fields.items():
            if field["start_seconds"] <= time + EPSILON < field[
                "end_seconds"
            ] and self._recipient_eligible(field, actor, time):
                zones.append(
                    (
                        ("field", field_id, actor["id"]),
                        field["position"],
                        field["radius"],
                    )
                )
        earliest = None
        for key, origin, radius in zones:
            self.crossing_hints.pop(key, None)
            poison = key[0] == "field" and self.fields[key[1]]["mode"] == "poison"
            if poison:
                # The shared hazard scheduler uses inclusive geometric membership,
                # not this runtime's directional hints. Its outward boundary
                # departure therefore needs one bounded numerical-epsilon step.
                point = center(actor)
                inside = (
                    hypot(point[0] - origin[0], point[1] - origin[1])
                    <= radius + EPSILON
                )
            else:
                inside = self._circle_inside(key, actor, origin, radius)
            previous, traveled = center(actor), 0
            found = False
            for point_index, point in enumerate(route):
                length = hypot(point[0] - previous[0], point[1] - previous[1])
                for contact, inside_after in _circle_events(
                    previous, point, origin, radius
                ):
                    if abs(contact - length) <= EPSILON:
                        for following in route[point_index + 1 :]:
                            direction = (
                                following[0] - point[0],
                                following[1] - point[1],
                            )
                            if hypot(*direction) <= EPSILON:
                                continue
                            projection = (point[0] - origin[0]) * direction[0] + (
                                point[1] - origin[1]
                            ) * direction[1]
                            inside_after = projection < -EPSILON
                            break
                    if inside_after == inside:
                        continue
                    if traveled + contact <= speed * EPSILON:
                        contact = max(contact, speed * EPSILON * 2, EPSILON * 4)
                    delay = (traveled + contact) / speed
                    if (
                        delay <= EPSILON
                        or delay > horizon + EPSILON
                        or contact > length + EPSILON
                    ):
                        continue
                    fraction = min(contact / length, 1)
                    position = tuple(
                        previous[index] + (point[index] - previous[index]) * fraction
                        for index in (0, 1)
                    )
                    self.crossing_hints[key] = {
                        "time_seconds": time + delay,
                        "position": position,
                        "inside_after": inside_after,
                    }
                    earliest = min(earliest, delay) if earliest is not None else delay
                    found = True
                    break
                if found:
                    break
                traveled += length
                if traveled > speed * horizon:
                    break
                previous = point
        return earliest

    def frame(self, actor):
        return {
            "spell_tower_damage_multiplier": actor.get(
                "_spell_tower_damage_multiplier", 1
            ),
            "spell_tower_untargetable_until": actor.get(
                "_spell_tower_untargetable_until", 0
            ),
            "spell_tower_fields": list(actor.get("_spell_tower_fields", [])),
            **(
                {"spell_tower_state": deepcopy(self.states[actor["id"]])}
                if actor["id"] in self.states
                else {}
            ),
        }

    def result(self):
        return {
            "states": deepcopy(self.states),
            "fields": deepcopy(self.fields),
            "pending_releases": [
                deepcopy(packet) for _, _, packet in sorted(self.pending)
            ],
            "unsupported_modes": deepcopy(UNSUPPORTED_MODES),
            "limitations": [
                "Invisibility triggers observe aggregate positive actual allied-structure damage without attacker-cause attribution",
                "Rage boosts declared recipients' flat weapon damage; movement, healing, maximum-HP terms and death effects are unchanged",
                "Cast, recharge, death release, membership geometry and poison growth remain explicit uncalibrated hypotheses",
            ],
            "full_game_prediction": False,
        }
