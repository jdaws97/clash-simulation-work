"""Source attribution for damage-sensitive hero behavior.

Resolvers register a packet before adding its returned damage to the shared
health batch. The health boundary settles receipts against pre-damage health,
so counters cannot be inferred from requested damage, healing, or trace text.
"""

from collections import defaultdict
from copy import deepcopy
from math import isclose

from .common import InputError, identifier, number


EPSILON = 1e-10
ORIGINS = {
    "weapon",
    "trap",
    "hazard",
    "death",
    "ability",
    "revenge_counter",
    "scripted",
    "spell",
}


def record_damage(
    runtime,
    target,
    amount,
    time,
    *,
    source_id,
    source_team,
    origin,
    source_actor_id=None,
    apply_immediately=False,
):
    """Apply the same protection path with optional source-attributed receipts."""
    receipts = getattr(runtime, "damage_receipts", None)
    if receipts is not None:
        return receipts.register(
            target,
            amount,
            time,
            source_id=source_id,
            source_actor_id=source_actor_id,
            source_team=source_team,
            origin=origin,
            apply_immediately=apply_immediately,
        )
    protected = target.get("_tesla_hidden", False) or (
        target["immune_until"] > time + EPSILON
    )
    flat = number(
        target.get("_equipment_owner_flat_reduction", 0), "equipment flat reduction", 0
    )
    factor = number(
        target.get("_equipment_field_incoming_multiplier", 1),
        "equipment incoming multiplier",
        0,
        1,
    )
    factor *= number(
        target.get("_spell_incoming_damage_multiplier", 1),
        "spell incoming multiplier",
        0,
        1,
    )
    final = 0 if protected else max(amount - flat, 0) * factor
    if target.get("_spell_armor_hp", 0) > 0:
        from .advanced_spells import armor_damage

        final = armor_damage(target, final)
    return final


class DamageReceipts:
    """Preserve deterministic packet order and attribute actual health loss."""

    def __init__(self, target_ids=None):
        if target_ids is not None:
            if isinstance(target_ids, str):
                raise InputError(
                    "Tracked damage recipients require a collection of IDs"
                )
            target_ids = frozenset(target_ids)
            for target_id in target_ids:
                identifier(target_id, "tracked damage recipient")
        self.target_ids = target_ids
        self.pending = []
        self.immediate = []
        self.sequence = 0

    def register(
        self,
        target,
        amount,
        time,
        *,
        source_id,
        source_team,
        origin,
        source_actor_id=None,
        protection="respect_invulnerability",
        apply_immediately=False,
    ):
        identifier(source_id, "damage source ID")
        if source_actor_id is not None:
            identifier(source_actor_id, "damage source actor ID")
        if source_team not in {"attack", "defense", "environment"}:
            raise InputError("Damage attribution requires an explicit source team")
        if origin not in ORIGINS:
            raise InputError("Damage attribution requires a supported origin")
        if protection not in {"respect_invulnerability", "bypass_invulnerability"}:
            raise InputError("Damage protection must be explicit")
        amount = number(amount, "requested attributed damage", 0)
        time = number(time, "attributed damage time", 0)
        if not isinstance(apply_immediately, bool):
            raise InputError("Immediate damage application must be explicit")
        outstanding = self.pending or self.immediate
        if outstanding and abs(outstanding[0]["time_seconds"] - time) > EPSILON:
            raise InputError("Damage receipts must settle before advancing time")
        protected = target.get("_tesla_hidden", False) or (
            protection == "respect_invulnerability"
            and target["immune_until"] > time + EPSILON
        )
        multiplier = number(
            target.get("_hero_incoming_damage_multiplier", 1),
            "hero incoming damage multiplier",
            0,
            1,
        )
        multiplier *= number(
            target.get("_equipment_field_incoming_multiplier", 1),
            "equipment incoming multiplier",
            0,
            1,
        )
        multiplier *= number(
            target.get("_spell_incoming_damage_multiplier", 1),
            "spell incoming multiplier",
            0,
            1,
        )
        flat = number(
            target.get("_equipment_owner_flat_reduction", 0),
            "equipment flat reduction",
            0,
        )
        if origin == "trap":
            multiplier *= number(
                target.get("_hero_trap_damage_multiplier", 1),
                "hero trap damage multiplier",
                0,
                1,
            )
        final = 0 if protected else max(amount - flat, 0) * multiplier
        armor_before = target.get("_spell_armor_hp", 0)
        before_armor = final
        if armor_before > 0:
            from .advanced_spells import armor_damage

            final = armor_damage(target, final)
        if self.target_ids is not None and target["id"] not in self.target_ids:
            return final
        receipt = {
            "sequence": self.sequence,
            "time_seconds": time,
            "source_id": source_id,
            "source_actor_id": source_actor_id,
            "source_team": source_team,
            "target_id": target["id"],
            "origin": origin,
            "requested_damage": amount,
            "protected": protected,
            "damage_multiplier": multiplier,
            "final_damage": final,
            "actual_health_loss": None,
            **(
                {
                    "armor_before": armor_before,
                    "armor_after": target["_spell_armor_hp"],
                    "armor_absorbed_packet_damage": before_armor - final,
                }
                if armor_before > 0
                else {}
            ),
        }
        self.sequence += 1
        if apply_immediately:
            receipt["actual_health_loss"] = min(max(target["hp"], 0), final)
            self.immediate.append(receipt)
        else:
            self.pending.append(receipt)
        return final

    def settle(self, actors, damage, time, *, require_attribution_for=()):
        """Settle before applying health changes, including lethal interception.

        Actual health loss means damage removed from existing health before a
        Phoenix interception or subsequent healing. When several packets
        overkill the same actor, registration order allocates the remaining HP.
        """
        totals = defaultdict(float)
        for receipt in [*self.pending, *self.immediate]:
            if abs(receipt["time_seconds"] - time) > EPSILON:
                raise InputError("Damage receipt time differs from its health batch")
            if receipt["target_id"] not in actors:
                raise InputError("Damage receipt names an unknown recipient")
        for receipt in self.pending:
            totals[receipt["target_id"]] += receipt["final_damage"]
        checked = (
            set(totals) | set(require_attribution_for) | (self.target_ids or set())
        )
        for key in checked:
            if key not in actors:
                raise InputError("Attributed damage requires a known recipient")
            if not isclose(
                totals[key], damage.get(key, 0), rel_tol=1e-10, abs_tol=EPSILON
            ):
                raise InputError("Damage attribution does not match the health batch")
        remaining = {key: max(actor["hp"], 0) for key, actor in actors.items()}
        settled = []
        for pending in self.pending:
            receipt = deepcopy(pending)
            key = receipt["target_id"]
            receipt["actual_health_loss"] = min(remaining[key], receipt["final_damage"])
            remaining[key] -= receipt["actual_health_loss"]
            settled.append(receipt)
        self.pending.clear()
        settled.extend(deepcopy(self.immediate))
        self.immediate.clear()
        return sorted(settled, key=lambda receipt: receipt["sequence"])

    def assert_settled(self):
        if self.pending or self.immediate:
            raise InputError("Pending damage receipts cannot be discarded")
