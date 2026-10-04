"""Shared validation helpers for explicit hero behavior extensions."""

import re

from .common import InputError, identifier, require


def source_quantity(value, unit, *, allow_leading_plus=False):
    if not isinstance(value, str):
        raise InputError(f"Hero quantity must explicitly use {unit}")
    prefix = r"\+?" if allow_leading_plus else ""
    match = re.fullmatch(prefix + r"([0-9]+(?:\.[0-9]+)?)\s*" + re.escape(unit), value)
    if match is None:
        raise InputError("Unsupported hero snapshot quantity")
    return float(match.group(1))


def require_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise InputError(f"{label} requires its complete explicit contract")


def require_values(values, allowed, label):
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) for value in values)
        or len(values) != len(set(values))
        or not set(values) <= allowed
    ):
        raise InputError(f"{label} requires unique supported values")


def validate_locked_projectile(projectile):
    from .combat import validate_pattern

    validate_pattern(
        {
            "kind": "single",
            "source": "explicit-hero-projectile-validation",
            "target_kinds": ["defense", "building", "unit"],
            "target_layers": ["ground", "air"],
            "maximum_hp_fraction": 0,
            "projectile": projectile,
        }
    )
    if projectile["destination"] != "locked_actor_center_at_impact":
        raise InputError("This hero weapon requires a locked-actor projectile")


def parameter_provenance(parameters):
    if not isinstance(parameters, dict):
        raise InputError("Hero behavior parameters require an explicit mapping")
    source = identifier(require(parameters, "source"), "hero parameter source")
    return {
        key: {
            "source": source,
            "status": "explicit_uncalibrated_hypothesis",
        }
        for key in parameters
        if key != "source"
    }


def validate_parameter_provenance(model):
    identifier(model["source_description"], "hero source description")
    if model["parameter_provenance"] != parameter_provenance(model["parameters"]):
        raise InputError(
            "Hero parameter provenance must identify each declared hypothesis"
        )
