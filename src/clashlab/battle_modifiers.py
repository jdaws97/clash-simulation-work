"""Apply one explicit battle profile to a freshly compiled, neutral scene.

Roles come from catalog identity and team, never a caller-supplied actor role.
Secondary damage policies are declared hypotheses, not verified game behavior.
"""

from copy import deepcopy
from math import isclose

from .common import InputError, identifier, number, require
from .modifiers import ROLES, resolve_battle_modifiers


VERSION = "role-aware-battle-modifiers-v1"
MARKER = "battle_modifier_application"
MODIFIER_FIELDS = {
    "hitpoints_multiplier",
    "damage_multiplier",
    "maximum_hp_damage_multiplier",
    "attack_interval_multiplier",
    "range_multiplier",
    "movement_speed_multiplier",
}
POLICY_CHOICES = {
    "maximum_hp_damage_policy": {"unchanged", "scale_with_damage"},
    "trap_damage_policy": {"unchanged", "scale_with_defense"},
    "death_damage_policy": {"unchanged", "scale_with_source_role"},
    "impact_hazard_damage_policy": {"unchanged", "scale_with_source_role"},
    "equipment_aura_damage_policy": {"unchanged", "scale_with_source_role"},
    "hero_summon_statistics_policy": {"unchanged", "inherit_parent_role"},
    "healing_and_status_policy": {"unchanged"},
}
INDEPENDENT_DAMAGE_PATHS = (
    ("death_parameters", "damage_multiplier"),
    ("bomb_death_parameters", "damage_multiplier"),
    ("lifecycle_parameters", "death", "blast_damage_multiplier"),
    ("lifecycle_parameters", "death", "poison_max_dps_multiplier"),
    ("lifecycle_parameters", "flame", "maximum_dps_multiplier"),
    ("spell_tower_parameters", "effect", "damage_multiplier"),
)


def _validate_policy(policy, mode_rules):
    if not isinstance(policy, dict) or set(policy) != {
        "profile_id",
        "policy_source",
        *POLICY_CHOICES,
    }:
        raise InputError("Battle modifier policy needs every explicit scaling policy")
    for field, choices in POLICY_CHOICES.items():
        if not isinstance(policy[field], str) or policy[field] not in choices:
            raise InputError(f"Unsupported battle modifier {field}")
    return {
        role: resolve_battle_modifiers(
            {
                "profile_id": policy["profile_id"],
                "entity_role": role,
                "maximum_hp_damage_policy": policy["maximum_hp_damage_policy"],
                "policy_source": policy["policy_source"],
            },
            mode_rules,
        )
        for role in sorted(ROLES)
    }


def _path_value(container, path):
    value = container
    for component in path:
        if not isinstance(value, dict) or component not in value:
            return None
        value = value[component]
    return value


def _assert_neutral(actor):
    if MARKER in actor:
        raise InputError("A battle profile cannot be applied to an actor twice")
    if any(key.startswith("_") for key in actor) or any(
        key in actor for key in ("hp", "maximum_hp", "next_attack", "death_time")
    ):
        raise InputError(
            "Battle modifiers require a fresh scene before runtime loading"
        )
    if any(key in actor for key in ("profile_id", "entity_role", "modifiers")):
        raise InputError("Per-actor battle profile or role overrides are not allowed")
    adapter = actor.get("entity_adapter")
    if adapter is None:
        if "summon_model" not in actor:
            raise InputError("Battle modifier roles require compiled catalog identity")
        return
    if any(key in adapter for key in (MARKER, "profile_id", "entity_role")):
        raise InputError("Per-actor battle profile or role overrides are not allowed")
    modifiers = require(adapter, "modifiers")
    if not isinstance(modifiers, dict) or set(modifiers) != MODIFIER_FIELDS | {
        "source"
    }:
        raise InputError("Battle profile inputs need the complete neutral modifiers")
    for field in sorted(MODIFIER_FIELDS):
        if number(modifiers[field], field, 0) != 1:
            raise InputError("Battle profile inputs must have neutral actor modifiers")
    for path in INDEPENDENT_DAMAGE_PATHS:
        value = _path_value(adapter, path)
        if value is not None and number(value, ".".join(path), 0) != 1:
            raise InputError("Independent death and hazard damage must start neutral")
    if "hero_model" in actor:
        for field in ("damage_multiplier", "range_multiplier"):
            if number(require(actor["hero_model"], field), field, 0) != 1:
                raise InputError("Hero runtime modifiers must start neutral")


def _catalog_role(actor, catalog):
    adapter = require(actor, "entity_adapter")
    entity_id = require(adapter, "entity")
    category = require(catalog.entity(entity_id), "category")
    team = require(actor, "team")
    if team not in {"attack", "defense"}:
        raise InputError("Battle profiles require attack or defense teams")
    if category == "hero":
        role = "attacking_hero" if team == "attack" else "defending_hero"
    elif category == "guardian":
        if team != "defense":
            raise InputError("Guardian battle modifiers require a defending guardian")
        role = "guardian"
    elif category in {"defense", "crafted-defense", "town-hall"}:
        if team != "defense":
            raise InputError("Defense battle modifiers require the defending team")
        # A weaponless early Town Hall is a passive building. A dormant Giga
        # weapon retains its compiled damage and receives the defense profile.
        role = (
            None
            if category == "town-hall"
            and not actor.get("damage", 0)
            and not any(key in actor for key in ("town_hall_model", "artillery_model"))
            else "defense"
        )
    else:
        role = None
    return entity_id, category, role


