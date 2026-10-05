"""Defensive role validation around shared troop lifecycle implementations."""

from copy import deepcopy

from .common import InputError
from .druids import DruidCombat
from .electro_titans import ElectroTitanCombat
from .troop_behaviors import AttackingTroopCombat
from .troop_projectiles import TroopLineCombat


def _defensive_sources(actors, model):
    for actor in actors.values():
        if model in actor and actor.get("team") == "defense":
            if (
                "defending_extension_model" not in actor
                or "garrison_member_model" not in actor
            ):
                raise InputError(
                    "Defensive troop lifecycle requires explicit Castle ownership"
                )


class DefendingTroopBehaviorCombat(AttackingTroopCombat):
    def __init__(self, actors):
        _defensive_sources(actors, "troop_behavior_model")
        super().__init__(actors)


class DefendingTroopLineCombat(TroopLineCombat):
    def __init__(self, actors):
        _defensive_sources(actors, "troop_line_model")
        super().__init__(actors)

    def continuation_reasons(self, time):
        facts = super().continuation_reasons(time)
        for fact, (_, _, packet) in zip(facts, self.pending):
            fact["source_team"] = packet["team"]
        return facts


class DefendingTitanCombat(ElectroTitanCombat):
    def __init__(self, actors):
        _defensive_sources(actors, "aura_model")
        views = deepcopy(actors)
        for key, actor in actors.items():
            if "aura_model" not in actor or actor["team"] != "defense":
                continue
            if actor["aura_model"]["target_kinds"] != ["unit"]:
                raise InputError("Defending Titan aura may damage attacking units only")
            # Reuse numeric/schema validation, then restore real role filters.
            views[key]["team"] = "attack"
            views[key]["aura_model"]["target_kinds"] = ["unit", "defense", "building"]
        super().__init__(views)
        self.actors = actors
        self.models = {key: deepcopy(actors[key]["aura_model"]) for key in self.models}


class DefendingDruidCombat(DruidCombat):
    def __init__(self, actors):
        _defensive_sources(actors, "druid_model")
        views = deepcopy(actors)
        for key, actor in actors.items():
            if "druid_model" not in actor or actor["team"] != "defense":
                continue
            child_id = actor["druid_model"]["bear_id"]
            child = actors.get(child_id, {})
            if (
                child.get("team") != "defense"
                or child.get("defending_child_model", {}).get("parent") != key
            ):
                raise InputError(
                    "Defending Druid requires its own defensive Bear reserve"
                )
            views[key]["team"] = views[child_id]["team"] = "attack"
        super().__init__(views)
        self.actors = actors
