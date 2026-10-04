"""Attacking Clan Castle inventory and controlled payload release hypotheses.

Reinforcement resources belong to the attacking army. They never borrow the
defending castle's roster or its release trigger. Explicit deployment regions
are caller hypotheses, not verified in-game exclusion zones.
"""

from collections import Counter
from copy import deepcopy
from math import floor, hypot

from .common import InputError, identifier, integer, number, require
from .garrisons import _receiver_lab_requirement
from .spatial import EPSILON, _active
from .attack_spell_models import SUPPORTED_ATTACK_SPELLS


RECEIVED_LEVEL_BASIS = "snapshot_receiver_lab_cap_with_unlock_floor"
MEMBER_PARAMETERS = {
    "source",
    "group_id",
    "donor_town_hall",
    "receiver_clan_castle_level",
    "level_basis",
}
REINFORCEMENT_RULES = {
    "attacking_cc_inventory": "separate_exact_donated_troop_and_spell_resources_with_confirmed_received_caps",
    "attacking_cc_delivery": "one_declared_direct_or_single_siege_delivery_never_both",
    "attacking_cc_release": "ordered_controlled_reserves_with_explicit_delays_from_captured_delivery_point",
    "attacking_cc_spawn": "explicit_offsets_then_bounded_nearest_clear_cell_for_ground_members",
    "attacking_cc_deployment": "caller_sourced_allowed_regions_are_hypotheses_not_verified_game_exclusion_zones",
    "attacking_cc_persistence": "pending_releases_and_released_troops_survive_carrier_loss",
}
GROUP_FIELDS = {
    "id",
    "source",
    "receiver_town_hall",
    "receiver_clan_castle_level",
    "member_ids",
    "delivery",
    "release",
    "deployment_policy",
}
SUPPORTED_PAID_SPELLS = {
    "freeze-spell",
    "healing-spell",
    "rage-spell",
    "haste-spell",
    *SUPPORTED_ATTACK_SPELLS,
}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise InputError(f"{label} requires its complete explicit parameters")


def validate_reinforcement_deployment(command, actors):
    if command.get("kind") == "deploy" and any(
        "payload_member_model" in actors.get(actor_id, {})
        for actor_id in command.get("targets", [])
    ):
        raise InputError(
            "Payload reserves can only deploy through their declared delivery group"
        )


def _validate_member_parameters(parameters, maximum_town_hall):
    _fields(parameters, MEMBER_PARAMETERS, "Attacking payload member")
    identifier(parameters["source"], "payload member evidence")
    identifier(parameters["group_id"], "payload group ID")
    integer(
        parameters["donor_town_hall"], "payload donor Town Hall", 1, maximum_town_hall
    )
    integer(parameters["receiver_clan_castle_level"], "receiving castle level", 1)
    if parameters["level_basis"] != RECEIVED_LEVEL_BASIS:
        raise InputError("Received payload levels need an explicit laboratory mapping")


def validate_received_entity(entity_id, level, receiver_town_hall, parameters, catalog):
    """Validate source relations without treating them as confirmed receipt."""
    _validate_member_parameters(parameters, catalog.maximum_town_hall)
    if not catalog.available(entity_id, level, parameters["donor_town_hall"]):
        raise InputError("The donor cannot supply the declared reinforcement level")
    castle_level = parameters["receiver_clan_castle_level"]
    if not catalog.available("clan-castle", castle_level, receiver_town_hall):
        raise InputError(
            "The receiving castle level is unavailable at the recipient Town Hall"
        )
    row = catalog.level(entity_id, level)
    laboratory = _receiver_lab_requirement(entity_id, row, catalog)
    castle = catalog.level("clan-castle", castle_level)
    if laboratory > castle["labLevelCap"]:
        raise InputError(
            "The received reinforcement exceeds the declared receiver laboratory mapping"
        )
    return laboratory