def _scale(container, path, factor, policy, changes):
    parent = container
    for component in path[:-1]:
        parent = parent[component]
    field = path[-1]
    before = number(parent[field], ".".join(map(str, path)), 0)
    after = before * factor
    parent[field] = after
    changes.append(
        {
            "path": list(path),
            "before": before,
            "multiplier": factor,
            "after": after,
            "policy": policy,
        }
    )


def _secondary_factor(policy, field, damage):
    return 1 if policy[field] == "unchanged" else damage


def _scale_actor(actor, resolved, policy, changes):
    modifiers = resolved["modifiers"]
    damage = modifiers["damage_multiplier"]
    _scale(actor, ("hitpoints",), modifiers["hitpoints_multiplier"], "role_hp", changes)
    _scale(actor, ("damage",), damage, "role_weapon_damage", changes)
    if "maximum_hp_fraction" in actor.get("attack_model", {}):
        _scale(
            actor,
            ("attack_model", "maximum_hp_fraction"),
            modifiers["maximum_hp_damage_multiplier"],
            policy["maximum_hp_damage_policy"],
            changes,
        )
    if "ramp_model" in actor:
        for index, _ in enumerate(actor["ramp_model"]["stages"]):
            _scale(
                actor,
                ("ramp_model", "stages", index, "damage_per_hit"),
                damage,
                "role_weapon_damage",
                changes,
            )
    if "weapon" in actor.get("wall_behavior", {}):
        _scale(
            actor,
            ("wall_behavior", "weapon", "damage"),
            damage,
            "role_weapon_damage",
            changes,
        )
    death_factor = _secondary_factor(policy, "death_damage_policy", damage)
    for index, effect in enumerate(actor.get("death_model", {}).get("effects", [])):
        if effect["kind"] == "area_damage":
            _scale(
                actor,
                ("death_model", "effects", index, "amount"),
                death_factor,
                policy["death_damage_policy"],
                changes,
            )
    if "death_poison" in actor.get("town_hall_model", {}):
        _scale(
            actor,
            ("town_hall_model", "death_poison", "maximum_dps"),
            death_factor,
            policy["death_damage_policy"],
            changes,
        )
    if "flame" in actor.get("artillery_model", {}):
        _scale(
            actor,
            ("artillery_model", "flame", "maximum_dps"),
            _secondary_factor(policy, "impact_hazard_damage_policy", damage),
            policy["impact_hazard_damage_policy"],
            changes,
        )
    if actor.get("spell_tower_model", {}).get("mode") == "poison":
        _scale(
            actor,
            ("spell_tower_model", "effect", "maximum_dps"),
            _secondary_factor(policy, "impact_hazard_damage_policy", damage),
            policy["impact_hazard_damage_policy"],
            changes,
        )
    if "hero_model" in actor:
        # prepare() adds Vial/Spear bonuses using this multiplier. Scaling the
        # source equipment bonus as well would apply the profile twice.
        _scale(
            actor,
            ("hero_model", "damage_multiplier"),
            damage,
            "role_weapon_damage_for_runtime_equipment_bonuses",
            changes,
        )
        for index, item in enumerate(actor["hero_model"]["equipment"]):
            if "aura_damage" in item:
                _scale(
                    actor,
                    ("hero_model", "equipment", index, "aura_damage"),
                    _secondary_factor(policy, "equipment_aura_damage_policy", damage),
                    policy["equipment_aura_damage_policy"],
                    changes,
                )


def _trap_ledger(traps, catalog, resolved, policy):
    if not isinstance(traps, list):
        raise InputError("Battle modifier traps must be an explicit list")
    ledger = []
    ids = set()
    for trap in traps:
        trap_id = identifier(require(trap, "id"), "trap instance")
        if trap_id in ids or MARKER in trap:
            raise InputError("Traps must be unique and have no previous battle profile")
        if any(key in trap for key in ("profile_id", "entity_role", "modifiers")):
            raise InputError(
                "Per-trap battle profile or role overrides are not allowed"
            )
        ids.add(trap_id)
        entity_id = require(trap, "entity")
        if catalog.entity(entity_id)["category"] != "trap" or trap["team"] != "defense":
            raise InputError("Trap modifiers require a catalog defending trap")
        expected = number(
            catalog.level(entity_id, trap["level"])["damage"], "trap damage", 0
        )
        if not isclose(trap["damage"], expected, rel_tol=1e-12, abs_tol=1e-12):
            raise InputError("Battle profile inputs must have neutral trap damage")
        if trap.get("damage_multiplier", 1) != 1:
            raise InputError("Spring Trap damage must start neutral")
        factor = _secondary_factor(
            policy,
            "trap_damage_policy",
            resolved["defense"]["modifiers"]["damage_multiplier"],
        )
        changes = []
        _scale(trap, ("damage",), factor, policy["trap_damage_policy"], changes)
        # Spring retains its source parameters; runtime reads damage directly.
        # Its per-class coefficients intentionally remain unchanged.
        trap[MARKER] = {"version": VERSION, "profile_id": policy["profile_id"]}
        ledger.append(
            {"id": trap_id, "entity": entity_id, "role": "trap", "statistics": changes}
        )
    return ledger


