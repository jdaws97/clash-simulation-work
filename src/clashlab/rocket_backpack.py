"""Explicit Rocket Backpack forced-motion contract, awaiting central binding.

The trajectory, speed and contact interpretation are hypotheses supplied by the
caller. Existing relative-contact geometry and damage receipts are reused.
The component emits motion/protection demands; it never overwrites other
systems' immunity or ordinary cooldown state.
"""

from copy import deepcopy
from math import hypot

from .common import InputError, identifier, number
from .equipment_event_clock import advancing_deadline
from .equipment_gap_sources import (
    EXTRACTION_URL,
    ROCKET_BALANCE_SOURCE,
    explicit_policy,
    extracted_equipment,
    selected_row,
)
from .hero_extensions import source_quantity
from .range_events import first_weapon_range_entry_delay
from .spatial import EPSILON, _active, center, target_distance


POLICIES = {
    "experimental_policy": "rocket_backpack_motion_v1_uncalibrated",
    "trajectory": "caller_declared_endpoint_no_inferred_village_geometry",
    "contact": "moving_disk_once_per_enemy_building_or_defense_both_layers",
    "area_interpretation": "catalog_damage_area_is_disk_diameter",
    "interruptions": "cancel_on_source_death_recall_or_freeze_no_resume",
    "protection": "request_shared_damage_immunity_during_half_open_dash",
    "ordinary_weapon": "suppress_launch_and_preserve_remaining_work_during_dash",
    "pair_order": "capture_flame_blower_initial_direction_before_dash",
    "damage_scaling": "selected_equipment_damage_times_explicit_profile_factor",
    "visibility": "collateral_ignores_cloak_excludes_hidden_tesla",
}
NUMERIC = {
    "endpoint_tiles",
    "speed_tiles_per_second",
    "damage_source",
    "profile_factor",
}


def compile_model(catalog, level, town_hall, parameters):
    explicit_policy(parameters, POLICIES, NUMERIC)
    endpoint = parameters["endpoint_tiles"]
    if not isinstance(endpoint, list) or len(endpoint) != 2:
        raise InputError("Rocket Backpack needs a declared endpoint")
    for value in endpoint:
        number(value, "dash endpoint", 0)
    number(parameters["speed_tiles_per_second"], "dash speed", EPSILON)
    number(parameters["profile_factor"], "dash profile factor", 0)
    row = selected_row(catalog, "rocket-backpack", level, town_hall)
    extracted = extracted_equipment(catalog, "Rocket Backpack", level)
    damage = number(
        extracted["abilities"][0]["ActAsPenetratingDamage"], "extracted dash damage", 0
    )
    choice = parameters["damage_source"]
    if choice not in {"pinned_catalog_historical", "pinned_extraction_post_may_2026"}:
        raise InputError(
            "Rocket Backpack requires an explicit conflicting damage source choice"
        )
    selected = (
        row["stats"]["abilityDamage"]
        if choice == "pinned_catalog_historical"
        else damage
    )
    return {
        "entity": "rocket-backpack",
        "level": level,
        "parameters": deepcopy(parameters),
        "damage": number(selected, "selected dash damage", 0)
        * parameters["profile_factor"],
        "radius_tiles": source_quantity(
            catalog.entity("rocket-backpack")["ability"]["damageArea"], "tiles"
        )
        / 2,
        "statistics_source": (
            catalog.records["rocket-backpack"]["source"]
            if choice == "pinned_catalog_historical"
            else EXTRACTION_URL
        ),
        "source_conflict": {
            "catalog_damage": row["stats"]["abilityDamage"],
            "extracted_damage": damage,
            "official_balance_reference": ROCKET_BALANCE_SOURCE,
        },
    }