def attach_payload_member(actor, instance, entity, row, catalog):
    """Attach reserve ownership after the ordinary attacking-troop compiler.

    The caller validates the donor relation before bypassing the recipient's
    self-training level ceiling. The ordinary weapon/lifecycle adapter remains
    mandatory; this helper never creates a generic unsupported troop.
    """
    from .adapters import partial_adapter_status

    parameters = require(instance, "payload_member_parameters")
    if (
        entity["category"] != "troop"
        or not partial_adapter_status(entity)["available"]
        or actor["team"] != "attack"
        or actor["kind"] != "unit"
        or actor["counts_for_destruction"]
        or actor["spawn_seconds"] != "controlled"
        or actor["entity_adapter"]["entity"] != entity["id"]
        or any(
            field in actor
            for field in ("garrison_member_model", "summon_model", "siege_model")
        )
    ):
        raise InputError(
            "Payloads require independently supported, controlled attacking troops"
        )
    laboratory = validate_received_entity(
        entity["id"], instance["level"], instance["town_hall"], parameters, catalog
    )
    if row["level"] != instance["level"]:
        raise InputError("Payload statistics and declared received level differ")
    actor["payload_member_model"] = {
        "entity": entity["id"],
        "level": instance["level"],
        "receiver_town_hall": instance["town_hall"],
        "housing_space": integer(require(entity, "housingSpace"), "payload housing", 1),
        "laboratory_required": laboratory,
        "parameters": deepcopy(parameters),
    }
    actor["entity_adapter"]["payload_member_parameters"] = deepcopy(parameters)
    actor["entity_adapter"]["town_hall"] = instance["town_hall"]
    return actor


def compile_received_spell(instance, catalog, compiler):
    """Apply an ordinary spell adapter after checking its separate donor source."""
    origin = instance.get("origin", "army")
    if origin == "army":
        if "received_spell_parameters" in instance:
            raise InputError("Owned spells cannot use a received-level override")
        return compiler(instance, catalog)
    if origin != "clan_castle":
        raise InputError("Spell origin must identify army or Clan Castle inventory")
    entity_id = require(instance, "entity")
    if entity_id not in SUPPORTED_PAID_SPELLS:
        raise InputError("Received spell behavior requires its own supported adapter")
    parameters = require(instance, "received_spell_parameters")
    _fields(parameters, MEMBER_PARAMETERS - {"group_id"}, "Received spell")
    receiver = integer(require(instance, "town_hall"), "spell recipient Town Hall", 1)
    level = integer(require(instance, "level"), "received spell level", 1)
    laboratory = validate_received_entity(
        entity_id,
        level,
        receiver,
        {**parameters, "group_id": f"spell:{instance['id']}"},
        catalog,
    )
    donor_instance = deepcopy(instance)
    donor_instance["town_hall"] = parameters["donor_town_hall"]
    result = compiler(donor_instance, catalog)
    result["entity_adapter"].update(
        town_hall=receiver,
        origin="clan_castle",
        received_spell_parameters=deepcopy(parameters),
        receiver_laboratory_requirement=laboratory,
    )
    return result


def _validate_deployment_policy(policy):
    _fields(
        policy,
        {"source", "kind", "regions", "point_policy"},
        "Reinforcement deployment policy",
    )
    identifier(policy["source"], "deployment region evidence")
    if (
        policy["kind"] != "explicit_allowed_regions_hypothesis"
        or policy["point_policy"]
        != "inside_declared_region_and_clear_of_hostile_footprints"
    ):
        raise InputError(
            "Reinforcement deployment regions require a named conditional policy"
        )
    regions = policy["regions"]
    if not isinstance(regions, list) or not regions:
        raise InputError("Deployment needs at least one explicit allowed rectangle")
    for region in regions:
        _fields(region, {"left", "top", "right", "bottom"}, "Deployment rectangle")
        for coordinate in region.values():
            number(coordinate, "deployment region coordinate", 0)
        if region["left"] >= region["right"] or region["top"] >= region["bottom"]:
            raise InputError("Deployment rectangles need positive area")


