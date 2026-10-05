"""Source-grounded Monolith Arrow tiers with an explicit deployment ledger.

June 15 publisher notes resolve target max-HP basis and membership weights.
Recall deduplication, launch sampling, buff composition and targeting remain
explicit experiment policies. This module does not grant deployment resources.
"""

from copy import deepcopy

from .common import InputError, identifier, integer, number
from .equipment_gap_sources import MONOLITH_SOURCE, explicit_policy, selected_row
from .hero_extensions import require_fields, source_quantity
from .spatial import _active


POLICIES = {
    "experimental_policy": "monolith_arrow_ledger_v1_uncalibrated",
    "deployment": "first_paid_identity_once_no_subtract_death_recall_or_redeploy",
    "sampling": "capture_deployed_housing_and_target_maximum_hp_at_weapon_launch",
    "damage_composition": "add_unscaled_maximum_hp_bonus_after_ordinary_weapon_buffs",
    "reduction_composition": "multiply_independent_shared_incoming_damage_factors",
    "targets": "ordinary_single_target_enemy_buildings_defenses_units_no_wall_hook",
}
MEMBERSHIPS = {"army_troop", "hero", "siege", "pet", "castle", "generated", "spell"}


class MonolithArrowLedger:
    """Bind inventory from the central paid compiler, never from active counts."""

    def __init__(self, catalog, owner_id, level, town_hall, parameters, inventory):
        explicit_policy(parameters, POLICIES)
        self.owner_id = identifier(owner_id, "Monolith Arrow Queen")
        row = selected_row(catalog, "monolith-arrow", level, town_hall)
        stats = row["stats"]
        self.fractions = tuple(
            source_quantity(stats[key], "%") / 100
            for key in (
                "extraDamageBelow180",
                "extraDamage181To250",
                "extraDamage251Plus",
            )
        )
        for value in self.fractions:
            number(value, "Monolith Arrow max-HP fraction", 0, 1)
        reduction = source_quantity(stats["incomingDamageReduction"], "%") / 100
        self.incoming_multiplier = 1 - number(
            reduction, "Monolith Arrow reduction", 0, 0.1
        )
        self.parameters = deepcopy(parameters)
        self.statistics_source = catalog.records["monolith-arrow"]["source"]
        self.inventory = deepcopy(inventory)
        for key, entry in self.inventory.items():
            identifier(key, "deployment actor ID")
            require_fields(
                entry,
                {"membership", "housing_space"},
                "Monolith deployment inventory entry",
            )
            membership = entry["membership"]
            if membership not in MEMBERSHIPS:
                raise InputError("Monolith deployment membership is unsupported")
            weight = integer(
                entry["housing_space"], "Monolith declared inventory weight", 0
            )
            expected = {"hero": 25, "siege": 1}.get(membership, 0)
            if (membership == "army_troop" and weight <= 0) or (
                membership != "army_troop" and weight != expected
            ):
                raise InputError(
                    "Monolith inventory weight violates publisher membership"
                )
        if self.inventory.get(owner_id) != {"membership": "hero", "housing_space": 25}:
            raise InputError(
                "Monolith deployment inventory must include its Queen as 25"
            )
        self.deployed = {}
        self.events = {}
        self.total_housing = 0
        self.last_time = 0

    def deploy(self, event_id, actor_id, time):
        """Feed successful deployments only, after central entitlement settlement."""
        identifier(event_id, "paid deployment event")
        number(time, "Monolith deployment time", self.last_time)
        if actor_id not in self.inventory:
            raise InputError("Monolith saw an unregistered paid/generated identity")
        signature = (actor_id, time)
        if event_id in self.events:
            if self.events[event_id] != signature:
                raise InputError("Monolith deployment receipt changed identity")
            return False
        self.last_time = time
        self.events[event_id] = signature
        if actor_id in self.deployed:
            return False
        weight = self.inventory[actor_id]["housing_space"]
        self.deployed[actor_id] = {
            "event": event_id,
            "time_seconds": time,
            "housing_space": weight,
        }
        self.total_housing += weight
        return True

    @property
    def fraction(self):
        return self.fractions[
            0 if self.total_housing <= 180 else 1 if self.total_housing <= 250 else 2
        ]

    def capture_launch(self, owner, target, time):
        number(time, "Monolith launch time", self.last_time)
        if (
            owner["id"] != self.owner_id
            or owner["team"] != "attack"
            or owner["id"] not in self.deployed
            or owner.get("hero_model", {}).get("entity") != "archer-queen"
            or not _active(owner, time)
            or not _active(target, time)
            or owner["team"] == target["team"]
            or target["kind"] not in {"building", "defense", "unit"}
        ):
            raise InputError(
                "Monolith launch requires its deployed live Queen and legal target"
            )
        maximum = number(target["maximum_hp"], "Monolith target maximum HP", 0)
        self.last_time = time
        return {
            "source_actor_id": self.owner_id,
            "target_id": target["id"],
            "time_seconds": time,
            "deployed_housing": self.total_housing,
            "maximum_hp_fraction": self.fraction,
            "captured_maximum_hp": maximum,
            "additional_damage": maximum * self.fraction,
        }

    def result(self):
        return {
            "calibrated": False,
            "source": self.statistics_source,
            "publisher_source": MONOLITH_SOURCE,
            "parameters": deepcopy(self.parameters),
            "deployed_housing": self.total_housing,
            "deployed": deepcopy(self.deployed),
            "maximum_hp_fraction": self.fraction,
            "incoming_multiplier": self.incoming_multiplier,
        }