class RocketBackpackMotion:
    def __init__(self, catalog, owner_id, level, town_hall, parameters, width, height):
        self.owner_id = identifier(owner_id, "Rocket Backpack owner")
        self.model = compile_model(catalog, level, town_hall, parameters)
        number(width, "arena width", EPSILON)
        number(height, "arena height", EPSILON)
        x, y = parameters["endpoint_tiles"]
        if x > width or y > height:
            raise InputError("Dash endpoint lies outside the arena")
        self.activation_id = None
        self.state = None
        self.visited = set()

    def activate(self, activation_id, owner, time, trace):
        identifier(activation_id, "shared hero activation receipt")
        number(time, "dash activation time", 0)
        if self.activation_id is not None:
            if self.activation_id == activation_id:
                return False
            raise InputError(
                "Rocket Backpack cannot acquire a second shared ability charge"
            )
        if (
            owner["id"] != self.owner_id
            or owner["team"] != "attack"
            or not _active(owner, time)
            or owner.get("hero_model", {}).get("entity") != "dragon-duke"
            or owner["layer"] != "air"
            or owner["width"] != 0
            or owner["height"] != 0
            or owner["frozen_until"] > time
        ):
            raise InputError(
                "Rocket Backpack requires its active unfrozen point-air Duke"
            )
        start = center(owner)
        endpoint = self.model["parameters"]["endpoint_tiles"]
        distance = hypot(endpoint[0] - start[0], endpoint[1] - start[1])
        if distance <= EPSILON:
            raise InputError("Rocket Backpack endpoint must differ from origin")
        ends_at = advancing_deadline(
            time,
            distance / self.model["parameters"]["speed_tiles_per_second"],
            "Rocket Backpack dash",
        )
        self.activation_id = activation_id
        self.state = {
            "starts_at": time,
            "ends_at": ends_at,
            "origin": start,
            "endpoint": tuple(endpoint),
            "source_team": owner["team"],
            "finished": False,
            "last_time": time,
        }
        trace.append(
            {
                "event": "rocket_backpack_start",
                "source": self.owner_id,
                "time_seconds": time,
                "activation_id": activation_id,
                "ends_at": self.state["ends_at"],
            }
        )
        return True

    def position(self, time):
        number(time, "dash position time", 0)
        if self.state is None:
            raise InputError("Rocket Backpack motion has not activated")
        state = self.state
        time = min(time, state.get("interrupted_at", time))
        fraction = max(
            0,
            min(
                1, (time - state["starts_at"]) / (state["ends_at"] - state["starts_at"])
            ),
        )
        return tuple(
            a + fraction * (b - a) for a, b in zip(state["origin"], state["endpoint"])
        )

    def demands(self, time):
        """Central owner applies/removes these by source, not by overwriting peers."""
        active = (
            self.state is not None
            and not self.state["finished"]
            and self.state["starts_at"] <= time < self.state["ends_at"]
        )
        return {
            "owner": self.owner_id,
            "modifier_source": "rocket-backpack:" + self.owner_id,
            "forced_motion": active,
            "damage_immunity": active,
            "suppress_ordinary_weapon": active,
            "preserve_attack_work": active,
            "position": self.position(time) if self.state else None,
        }

    def _eligible(self, target, time):
        return (
            _active(target, time)
            and target["team"] != self.state["source_team"]
            and target["kind"] in {"building", "defense"}
            and not target.get("_tesla_hidden", False)
        )

    def prepare(self, owner, time, trace):
        if self.state is None or self.state["finished"]:
            return
        number(
            time,
            "dash event time",
            self.state["last_time"],
            self.state["ends_at"],
        )
        self.state["last_time"] = time
        if not _active(owner, time) or owner["frozen_until"] > time:
            self.state["finished"] = True
            self.state["interrupted_at"] = time
            trace.append(
                {
                    "event": "rocket_backpack_cancel",
                    "source": self.owner_id,
                    "time_seconds": time,
                }
            )

    def resolve(self, actors, time, trace, receipts):
        """Call at every shared relative contact and the terminal boundary."""
        self.prepare(actors[self.owner_id], time, trace)
        if self.state is None or self.state["finished"]:
            return {}
        point = self.position(time)
        damage = {}
        for key, target in sorted(actors.items()):
            if (
                key in self.visited
                or not self._eligible(target, time)
                or target_distance(point, target) > self.model["radius_tiles"] + EPSILON
            ):
                continue
            self.visited.add(
                key
            )  # Protected contacts also consume the once-only budget.
            damage[key] = receipts.register(
                target,
                self.model["damage"],
                time,
                source_id="rocket-backpack:" + self.owner_id,
                source_actor_id=self.owner_id,
                source_team=self.state["source_team"],
                origin="ability",
            )
            trace.append(
                {
                    "event": "rocket_backpack_contact",
                    "time_seconds": time,
                    "source": self.owner_id,
                    "target": key,
                    "damage": damage[key],
                }
            )
        if time >= self.state["ends_at"]:
            self.state["finished"] = True
            trace.append(
                {
                    "event": "rocket_backpack_end",
                    "source": self.owner_id,
                    "time_seconds": time,
                }
            )
        return damage

    def first_crossing_delay(self, actors, routes, speeds, time, horizon):
        if (
            self.state is None
            or self.state["finished"]
            or time >= self.state["ends_at"]
        ):
            return None
        point = self.position(time)
        source = {
            "x": point[0],
            "y": point[1],
            "width": 0,
            "height": 0,
            "range": self.model["radius_tiles"],
        }
        delays = []
        for key, target in actors.items():
            if key in self.visited or not self._eligible(target, time):
                continue
            delay = first_weapon_range_entry_delay(
                source,
                target,
                [self.state["endpoint"]],
                routes.get(key, []),
                self.model["parameters"]["speed_tiles_per_second"],
                speeds.get(key, 0),
                min(horizon, self.state["ends_at"] - time),
            )
            if delay is not None:
                delays.append(delay)
        return min(delays, default=None)

    def next_boundary(self):
        return (
            self.state["ends_at"] if self.state and not self.state["finished"] else None
        )

    def result(self):
        return {
            "calibrated": False,
            "model": deepcopy(self.model),
            "state": deepcopy(self.state),
            "visited": sorted(self.visited),
            "activation_id": self.activation_id,
        }
