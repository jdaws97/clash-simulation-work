"""Paid Totem and Recall lifecycles with explicit, uncalibrated contracts."""

from collections import defaultdict
from copy import deepcopy
from math import hypot

from .battle_termination import continuation_fact
from .common import InputError, identifier, number, require
from .damage_receipts import record_damage
from .rates import pause_attack_work
from .spatial import EPSILON, _active, _blocked, center, target_distance
from .spell_visibility import untargetable_until


RECIPE_SPELLS = {"totem-spell", "recall-spell"}
COMMON = {
    "source",
    "status",
    "caster_team",
    "radius_multiplier",
    "impact_delay_seconds",
    "geometry",
    "hidden_tesla_policy",
    "source_persistence",
}
SPECIFIC = {
    "totem-spell": {
        "landing_damage",
        "landing_stun_seconds",
        "landing_statistics_source",
        "decay_interval_seconds",
        "taunt",
        "decoy_interactions",
    },
    "recall-spell": {
        "selection",
        "hero_weight",
        "pet_weight",
        "state_policy",
        "redeployment",
    },
}


def validate_recipe_spell_parameters(entity, parameters):
    if not isinstance(parameters, dict) or set(parameters) != COMMON | SPECIFIC[entity]:
        raise InputError("Recipe spell requires every explicit contract field")
    for key in ("source",):
        identifier(parameters[key], key)
    for key, expected in {
        "status": "explicit_uncalibrated_hypothesis",
        "caster_team": "attack",
        "geometry": "live_center_distance",
        "hidden_tesla_policy": "exclude_hidden_teslas",
        "source_persistence": "released_cast_independent_of_attacker_survival",
    }.items():
        if parameters[key] != expected:
            raise InputError(f"Recipe spell requires {key}={expected}")
    number(parameters["radius_multiplier"], "spell radius multiplier", EPSILON)
    number(parameters["impact_delay_seconds"], "spell landing delay", 0)
    if entity == "totem-spell":
        for key in ("landing_damage", "landing_stun_seconds"):
            number(parameters[key], key, 0)
        identifier(
            parameters["landing_statistics_source"],
            "missing landing statistic hypothesis",
        )
        number(parameters["decay_interval_seconds"], "Totem decay interval", EPSILON, 1)
        if (
            parameters["taunt"]
            != "live_defenses_in_radius_force_all_new_acquisition_nearest_then_id"
        ):
            raise InputError("Totem taunt acquisition policy must be explicit")
        if (
            parameters["decoy_interactions"]
            != "immobile_both_weapon_layers_no_traps_buffs_healing_or_unit_status"
        ):
            raise InputError("Totem decoy interactions must be explicit")
    else:
        if (
            parameters["selection"]
            != "highest_housing_then_distance_then_id_skip_nonfitting"
        ):
            raise InputError("Recall capacity selection policy must be explicit")
        if parameters["hero_weight"] != 25 or parameters["pet_weight"] != 20:
            raise InputError("Recall uses published hero25/pet20 housing weights")
        if (
            parameters["state_policy"]
            != "preserve_hp_spent_ability_and_absolute_status_clocks_released_packets_continue"
        ):
            raise InputError("Recall preservation and clock policy must be explicit")
        deployment = parameters["redeployment"]
        if deployment is not None:
            if not isinstance(deployment, dict) or set(deployment) != {
                "time_seconds",
                "position",
                "regions",
                "source",
            }:
                raise InputError(
                    "Recall redeployment needs time, point and declared legal regions"
                )
            identifier(deployment["source"], "Recall deployment evidence")
            number(deployment["time_seconds"], "Recall redeployment time", 0)
            if set(deployment["position"]) != {"x", "y"}:
                raise InputError("Recall point needs x and y")
            for value in deployment["position"].values():
                number(value, "Recall coordinate", 0)
            if not isinstance(deployment["regions"], list) or not deployment["regions"]:
                raise InputError("Recall needs explicitly declared deployment regions")
            for region in deployment["regions"]:
                if set(region) != {"left", "right", "top", "bottom"}:
                    raise InputError("Recall region needs explicit rectangle bounds")
                for value in region.values():
                    number(value, "Recall region bound", 0)
                if (
                    region["left"] >= region["right"]
                    or region["top"] >= region["bottom"]
                ):
                    raise InputError(
                        "Recall deployment regions must have positive area"
                    )


