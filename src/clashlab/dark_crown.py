"""Three-stage Dark Crown ledger with explicit unresolved death thresholds.

Extraction supplies distinct stage percentages, but not their order or trigger
weights. The selected ascending cumulative interpretation is experimental.
Modifiers are returned for a central composable ledger, never applied by
overwriting maximum_hp (which would conflict with Life Gem).
"""

from copy import deepcopy

from .common import InputError, identifier, number
from .equipment_gap_sources import (
    EXTRACTION_URL,
    explicit_policy,
    extracted_equipment,
    selected_row,
)
from .spatial import _active


POLICIES = {
    "experimental_policy": "dark_crown_death_ledger_v1_uncalibrated",
    "stages": "sort_extracted_health_and_damage_pairs_ascending_cumulative_not_compounding",
    "eligibility": "explicit_actor_weight_manifest_first_defeat_per_identity",
    "owner_unavailable": "ignore_deaths_while_owner_dead_or_recalled_no_replay",
    "revival": "preserve_existing_stage_no_reset_or_new_death_entitlement",
    "health": "shared_source_modifier_preserve_positive_current_hp_fraction_never_revive",
    "cadence": "catalog_attack_speed_percent_is_passive_at_all_stages",
}


class DarkCrownLedger:
    def __init__(self, catalog, owner_id, level, town_hall, parameters):
        explicit_policy(parameters, POLICIES, {"thresholds", "death_weights"})
        self.owner_id = identifier(owner_id, "Dark Crown owner")
        row = selected_row(catalog, "dark-crown", level, town_hall)
        extracted = extracted_equipment(catalog, "Dark Crown", level)
        stages = sorted(
            (
                number(a["PercentHealthIncrease"], "Crown health percent", 0),
                number(a["BoostDamagePercentage"], "Crown damage percent", 0),
            )
            for a in extracted["abilities"]
        )
        if len(stages) != 3 or len(set(stages)) != 3:
            raise InputError("Dark Crown needs three distinct extracted stage pairs")
        self.stages = [(1 + hp / 100, 1 + damage / 100) for hp, damage in stages]
        self.cadence = (
            1
            + number(row["stats"]["attackSpeedIncrease"], "Crown cadence percent", 0)
            / 100
        )
        self.parameters = deepcopy(parameters)
        thresholds = parameters["thresholds"]
        if not isinstance(thresholds, list) or len(thresholds) != 3:
            raise InputError(
                "Dark Crown requires three caller-declared death thresholds"
            )
        previous = 0
        for threshold in thresholds:
            number(threshold, "Crown threshold", 0)
            if threshold <= previous:
                raise InputError("Dark Crown thresholds must be strictly increasing")
            previous = threshold
        weights = parameters["death_weights"]
        if not isinstance(weights, dict) or not weights or owner_id in weights:
            raise InputError(
                "Dark Crown requires explicit allied death weights excluding its owner"
            )
        for key, weight in weights.items():
            identifier(key, "Crown eligible ally")
            number(weight, "Crown ally weight", 0)
        self.events = {}
        self.seen_actors = set()
        self.weight = 0
        self.stage = 0
        self.last_time = 0

    def defeat(self, event_id, target, owner, time):
        """Feed actual settled HP-zero events, not Recall/despawn notifications."""
        identifier(event_id, "Crown death receipt")
        number(time, "Crown death time", self.last_time)
        if (
            owner["id"] != self.owner_id
            or owner["team"] != "attack"
            or owner.get("hero_model", {}).get("entity") != "minion-prince"
            or target["team"] != owner["team"]
            or target["hp"] != 0
            or target["spawn_seconds"] == "controlled"
            or target["spawn_seconds"] > time
            or target.get("_recalled", False)
        ):
            raise InputError(
                "Dark Crown requires a real deployed ally defeat and its Prince"
            )
        signature = (target["id"], time)
        if event_id in self.events:
            if self.events[event_id] != signature:
                raise InputError("Dark Crown defeat receipt changed identity")
            return False
        self.last_time = time
        self.events[event_id] = signature
        if target["id"] in self.seen_actors:
            return False
        self.seen_actors.add(target["id"])
        if not _active(owner, time):
            return False
        if target["id"] not in self.parameters["death_weights"]:
            raise InputError(
                "Dark Crown defeated ally missing explicit weight (use zero to exclude)"
            )
        old = self.stage
        self.weight += self.parameters["death_weights"][target["id"]]
        self.stage = sum(
            self.weight >= value for value in self.parameters["thresholds"]
        )
        return self.stage != old

    def modifiers(self):
        hp, damage = self.stages[self.stage - 1] if self.stage else (1, 1)
        return {
            "source": "dark-crown:" + self.owner_id,
            "maximum_hp_factor": hp,
            "outgoing_damage_factor": damage,
            "attack_rate_factor": self.cadence,
        }

    def result(self):
        return {
            "calibrated": False,
            "source": EXTRACTION_URL,
            "parameters": deepcopy(self.parameters),
            "stage": self.stage,
            "defeated_weight": self.weight,
            "seen_actors": sorted(self.seen_actors),
            "modifiers": self.modifiers(),
        }
