"""Coverage-first full-battle bridge and unweighted conditional case summaries."""

from collections import defaultdict
from hashlib import sha256
import json

from .common import InputError, integer, number
from .deployment_mask import inspect_deployments
from .full_battle import compile_full_battle, simulate_full_battle
from .layout_battle_bridge import assert_crafted_compiled
from .layout_inventory import inspect_inventory
from .scoring import validate_outcome


def content_sha(value):
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def candidate_layout_sha256(layout):
    """Canonical declared layout content, independent of human labels/provenance.

    Coordinates are in the actual simulation board (padding included). Complete
    building records, selected inventory and directional/destruction settings
    are identity-bearing. Sorting buildings makes list order non-identifying.
    """
    content = {
        key: value
        for key, value in layout.items()
        if key
        not in {
            "id",
            "candidate_id",
            "generation_origin",
            "generation_receipt",
            "station_change_cost",
            "recommendation_status",
            "objective",
        }
    }
    content["buildings"] = sorted(layout["buildings"], key=lambda b: b["instance"])
    return content_sha(content)


def _candidate_digest(case):
    digest = case.get("candidate_layout_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise InputError("Case requires a registered canonical candidate_layout_sha256")
    return digest


def validate_case(bundle, catalog):
    case, layout, account = bundle["case"], bundle["layout"], bundle["account"]
    if case["mode"] not in {"ranked", "war", "cwl"}:
        raise InputError("Keep ranked, war and CWL cases explicit and separate")
    if case["split"] not in {"search", "held_out"}:
        raise InputError("Declare search or held_out case split")
    for key in ("id", "candidate_id", "family", "entry_policy", "ability_policy"):
        if not isinstance(case.get(key), str) or not case[key]:
            raise InputError(f"Missing case dimension: {key}")
    if case["candidate_id"] != layout.get("candidate_id"):
        raise InputError("Case candidate label differs from the declared layout")
    if _candidate_digest(case) != candidate_layout_sha256(layout):
        raise InputError("Layout differs from registered canonical candidate content")
    if case["id"] != bundle["specification"].get("id"):
        raise InputError("Case and battle specification identities differ")
    for th in (case["attacker_town_hall"], case["defender_town_hall"]):
        integer(th, "case Town Hall", 16, 18)
    if (
        case["attacker_town_hall"] != account["town_hall"]
        or case["defender_town_hall"] != layout["town_hall"]
        or case["mode"] != account.get("effective_mode")
    ):
        raise InputError("Case/account/layout Town Hall or mode mismatch")
    expected_modifier = "legend_i" if case["mode"] == "ranked" else "none"
    if (
        bundle["specification"]["battle_modifier_policy"]["profile_id"]
        != expected_modifier
    ):
        raise InputError("Legend I and war/CWL modifier profiles cannot be pooled")
    inspect_inventory(layout, catalog, layout["inventory_selection"])
    if layout["inventory_selection"]["crafted"] is None:
        raise InputError(
            "Active selected crafted defense is a mandatory evaluation gate"
        )
    inspect_deployments(
        layout,
        catalog,
        bundle["specification"]["entity_scene"],
        bundle["deployment_policy"],
    )
    return content_sha(bundle)


def compile_case(bundle, catalog, mode_rules):
    digest = validate_case(bundle, catalog)
    args = [bundle[k] for k in ("specification", "account", "army", "layout")]
    compiled = compile_full_battle(*args, catalog, mode_rules)
    crafted = assert_crafted_compiled(compiled, bundle["layout"])
    return {
        "input_sha256": digest,
        "candidate_layout_sha256": bundle["case"]["candidate_layout_sha256"],
        "crafted": crafted,
        "status": "compiled_no_outcome",
    }


def simulate_case(bundle, catalog, mode_rules):
    digest = validate_case(bundle, catalog)
    result = simulate_full_battle(
        *[bundle[k] for k in ("specification", "account", "army", "layout")],
        catalog,
        mode_rules,
    )
    crafted = assert_crafted_compiled(result, bundle["layout"])
    outcome = validate_outcome(result["outcome"])
    decision = result["combat"].get("termination", {}).get("decision")
    if not decision or decision["end_reason"] != outcome["end_reason"]:
        raise InputError("No matching terminal battle receipt; no score")
    if (
        abs(
            number(decision["time_seconds"], "terminal time", 0)
            - outcome["elapsed_seconds"]
        )
        > 1e-8
    ):
        raise InputError("Termination/outcome clocks disagree")
    return {
        "case": bundle["case"],
        "input_sha256": digest,
        "candidate_layout_sha256": bundle["case"]["candidate_layout_sha256"],
        "status": "completed",
        "completion_proven": True,
        "outcome": outcome,
        "crafted": crafted,
        "crafted_runtime": result["combat"].get("crafted_defenses"),
        "resource_use": result["resource_use"],
        "calibrated": False,
    }, result


def summarize_cases(cases, receipts):
    """No imputation, mixture weights, trophy formulas or cross-class ranking.

    Worst observed attacker result is lexicographic stars/destruction. Missing
    cells invalidate the full-grid worst case and mean, not count as defense wins.
    """
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise InputError("Duplicate planned case IDs")
    indexed = {r["case"]["id"]: r for r in receipts}
    if len(indexed) != len(receipts) or set(indexed) - set(ids):
        raise InputError("Duplicate or unplanned receipts")
    groups = defaultdict(list)
    registered = {}
    for case in cases:
        candidate_digest = _candidate_digest(case)
        prior = registered.setdefault(case["candidate_id"], candidate_digest)
        if prior != candidate_digest:
            raise InputError(
                "Candidate label maps to different canonical layout contents"
            )
        key = tuple(
            case[k]
            for k in (
                "candidate_id",
                "candidate_layout_sha256",
                "mode",
                "attacker_town_hall",
                "defender_town_hall",
                "split",
            )
        )
        receipt = indexed.get(case["id"], {"status": "not_run"})
        if "case" in receipt and receipt["case"] != case:
            raise InputError("Receipt case differs from the frozen plan")
        if receipt["status"] != "completed":
            if receipt.get("outcome") is not None or receipt.get("completion_proven"):
                raise InputError("Failed/unsupported/unrun cases cannot carry outcomes")
        elif not receipt.get("completion_proven"):
            raise InputError("Completed receipt lacks terminal evidence")
        else:
            validate_outcome(receipt["outcome"])
        groups[key].append((case, receipt))
    result = []
    for key, rows in sorted(groups.items()):
        successes = [(c, r) for c, r in rows if r["status"] == "completed"]
        gaps = [
            {"case_id": c["id"], "status": r["status"], "reason": r.get("reason")}
            for c, r in rows
            if r["status"] != "completed"
        ]
        worst = max(
            successes,
            key=lambda cr: (cr[1]["outcome"]["stars"], cr[1]["outcome"]["destruction"]),
            default=None,
        )
        result.append(
            {
                **dict(
                    zip(
                        (
                            "candidate_id",
                            "candidate_layout_sha256",
                            "mode",
                            "attacker_town_hall",
                            "defender_town_hall",
                            "split",
                        ),
                        key,
                    )
                ),
                "planned": len(rows),
                "completed": len(successes),
                "gaps": gaps,
                "full_grid_complete": not gaps,
                "worst_observed_case": (
                    None
                    if worst is None
                    else {"case": worst[0], "outcome": worst[1]["outcome"]}
                ),
                "full_grid_worst_case": (
                    None if gaps or worst is None else worst[0]["id"]
                ),
                "unweighted_grid_mean": (
                    None
                    if gaps
                    else {
                        k: sum(r["outcome"][k] for c, r in successes) / len(successes)
                        for k in ("stars", "destruction")
                    }
                ),
                "mean_is_population_estimate": False,
            }
        )
    return {
        "groups": result,
        "mixture_weights": None,
        "ranking": None,
        "best_layout": None,
        "replay_calibrated": False,
        "assumption": "All statistics condition on the explicitly listed synthetic cases.",
    }
