"""Experimental, caller-declared Revenge Tower lifecycle; never inferred phases.

The publisher establishes four phases and 5/25/50 destroyed-building thresholds.
The pinned catalog has only three weapon modes and no per-phase HP. Callers must
explicitly choose the missing mapping and HP multipliers. Released shots retain
their captured pattern; destruction cannot revive a tower.
"""

from copy import deepcopy

from .common import InputError, identifier, number, require
from .rates import attack_rate, attack_resume_time, rescale_remaining_cooldown
from .spatial import EPSILON, _active


EXPERIMENT = "experimental_four_phase_mapping_not_replay_verified"
POLICIES = {
    "verification": EXPERIMENT,
    "thresholds": [5, 25, 50],
    "eligibility": "counted_same_team_structures_excluding_self",
    "transition": "after_settled_health_before_next_weapon_phase",
    "health_transition": "preserve_fraction_no_revive",
    "attack_work": "preserve_fraction_excluding_freeze",
    "activation_readiness": "one_full_selected_interval_after_current_freeze",
    "released_projectiles": "retain_launch_phase_independent_of_source",
}


def validate_parameters(parameters):
    if set(parameters) != set(POLICIES) | {
        "source",
        "phase_modes",
        "hp_multipliers",
        "chain",
    }:
        raise InputError(
            "Revenge Tower needs every explicit experimental lifecycle policy"
        )
    identifier(parameters["source"], "Revenge Tower policy source")
    for key, value in POLICIES.items():
        if parameters[key] != value:
            raise InputError(
                f"Unsupported Revenge Tower {key}; explicit experimental policy required"
            )
    # There is no catalog normal weapon. An absent initial weapon is a selected
    # hypothesis, not a claim that the live game is dormant before five deaths.
    if parameters["phase_modes"] != [None, "stage1", "stage2", "stage3"]:
        raise InputError(
            "Supported experimental mapping is dormant then three catalog modes"
        )
    multipliers = parameters["hp_multipliers"]
    if (
        not isinstance(multipliers, list)
        or len(multipliers) != 4
        or multipliers[0] != 1
    ):
        raise InputError(
            "Revenge Tower needs four caller-supplied HP multipliers starting at one"
        )
    for multiplier in multipliers:
        number(multiplier, "Revenge phase HP multiplier", 1)
    if multipliers != sorted(multipliers):
        raise InputError("Revenge Tower HP phases must be nondecreasing")
    chain = parameters["chain"]
    if set(chain) != {
        "jump_metric",
        "jump_delay_seconds",
        "tie_break",
        "allow_protected_links",
    }:
        raise InputError(
            "Revenge Tower chain geometry and release timing must be explicit"
        )


