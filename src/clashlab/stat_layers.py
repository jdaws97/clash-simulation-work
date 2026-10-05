"""Explicit primary-publication branches over an immutable community snapshot."""

from copy import deepcopy
from datetime import date

from .common import InputError, identifier, integer, number, require, stable_id


DEPLOYMENT_POLICY = "model_published_values_without_claiming_client_verification"


def _date(value, label):
    identifier(value, label)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise InputError(f"{label} must be an ISO date") from error


def build_statistic_branch(catalog, claims, policy):
    branch_name = identifier(require(policy, "id"), "statistic branch name")
    if "statistic_branch" in catalog.snapshot:
        raise InputError("Build every branch directly from the immutable base snapshot")
    if require(policy, "snapshot_commit") != catalog.snapshot["snapshotCommit"]:
        raise InputError("Statistic branch must match its exact base snapshot")
    if require(policy, "deployment_policy") != DEPLOYMENT_POLICY:
        raise InputError("This source branch cannot certify a live client patch")
    if require(policy, "unmatched_snapshot_value_policy") != "reject":
        raise InputError(
            "Unknown intervening values must be reviewed before overriding"
        )
    if require(policy, "conflict_policy") != "latest_selected_publication":
        raise InputError("Publication precedence must be explicitly selected")
    as_of = _date(require(policy, "as_of"), "branch as-of date")
    by_id = {}
    for claim in claims:
        claim_id = identifier(require(claim, "id"), "primary claim id")
        if claim_id in by_id:
            raise InputError("Primary statistic claim IDs must be unique")
        by_id[claim_id] = claim
    selected = require(policy, "selected_claim_ids")
    if (
        not isinstance(selected, list)
        or not selected
        or len(selected) != len(set(selected))
    ):
        raise InputError("A source branch requires explicitly selected unique claims")
    if not set(selected) <= set(by_id):
        raise InputError("Source branch selects unknown claims")
    chosen = [by_id[claim_id] for claim_id in selected]
    simultaneous = {}
    for claim in chosen:
        if require(claim, "kind") != "primary_published_numeric_field":
            raise InputError("Unmapped behavior claims cannot become numeric overrides")
        published = _date(require(claim, "published_on"), "claim publication date")
        if published > as_of:
            raise InputError(
                "A branch cannot use claims published after its as-of date"
            )
        path = require(claim, "path")
        if (
            not isinstance(path, list)
            or not path
            or any(not isinstance(field, str) or not field for field in path)
        ):
            raise InputError("A statistic claim needs an exact mapped field path")
        number(require(claim, "previous_value"), "published prior value")
        number(require(claim, "value"), "published new value")
        identifier(require(claim, "source"), "primary publication source")
        identifier(require(claim, "field_semantics"), "mapped field semantics")
        integer(require(claim, "level"), "claim level", 1)
        key = (claim["entity"], claim["level"], tuple(path), published)
        if key in simultaneous and simultaneous[key] != claim["value"]:
            raise InputError(
                "Conflicting same-date primary values need manual resolution"
            )
        simultaneous[key] = claim["value"]
    branch = deepcopy(catalog)
    applied = []
    for claim in sorted(chosen, key=lambda item: (item["published_on"], item["id"])):
        row = branch.level(claim["entity"], claim["level"])
        parent = row
        for field in claim["path"][:-1]:
            parent = require(parent, field)
            if not isinstance(parent, dict):
                raise InputError(
                    "Primary field semantics do not match the snapshot schema"
                )
        field = claim["path"][-1]
        before = require(parent, field)
        if before not in {claim["previous_value"], claim["value"]}:
            raise InputError(
                "Snapshot value matches neither published prior nor new value; review intervening changes"
            )
        parent[field] = claim["value"]
        evidence = {
            "claim_id": claim["id"],
            "entity": claim["entity"],
            "level": claim["level"],
            "path": claim["path"],
            "branch_value_before": before,
            "published_value": claim["value"],
            "source": claim["source"],
            "published_on": claim["published_on"],
            "field_semantics": claim["field_semantics"],
            "verification": "primary_publication_not_current_client_confirmation",
        }
        entry = branch.records[claim["entity"]]
        entry.setdefault("field_provenance", []).append(evidence)
        entry["verification"] = "unverified_snapshot_with_selected_primary_fields"
        applied.append(evidence)
    branch.snapshot["statistic_branch"] = {
        "id": branch_name,
        "fingerprint": stable_id({"policy": policy, "applied": applied}),
        "policy": deepcopy(policy),
        "applied_fields": applied,
        "base_snapshot_is_unchanged": True,
        "full_current_patch_verified": False,
        "unspecified_levels_are_interpolated": False,
    }
    return branch