def apply_battle_modifiers(compiled_scene, policy, catalog, mode_rules):
    """Return a modified copy and exhaustive application ledger for one profile.

    Call after compile_entity_scene and before loading any combat runtime. This
    function consumes the inner ``scene`` object, not the compiler's report.
    Unsupported equipment level reconciliation is rejected before any result is
    returned. The caller's scene, policy, catalog and owned levels are untouched.
    """
    resolved = _validate_policy(policy, mode_rules)
    if MARKER in compiled_scene:
        raise InputError("A battle profile cannot be applied to a scene twice")
    scene = deepcopy(compiled_scene)
    actors = require(scene, "actors")
    if not isinstance(actors, list) or not actors:
        raise InputError("Battle modifiers need a nonempty compiled actor list")
    by_id = {}
    roles = {}
    for actor in actors:
        actor_id = identifier(require(actor, "id"), "actor instance")
        if actor_id in by_id:
            raise InputError("Battle modifier actors must have unique identities")
        _assert_neutral(actor)
        by_id[actor_id] = actor
        if "entity_adapter" in actor:
            roles[actor_id] = _catalog_role(actor, catalog)
    for actor in actors:
        if "entity_adapter" in actor:
            continue
        summon = actor["summon_model"]
        parent = summon.get("parent")
        if (
            parent not in roles
            or roles[parent][2] != "attacking_hero"
            or summon.get("equipment") != "magic-mirror"
            or actor["team"] != by_id[parent]["team"]
        ):
            raise InputError("Summon modifiers need a compiled attacking Mirror parent")
        role = (
            roles[parent][2]
            if policy["hero_summon_statistics_policy"] == "inherit_parent_role"
            else None
        )
        roles[actor["id"]] = (roles[parent][0], "hero_summon", role)
    ledger = []
    for actor in actors:
        entity_id, category, role = roles[actor["id"]]
        changes = []
        application = {
            "id": actor["id"],
            "entity": entity_id,
            "category": category,
            "team": actor["team"],
            "role": role,
            "statistics": changes,
        }
        if role is None:
            application["status"] = "unchanged_outside_profile_roles"
        else:
            selected = resolved[role]
            equipment = actor.get("hero_model", {}).get("equipment", [])
            if selected["equipment_statistic_reconciliation_required"] and equipment:
                raise InputError(
                    "Selected profile reduces attacking hero equipment levels; owned "
                    "and effective equipment statistics are not yet represented separately"
                )
            application["status"] = "applied_once"
            application["equipment_level_reduction"] = (
                deepcopy(selected["attacking_hero_equipment_level_reduction"])
                if role == "attacking_hero"
                else {"common": 0, "epic": 0}
            )
            application["equipment_reconciliation"] = (
                "no_equipped_items" if not equipment else "no_level_reduction_required"
            )
            if "entity_adapter" in actor:
                application["input_modifiers"] = deepcopy(
                    actor["entity_adapter"]["modifiers"]
                )
                actor["entity_adapter"]["modifiers"] = deepcopy(selected["modifiers"])
            _scale_actor(actor, selected, policy, changes)
            actor[MARKER] = {
                "version": VERSION,
                "profile_id": policy["profile_id"],
                "role": role,
            }
        ledger.append(application)
    trap_ledger = _trap_ledger(scene.get("traps", []), catalog, resolved, policy)
    application = {
        "version": VERSION,
        "profile_id": policy["profile_id"],
        "policy": deepcopy(policy),
        "resolved_roles": resolved,
        "actors": ledger,
        "traps": trap_ledger,
        "unchanged": [
            "ordinary troop and passive structure statistics",
            "attack intervals, range, movement, projectile and activation timing",
            "healing, recovery, status durations and magnitude, spring capacity and push",
            "owned hero and equipment levels and raw source statistic metadata",
            "scene effects, buffs and independently declared persistent hazards",
        ],
        "limitations": [
            "Role profiles do not validate battle mechanics or establish replay equivalence",
            "Secondary damage scaling follows the caller's explicit hypothesis",
            "Profiles reducing equipped attacking hero levels are rejected pending effective-level reconciliation",
        ],
        "full_game_prediction": False,
    }
    scene[MARKER] = {
        "version": VERSION,
        "profile_id": policy["profile_id"],
        "policy": deepcopy(policy),
    }
    return {"scene": scene, "application": application, "full_game_prediction": False}
