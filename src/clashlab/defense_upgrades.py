"""Absolute supercharge rows and explicitly sourced Inferno fuel contracts."""

from copy import deepcopy

from .common import InputError, identifier, integer, number, require
from .spatial import _active


class _SelectedRowCatalog:
    """Read-only catalog view; original records/statistics remain untouched."""

    def __init__(self, catalog, entity_id, base_level, selected):
        self.catalog, self.entity_id, self.base_level = catalog, entity_id, base_level
        self.selected = deepcopy(selected)
        self.selected.update(level=base_level, supercharge=False)

    def __getattr__(self, name):
        return getattr(self.catalog, name)

    def level(self, entity_id, level, supercharge=False):
        if entity_id == self.entity_id and level == self.base_level and not supercharge:
            return deepcopy(self.selected)
        return self.catalog.level(entity_id, level, supercharge)


def compile_supercharged_defense(instance, catalog, conversion, compiler, **flags):
    """Reuse the defense's existing lifecycle compiler with an absolute source row.

    Integration must bind the base level and charge tier independently. A tier
    number is not a building level, and the selected row is not an additive bonus.
    """
    parameters = require(instance, "supercharge_parameters")
    if set(parameters) != {
        "source",
        "status",
        "tier",
        "base_level",
        "statistics_mapping",
    }:
        raise InputError("Supercharge needs explicit base level, tier and provenance")
    identifier(parameters["source"], "supercharge evidence")
    if (
        parameters["status"] != "explicit_uncalibrated_hypothesis"
        or parameters["statistics_mapping"] != "absolute_pinned_supercharge_row"
    ):
        raise InputError("Unknown supercharge statistic mapping")
    entity_id = instance["entity"]
    entity = catalog.entity(entity_id)
    if (
        entity["category"] != "defense"
        or instance["team"] != "defense"
        or instance["supercharge"] is not True
    ):
        raise InputError("Only explicit defending supercharges use this adapter")
    base_level = integer(parameters["base_level"], "supercharge base level", 1)
    tier = integer(parameters["tier"], "supercharge tier", 1)
    ordinary = [row for row in entity["levels"] if not row.get("supercharge")]
    if (
        base_level != max(row["level"] for row in ordinary)
        or instance["level"] != base_level
    ):
        raise InputError("Supercharge requires the entity's final ordinary level")
    selected = catalog.level(entity_id, tier, True)
    if selected["townHallRequired"] > instance["town_hall"] or not catalog.available(
        entity_id, base_level, instance["town_hall"]
    ):
        raise InputError(
            "Supercharge tier or base level is unavailable at this Town Hall"
        )
    # No merging of missing stats with the base row: required mode quantities
    # remain absent and the ordinary compiler rejects them.
    shadow = deepcopy(instance)
    shadow.pop("supercharge_parameters")
    shadow["supercharge"] = False
    actor = compiler(
        shadow,
        _SelectedRowCatalog(catalog, entity_id, base_level, selected),
        conversion,
        **flags,
    )
    actor["entity_adapter"].update(
        supercharge=True,
        supercharge_tier=tier,
        supercharge_parameters=deepcopy(parameters),
        supercharge_source_row=deepcopy(selected),
    )
    actor["supercharge_model"] = {
        "entity": entity_id,
        "base_level": base_level,
        "tier": tier,
        "parameters": deepcopy(parameters),
    }
    return actor


def attach_inferno_ammunition(actor, parameters):
    """Source count is absent; caller chooses explicit fuel accounting semantics."""
    if actor.get("entity_adapter", {}).get("entity") != "inferno-tower":
        raise InputError("Inferno ammunition requires its owning defense")
    if set(parameters) != {
        "source",
        "status",
        "initial_rounds",
        "consumption",
        "reload",
        "depleted_lock",
    }:
        raise InputError("Inferno ammunition requires every explicit fuel policy")
    identifier(parameters["source"], "Inferno fuel evidence")
    if (
        parameters["status"] != "explicit_uncalibrated_hypothesis"
        or parameters["reload"] != "none_during_battle"
        or parameters["depleted_lock"] != "clear_target_no_new_launches"
    ):
        raise InputError("Unknown Inferno fuel or replenishment behavior")
    if parameters["consumption"] not in {
        "one_round_per_synchronized_weapon_pulse",
        "one_round_per_released_beam",
    }:
        raise InputError("Inferno beam-versus-pulse consumption must be explicit")
    integer(parameters["initial_rounds"], "Inferno initial fuel", 0)
    actor["inferno_ammunition_model"] = deepcopy(parameters)
    return actor


class InfernoAmmunitionCombat:
    """Gate existing beam/ramp launches; never create a second weapon clock."""

    def __init__(self, actors):
        self.models, self.remaining = {}, {}
        for key, actor in actors.items():
            if "inferno_ammunition_model" not in actor:
                continue
            model = deepcopy(actor["inferno_ammunition_model"])
            attach_inferno_ammunition(actor, model)
            self.models[key] = model
            self.remaining[key] = model["initial_rounds"]
            actor["_inferno_fuel_depleted"] = self.remaining[key] == 0

    def reserve_launch(self, actor, eligible_beams, time, trace):
        """Call once after beam selection, before shared projectile emission.

        Return an ordered prefix. The beam-count hypothesis consumes only
        released beams; a pulse consumes one round for all selected beams.
        Rejected launches/Freeze/inactivity consume no fuel.
        """
        if actor["id"] not in self.models:
            return list(eligible_beams)
        if (
            not _active(actor, time)
            or actor["frozen_until"] > time
            or actor["next_attack"] > time
            or not eligible_beams
        ):
            return []
        key = actor["id"]
        model = self.models[key]
        beams = list(eligible_beams)
        if model["consumption"] == "one_round_per_released_beam":
            beams = beams[: self.remaining[key]]
            consumed = len(beams)
        else:
            consumed = 1 if self.remaining[key] else 0
            if not consumed:
                beams = []
        self.remaining[key] -= consumed
        actor["_inferno_fuel_depleted"] = self.remaining[key] == 0
        if actor["_inferno_fuel_depleted"]:
            actor["target"] = None
        trace.append(
            {
                "event": "inferno_fuel_reservation",
                "time_seconds": time,
                "source": key,
                "consumed": consumed,
                "remaining": self.remaining[key],
            }
        )
        return beams

    def result(self):
        return {"ammunition_remaining": deepcopy(self.remaining), "experimental": True}