def compile_revenge_tower(actor, instance, entity, row, modifiers):
    from .advanced_defenses import _defense_identity, _projectile, _weapon, REVENGE_GAPS
    from .combat import validate_pattern

    _defense_identity(instance, entity, row, "revenge-tower", {"stage1"})
    parameters = require(instance, "revenge_parameters")
    validate_parameters(parameters)
    phases = []
    for mode_name in ("stage1", "stage2", "stage3"):
        mode = entity["modes"][mode_name]
        stats = row["stats"][mode_name]
        damage = number(stats["damagePerShot"], "Revenge per-shot damage", EPSILON)
        pattern = {
            "kind": "single" if mode_name == "stage1" else "chain",
            "source": actor["source"],
            "target_kinds": ["unit"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
            "projectile": _projectile(instance["attack_parameters"]),
        }
        if mode_name != "stage1":
            pattern.update(
                **deepcopy(parameters["chain"]),
                jump_range=mode["chainRange"],
                damage_multipliers=[1, stats["secondaryChainDamagePerShot"] / damage],
            )
            if mode_name == "stage3":
                pattern["damage_multipliers"].append(
                    stats["tertiaryChainDamagePerShot"] / damage
                )
        validate_pattern(pattern)
        phases.append(
            {
                "damage_ratio": damage / row["stats"]["stage1"]["damagePerShot"],
                "interval_ratio": mode["attackSpeed"]
                / entity["modes"]["stage1"]["attackSpeed"],
                "range_ratio": mode["range"] / entity["modes"]["stage1"]["range"],
                "pattern": pattern,
            }
        )
    _weapon(actor, instance, entity, row, modifiers, deepcopy(phases[0]["pattern"]))
    actor["revenge_model"] = {**deepcopy(parameters), "phases": phases}
    actor["entity_adapter"].update(
        revenge_parameters=deepcopy(parameters),
        behavior_verification=EXPERIMENT,
        source_audit=deepcopy(REVENGE_GAPS),
    )
    return actor


class RevengeTowerCombat:
    """Called by the existing advanced-defense preparation hooks."""

    def __init__(self, actors, combat):
        self.combat = combat
        self.models = {}
        self.states = {}
        self.baselines = {}
        for key, actor in actors.items():
            if "revenge_model" not in actor:
                continue
            model = deepcopy(actor["revenge_model"])
            validate_parameters({k: v for k, v in model.items() if k != "phases"})
            if actor.get("entity_adapter", {}).get("entity") != "revenge-tower":
                raise InputError("Revenge lifecycle requires its owning Revenge Tower")
            if len(model["phases"]) != 3:
                raise InputError(
                    "Revenge lifecycle requires three explicit compiled weapons"
                )
            self.models[key] = model
            self.states[key] = {
                "phase": 0,
                "destroyed_buildings": 0,
                "destroyed": False,
            }
            # Capture AFTER account/mode modifiers; ratios avoid bypassing those
            # modifiers on subsequent transitions.
            self.baselines[key] = {
                k: actor[k]
                for k in ("damage", "maximum_hp", "range", "attack_interval_seconds")
            }
            actor["damage"] = 0

    def dormant(self, actor):
        return actor["id"] in self.states and self.states[actor["id"]]["phase"] == 0

    def prepare(self, actors, time, trace):
        for key, model in self.models.items():
            actor, state = actors[key], self.states[key]
            if not _active(actor, time):
                if actor["hp"] <= 0:
                    state["destroyed"] = True
                continue
            destroyed = sum(
                target["death_time"] is not None
                for other, target in actors.items()
                if other != key
                and target["team"] == actor["team"]
                and target["counts_for_destruction"]
                and target["kind"] in {"building", "defense"}
            )
            state["destroyed_buildings"] = destroyed
            phase = sum(destroyed >= threshold for threshold in model["thresholds"])
            if phase <= state["phase"]:
                continue
            old_phase = state["phase"]
            old_interval = actor["attack_interval_seconds"]
            fraction = actor["hp"] / actor["maximum_hp"]
            baseline = self.baselines[key]
            selected = model["phases"][phase - 1]
            actor["maximum_hp"] = (
                baseline["maximum_hp"] * model["hp_multipliers"][phase]
            )
            actor["hp"] = actor["maximum_hp"] * fraction
            actor["damage"] = baseline["damage"] * selected["damage_ratio"]
            actor["range"] = baseline["range"] * selected["range_ratio"]
            actor["attack_interval_seconds"] = (
                baseline["attack_interval_seconds"] * selected["interval_ratio"]
            )
            actor["attack_model"] = deepcopy(selected["pattern"])
            self.combat.patterns[key] = deepcopy(selected["pattern"])
            rescale_remaining_cooldown(
                actor, time, 1 / old_interval, 1 / actor["attack_interval_seconds"]
            )
            if old_phase == 0:
                # A strictly future weapon boundary also prevents an immediate
                # activation after weapon damage being delayed by solver step.
                actor["next_attack"] = attack_resume_time(actor, time) + actor[
                    "attack_interval_seconds"
                ] / attack_rate(actor)
            state["phase"] = phase
            trace.append(
                {
                    "event": "revenge_tower_phase",
                    "time_seconds": time,
                    "source": key,
                    "previous_phase": old_phase,
                    "phase": phase,
                    "destroyed_buildings": destroyed,
                    "hp": actor["hp"],
                    "maximum_hp": actor["maximum_hp"],
                    "verification": EXPERIMENT,
                }
            )

    def frame(self, actor):
        state = self.states.get(actor["id"])
        return {"revenge_tower_state": deepcopy(state)} if state is not None else {}

    def result(self):
        return {"states": deepcopy(self.states), "verification": EXPERIMENT}