def _validate_group(parameters):
    _fields(parameters, GROUP_FIELDS, "Attacking reinforcements")
    identifier(parameters["id"], "reinforcement group ID")
    identifier(parameters["source"], "reinforcement group evidence")
    integer(parameters["receiver_town_hall"], "recipient Town Hall", 1)
    integer(parameters["receiver_clan_castle_level"], "receiving castle level", 1)
    member_ids = parameters["member_ids"]
    if not isinstance(member_ids, list) or len(member_ids) != len(set(member_ids)):
        raise InputError("Payload group needs an ordered list of unique members")
    for member_id in member_ids:
        identifier(member_id, "payload actor ID")
    delivery = parameters["delivery"]
    _fields(delivery, {"kind", "carrier_id"}, "Payload delivery")
    if delivery["kind"] == "direct":
        if delivery["carrier_id"] is not None or not member_ids:
            raise InputError(
                "Direct Clan Castle deployment requires troops and no carrier"
            )
    elif delivery["kind"] == "siege":
        identifier(delivery["carrier_id"], "payload siege carrier")
    else:
        raise InputError("Payload delivery must be direct or a single linked siege")
    release = parameters["release"]
    _fields(
        release,
        {
            "initial_delay_seconds",
            "interval_seconds",
            "order",
            "offsets",
            "position_policy",
            "maximum_displacement_tiles",
            "blocked_position",
            "initial_state",
            "clock",
        },
        "Attacking payload release",
    )
    number(release["initial_delay_seconds"], "payload release delay", 0)
    number(release["interval_seconds"], "payload release interval", EPSILON)
    number(release["maximum_displacement_tiles"], "payload position search bound", 0)
    policies = {
        "order": "declared_order",
        "position_policy": "explicit_offset_then_nearest_clear_ground_cell",
        "blocked_position": "hold_member_until_legal_point_exists",
        "initial_state": "fresh_health_and_release_relative_attack_clock",
        "clock": "continues_after_carrier_loss",
    }
    for field, value in policies.items():
        if release[field] != value:
            raise InputError(f"Unsupported payload {field}")
    offsets = release["offsets"]
    if not isinstance(offsets, dict) or set(offsets) != set(member_ids):
        raise InputError("Payload release needs an explicit offset per reserve")
    for offset in offsets.values():
        _fields(offset, {"x", "y"}, "Payload offset")
        number(offset["x"], "payload horizontal offset")
        number(offset["y"], "payload vertical offset")
    _validate_deployment_policy(parameters["deployment_policy"])


def compile_attacking_reinforcements(parameters, catalog, actors):
    """Bind a single attacking delivery group to its compiled actors."""
    _validate_group(parameters)
    receiver = parameters["receiver_town_hall"]
    castle_level = parameters["receiver_clan_castle_level"]
    if not catalog.available("clan-castle", castle_level, receiver):
        raise InputError("Declared receiving Clan Castle is unavailable")
    castle = catalog.level("clan-castle", castle_level)
    model = {
        "parameters": deepcopy(parameters),
        "capacity": integer(
            require(castle, "troopCapacity"), "receiver troop capacity", 0
        ),
        "laboratory_cap": integer(
            require(castle, "labLevelCap"), "receiver laboratory cap", 0
        ),
        "spell_capacity": integer(
            require(castle, "spellCapacity"), "receiver spell capacity", 0
        ),
    }
    _validate_bindings(model, actors)
    if parameters["delivery"]["kind"] == "siege":
        carrier = actors[parameters["delivery"]["carrier_id"]]
        source = carrier["siege_model"]["parameters"]
        if source["origin"] == "donated":
            identity = carrier["entity_adapter"]
            validate_received_entity(
                identity["entity"],
                identity["level"],
                receiver,
                {
                    "source": source["source"],
                    "group_id": parameters["id"],
                    "donor_town_hall": source["donor_town_hall"],
                    "receiver_clan_castle_level": castle_level,
                    "level_basis": RECEIVED_LEVEL_BASIS,
                },
                catalog,
            )
    return model


