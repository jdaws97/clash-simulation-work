"""Opt-in, per-hit Poison Lizard exposure; shared status and damage settlement.

Publisher sources establish defender preference and building slow exclusion.
The pinned row establishes ceilings, not a ramp or duration. Every temporal
choice below is caller-declared experimental input. No spell poison is borrowed.
"""

from collections import defaultdict
from copy import deepcopy

from .common import InputError, identifier, number
from .equipment_event_clock import advancing_deadline
from .equipment_gap_sources import explicit_policy, selected_row
from .hero_extensions import require_fields
from .spatial import EPSILON, _active, center, target_distance


POLICIES = {
    "experimental_policy": "poison_lizard_exposure_v1_uncalibrated",
    "refresh": "extend_expiry_preserve_first_hit_ramp_and_pulse_grid",
    "stacking": "independent_source_damage_shared_strongest_slow",
    "source_loss": "existing_exposures_persist_death_freeze_recall_retarget",
    "target_recall": "absolute_expiry_skip_held_pulses_no_catchup_restore_remaining_slow",
    "target_death": "discard_exposure_no_revival_restore",
    "tick": "right_endpoint_rate_times_interval_first_after_one_interval_expiry_exclusive",
    "protection": "damage_immunity_does_not_block_exposure_or_slow",
    "buildings": "ordinary_hit_only_no_poison_or_slow",
    "poison_targets": "explicit_hero_troop_guardian_roles_guardian_inclusion_experimental",
    "targeting": "nearby_defenders_then_owner_building_then_ordinary_selector",
}
NUMERIC = {"duration_seconds", "pulse_seconds", "ramp_knots", "defender_radius_tiles"}
ROLES = {"hero", "troop", "guardian", "building"}


def compile_model(catalog, level, town_hall, parameters):
    explicit_policy(parameters, POLICIES, NUMERIC)
    duration = number(
        parameters["duration_seconds"], "lizard exposure duration", EPSILON
    )
    pulse = number(parameters["pulse_seconds"], "lizard pulse interval", EPSILON)
    if pulse >= duration:
        raise InputError("Lizard exposure must contain at least one pulse")
    number(parameters["defender_radius_tiles"], "lizard defender acquisition radius", 0)
    knots = parameters["ramp_knots"]
    if not isinstance(knots, list) or len(knots) < 2:
        raise InputError("Lizard needs an explicit piecewise-linear ramp")
    previous = -1
    strength = -1
    for knot in knots:
        require_fields(knot, {"seconds", "fraction_of_max_dps"}, "Lizard ramp knot")
        clock = number(knot["seconds"], "lizard ramp clock", 0)
        factor = number(knot["fraction_of_max_dps"], "lizard ramp factor", 0, 1)
        if clock <= previous or factor < strength:
            raise InputError(
                "Lizard ramp time must increase and damage cannot decrease"
            )
        previous, strength = clock, factor
    if knots[0]["seconds"] != 0 or strength != 1:
        raise InputError(
            "Lizard ramp starts at zero age and explicitly reaches its ceiling"
        )
    row = selected_row(catalog, "poison-lizard", level, town_hall)
    return {
        "entity": "poison-lizard",
        "level": level,
        "statistics_source": catalog.records["poison-lizard"]["source"],
        "parameters": deepcopy(parameters),
        "max_dps": number(row["poisonMaxDps"], "lizard poison ceiling", 0),
        "attack_rate_multiplier": 1
        - number(row["poisonAttackRateDecreasePercent"], "lizard attack slow", 0, 100)
        / 100,
        "movement_multiplier": 1
        - number(row["poisonSpeedDecreasePercent"], "lizard movement slow", 0, 100)
        / 100,
    }


