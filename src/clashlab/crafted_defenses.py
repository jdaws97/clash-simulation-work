"""Conditional phase-4 crafted weapons; the Station is not a weapon substitute."""

from collections import defaultdict
from copy import deepcopy
from heapq import heappop, heappush
from math import nextafter, inf, isfinite

from .crafted_selection import (
    VARIANTS,
    selected_modules,
    validate_availability,
    selection_projection,
)
from .battle_termination import continuation_fact
from .common import InputError, identifier, integer, number, require
from .damage_receipts import record_damage
from .hazards import validate_hazard
from .rates import attack_rate
from .buffs import damage_multiplier
from .spatial import EPSILON, _active, _eligible, center, target_distance


SCOPE = "conditional_phase4_crafted_defenses"
WEAPON_KIND = "crafted_phase4_weapon"


def _clock_after(time, delay):
    result = time + delay
    if not isfinite(result):
        raise InputError("Crafted clock must remain finite")
    return nextafter(time, inf) if delay > 0 and result <= time else result


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise InputError(label + " requires its complete explicit contract")


def compile_crafted_defense(actor, instance, catalog, secondary_station):
    """Bind one counted Station actor to three independent module selections.

    Catalog current flags are not October certification. All uncertain geometry,
    projectile, second melt and poison-field policies remain explicit experiments.
    """
    p = deepcopy(require(instance, "crafted_parameters"))
    _fields(
        {key: value for key, value in p.items() if key != "availability_policy"},
        {
            "source",
            "status",
            "scope",
            "variant",
            "phase",
            "as_of_date",
            "rotation_policy",
            "module_levels",
            "module_statistics_policy",
            "projectile_delay_seconds",
            "impact_position",
            "minimum_range_policy",
            "hero_selector",
            "candle",
            "poison",
        },
        "Crafted defense",
    )
    identifier(p["source"], "crafted evidence")
    if (
        p["scope"] != SCOPE
        or p["status"] != "explicit_uncalibrated_hypothesis"
        or p["rotation_policy"]
        != "explicit_phase4_selection_not_current_date_certified"
        or p["module_statistics_policy"]
        != "pinned_catalog_crosschecked_secondary_module_rows"
    ):
        raise InputError(
            "Crafting rotation and statistics must be explicitly conditional"
        )
    identifier(p["as_of_date"], "crafted observation date")
    variant = p["variant"]
    if variant not in VARIANTS or p["phase"] != 4:
        raise InputError("Historical or unknown crafted rotation is unavailable")
    if (
        instance["entity"] != "crafting-station"
        or instance["level"] != 1
        or instance["supercharge"]
        or instance["mode"] != "normal"
        or instance["statistics_mode"] != "normal"
        or actor["team"] != "defense"
        or actor["kind"] != "defense"
        or not actor["counts_for_destruction"]
    ):
        raise InputError(
            "A crafted weapon requires one ordinary counted defending Station"
        )
    th = instance["town_hall"]
    entity, values, rows = selected_modules(p, th, catalog, secondary_station)
    stats = deepcopy(entity["stats"])
    interval = number(stats["attackSpeed"], "crafted cadence", 1e-10)
    damage = values["Damage"] * (interval if variant != "cake-a-pult" else 1)
    hp_raw, weapon_raw = rows[0]["ability_data"], rows[1]["ability_data"]
    raw_damage = weapon_raw.get("Damage", weapon_raw.get("DPS", 0) * interval)
    if (
        hp_raw.get("HealthOverride") != values["Hitpoints"]
        or weapon_raw.get("AttackSpeed") != interval * 1000
        or abs(raw_damage - damage) > 1e-8
    ):
        raise InputError("Catalog and secondary selected combat module values disagree")
    number(p["projectile_delay_seconds"], "crafted projectile delay", 0)
    if (
        p["impact_position"] != "launch_sampled_primary_center"
        or p["minimum_range_policy"] != "launch_eligibility_only"
    ):
        raise InputError("Unknown crafted projectile or minimum-range policy")
    expected_selector = (
        "heroes_first_nearest_then_id" if variant == "hero-hunter" else "not_applicable"
    )
    if p["hero_selector"] != expected_selector:
        raise InputError("Crafted selector must be explicit")
    if variant == "hot-candle":
        _fields(
            p["candle"],
            {"second_decay_after_first_seconds", "melt_clock", "freeze", "launch_cap"},
            "Candle melt",
        )
        number(
            p["candle"]["second_decay_after_first_seconds"],
            "second Candle decay",
            1e-10,
        )
        if (
            p["candle"]["melt_clock"] != "battle_start_zero"
            or p["candle"]["freeze"] != "melt_clock_continues_experimental"
            or p["candle"]["launch_cap"] != "live_capacity_at_launch_distinct_targets"
        ):
            raise InputError(
                "Candle decay requires explicit battle-time/Freeze/selection policies"
            )
    elif p["candle"] is not None:
        raise InputError("Only Hot Candle owns a melt clock")
    poison = None
    if variant == "hero-hunter":
        _fields(
            p["poison"],
            {
                "membership",
                "radius",
                "pulse_interval_seconds",
                "first_pulse_offset_seconds",
                "growth_by_field_age",
                "exit_linger_seconds",
                "protection_policy",
                "excluded_classes",
            },
            "Hunter poison",
        )
        if p["poison"]["membership"] != "impact_anchored_shared_hazard_experimental":
            raise InputError(
                "Hunter poison membership is unknown without an explicit experiment"
            )
        poison_level = integer(values["Poison Level"], "Hunter Poison level", 1)
        if rows[2]["ability_data"].get("PoisonOnHitSpellLevel") != poison_level:
            raise InputError("Hunter Poison level source mismatch")
        poison = deepcopy(catalog.level("poison-spell", poison_level))
    elif p["poison"] is not None:
        raise InputError("Only Hero Hunter owns poison")
    modifiers = instance["modifiers"]
    width, height = map(int, entity["size"].split("x"))
    actor.update(
        hitpoints=values["Hitpoints"] * modifiers["hitpoints_multiplier"],
        damage=0,
        attack_interval_seconds=interval * modifiers["attack_interval_multiplier"],
        range=stats["range"] * modifiers["range_multiplier"],
        minimum_range=stats.get("minRange", 0),
        movement="stationary",
        speed=0,
        width=width,
        height=height,
        blocking=True,
        target_priorities=["unit"],
        target_priority_tiers=[["unit"]],
        target_layers=["ground", "air"],
        attack_model={"kind": WEAPON_KIND, "source": p["source"]},
    )
    actor["crafted_defense_model"] = {
        "variant": variant,
        "availability": validate_availability(p, th),
        "parameters": p,
        "statistics": stats,
        "values": values,
        "damage_per_hit": damage * modifiers["damage_multiplier"],
        "explosion_damage": values.get("Explosion Damage", 0)
        * modifiers["damage_multiplier"],
        "poison_row": poison,
        "poison_maximum_dps": poison["maxDamagePerSecond"] if poison is not None else 0,
        "catalog_source": catalog.records[variant]["source"],
        "secondary_module_rows": rows,
    }
    actor["entity_adapter"]["crafted_parameters"] = deepcopy(p)
    return actor


