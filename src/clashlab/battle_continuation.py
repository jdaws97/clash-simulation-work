"""Read continuation facts from the owners of released combat and latent units.

These collectors do not advance runtime state or predict whether a future hit
will find a target. A pending positive damage packet remains relevant after its
source dies. A controlled reserve matters only when its owning lifecycle can
still release or reactivate it.
"""

from math import ceil

from .battle_termination import EPSILON, continuation_fact
from .common import InputError, require


def pattern_continuation(patterns):
    if patterns is None:
        return []
    return [
        continuation_fact(
            "pending_damage",
            f"weapon:{serial}",
            [packet["source"]],
            source_team=packet["source_team"],
            not_before_seconds=arrival,
        )
        for arrival, serial, packet in patterns.pending
        if packet["source_team"] == "attack"
        and (
            packet["flat_damage"] > 0
            or packet["pattern"].get("maximum_hp_fraction", 0) > 0
        )
    ]


def death_continuation(deaths, actors):
    if deaths is None:
        return []
    return [
        continuation_fact(
            "pending_damage",
            f"death:{serial}:{effect['id']}",
            [effect["death_source"]],
            source_team=actors[effect["death_source"]]["team"],
            not_before_seconds=arrival,
        )
        for arrival, serial, effect in deaths.pending
        if effect["kind"] == "area_damage"
        and effect["amount"] > 0
        and actors[effect["death_source"]]["team"] == "attack"
    ]


def siege_continuation(siege):
    if siege is None:
        return []
    return [
        continuation_fact(
            "pending_damage",
            f"siege:{serial}",
            [packet["source"]],
            source_team=packet["source_team"],
            not_before_seconds=arrival,
        )
        for arrival, serial, packet in siege.pending
        if packet["source_team"] == "attack" and packet["amount"] > 0
    ]


def reinforcement_continuation(reinforcements):
    if reinforcements is None:
        return []
    state = reinforcements.state
    members = list(state["remaining"])
    if not members or state["phase"] == "empty":
        return []
    delivery = reinforcements.parameters["delivery"]
    if state["phase"] == "waiting_for_delivery" and delivery["kind"] == "siege":
        carrier = reinforcements.actors[delivery["carrier_id"]]
        if carrier["hp"] <= 0:
            return []
    return [
        continuation_fact(
            "pending_release",
            f"payload:{reinforcements.parameters['id']}",
            members,
            not_before_seconds=state["next_release"],
        )
    ]


def pet_continuation(pets):
    if pets is None:
        return []
    facts = []
    for pet_id, state in pets.states.items():
        actor = pets.actors[pet_id]
        if actor.get("_recalled", False):
            continue
        if actor["hp"] <= 0 or state["phase"] in {
            "dead",
            "waiting_for_owner",
            "active",
        }:
            continue
        if state["phase"] == "attached":
            facts.extend(
                fact
                for fact in pets.jelly.continuation_reasons(pets.actors)
                if fact["actor_ids"] == [pet_id]
            )
            continue
        if state["phase"] == "egg":
            owner = pets.actors[pets.models[pet_id]["hero_id"]]
            if owner.get("_recalled", False):
                continue
            if owner["hp"] <= 0 or state["rescue_used"]:
                continue
        elif state["phase"] != "underground":
            raise InputError("Unknown latent pet phase in termination collector")
        burrow = state["burrow"]
        facts.append(
            continuation_fact(
                "latent_attacker",
                f"pet:{pet_id}",
                [pet_id],
                not_before_seconds=(burrow["surface_seconds"] if burrow else None),
            )
        )
    return facts


def hazard_continuation(hazards, time, actors=None):
    """Only positive future pulses count; lingering movement/status clocks do not."""
    if hazards is None:
        return []
    facts = []
    for field_id, field in hazards.fields.items():
        expiry = field["start_seconds"] + field["duration_seconds"]
        if expiry <= time + EPSILON or field["maximum_dps"] <= 0:
            continue
        positive_stages = [
            stage["after_seconds"]
            for stage in field["growth_by_field_age"]
            if stage["dps_multiplier"] > 0
        ]
        if not positive_stages:
            continue
        source_id = getattr(hazards, "source_actor_ids", {}).get(field_id)
        if source_id is not None:
            if actors is None or source_id not in actors:
                raise InputError("Owned persistent damage needs its source actor")
            owner = actors[source_id]["team"]
            if field.get("source_team", owner) != owner:
                raise InputError("Hazard source actor and declared team disagree")
        else:
            owner = require(field, "source_team")
        if owner not in {"attack", "defense", "environment"}:
            raise InputError("Persistent damage needs explicit source ownership")
        if owner != "attack":
            continue
        first = hazards.next_pulses[field_id]
        threshold = field["start_seconds"] + min(positive_stages)
        interval = field["pulse_interval_seconds"]
        skips = max(0, ceil((threshold - first - EPSILON) / interval))
        next_positive = first + skips * interval
        if next_positive >= expiry - EPSILON:
            continue
        if next_positive <= time + EPSILON:
            raise InputError("Due hazard damage must settle before termination")
        facts.append(
            continuation_fact(
                "lingering_damage",
                f"hazard:{field_id}",
                [source_id] if source_id is not None else [],
                source_team=owner,
                not_before_seconds=next_positive,
                expires_at_seconds=expiry,
            )
        )
    return facts


def runtime_continuation_reasons(
    time,
    actors,
    *,
    patterns=None,
    deaths=None,
    siege=None,
    reinforcements=None,
    pets=None,
    hazards=None,
    hero_providers=(),
    attack_spells=None,
    damage_receipts=None,
):
    """Collect after all damage, death cascades and same-time releases settle."""
    if damage_receipts is not None:
        damage_receipts.assert_settled()
    facts = [
        *pattern_continuation(patterns),
        *death_continuation(deaths, actors),
        *siege_continuation(siege),
        *reinforcement_continuation(reinforcements),
        *pet_continuation(pets),
        *hazard_continuation(hazards, time, actors),
    ]
    for provider in (*hero_providers, attack_spells):
        if provider is not None:
            facts.extend(provider.continuation_reasons(time))
    return sorted(facts, key=lambda fact: (fact["kind"], fact["id"]))