def _validate_bindings(model, actors):
    _fields(
        model,
        {"parameters", "capacity", "laboratory_cap", "spell_capacity"},
        "Compiled reinforcement group",
    )
    parameters = model["parameters"]
    _validate_group(parameters)
    for field in ("capacity", "laboratory_cap", "spell_capacity"):
        integer(model[field], field, 0)
    members = {
        actor_id: actor
        for actor_id, actor in actors.items()
        if "payload_member_model" in actor
    }
    if set(members) != set(parameters["member_ids"]):
        raise InputError(
            "Every attacking payload reserve must belong to the declared delivery group"
        )
    housing = 0
    for actor_id, actor in members.items():
        member = actor["payload_member_model"]
        _fields(
            member,
            {
                "entity",
                "level",
                "receiver_town_hall",
                "housing_space",
                "laboratory_required",
                "parameters",
            },
            "Compiled payload member",
        )
        _validate_member_parameters(member["parameters"], None)
        if (
            actor["team"] != "attack"
            or actor["kind"] != "unit"
            or actor["spawn_seconds"] != "controlled"
            or actor["counts_for_destruction"]
            or member["parameters"]["group_id"] != parameters["id"]
            or member["parameters"]["receiver_clan_castle_level"]
            != parameters["receiver_clan_castle_level"]
            or member["receiver_town_hall"] != parameters["receiver_town_hall"]
            or member["laboratory_required"] > model["laboratory_cap"]
            or actor.get("entity_adapter", {}).get("entity") != member["entity"]
            or actor["entity_adapter"].get("level") != member["level"]
        ):
            raise InputError(
                f"Payload member linkage or received statistics are invalid: {actor_id}"
            )
        housing += integer(member["housing_space"], "payload member housing", 1)
    if housing > model["capacity"]:
        raise InputError("Attacking payload exceeds the receiving Clan Castle capacity")
    carrier_id = parameters["delivery"]["carrier_id"]
    carriers = {
        actor_id for actor_id, actor in actors.items() if "siege_model" in actor
    }
    if parameters["delivery"]["kind"] == "siege":
        if carriers != {carrier_id}:
            raise InputError(
                "Payload delivery requires exactly its one declared siege carrier"
            )
        carrier = actors[carrier_id]
        if carrier["siege_model"]["parameters"]["payload_group_id"] != parameters["id"]:
            raise InputError("Siege carrier points at a different payload group")
    elif carriers:
        raise InputError(
            "Direct Clan Castle deployment cannot coexist with a selected siege"
        )


def validate_reinforcement_inventory(model, actors, army, account, catalog):
    """Keep CC receipts, own army housing and the single siege slot independent."""
    from .army import validate_army

    validate_army(army, account, catalog)
    _validate_bindings(model, actors)
    parameters = model["parameters"]
    if parameters["receiver_town_hall"] != account["town_hall"]:
        raise InputError("Reinforcement receiver differs from the attacking account")
    if (
        account["capacities"]["clan_castle_troops"] != model["capacity"]
        or account["capacities"]["clan_castle_spells"] != model["spell_capacity"]
    ):
        raise InputError(
            "Entered Clan Castle capacities disagree with the selected receiver level"
        )
    expected = Counter(
        {
            (item["id"], item["level"]): item["count"]
            for item in army["clan_castle"]["troops"]
        }
    )
    actual = Counter()
    bindings = {}
    for member_id in parameters["member_ids"]:
        member = actors[member_id]["payload_member_model"]
        key = member["entity"], member["level"]
        actual[key] += 1
        bindings[member_id] = {
            "origin": "clan_castle_troops",
            "entity": key[0],
            "level": key[1],
            "ordinal": actual[key],
        }
    if actual != expected:
        raise InputError(
            "Payload actor identity, count and level must match the attacking CC troop inventory"
        )
    delivery = parameters["delivery"]
    siege = army["siege"]
    if delivery["kind"] == "direct":
        if siege is not None:
            raise InputError(
                "Direct reinforcement delivery cannot spend a siege deployment"
            )
    else:
        if siege is None:
            raise InputError(
                "The selected payload carrier has no charged siege resource"
            )
        carrier = actors[delivery["carrier_id"]]
        identity = carrier["entity_adapter"]
        if (
            identity["entity"] != siege["id"]
            or identity["level"] != siege["level"]
            or carrier["siege_model"]["parameters"]["origin"] != siege["origin"]
        ):
            raise InputError("The carrier differs from the declared siege slot")
        bindings[carrier["id"]] = {
            "origin": "siege",
            "entity": siege["id"],
            "level": siege["level"],
            "siege_origin": siege["origin"],
        }
    return bindings


def validate_spell_origin_counts(army, spells):
    """Bind charges once per cast; an own spell cannot also spend a CC charge."""
    expected = {"army": Counter(), "clan_castle": Counter()}
    inventories = {
        "army": army["spells"],
        "clan_castle": army["clan_castle"]["spells"],
    }
    for origin, inventory in inventories.items():
        seen_entities = set()
        for item in inventory:
            entity_id = require(item, "id")
            if entity_id in seen_entities or entity_id not in SUPPORTED_PAID_SPELLS:
                raise InputError("Spell inventory requires unique supported entities")
            seen_entities.add(entity_id)
            level = integer(require(item, "level"), "spell inventory level", 1)
            count = integer(require(item, "count"), "spell inventory count", 1)
            expected[origin][entity_id, level] = count
    actual = {origin: Counter() for origin in expected}
    bindings = {}
    for spell in spells:
        cast_id = identifier(require(spell, "id"), "paid spell cast ID")
        if cast_id in bindings:
            raise InputError("A spell cast cannot spend more than one origin resource")
        origin = require(spell, "origin")
        if origin not in expected or spell["entity"] not in SUPPORTED_PAID_SPELLS:
            raise InputError("Unsupported spell origin or spell behavior")
        key = spell["entity"], integer(spell["level"], "paid spell level", 1)
        actual[origin][key] += 1
        if actual[origin][key] > expected[origin][key]:
            raise InputError(
                "Paid spell casts exceed their separately declared origin inventory"
            )
        bindings[cast_id] = {
            "origin": f"{origin}_spells",
            "entity": key[0],
            "level": key[1],
            "ordinal": actual[origin][key],
        }
    return bindings


