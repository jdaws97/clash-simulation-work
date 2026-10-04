"""Explicit, uncalibrated hypotheses for ending a complete declared battle.

This module does not infer whether a living attacker can eventually reach or
damage a target. Runtime owners report pending work after their current boundary
has settled. Only inventory bindings identify user-deployable reserves; a
generated actor's controlled spawn flag is not an inventory entitlement.
"""

from copy import deepcopy

from .common import InputError, identifier, integer, number, require


EPSILON = 1e-10
POLICY_MODE = "all_counted_destroyed_or_attack_force_exhausted"
POLICY_ASSUMPTIONS = {
    "active_attackers": "every_living_deployed_attacking_unit_including_support",
    "undeployed_army": "every_unspent_bound_user_deployable_unit",
    "pending_payloads": "continue_including_blocked_ground_release",
    "latent_lifecycles": "continue_while_reported_by_runtime_owner",
    "released_offense": "continue_until_resolved_or_expired",
    "reachability": "do_not_infer_eventual_target_reachability_or_damage",
}
USER_DEPLOYABLE_ORIGINS = {"army_troops", "army_heroes", "siege"}
GENERATED_ORIGINS = {"clan_castle_troops", "assigned_hero_pet"}
SPELL_CLASSES = {"support_only", "damage", "summon", "recall", "revive"}
SPELL_CONTINUATION = {"ignore", "while_unspent", "while_runtime_eligible"}
RUNTIME_KINDS = {
    "pending_release",
    "latent_attacker",
    "pending_damage",
    "lingering_damage",
}
FACT_FIELDS = {
    "kind",
    "id",
    "source_team",
    "actor_ids",
    "not_before_seconds",
    "expires_at_seconds",
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires its complete explicit fields")


def _spell_key(value):
    origin = require(value, "origin")
    if origin not in {"army", "clan_castle"}:
        raise InputError("Termination spell origin must be army or clan_castle")
    entity = identifier(require(value, "entity"), "termination spell entity")
    level = integer(require(value, "level"), "termination spell level", 1)
    return origin, entity, level


def spell_slot_id(binding):
    """Return a stable resource identity independent of an optional cast command."""
    origin, entity, level = _spell_key(binding)
    ordinal = integer(require(binding, "ordinal"), "spell slot ordinal", 1)
    return f"{origin}:{entity}:{level}:{ordinal}"


def validate_termination_policy(policy, spell_bindings):
    """Require source and explicit behavior for every reserved spell identity."""
    _fields(
        policy,
        {"source", "mode", "assumptions", "spell_inventory"},
        "Battle termination policy",
    )
    identifier(policy["source"], "battle termination policy source")
    if policy["mode"] != POLICY_MODE:
        raise InputError("Unsupported battle termination hypothesis")
    if policy["assumptions"] != POLICY_ASSUMPTIONS:
        raise InputError("Battle termination assumptions must be explicit")
    entries = policy["spell_inventory"]
    if not isinstance(entries, list):
        raise InputError("Termination spell inventory must be an explicit list")
    classifications = {}
    for entry in entries:
        _fields(
            entry,
            {"origin", "entity", "level", "classification", "continuation"},
            "Termination spell classification",
        )
        key = _spell_key(entry)
        if key in classifications:
            raise InputError("Duplicate termination spell classification")
        if entry["classification"] not in SPELL_CLASSES:
            raise InputError("Unknown termination spell classification")
        if entry["continuation"] not in SPELL_CONTINUATION:
            raise InputError("Unknown termination spell continuation policy")
        if (
            entry["classification"] == "support_only"
            and entry["continuation"] != "ignore"
        ):
            raise InputError("Support-only spells cannot prolong force exhaustion")
        classifications[key] = deepcopy(entry)
    expected = {_spell_key(binding) for binding in spell_bindings}
    if set(classifications) != expected:
        raise InputError(
            "Every declared spell identity needs exactly one termination classification"
        )
    return classifications


def continuation_fact(
    kind,
    fact_id,
    actor_ids=(),
    *,
    source_team="attack",
    not_before_seconds=None,
    expires_at_seconds=None,
):
    """Build the small provider contract; the evaluator validates live input."""
    return {
        "kind": kind,
        "id": fact_id,
        "source_team": source_team,
        "actor_ids": list(actor_ids),
        "not_before_seconds": not_before_seconds,
        "expires_at_seconds": expires_at_seconds,
    }


class BattleTermination:
    """Observe a settled boundary without commands, replay, or actor mutation."""

    requires_runtime_facts = True

    def __init__(self, policy, counted_ids, attacker_bindings, spell_bindings, limit):
        self.policy = deepcopy(policy)
        self.limit = number(limit, "battle termination time limit", EPSILON)
        self.counted_ids = list(counted_ids)
        if not self.counted_ids or len(set(self.counted_ids)) != len(self.counted_ids):
            raise InputError("Termination requires unique counted defender IDs")
        for actor_id in self.counted_ids:
            identifier(actor_id, "counted defender ID")
        if not isinstance(attacker_bindings, dict):
            raise InputError(
                "Termination attacker bindings must be an explicit mapping"
            )
        self.attacker_bindings = deepcopy(attacker_bindings)
        for actor_id, binding in self.attacker_bindings.items():
            identifier(actor_id, "bound attacker ID")
            if require(binding, "origin") not in (
                USER_DEPLOYABLE_ORIGINS | GENERATED_ORIGINS
            ):
                raise InputError("Unknown attacker origin in termination inventory")
        if not isinstance(spell_bindings, list):
            raise InputError("Termination spell bindings must be an explicit list")
        self.spell_bindings = deepcopy(spell_bindings)
        self.spell_policies = validate_termination_policy(policy, spell_bindings)
        slots = [spell_slot_id(binding) for binding in spell_bindings]
        if len(set(slots)) != len(slots):
            raise InputError("Duplicate termination spell resource")
        for binding in spell_bindings:
            if "cast" not in binding:
                raise InputError(
                    "Termination spell resources need cast or explicit null"
                )
            if binding["cast"] is not None:
                identifier(require(binding["cast"], "cast_id"), "spell cast ID")
                number(
                    require(binding["cast"], "time_seconds"),
                    "termination spell cast time",
                    0,
                    self.limit,
                )
        self.last_reasons = []
        self.decision = None

    @staticmethod
    def _living(actor):
        return number(require(actor, "hp"), "termination actor HP", 0) > 0

    @staticmethod
    def _spawn_time(actor):
        spawn = require(actor, "spawn_seconds")
        return spawn if spawn == "controlled" else number(spawn, "actor spawn time", 0)

    def _validate_actors(self, actors):
        for actor_id in set(self.counted_ids) | set(self.attacker_bindings):
            if actor_id not in actors:
                raise InputError(f"Termination is missing its bound actor: {actor_id}")
        for actor_id in self.counted_ids:
            actor = actors[actor_id]
            if (
                actor.get("team") != "defense"
                or actor.get("counts_for_destruction") is not True
            ):
                raise InputError("Termination counted IDs must be counted defenders")
        for actor_id in self.attacker_bindings:
            actor = actors[actor_id]
            if actor.get("team") != "attack" or actor.get("kind") != "unit":
                raise InputError("Termination inventory must bind attacking units")
            if self.attacker_bindings[actor_id][
                "origin"
            ] in USER_DEPLOYABLE_ORIGINS and any(
                field in actor
                for field in (
                    "summon_model",
                    "trap_summon_model",
                    "payload_member_model",
                    "pet_model",
                )
            ):
                raise InputError(
                    "Generated actors cannot claim user-deployable inventory"
                )

    def _runtime_reasons(self, time, actors, runtime_facts):
        reasons = []
        identities = set()
        for fact in runtime_facts:
            _fields(fact, FACT_FIELDS, "Runtime continuation fact")
            kind = fact["kind"]
            if kind not in RUNTIME_KINDS:
                raise InputError("Unsupported runtime continuation kind")
            fact_id = identifier(fact["id"], "runtime continuation ID")
            identity = kind, fact_id
            if identity in identities:
                raise InputError("Duplicate runtime continuation identity")
            identities.add(identity)
            if fact["source_team"] not in {"attack", "defense"}:
                raise InputError("Runtime continuation ownership must be explicit")
            members = fact["actor_ids"]
            if not isinstance(members, list) or len(set(members)) != len(members):
                raise InputError(
                    "Continuation actor IDs must be an explicit unique list"
                )
            for actor_id in members:
                if (
                    actor_id not in actors
                    or actors[actor_id]["team"] != fact["source_team"]
                ):
                    raise InputError(
                        "Continuation actors disagree with source ownership"
                    )
            start = fact["not_before_seconds"]
            end = fact["expires_at_seconds"]
            if start is not None:
                number(start, "continuation not-before time", 0)
            if end is not None:
                number(end, "continuation expiry time", 0)
                if start is not None and end < start:
                    raise InputError("Continuation expiry precedes its earliest time")
            if fact["source_team"] == "defense":
                continue
            if kind == "pending_damage" and (start is None or start <= time + EPSILON):
                raise InputError("Due attacking damage must settle before termination")
            if end is not None and end <= time + EPSILON:
                continue
            reasons.append(deepcopy(fact))
        return reasons

    def _spell_reasons(self, time, eligibility):
        if eligibility is None:
            eligibility = {}
        if not isinstance(eligibility, dict) or any(
            not isinstance(value, bool) for value in eligibility.values()
        ):
            raise InputError(
                "Spell eligibility must explicitly map slot IDs to booleans"
            )
        eligible_slots = {
            spell_slot_id(binding)
            for binding in self.spell_bindings
            if self.spell_policies[_spell_key(binding)]["continuation"]
            == "while_runtime_eligible"
        }
        if set(eligibility) - eligible_slots:
            raise InputError("Spell eligibility contains an unowned or irrelevant slot")
        reasons = []
        for binding in self.spell_bindings:
            cast = binding["cast"]
            if cast is not None and cast["time_seconds"] <= time + EPSILON:
                continue
            policy = self.spell_policies[_spell_key(binding)]
            continuation = policy["continuation"]
            if continuation == "ignore":
                continue
            slot_id = spell_slot_id(binding)
            if continuation == "while_runtime_eligible":
                if slot_id not in eligibility:
                    raise InputError("Unspent spell needs explicit runtime eligibility")
                if not eligibility[slot_id]:
                    continue
            reasons.append(
                {
                    "kind": "unspent_spell",
                    "id": slot_id,
                    "origin": binding["origin"],
                    "entity": binding["entity"],
                    "level": binding["level"],
                    "ordinal": binding["ordinal"],
                    "classification": policy["classification"],
                    "continuation": continuation,
                }
            )
        return reasons

    def continuation_reasons(
        self, time, actors, runtime_facts=(), spell_eligibility=None
    ):
        """Report why an otherwise incomplete battle may continue under the policy."""
        number(time, "termination observation time", 0, self.limit + EPSILON)
        self._validate_actors(actors)
        reasons = []
        for actor_id, actor in sorted(actors.items()):
            if actor.get("team") != "attack" or actor.get("kind") != "unit":
                continue
            if not self._living(actor):
                continue
            if actor.get("_recalled", False) or "spell_decoy_model" in actor:
                continue
            spawn = self._spawn_time(actor)
            if spawn != "controlled" and spawn <= time + EPSILON:
                reasons.append({"kind": "active_attacker", "id": actor_id})
            elif (
                self.attacker_bindings.get(actor_id, {}).get("origin")
                in USER_DEPLOYABLE_ORIGINS
            ):
                reasons.append(
                    {
                        "kind": "undeployed_army",
                        "id": actor_id,
                        "origin": self.attacker_bindings[actor_id]["origin"],
                    }
                )
        reasons.extend(self._runtime_reasons(time, actors, runtime_facts))
        reasons.extend(self._spell_reasons(time, spell_eligibility))
        return sorted(reasons, key=lambda reason: (reason["kind"], reason["id"]))

    def evaluate(
        self,
        time,
        actors,
        runtime_facts=(),
        spell_eligibility=None,
        *,
        settled,
    ):
        """Return a final decision, or None; callers must finish same-time work first."""
        if settled is not True:
            raise InputError("Battle termination requires a fully settled boundary")
        if self.decision is not None:
            return deepcopy(self.decision)
        number(time, "termination observation time", 0, self.limit + EPSILON)
        self._validate_actors(actors)
        if all(not self._living(actors[actor_id]) for actor_id in self.counted_ids):
            # Completion does not need hypothetical eligibility for an unspent
            # Recall/Revive resource, but due offensive work must be settled.
            self._runtime_reasons(time, actors, runtime_facts)
            self.last_reasons = []
            reason = "all_counted_buildings_destroyed"
        else:
            self.last_reasons = self.continuation_reasons(
                time, actors, runtime_facts, spell_eligibility
            )
            if not self.last_reasons:
                reason = "attack_force_exhausted"
            elif time >= self.limit - EPSILON:
                reason = "declared_time_limit"
            else:
                return None
        self.decision = {
            "time_seconds": time,
            "end_reason": reason,
            "continuation_reasons": deepcopy(self.last_reasons),
        }
        return deepcopy(self.decision)

    def result(self):
        return {
            "policy": deepcopy(self.policy),
            "policy_status": "explicit_uncalibrated_hypothesis",
            "decision": deepcopy(self.decision),
            "last_continuation_reasons": deepcopy(self.last_reasons),
            "full_game_prediction": False,
        }


class CompletionOnlyTermination:
    """Preserve legacy completion/limit behavior using the settled observer hook."""

    requires_runtime_facts = False

    def __init__(self, counted_ids, limit):
        self.counted_ids = list(counted_ids)
        if not self.counted_ids or len(set(self.counted_ids)) != len(self.counted_ids):
            raise InputError("Termination requires unique counted defender IDs")
        for actor_id in self.counted_ids:
            identifier(actor_id, "counted defender ID")
        self.limit = number(limit, "battle termination time limit", EPSILON)
        self.decision = None

    def evaluate(
        self,
        time,
        actors,
        runtime_facts=(),
        spell_eligibility=None,
        *,
        settled,
    ):
        if settled is not True:
            raise InputError("Battle termination requires a fully settled boundary")
        if self.decision is not None:
            return deepcopy(self.decision)
        number(time, "termination observation time", 0, self.limit + EPSILON)
        for actor_id in self.counted_ids:
            actor = actors.get(actor_id)
            if (
                actor is None
                or actor.get("team") != "defense"
                or actor.get("counts_for_destruction") is not True
            ):
                raise InputError("Termination requires all its counted defender actors")
            number(require(actor, "hp"), "termination actor HP", 0)
        if all(actors[actor_id]["hp"] <= 0 for actor_id in self.counted_ids):
            reason = "all_counted_buildings_destroyed"
        elif time >= self.limit - EPSILON:
            reason = "declared_time_limit"
        else:
            return None
        self.decision = {
            "time_seconds": time,
            "end_reason": reason,
            "continuation_reasons": [],
        }
        return deepcopy(self.decision)

    def result(self):
        return {
            "policy": {
                "mode": "all_counted_destroyed_or_declared_time_limit",
                "source": "legacy_complete_declared_battle_contract",
            },
            "policy_status": "legacy_completion_conditions_preserved",
            "decision": deepcopy(self.decision),
            "last_continuation_reasons": [],
            "full_game_prediction": False,
        }
