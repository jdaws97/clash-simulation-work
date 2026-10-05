"""Compose the extended heroes with the common equipment activation clock."""

from collections import defaultdict

from .barbarian_king import BarbarianKingCombat
from .dragon_duke import DragonDukeCombat
from .minion_prince import MinionPrinceCombat
from .recipe_equipment import RecipeEquipmentCombat
from .equipment_weapons import EquipmentWeaponCombat
from .equipment_summons import EquipmentSummonCombat


EXTENDED_HEROES = {"barbarian-king", "minion-prince", "dragon-duke"}


class HeroRosterCombat:
    """Keep hero-specific queues explicit and expose one scheduler boundary."""

    def __init__(self, actors, combat, hit_status, select_target, width, height):
        self.king = BarbarianKingCombat(actors, combat, select_target)
        self.duke = DragonDukeCombat(actors, combat)
        self.prince = MinionPrinceCombat(actors, combat, hit_status)
        self.recipe = RecipeEquipmentCombat(actors)
        self.equipment_weapons = EquipmentWeaponCombat(
            actors, select_target, width, height
        )
        self.equipment_summons = EquipmentSummonCombat(actors, width, height)
        self.width = width
        self.height = height
        self.select_target = self.king.select_target

    def prepare(self, actors, time, trace):
        self.king.prepare(actors, time, trace, self.width, self.height)
        self.duke.prepare(actors, time, trace)
        self.prince.prepare(actors, time, trace)
        self.recipe.prepare(actors, time, trace)
        self.equipment_weapons.prepare(actors, time, trace)
        self.equipment_summons.prepare(actors, time, trace)

    def activate(self, hero_id, actors, time, trace):
        self.king.activate(hero_id, actors, time, trace)
        self.prince.activate(hero_id, actors, time, trace)
        self.recipe.activate(hero_id, actors, time, trace)
        self.equipment_weapons.activate(hero_id, actors, time, trace)
        self.equipment_summons.activate(hero_id, actors, time, trace)

    def weapon_launched(self, hero_id, time, trace):
        self.prince.weapon_launched(hero_id, time, trace)
        self.equipment_weapons.weapon_launched(hero_id, time, trace)

    def resolve(self, actors, time, trace, receipts):
        damage = defaultdict(float)
        healing = defaultdict(float)
        for runtime in (
            self.king,
            self.duke,
            self.recipe,
            self.equipment_weapons,
            self.equipment_summons,
        ):
            extra_damage, extra_healing = runtime.resolve(actors, time, trace, receipts)
            for key, amount in extra_damage.items():
                damage[key] += amount
            for key, amount in extra_healing.items():
                healing[key] += amount
        for key, amount in self.prince.resolve(actors, time, trace, receipts).items():
            damage[key] += amount
        return damage, healing

    def after_health(self, actors, receipts, time, trace):
        self.equipment_summons.after_health(actors, receipts, time, trace)
        self.recipe.prepare(actors, time, trace)
        return self.duke.after_health(actors, receipts, time, trace)

    def wall_impacts(self, actor, primary, actors, time):
        impacts = self.recipe.wall_impacts(actor, primary, actors, time)
        if impacts is not None:
            return impacts
        return self.king.wall_impacts(actor, primary, actors, time)

    def next_boundary(self, time):
        candidates = []
        for runtime in (
            self.king,
            self.duke,
            self.prince,
            self.recipe,
            self.equipment_weapons,
            self.equipment_summons,
        ):
            boundary = runtime.next_boundary(time)
            if boundary is not None:
                candidates.append(boundary)
        return min(candidates) if candidates else None

    def first_crossing_delay(self, actors, motions, time, horizon):
        routes = {key: route for key, (route, _) in motions.items()}
        speeds = {key: speed for key, (_, speed) in motions.items()}
        candidates = []
        for runtime in (self.duke, self.prince, self.recipe):
            crossing = runtime.first_crossing_delay(
                actors, routes, speeds, time, horizon
            )
            if crossing is not None:
                candidates.append(crossing)
        return min(candidates) if candidates else None

    def frame(self, actor_id, actor):
        return {
            **self.king.frame(actor_id, actor),
            **self.duke.frame(actor_id, actor),
            **self.prince.frame(actor_id, actor),
        }

    def has_due_offense(self, time):
        return (
            bool(self.equipment_weapons.packets)
            and self.equipment_weapons.packets[0][0] <= time
        ) or any(
            runtime.packets and runtime.packets[0][0] <= time + 1e-10
            for runtime in (self.king, self.duke, self.recipe)
        )

    def continuation_reasons(self, time):
        from .battle_termination import continuation_fact

        reasons = []
        for label, runtime in (("spiky_ball", self.king), ("duke", self.duke)):
            for arrival, sequence, packet in runtime.packets:
                if packet["source_team"] != "attack" or packet["damage"] <= 0:
                    continue
                reasons.append(
                    continuation_fact(
                        "pending_damage",
                        f"hero:{label}:{sequence}",
                        [packet["source"]],
                        not_before_seconds=arrival,
                    )
                )
        for index, orb in enumerate(self.prince.orbs):
            if orb["finished"] or orb["source_team"] != "attack" or orb["damage"] <= 0:
                continue
            reasons.append(
                continuation_fact(
                    "lingering_damage",
                    f"hero:dark_orb:{index}",
                    [orb["source"]],
                    not_before_seconds=orb["starts_at"],
                    expires_at_seconds=orb["ends_at"],
                )
            )
        return (
            reasons
            + self.recipe.continuation_reasons()
            + self.equipment_weapons.continuation_reasons(time)
        )

    def result(self):
        return {
            "barbarian_king": self.king.result(),
            "dragon_duke": self.duke.result(),
            "minion_prince": self.prince.result(),
            "recipe_equipment": self.recipe.result(),
            "equipment_weapons": self.equipment_weapons.result(),
            "equipment_summons": self.equipment_summons.result(),
        }