class PoisonLizardExposure:
    """Impact adapter. The common weapon still owns launch and ordinary damage.

    Call resolve at next_boundary before later-time impacts; same-time impacts may
    refresh before resolve. Receipts must settle at every boundary. Models are
    compiled inside this constructor so raw callers cannot replace source ceilings.
    """

    def __init__(self, catalog, assignments, target_roles, hit_status):
        self.models = {}
        for actor_id, assignment in assignments.items():
            identifier(actor_id, "lizard actor identity")
            require_fields(
                assignment, {"level", "town_hall", "parameters"}, "Lizard assignment"
            )
            self.models[actor_id] = compile_model(catalog, **assignment)
        self.roles = deepcopy(target_roles)
        for actor_id, role in self.roles.items():
            identifier(actor_id, "lizard target identity")
            if role not in ROLES:
                raise InputError(
                    "Lizard target requires explicit defender/building role"
                )
        self.hit_status = hit_status
        self.exposures = {}
        self.seen_impacts = {}
        self.last_time = 0

    def preferred_targets(self, source_id, source, actors, owner_target_id, time):
        radius = self.models[source_id]["parameters"]["defender_radius_tiles"]
        candidates = []
        for key, target in actors.items():
            if target["team"] == source["team"] or not _active(target, time):
                continue
            role = self.roles.get(key)
            if role is None:
                raise InputError("Lizard defender role binding missing")
            distance = target_distance(center(source), target)
            if role != "building" and distance <= radius + EPSILON:
                candidates.append((distance, key))
        if candidates:
            return [key for _, key in sorted(candidates)]
        owner_target = actors.get(owner_target_id)
        if (
            owner_target is not None
            and _active(owner_target, time)
            and owner_target["team"] != source["team"]
            and self.roles.get(owner_target_id) == "building"
        ):
            return [owner_target_id]
        return []  # Delegate reachable/visible eligibility and ordinary fallback.

    def _check_time(self, time):
        number(time, "lizard event time", 0)
        boundary = self.next_boundary()
        if time < self.last_time or (boundary is not None and time > boundary):
            raise InputError(
                "Lizard event clock skipped or reversed an exposure boundary"
            )
        self.last_time = time

    def _slow(self, source_id, target, actors, exposure, time, trace):
        model = self.models[source_id]
        self.hit_status.impact(
            {
                "source": "poison-lizard:" + source_id,
                "on_hit_status": {
                    "source": model["statistics_source"],
                    "duration_seconds": exposure["expires_at"] - time,
                    "attack_rate_multiplier": model["attack_rate_multiplier"],
                    "movement_multiplier": model["movement_multiplier"],
                    "protection_policy": "damage_immunity_does_not_block_status",
                },
            },
            target,
            actors,
            time,
            trace,
        )

    def impact(self, impact_id, packet, target, actors, time, trace):
        """Called only for a successful shared hit, with a stable impact ID."""
        self._check_time(time)
        identifier(impact_id, "lizard impact ID")
        source_id = packet["source"]
        if source_id not in self.models:
            return
        if packet["source_team"] != "attack":
            raise InputError("Poison Lizard requires a captured attacking pet source")
        signature = (source_id, target["id"], packet["source_team"], time)
        if impact_id in self.seen_impacts:
            if self.seen_impacts[impact_id] != signature:
                raise InputError("Lizard impact identity was reused inconsistently")
            return
        self.seen_impacts[impact_id] = signature
        if not _active(target, time) or target["team"] == packet["source_team"]:
            return
        role = self.roles.get(target["id"])
        if role is None:
            raise InputError("Lizard impact requires an explicit target role")
        if role == "building":
            if target["kind"] not in {"building", "defense"}:
                raise InputError("Lizard building exclusion cannot hide an enemy unit")
            return
        if target["kind"] != "unit":
            raise InputError("Lizard defender role cannot describe a building")
        model = self.models[source_id]
        parameters = model["parameters"]
        key = source_id, target["id"]
        exposure = self.exposures.get(key)
        expires_at = advancing_deadline(
            time, parameters["duration_seconds"], "lizard exposure"
        )
        if exposure is None or exposure["expires_at"] <= time:
            next_pulse = advancing_deadline(
                time, parameters["pulse_seconds"], "lizard first pulse"
            )
            if next_pulse >= expires_at:
                raise InputError("Lizard first pulse must precede exposure expiry")
            exposure = {
                "starts_at": time,
                "next_pulse": next_pulse,
                "source_team": packet["source_team"],
                "held": False,
            }
            self.exposures[key] = exposure
        exposure["expires_at"] = expires_at
        self._slow(source_id, target, actors, exposure, time, trace)

    def _fraction(self, model, age):
        knots = model["parameters"]["ramp_knots"]
        for left, right in zip(knots, knots[1:]):
            if age < right["seconds"]:
                t = (age - left["seconds"]) / (right["seconds"] - left["seconds"])
                return (
                    left["fraction_of_max_dps"] * (1 - t)
                    + right["fraction_of_max_dps"] * t
                )
        return 1

    def resolve(self, actors, time, trace, receipts):
        self._check_time(time)
        damage = defaultdict(float)
        for (source_id, target_id), exposure in list(self.exposures.items()):
            target = actors[target_id]
            if target["hp"] <= 0 or time >= exposure["expires_at"]:
                del self.exposures[source_id, target_id]
                continue
            active = _active(target, time)
            if active and exposure["held"]:
                self._slow(source_id, target, actors, exposure, time, trace)
            exposure["held"] = not active
            if exposure["next_pulse"] > time:
                continue
            model = self.models[source_id]
            interval = model["parameters"]["pulse_seconds"]
            exposure["next_pulse"] = advancing_deadline(
                exposure["next_pulse"], interval, "lizard next pulse"
            )
            if not active:
                continue
            requested = (
                model["max_dps"]
                * self._fraction(model, time - exposure["starts_at"])
                * interval
            )
            damage[target_id] += receipts.register(
                target,
                requested,
                time,
                source_id="poison-lizard:" + source_id,
                source_actor_id=source_id,
                source_team=exposure["source_team"],
                origin="ability",
            )
            trace.append(
                {
                    "event": "poison_lizard_pulse",
                    "time_seconds": time,
                    "source": source_id,
                    "target": target_id,
                    "requested_damage": requested,
                }
            )
        return dict(damage)

    def next_boundary(self):
        return min(
            (min(e["next_pulse"], e["expires_at"]) for e in self.exposures.values()),
            default=None,
        )

    def after_health(self, actors):
        """Call after lethal settlement, before any later revival transition."""
        for source_id, target_id in list(self.exposures):
            if actors[target_id]["hp"] <= 0:
                del self.exposures[source_id, target_id]
                self.hit_status.exposures.pop(
                    (target_id, "poison-lizard:" + source_id), None
                )

    def continuation_reasons(self):
        from .battle_termination import continuation_fact

        return [
            continuation_fact(
                "lingering_damage",
                f"poison-lizard:{source}:{target}",
                [source],
                not_before_seconds=e["next_pulse"],
                expires_at_seconds=e["expires_at"],
            )
            for (source, target), e in sorted(self.exposures.items())
            if e["source_team"] == "attack" and e["next_pulse"] < e["expires_at"]
        ]

    def result(self):
        return {
            "calibrated": False,
            "models": deepcopy(self.models),
            "exposures": [
                {"source": source, "target": target, **deepcopy(e)}
                for (source, target), e in sorted(self.exposures.items())
            ],
        }