class CraftedDefenseCombat:
    """Released cake/bombs/cards/flames survive source loss; no duplicate clock."""

    def __init__(self, actors, hazards):
        self.actors, self.hazards = actors, hazards
        self.models = {
            key: deepcopy(a["crafted_defense_model"])
            for key, a in actors.items()
            if "crafted_defense_model" in a
        }
        self.pending, self.serial, self.impacts = [], 0, []
        for key in self.models:
            actor = actors[key]
            if (
                actor["team"] != "defense"
                or actor["kind"] != "defense"
                or actor["attack_model"]["kind"] != WEAPON_KIND
                or actor["damage"] != 0
            ):
                raise InputError(
                    "Crafted runtime requires a dedicated nonfallback Station weapon"
                )
            if actor["spawn_seconds"] != 0:
                raise InputError(
                    "Crafted defenses exist at battle start, never on scouting/deployment clocks"
                )
            if self.models[key]["variant"] == "hero-hunter":
                if hazards is None:
                    raise InputError(
                        "Hero Hunter requires the shared poison hazard scheduler"
                    )
                validate_hazard(
                    self._poison_field({"point": center(actor)}, self.models[key], 0),
                    actors,
                )

    def capacity(self, key, time):
        model = self.models[key]
        if model["variant"] != "hot-candle":
            return 1
        first = model["values"]["Seconds Active"]
        second = _clock_after(
            first, model["parameters"]["candle"]["second_decay_after_first_seconds"]
        )
        field = (
            "targetsBaseForm"
            if time < first
            else "targetsFirstDecay" if time < second else "targetsSecondDecay"
        )
        return integer(model["statistics"][field], "Candle target capacity", 1)

    def select_targets(self, key, time):
        actor = self.actors[key]
        targets = [
            t
            for t in self.actors.values()
            if _eligible(actor, t, time)
            and actor["minimum_range"] - EPSILON
            <= target_distance(center(actor), t)
            <= actor["range"] + EPSILON
        ]
        hunter = self.models[key]["variant"] == "hero-hunter"
        targets.sort(
            key=lambda t: (
                0 if hunter and t.get("healing_class") == "hero" else 1,
                target_distance(center(actor), t),
                t["id"],
            )
        )
        return targets[: self.capacity(key, time)]

    def launch(self, key, time, trace):
        actor, model = self.actors[key], self.models[key]
        if (
            not _active(actor, time)
            or actor["frozen_until"] > time
            or actor["next_attack"] > time
        ):
            return False
        targets = self.select_targets(key, time)
        if not targets:
            return False
        for target in targets:
            self.serial += 1
            amount = model["damage_per_hit"] * damage_multiplier(actor)
            if (
                model["variant"] == "hero-hunter"
                and target.get("healing_class") == "hero"
            ):
                amount *= model["statistics"]["heroDamageMultiplier"]
            packet = {
                "source": key,
                "target": target["id"],
                "point": center(target),
                "amount": amount,
                "explosion_amount": model["explosion_damage"]
                * damage_multiplier(actor),
                "kind": "shot",
            }
            due = _clock_after(time, model["parameters"]["projectile_delay_seconds"])
            heappush(self.pending, (due, self.serial, packet))
        actor["next_attack"] = _clock_after(
            time, actor["attack_interval_seconds"] / attack_rate(actor)
        )
        trace.append(
            {
                "event": "crafted_launch",
                "source": key,
                "targets": [t["id"] for t in targets],
                "time_seconds": time,
            }
        )
        return True

    def _poison_field(self, packet, model, time):
        p, row = model["parameters"]["poison"], model["poison_row"]
        field = {
            k: deepcopy(v) for k, v in p.items() if k not in {"membership", "radius"}
        }
        field.update(
            id="crafted-poison-" + str(self.serial),
            source=model["parameters"]["source"],
            source_team="defense",
            start_seconds=time,
            duration_seconds=model["statistics"]["poisonDuration"],
            maximum_dps=model["poison_maximum_dps"],
            movement_multiplier=1 - row["speedDecrease"] / 100,
            attack_rate_multiplier=1 - row["attackRateDecrease"] / 100,
            area={
                "x": packet["point"][0],
                "y": packet["point"][1],
                "radius": p["radius"],
                "target_team": "attack",
                "target_kinds": ["unit"],
                "target_layers": ["ground", "air"],
            },
        )
        return field

    def _poison(self, packet, model, time):
        field = self._poison_field(packet, model, time)
        self.hazards.schedule(field, self.actors, source_actor_id=packet["source"])

    def resolve(self, time, trace):
        damage = defaultdict(float)
        while self.pending and self.pending[0][0] <= time:
            due, serial, packet = heappop(self.pending)
            if due < time:
                raise InputError("Crafted impact boundary was skipped")
            model = self.models[packet["source"]]
            cake = model["variant"] == "cake-a-pult"
            if cake:
                radius = model["statistics"][
                    (
                        "bombExplosionRadius"
                        if packet["kind"] == "bomb"
                        else "splashRadius"
                    )
                ]
                targets = [
                    t
                    for t in self.actors.values()
                    if _active(t, time)
                    and t["team"] == "attack"
                    and t["kind"] == "unit"
                    and t["layer"] in {"ground", "air"}
                    and target_distance(packet["point"], t) <= radius
                ]
                if packet["kind"] == "shot":
                    bomb = deepcopy(packet)
                    bomb.update(kind="bomb", amount=packet["explosion_amount"])
                    self.serial += 1
                    heappush(
                        self.pending,
                        (
                            _clock_after(
                                time, model["statistics"]["bombDetonationDelay"]
                            ),
                            self.serial,
                            bomb,
                        ),
                    )
            else:
                target = self.actors[packet["target"]]
                targets = (
                    [target]
                    if _active(target, time) and target["team"] == "attack"
                    else []
                )
            for target in targets:
                value = record_damage(
                    self,
                    target,
                    packet["amount"],
                    time,
                    source_id=packet["source"],
                    source_actor_id=packet["source"],
                    source_team="defense",
                    origin="weapon",
                )
                damage[target["id"]] += value
                trace.append(
                    {
                        "event": "crafted_" + packet["kind"] + "_impact",
                        "source": packet["source"],
                        "target": target["id"],
                        "amount": value,
                        "time_seconds": time,
                    }
                )
            if model["variant"] == "hero-hunter" and targets:
                self.serial += 1
                self._poison(packet, model, time)
        return damage

    def next_boundary(self, time):
        times = [due for due, _, _ in self.pending if due > time]
        for key, model in self.models.items():
            actor = self.actors[key]
            if _active(actor, time):
                times.extend(
                    t for t in (actor["next_attack"], actor["frozen_until"]) if t > time
                )
            if model["variant"] == "hot-candle" and _active(self.actors[key], time):
                first = model["values"]["Seconds Active"]
                times.extend(
                    t
                    for t in (
                        first,
                        _clock_after(
                            first,
                            model["parameters"]["candle"][
                                "second_decay_after_first_seconds"
                            ],
                        ),
                    )
                    if t > time
                )
        return min(times) if times else None

    def continuation_reasons(self, time):
        return [
            continuation_fact(
                "pending_damage",
                "crafted:" + str(serial),
                [packet["source"]],
                source_team="defense",
                not_before_seconds=due,
            )
            for due, serial, packet in self.pending
        ]

    def result(self):
        return {
            "status": "CONDITIONAL_PHASE4_NOT_CURRENT_DATE_CERTIFIED",
            "pending_count": len(self.pending),
            "variants": {key: m["variant"] for key, m in self.models.items()},
            "selections": {
                key: selection_projection(m["parameters"])
                for key, m in self.models.items()
            },
            "availability": {
                key: deepcopy(m.get("availability")) for key, m in self.models.items()
            },
            "catalog_sources": {
                key: m["catalog_source"] for key, m in self.models.items()
            },
        }