class ReinforcementCombat:
    """Release owned payload reserves from one captured direct/carrier position."""

    def __init__(self, actors, model, width, height):
        _validate_bindings(model, actors)
        self.actors = actors
        self.model = deepcopy(model)
        self.parameters = self.model["parameters"]
        self.width = width
        self.height = height
        self.state = {
            "phase": "waiting_for_delivery",
            "delivery_time": None,
            "delivery_point": None,
            "delivery_reason": None,
            "remaining": list(self.parameters["member_ids"]),
            "released": [],
            "next_release": None,
        }
        self.member_states = {
            member_id: {"phase": "reserve", "released_at": None}
            for member_id in self.parameters["member_ids"]
        }
        for region in self.parameters["deployment_policy"]["regions"]:
            if region["right"] > width or region["bottom"] > height:
                raise InputError("Declared deployment region lies outside the board")

    def _blocked_cells(self, time):
        return {
            (x, y)
            for actor in self.actors.values()
            if actor["blocking"] and _active(actor, time)
            for x in range(actor["x"], actor["x"] + actor["width"])
            for y in range(actor["y"], actor["y"] + actor["height"])
        }

    def validate_deployment_point(self, point, time=None):
        _fields(point, {"x", "y"}, "Reinforcement deployment point")
        x = number(point["x"], "deployment x", 0, self.width - EPSILON)
        y = number(point["y"], "deployment y", 0, self.height - EPSILON)
        regions = self.parameters["deployment_policy"]["regions"]
        if not any(
            region["left"] <= x < region["right"]
            and region["top"] <= y < region["bottom"]
            for region in regions
        ):
            raise InputError(
                "Deployment point violates the explicit caller-sourced allowed-region hypothesis"
            )
        if time is None:
            return
        for actor in self.actors.values():
            if (
                actor["team"] != "attack"
                and actor["blocking"]
                and _active(actor, time)
                and actor["x"] <= x < actor["x"] + actor["width"]
                and actor["y"] <= y < actor["y"] + actor["height"]
            ):
                raise InputError(
                    "Reinforcement deployment point occupies a hostile footprint"
                )

    def validate_command(self, command, time=None):
        validate_reinforcement_deployment(command, self.actors)
        kind = command.get("kind")
        if kind == "deploy":
            targets = command.get("targets", [])
            if set(targets) & set(self.member_states):
                raise InputError(
                    "Payload reserves can only deploy through their declared delivery group"
                )
            carrier_id = self.parameters["delivery"]["carrier_id"]
            if carrier_id in targets:
                self.validate_deployment_point(command["positions"][carrier_id], time)
        elif kind == "clan_castle_deploy":
            _fields(
                command,
                {"id", "kind", "time_seconds", "group_id", "position"},
                "Direct Clan Castle command",
            )
            identifier(command["id"], "direct reinforcement command ID")
            number(command["time_seconds"], "direct reinforcement command time", 0)
            if (
                self.parameters["delivery"]["kind"] != "direct"
                or command["group_id"] != self.parameters["id"]
            ):
                raise InputError(
                    "Direct Clan Castle command does not own this delivery group"
                )
            self.validate_deployment_point(command["position"], time)

    def apply_commands(self, commands, time, trace):
        remaining = []
        for command in commands:
            self.validate_command(command, time)
            if command["kind"] == "clan_castle_deploy":
                if self.state["delivery_time"] is not None:
                    raise InputError(
                        "The attacking Clan Castle resource was already deployed"
                    )
                self.begin_release(
                    time, command["position"], "direct_command", None, trace
                )
            else:
                remaining.append(command)
        return remaining

    def begin_release(self, time, point, reason, carrier_id, trace):
        expected = self.parameters["delivery"]["carrier_id"]
        if carrier_id != expected:
            raise InputError("The releasing carrier does not own this payload")
        if self.state["delivery_time"] is not None:
            return False
        number(time, "payload delivery time", 0)
        _fields(point, {"x", "y"}, "Captured payload position")
        for value in point.values():
            number(value, "captured payload coordinate")
        self.state.update(
            phase="releasing" if self.state["remaining"] else "empty",
            delivery_time=time,
            delivery_point=deepcopy(point),
            delivery_reason=reason,
            next_release=time + self.parameters["release"]["initial_delay_seconds"],
        )
        trace.append(
            {
                "time_seconds": time,
                "event": "payload_delivery",
                "group": self.parameters["id"],
                "carrier": carrier_id,
                "reason": reason,
                "position": deepcopy(point),
            }
        )
        return True

    def _release_point(self, member_id, time):
        release = self.parameters["release"]
        point = self.state["delivery_point"]
        offset = release["offsets"][member_id]
        desired = point["x"] + offset["x"], point["y"] + offset["y"]
        actor = self.actors[member_id]
        inside = 0 <= desired[0] < self.width and 0 <= desired[1] < self.height
        blocked = self._blocked_cells(time)
        if inside and (
            actor["movement"] == "air"
            or (floor(desired[0]), floor(desired[1])) not in blocked
        ):
            return desired
        if actor["movement"] == "air":
            return None
        choices = []
        bound = release["maximum_displacement_tiles"]
        for x in range(
            max(0, floor(desired[0] - bound)),
            min(self.width, floor(desired[0] + bound) + 1),
        ):
            for y in range(
                max(0, floor(desired[1] - bound)),
                min(self.height, floor(desired[1] + bound) + 1),
            ):
                distance = hypot(x + 0.5 - desired[0], y + 0.5 - desired[1])
                if (x, y) not in blocked and distance <= bound + EPSILON:
                    choices.append((distance, y, x))
        if not choices:
            return None
        _, y, x = min(choices)
        return x + 0.5, y + 0.5

    def prepare(self, time, trace, allow_release=True):
        for member_id, state in self.member_states.items():
            actor = self.actors[member_id]
            if state["phase"] == "reserve" and actor["spawn_seconds"] != "controlled":
                raise InputError("Payload reserve was externally deployed")
            if state["phase"] == "released" and not _active(actor, time):
                state["phase"] = "dead"
        if (
            not allow_release
            or self.state["phase"] != "releasing"
            or self.state["next_release"] > time + EPSILON
        ):
            return False
        member_id = self.state["remaining"][0]
        point = self._release_point(member_id, time)
        if point is None:
            return False
        actor = self.actors[member_id]
        if actor["hp"] != actor["maximum_hp"]:
            raise InputError(
                "An undeployed payload reserve cannot carry unexplained health changes"
            )
        actor.update(spawn_seconds=time, x=point[0], y=point[1], target=None)
        actor["next_attack"] = time + actor["first_attack_seconds"]
        self.member_states[member_id].update(phase="released", released_at=time)
        self.state["remaining"].pop(0)
        self.state["released"].append(member_id)
        self.state["phase"] = "releasing" if self.state["remaining"] else "empty"
        self.state["next_release"] = (
            time + self.parameters["release"]["interval_seconds"]
        )
        trace.append(
            {
                "time_seconds": time,
                "event": "payload_released",
                "group": self.parameters["id"],
                "member": member_id,
                "x": point[0],
                "y": point[1],
            }
        )
        return True

    def next_boundary(self, time):
        boundary = self.state["next_release"]
        return (
            boundary
            if self.state["phase"] == "releasing" and boundary > time + EPSILON
            else None
        )

    def release_ready(self, time):
        return (
            self.state["phase"] == "releasing"
            and self.state["next_release"] <= time + EPSILON
            and self._release_point(self.state["remaining"][0], time) is not None
        )

    def frame(self, actor):
        state = self.member_states.get(actor["id"])
        return (
            {"payload_phase": state["phase"], "payload_group": self.parameters["id"]}
            if state
            else {}
        )

    def result(self):
        return {
            "group": deepcopy(self.state),
            "members": deepcopy(self.member_states),
            "deployment_policy": deepcopy(self.parameters["deployment_policy"]),
            "game_exclusion_zones_validated": False,
            "full_game_prediction": False,
        }