def recipe_spell_quantities(entity, row, parameters):
    if entity["id"] == "totem-spell":
        return {
            "hitpoints": number(row["totemHitpoints"], "Totem HP", EPSILON),
            "decay_per_second": number(
                entity["hitpointDecayPerSecond"], "Totem HP decay", EPSILON
            ),
            "damage": parameters["landing_damage"],
            "stun_seconds": parameters["landing_stun_seconds"],
        }
    return {"capacity": number(row["recalledCapacity"], "Recall capacity", 1)}


def compile_totem_reserve(model):
    if model["entity"] != "totem-spell":
        return []
    source = model["statistics_source"]
    return [
        {
            "id": model["id"] + ":totem",
            "source": source,
            "team": "attack",
            "kind": "unit",
            "layer": "ground",
            "movement": "stationary",
            "spawn_seconds": "controlled",
            "first_attack_seconds": 0,
            "x": model["position"][0],
            "y": model["position"][1],
            "width": 0,
            "height": 0,
            "blocking": False,
            "counts_for_destruction": False,
            "hitpoints": model["quantities"]["hitpoints"],
            "damage": 0,
            "attack_interval_seconds": 1,
            "speed": 0,
            "range": 0,
            "minimum_range": 0,
            "target_priorities": [],
            "target_layers": [],
            "healing_class": "troop",
            "buff_class": "other",
            "hazard_class": "troop",
            "spring_class": "other",
            "beneficial_field_immunity": True,
            "attack_model": {"kind": "none", "source": source},
            "spell_decoy_model": {
                "cast_id": model["id"],
                "entity": "totem-spell",
                "parameters": deepcopy(model["parameters"]),
            },
            "entity_adapter": {
                **deepcopy(model["entity_adapter"]),
                "modifiers": {
                    "source": model["source"],
                    **{
                        field: 1
                        for field in (
                            "hitpoints_multiplier",
                            "damage_multiplier",
                            "maximum_hp_damage_multiplier",
                            "attack_interval_multiplier",
                            "range_multiplier",
                            "movement_speed_multiplier",
                        )
                    },
                },
            },
        }
    ]


