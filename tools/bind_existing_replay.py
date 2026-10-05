"""Read the authorized prior microevent export; write private partial calibration.

No media access, network, extraction or gameplay. Input frames remain in place.
Outputs contain real evidence and must remain outside the publication checkout.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from clashlab.replay_calibration import (
    CASE_VERSION,
    PROTOCOL_VERSION,
    calibrate_rendered_cycle,
    canonical_digest,
    validate_case,
)


def bind(evidence_root, output, media_hashes=None):
    evidence_root, output = Path(evidence_root).resolve(), Path(output).resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError(
            "Use a fresh private directory outside the publication checkout"
        )
    paths = [
        evidence_root / "matched-observations.json",
        evidence_root / "evidence/pass2/rc-loadout-observations.json",
        evidence_root / "pass2-calibration-inputs.json",
    ]
    primary, followup, limits = [
        json.loads(p.read_text(encoding="utf-8")) for p in paths
    ]
    selected = [
        e for e in primary["events"] if e["id"] in ("RC-A-04", "RC-A-05", "RC-A-06")
    ]
    if len(selected) != 3:
        raise ValueError("Expected the three retained appearance intervals")
    selected.sort(key=lambda e: e["before"]["source_pts"])
    frames = []

    def frame(identifier, record):
        item = {
            "id": identifier,
            "path": record.get("file", record.get("path")),
            "source_id": "video-2",
            "pts": record["source_pts"],
            "sha256": record["sha256"],
        }
        frames.append(item)
        return identifier

    roster_ref = frame("roster", followup["matched_roster_frames"][0]["frame"])
    observations = []
    for occurrence, event in enumerate(selected, 1):
        refs = [
            frame(event["id"] + "-" + side, event[side]) for side in ("before", "after")
        ]
        observations.append(
            {
                "id": event["id"],
                "clock_id": "opening-1",
                "entity_id": "royal-champion-1",
                "target_id": "red-xbow-1",
                "observable": "projectile_appearance",
                "occurrence": occurrence,
                "pts_interval": [
                    event["before"]["source_pts"],
                    event["after"]["source_pts"],
                ],
                "left_open": True,
                "annotation_error_seconds": [0, 0],
                "evidence_ids": refs,
                "logical_event_time": None,
                "previously_inspected": True,
                "limitation": "Medium-confidence appearance/line attribution; no quantified annotation error beyond frame bounds. Conditional on same target and no missed appearances; no damage, release or causal label.",
            }
        )
    source_meta = next(
        s for s in primary["source_access"]["sources"] if s["id"] == "video-2"
    )
    case = {
        "schema_version": CASE_VERSION,
        "id": "rc-opening-rendered-cycle",
        "evidence_class": "real",
        "selection_method": "Convenience footage; narrow clearly annotated appearance sequence. No population weighting or base-generation objective derives from this example.",
        "sources": [
            {
                "id": "video-2",
                "filename": source_meta["filename"],
                "timebase": [1, 600],
                "size_bytes": source_meta["size_bytes"],
                "media_sha256": (media_hashes or {}).get("video-2"),
                "extraction_continuity": "Retained frame bytes verified; old extraction did not record source hash. A later media hash cannot retrospectively prove that link.",
            }
        ],
        "evidence": frames,
        "clock_segments": [
            {
                "id": "opening-1",
                "source_id": "video-2",
                "encounter_id": "attack-1",
                "pts_bounds": [8939, 9299],
                "origin_pts": 8939,
                "origin_game_seconds": [0, 0],
                "clock_kind": "local_relative",
                "speed": [4, 4],
                "evidence_ids": [roster_ref],
                "assumption": "Constant displayed 4x locally; not independently measured replay-clock jitter, battle-start time or an engine tick.",
            }
        ],
        "bindings": {
            "patch": {
                "status": "unknown",
                "value": None,
                "reason": "No per-replay build identifier; later UI panels also omit it.",
            },
            "mode": {
                "status": "unknown",
                "value": None,
                "reason": "Ranked user context is not an exact per-replay mode/ruleset binding.",
            },
            "modifiers": {
                "status": "unknown",
                "value": None,
                "reason": "Displayed levels do not determine every active modifier or boost.",
            },
            "loadout": {
                "status": "partial",
                "value": limits["replay_pet_assignments"],
                "evidence_ids": [roster_ref],
                "reason": "Displayed hero/pet levels and visually identified pairings only. Per-replay equipment levels, initial HP, ability charge and relevant other damage contributors remain unbound.",
            },
            "geometry": {
                "status": "partial",
                "value": primary["coordinate_references"][0]["coordinates_approx_px"],
                "evidence_ids": [
                    frame(
                        "geometry-reference",
                        primary["coordinate_references"][0]["reference"],
                    )
                ],
                "reason": "Approximate crop pixels only, not tile positions/ranges or target level/HP; no complete influencing-entity geometry.",
            },
        },
        "identifiability": {
            "duke_isolation_candidates_seconds": [0.05, 0.1, 0.2],
            "eliminated_candidates": [],
            "measured_duke_period": None,
            "scope": "Companion footage only; not identified by this RC case.",
        },
    }
    # The roster frame is a loadout source. The existing full-frame speed review
    # is separately retained; do not claim the cropped projectile images show UI.
    case["clock_segments"][0][
        "assumption"
    ] += " Displayed-speed review is recorded in VIDEO-FINDINGS.md; roster frame retains full UI."
    case["observations"] = observations
    integrity = validate_case(case, evidence_root)
    protocol = {
        "schema_version": PROTOCOL_VERSION,
        "id": "rendered-cycle-retrospective-v1",
        "case_sha256": canonical_digest(case),
        "target_layer": "rendered",
        "fit_ids": ["RC-A-04", "RC-A-05"],
        "validation_ids": ["RC-A-06"],
        "validation_design": "retrospective_same_encounter",
        "tolerance_seconds": 0,
        "max_prediction_width_seconds": 0.25,
        "tolerance_rationale": "Use observed PTS brackets only, plus the conservative two-appearance forecast envelope. Zero extra tolerance is conditional and does not assert zero annotation error.",
        "missing_prediction_policy": "incomplete",
        "falsification_rule": "Any disjoint predicted/observed visual interval rejects this conditional rendered-cycle model; a missing event is incomplete. Passing neither validates weapon cadence nor causal damage.",
    }
    output.mkdir(parents=True)

    def write(name, data):
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")

    write("case.json", case)
    write("protocol.json", protocol)
    write(
        "freeze-receipt.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "case_sha256": canonical_digest(case),
            "protocol_sha256": canonical_digest(protocol),
            "prior_observation_review": True,
            "preregistered_before_original_evidence_review": False,
            "input_file_hashes": {
                p.name: sha256(p.read_bytes()).hexdigest() for p in paths
            },
            "integrity": integrity,
        },
    )
    result = calibrate_rendered_cycle(case, protocol, evidence_root)
    write("trace.json", result["trace"])
    write("comparison.json", result["report"])
    write(
        "held-out-protocol.json",
        {
            "status": "NOT_EXECUTED_NO_PRISTINE_HELD_OUT_MECHANICAL_CASE",
            "previously_inspected_encounters": [
                "attack-1",
                "attack-2",
                "attack-3",
                "defense-1",
                "defense-2",
            ],
            "split_unit": "complete encounter, including all overlapping frames/crops and transitions",
            "required_before_prediction": [
                "Freeze exact loadout, initial state, geometry, build/mode/modifiers and source clock evidence.",
                "Freeze eligible event types, actor/target identity, occurrence ledger, uncertainty and rendering projection independently of predicted errors.",
                "Freeze candidate engine/model hash, seed, phase, tolerances and protocol/case hashes; no fitting on validation transitions.",
                "Obtain a genuinely uninspected independent encounter; no game actions or new collection authorized by this protocol.",
            ],
            "selection": "Neutral coverage across varied layout archetypes, army styles, entry directions and user-relevant TH distributions. War/CWL separated from ranked; difficult-base illustration carries no extra weight.",
            "decision": "All required events accounted for; disjoint intervals falsify the specified model, missing predictions are incomplete. Report per-encounter results, coverage and exclusions; no win-rate inference from convenience clips.",
            "duke_gate": "Do not eliminate .05/.10/.20 without identified isolation state, complete qualifying-neighbor geometry and independently bounded phase/rendering delay.",
        },
    )
    return result["report"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--media-hashes", type=Path, help="Optional JSON mapping source IDs to SHA-256"
    )
    args = parser.parse_args()
    hashes = json.loads(args.media_hashes.read_text()) if args.media_hashes else None
    report = bind(args.evidence_root, args.output, hashes)
    print(
        json.dumps(
            {
                "status": report["status"],
                "verdict": report["verdict"],
                "integrity": report["integrity"],
            }
        )
    )


if __name__ == "__main__":
    main()