class RecipeSpellCombat:
    def __init__(self, models, actors, width=None, height=None):
        self.models = {
            model["id"]: deepcopy(model)
            for model in models
            if model["entity"] in RECIPE_SPELLS
        }
        self.actors = actors
        self.width, self.height = width, height
        self.launched, self.resolved, self.returned = set(), set(), set()
        self.captured, self.decay = {}, {}
        self.pending_landing = set()
        for cast_id, model in self.models.items():
            validate_recipe_spell_parameters(model["entity"], model["parameters"])
            if model["entity"] == "totem-spell":
                actor = actors.get(cast_id + ":totem")
                if (
                    actor is None
                    or actor.get("spell_decoy_model", {}).get("cast_id") != cast_id
                ):
                    raise InputError(
                        "Every Totem cast must own one compiler-generated decoy"
                    )
                if (
                    actor["movement"] != "stationary"
                    or actor["damage"]
                    or actor["counts_for_destruction"]
                ):
                    raise InputError("Totem decoy role cannot be overridden")
                expected = compile_totem_reserve(model)[0]
                if any(actor.get(field) != expected[field] for field in expected):
                    raise InputError(
                        "Totem reserve differs from its paid spell contract"
                    )
            else:
                deployment = model["parameters"]["redeployment"]
                if (
                    deployment is not None
                    and deployment["time_seconds"] <= model["arrival_seconds"]
                ):
                    raise InputError("Recall redeployment must follow capture")
        expected = {
            key + ":totem"
            for key, model in self.models.items()
            if model["entity"] == "totem-spell"
        }
        if expected != {
            key for key, actor in actors.items() if "spell_decoy_model" in actor
        }:
            raise InputError("Unowned Totem decoy is forbidden")

    @staticmethod
    def _inside(model, actor):
        point = center(actor)
        return (
            hypot(point[0] - model["position"][0], point[1] - model["position"][1])
            <= model["radius"] + EPSILON
        )

    def _weight(self, actor, model):
        if "spell_decoy_model" in actor or "siege_model" in actor:
            return None
        if "hero_model" in actor or actor.get("healing_class") == "hero":
            return model["parameters"]["hero_weight"]
        if "pet_model" in actor:
            return model["parameters"]["pet_weight"]
        weight = actor.get("housing_space")
        if weight is None:
            raise InputError(
                "Recall needs explicit housing weight for every eligible troop, including generated troops"
            )
        return number(weight, "Recall troop housing", 1)

    def _capture(self, model, time, trace):
        remaining = model["quantities"]["capacity"]
        choices = []
        for key, actor in self.actors.items():
            if (
                actor["team"] != "attack"
                or actor["kind"] != "unit"
                or not _active(actor, time)
                or not self._inside(model, actor)
            ):
                continue
            weight = self._weight(actor, model)
            if weight is None:
                continue
            point = center(actor)
            distance = hypot(
                point[0] - model["position"][0], point[1] - model["position"][1]
            )
            choices.append((-weight, distance, key))
        captured = []
        for negative_weight, _, key in sorted(choices):
            weight = -negative_weight
            if weight > remaining:
                continue
            actor = self.actors[key]
            actor["_recalled"] = True
            actor["target"] = None
            actor.pop("_remaining_path", None)
            actor.pop("_path_signature", None)
            captured.append(key)
            remaining -= weight
        self.captured[model["id"]] = captured
        trace.append(
            {
                "event": "recall_capture",
                "time_seconds": time,
                "cast_id": model["id"],
                "actors": list(captured),
                "capacity_used": model["quantities"]["capacity"] - remaining,
            }
        )

    def _redeploy(self, model, time, trace):
        command = model["parameters"]["redeployment"]
        point = command["position"]
        if (
            self.width is None
            or self.height is None
            or not (0 <= point["x"] < self.width and 0 <= point["y"] < self.height)
        ):
            raise InputError("Recall redeployment must lie inside the battle board")
        if not any(
            region["left"] <= point["x"] < region["right"]
            and region["top"] <= point["y"] < region["bottom"]
            for region in command["regions"]
        ):
            raise InputError("Recall redeployment is outside declared legal regions")
        blocked = _blocked(self.actors, time)
        from math import floor

        cell = floor(point["x"]), floor(point["y"])
        owned = self.captured[model["id"]]
        if any(not self.actors[key].get("_recalled") for key in owned):
            raise InputError("Recall group lost ownership before redeployment")
        keys = [key for key in owned if self.actors[key]["hp"] > 0]
        if cell in blocked and any(
            self.actors[key]["movement"] == "ground" for key in keys
        ):
            raise InputError(
                "Recall cannot redeploy a ground member into a live blocking footprint"
            )
        for key in keys:
            actor = self.actors[key]
            actor["x"], actor["y"] = point["x"], point["y"]
            actor["_recalled"] = False
            actor["target"] = None
            actor.pop("_remaining_path", None)
            actor.pop("_path_signature", None)
        self.returned.add(model["id"])
        trace.append(
            {
                "event": "recall_redeployment",
                "time_seconds": time,
                "cast_id": model["id"],
                "actors": list(keys),
                "position": deepcopy(point),
                "additional_army_spend": 0,
            }
        )

    def prepare(self, time, trace):
        for cast_id, model in sorted(
            self.models.items(), key=lambda item: (item[1]["time_seconds"], item[0])
        ):
            if model["time_seconds"] <= time + EPSILON and cast_id not in self.launched:
                self.launched.add(cast_id)
                trace.append(
                    {
                        "event": "attack_spell_cast",
                        "time_seconds": time,
                        "cast_id": cast_id,
                        "entity": model["entity"],
                    }
                )
            if (
                cast_id in self.launched
                and cast_id not in self.resolved
                and model["arrival_seconds"] <= time + EPSILON
            ):
                self.resolved.add(cast_id)
                if model["entity"] == "totem-spell":
                    actor = self.actors[cast_id + ":totem"]
                    actor["spawn_seconds"] = time
                    self.pending_landing.add(cast_id)
                    self.decay[cast_id] = time
                    trace.append(
                        {
                            "event": "totem_landed",
                            "time_seconds": time,
                            "cast_id": cast_id,
                            "actor": actor["id"],
                        }
                    )
                else:
                    self._capture(model, time, trace)
            if (
                model["entity"] == "recall-spell"
                and cast_id in self.captured
                and cast_id not in self.returned
            ):
                deployment = model["parameters"]["redeployment"]
                if (
                    deployment is not None
                    and deployment["time_seconds"] <= time + EPSILON
                ):
                    self._redeploy(model, time, trace)
        for cast_id, previous in list(self.decay.items()):
            model = self.models[cast_id]
            actor = self.actors[cast_id + ":totem"]
            if actor["hp"] <= 0:
                del self.decay[cast_id]
            elif time > previous:
                actor["hp"] = max(
                    0,
                    actor["hp"]
                    - model["quantities"]["decay_per_second"] * (time - previous),
                )
                self.decay[cast_id] = time
                if actor["hp"] <= EPSILON:
                    actor["hp"] = 0
                    actor["death_time"] = time
                    del self.decay[cast_id]
                    trace.append(
                        {
                            "event": "totem_expired",
                            "time_seconds": time,
                            "cast_id": cast_id,
                        }
                    )
        for actor in self.actors.values():
            actor.pop("_totem_forced_target", None)
            if (
                actor["team"] != "defense"
                or actor["kind"] != "defense"
                or not _active(actor, time)
            ):
                continue
            choices = []
            for cast_id in self.decay:
                decoy = self.actors[cast_id + ":totem"]
                model = self.models[cast_id]
                if (
                    _active(decoy, time)
                    and self._inside(model, actor)
                    and untargetable_until(decoy) <= time + EPSILON
                ):
                    choices.append((target_distance(center(actor), decoy), decoy["id"]))
            if choices:
                actor["_totem_forced_target"] = min(choices)[1]

    def resolve(self, time, trace, status_observer=None):
        damage = defaultdict(float)
        for cast_id in sorted(self.pending_landing):
            model = self.models[cast_id]
            stunned = []
            for key, actor in self.actors.items():
                if (
                    actor["team"] != "defense"
                    or actor["kind"] == "wall"
                    or not _active(actor, time)
                    or actor.get("_tesla_hidden")
                    or not self._inside(model, actor)
                ):
                    continue
                amount = record_damage(
                    self,
                    actor,
                    model["quantities"]["damage"],
                    time,
                    source_id=cast_id,
                    source_team="attack",
                    origin="spell",
                )
                damage[key] += amount
                if actor["immune_until"] <= time + EPSILON:
                    stunned.append(key)
            duration = model["quantities"]["stun_seconds"]
            if duration > 0 and stunned:
                command = {
                    "id": cast_id + ":stun",
                    "kind": "freeze",
                    "time_seconds": time,
                    "targets": stunned,
                    "duration_seconds": duration,
                    "source": model["source"],
                }
                if status_observer is not None:
                    status_observer([command], self.actors, time, trace)
                for key in stunned:
                    actor = self.actors[key]
                    pause_attack_work(actor, time, time + duration)
                    actor["frozen_until"] = max(actor["frozen_until"], time + duration)
            trace.append(
                {
                    "event": "totem_landing_effect",
                    "time_seconds": time,
                    "cast_id": cast_id,
                    "targets": sorted(damage),
                    "stunned": stunned,
                }
            )
        self.pending_landing.clear()
        return damage

    def next_boundary(self, time):
        boundaries = []
        for key, model in self.models.items():
            if key not in self.launched:
                boundaries.append(model["time_seconds"])
            if key not in self.resolved:
                boundaries.append(model["arrival_seconds"])
            deployment = model["parameters"].get("redeployment")
            if (
                deployment is not None
                and key in self.captured
                and key not in self.returned
            ):
                boundaries.append(deployment["time_seconds"])
        for key, previous in self.decay.items():
            model = self.models[key]
            hp = self.actors[key + ":totem"]["hp"]
            if hp > 0:
                boundaries.append(
                    previous
                    + min(
                        model["parameters"]["decay_interval_seconds"],
                        hp / model["quantities"]["decay_per_second"],
                    )
                )
        future = [value for value in boundaries if value > time + EPSILON]
        return min(future) if future else None

    def continuation_reasons(self, time):
        facts = []
        for key in self.launched - self.resolved:
            model = self.models[key]
            if model["entity"] == "totem-spell" and model["quantities"]["damage"] > 0:
                facts.append(
                    continuation_fact(
                        "pending_damage",
                        "totem:" + key,
                        not_before_seconds=model["arrival_seconds"],
                    )
                )
        for key, members in self.captured.items():
            deployment = self.models[key]["parameters"]["redeployment"]
            live_members = [
                member
                for member in members
                if self.actors[member]["hp"] > 0
                and self.actors[member].get("_recalled")
            ]
            if live_members and key not in self.returned and deployment is not None:
                facts.append(
                    continuation_fact(
                        "pending_release",
                        "recall:" + key,
                        live_members,
                        not_before_seconds=deployment["time_seconds"],
                    )
                )
        return facts

    def result(self):
        return {
            "launched": sorted(self.launched),
            "resolved": sorted(self.resolved),
            "recall_groups": deepcopy(self.captured),
            "redeployed": sorted(self.returned),
            "active_totems": sorted(self.decay),
            "status": "explicit_uncalibrated_hypothesis",
        }
