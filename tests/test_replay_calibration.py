"""Five bounded acceptance scenarios for observation trust and falsification."""

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from math import inf, nextafter
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clashlab.replay_calibration import (
    BINDINGS,
    CASE_VERSION,
    PROTOCOL_VERSION,
    TRACE_VERSION,
    canonical_digest,
    calibrate_rendered_cycle,
    compare_replay,
    map_observation,
    validate_case,
    validate_protocol,
)
from clashlab.replay_observations import ObservationError


def fixture():
    frames, events = [], []
    for n, (low, high) in enumerate(((100, 110), (280, 290), (460, 470)), 1):
        refs = []
        for side, pts in (("before", low), ("after", high)):
            identifier = f"{n}-{side}"
            frames.append(
                {
                    "id": identifier,
                    "path": identifier + ".jpg",
                    "source_id": "synthetic-video",
                    "pts": pts,
                    "sha256": sha256(identifier.encode()).hexdigest(),
                }
            )
            refs.append(identifier)
        events.append(
            {
                "id": f"event-{n}",
                "clock_id": "clock",
                "entity_id": "synthetic-unit",
                "target_id": "synthetic-target",
                "observable": "projectile_appearance",
                "occurrence": n,
                "pts_interval": [low, high],
                "left_open": True,
                "annotation_error_seconds": [0, 0],
                "evidence_ids": refs,
                "logical_event_time": None,
                "previously_inspected": True,
                "limitation": "Declared synthetic times; not game measurements.",
            }
        )
    case = {
        "schema_version": CASE_VERSION,
        "id": "synthetic-acceptance",
        "evidence_class": "synthetic",
        "selection_method": "Synthetic acceptance fixture; no real-game calibration",
        "sources": [
            {
                "id": "synthetic-video",
                "timebase": [1, 600],
                "media_sha256": sha256(b"synthetic-video-content").hexdigest(),
                "extraction_continuity": "Synthetic bytes",
            }
        ],
        "evidence": frames,
        "clock_segments": [
            {
                "id": "clock",
                "source_id": "synthetic-video",
                "encounter_id": "synthetic-1",
                "pts_bounds": [0, 1000],
                "origin_pts": 100,
                "origin_game_seconds": [0, 0],
                "speed": [4, 4],
                "clock_kind": "local_relative",
                "evidence_ids": ["1-before"],
                "assumption": "Synthetic exact clock",
            }
        ],
        "bindings": {
            name: {
                "status": "unknown",
                "value": None,
                "reason": "Unbound synthetic context",
            }
            for name in BINDINGS
        },
        "observations": events,
    }
    protocol = {
        "schema_version": PROTOCOL_VERSION,
        "id": "synthetic-protocol",
        "case_sha256": canonical_digest(case),
        "fit_ids": ["event-1", "event-2"],
        "validation_ids": ["event-3"],
        "validation_design": "retrospective_same_encounter",
        "target_layer": "rendered",
        "tolerance_seconds": 0,
        "max_prediction_width_seconds": 0.25,
        "tolerance_rationale": "Synthetic PTS bounds suffice",
        "missing_prediction_policy": "incomplete",
        "falsification_rule": "Disjoint intervals reject this synthetic model",
    }
    return case, protocol


def rebind(case, protocol, trace=None):
    protocol["case_sha256"] = canonical_digest(case)
    if trace is not None:
        trace["case_sha256"] = canonical_digest(case)
        trace["protocol_sha256"] = canonical_digest(protocol)


class ReplayCalibrationAcceptance(unittest.TestCase):
    def test_rendered_forecast_is_deterministic_and_validation_does_not_fit_model(self):
        case, protocol = fixture()
        original = calibrate_rendered_cycle(case, protocol)
        self.assertEqual(original, calibrate_rendered_cycle(case, protocol))
        self.assertEqual(original["report"]["verdict"], "compatible")
        self.assertEqual(original["report"]["measured_engine_parameters"], {})
        for target in (None, "wrong-target", "missing-field"):
            mismatch = deepcopy(original["trace"])
            mismatch["events"][0]["target_id"] = target
            if target == "missing-field":
                del mismatch["events"][0]["target_id"]
            with (
                self.subTest(target=target),
                self.assertRaisesRegex(ObservationError, "target_id"),
            ):
                compare_replay(case, protocol, mismatch)
        unspecified, unknown_protocol, unknown_trace = (
            deepcopy(case),
            deepcopy(protocol),
            deepcopy(original["trace"]),
        )
        unspecified["observations"][0].update(
            target_id=None, target_status="not_applicable", observable="ring_appearance"
        )
        unknown_trace["events"][0].update(target_id=None, observable="ring_appearance")
        rebind(unspecified, unknown_protocol, unknown_trace)
        self.assertEqual(
            compare_replay(unspecified, unknown_protocol, unknown_trace)["verdict"],
            "compatible",
        )
        wide = deepcopy(original["trace"])
        wide["events"][2]["seconds"] = [0, 1000]
        with self.assertRaisesRegex(ObservationError, "frozen cap"):
            compare_replay(case, protocol, wide)
        # Move only the third observation. The model and forecast must stay fixed.
        changed = deepcopy(case)
        changed["observations"][2]["pts_interval"] = [800, 810]
        changed["evidence"][-2]["pts"], changed["evidence"][-1]["pts"] = 800, 810
        rebind(changed, protocol)
        outlier = calibrate_rendered_cycle(changed, protocol)
        self.assertEqual(
            outlier["trace"]["model_sha256"], original["trace"]["model_sha256"]
        )
        self.assertEqual(
            outlier["trace"]["events"][-1], original["trace"]["events"][-1]
        )
        self.assertEqual(outlier["report"]["verdict"], "falsified")
        trace = deepcopy(outlier["trace"])
        trace["events"].pop()
        self.assertEqual(
            compare_replay(changed, protocol, trace)["verdict"], "incomplete"
        )
        trace["events"][0]["entity_id"] = "wrong-actor"
        with self.assertRaisesRegex(ObservationError, "identity"):
            compare_replay(changed, protocol, trace)

    def test_clock_uncertainty_closure_and_frame_integrity_are_not_scalar_guesses(self):
        case, protocol = fixture()
        with TemporaryDirectory() as directory:
            for frame in case["evidence"]:
                (Path(directory) / frame["path"]).write_bytes(frame["id"].encode())
            self.assertEqual(validate_case(case, directory)["verified_frame_count"], 6)
            (Path(directory) / case["evidence"][0]["path"]).write_bytes(b"altered")
            with self.assertRaisesRegex(ObservationError, "Modified"):
                validate_case(case, directory)
        trace = calibrate_rendered_cycle(case, protocol)["trace"]
        trace["events"][0]["seconds"] = [0, 0]
        self.assertEqual(
            compare_replay(case, protocol, trace)["events"][0]["status"], "falsified"
        )
        # Both endpoints are nonterminating rationals. Only the published float
        # maps back to each boundary; adjacent floats and exact outside rationals
        # remain distinct, with no added timing tolerance.
        boundary_case, boundary_protocol = deepcopy(case), deepcopy(protocol)
        boundary_case["clock_segments"][0]["origin_pts"] = 99
        rebind(boundary_case, boundary_protocol)
        boundary_trace = calibrate_rendered_cycle(boundary_case, boundary_protocol)[
            "trace"
        ]
        mapped = map_observation(boundary_case, "event-1")
        lower, upper = mapped["seconds"]
        exact_lower, exact_upper = mapped["exact_seconds"]
        for point, expected in (
            (upper, "compatible"),
            (exact_upper, "compatible"),
            (nextafter(upper, inf), "falsified"),
            (lower, "falsified"),
            (exact_lower, "falsified"),
            (nextafter(lower, inf), "compatible"),
            (str(Fraction(exact_upper) + Fraction(1, 10**40)), "falsified"),
        ):
            boundary_trace["events"][0]["seconds"] = [point, point]
            with self.subTest(point=point):
                row = compare_replay(boundary_case, boundary_protocol, boundary_trace)[
                    "events"
                ][0]
                self.assertEqual(row["status"], expected)
        # Interval product must handle negative offsets relative to a local origin.
        case["clock_segments"][0].update(
            origin_pts=200, speed=[2, 4], origin_game_seconds=[1, 2]
        )
        mapped = map_observation(case, "event-1")
        self.assertEqual(mapped["exact_seconds"], ["1/3", "17/10"])
        self.assertFalse(mapped["left_open"])
        case["clock_segments"][0]["pts_bounds"] = [0, 465]
        with self.assertRaisesRegex(ObservationError, "crosses"):
            validate_case(case)

    def test_engine_context_projection_and_explicit_experiment_gates(self):
        case, protocol = fixture()
        trace = calibrate_rendered_cycle(case, protocol)["trace"]
        trace["layer"] = protocol["target_layer"] = "engine"
        for name in ("model_sha256", "input_sha256"):
            protocol[name] = trace[name]
        projection = {
            "basis": "experimental",
            "seconds": [0, 0],
            "evidence": "Synthetic unmeasured projection",
            "engine_event_kind": "projectile_release",
        }
        protocol["rendering_delays"] = {"projectile_appearance": projection}
        for event in trace["events"]:
            event["engine_event_kind"] = "projectile_release"
        rebind(case, protocol, trace)
        stale = deepcopy(trace)
        stale["model_sha256"] = "0" * 64
        with self.assertRaisesRegex(ObservationError, "Frozen engine"):
            compare_replay(case, protocol, stale)
        blocked = compare_replay(case, protocol, trace)
        self.assertEqual(blocked["verdict"], "blocked")
        self.assertIn("binding:geometry", blocked["blockers"])
        for name in BINDINGS:
            snapshot = {"synthetic_complete_context": name}
            case["bindings"][name] = {
                "status": "exact",
                "reason": "Synthetic complete scoped binding",
                "evidence_ids": ["1-before"],
                "value": {
                    "scope_id": "synthetic-acceptance",
                    "complete_for_scope": True,
                    "snapshot": snapshot,
                    "snapshot_sha256": canonical_digest(snapshot),
                },
            }
        trace["bindings"] = {name: case["bindings"][name]["value"] for name in BINDINGS}
        rebind(case, protocol, trace)
        self.assertEqual(
            compare_replay(case, protocol, trace)["blockers"],
            ["experimental_projection_requires_opt_in"],
        )
        self.assertEqual(
            compare_replay(case, protocol, trace, allow_experimental=True)["verdict"],
            "compatible",
        )
        trace["bindings"] = deepcopy(trace["bindings"])
        trace["bindings"]["geometry"]["scope_id"] = "other"
        self.assertIn(
            "context_mismatch:geometry",
            compare_replay(case, protocol, trace, allow_experimental=True)["blockers"],
        )

    def test_freeze_and_held_out_partition_reject_leakage_and_stale_evidence(self):
        case, protocol = fixture()
        changed = deepcopy(case)
        changed["observations"][2]["evidence_ids"].append("1-before")
        rebind(changed, protocol)
        with self.assertRaisesRegex(ObservationError, "frame leakage"):
            validate_protocol(changed, protocol)
        alias = deepcopy(case)
        source = deepcopy(alias["sources"][0])
        source["id"] = "different-display-name"
        alias["sources"].append(source)
        clock = deepcopy(alias["clock_segments"][0])
        clock.update(
            id="alias-clock",
            source_id=source["id"],
            encounter_id="different-encounter-label",
        )
        alias["clock_segments"].append(clock)
        alias["observations"][2].update(
            clock_id="alias-clock", pts_interval=[100, 110], previously_inspected=False
        )
        for frame, pts in zip(alias["evidence"][-2:], (100, 110)):
            frame.update(source_id=source["id"], pts=pts)
        rebind(alias, protocol)
        # Different crop bytes and labels still share physical media/time.
        with self.assertRaisesRegex(ObservationError, "Clock segments overlap"):
            validate_protocol(alias, protocol)
        # Even dishonest distinct media hashes cannot reuse identical frame bytes.
        alias["sources"][1]["media_sha256"] = sha256(b"another-source").hexdigest()
        for frame, original in zip(alias["evidence"][-2:], alias["evidence"][:2]):
            frame["sha256"] = original["sha256"]
        rebind(alias, protocol)
        with self.assertRaisesRegex(ObservationError, "frame hash leakage"):
            validate_protocol(alias, protocol)
        rebind(case, protocol)
        protocol["validation_design"] = "held_out_encounter"
        with self.assertRaisesRegex(ObservationError, "encounter leakage"):
            validate_protocol(case, protocol)
        second_clock = deepcopy(case["clock_segments"][0])
        case["clock_segments"][0]["pts_bounds"] = [0, 400]
        second_clock.update(
            id="clock-2",
            encounter_id="synthetic-2",
            pts_bounds=[401, 1000],
            origin_pts=401,
        )
        case["clock_segments"].append(second_clock)
        case["observations"][2]["clock_id"] = "clock-2"
        rebind(case, protocol)
        with self.assertRaisesRegex(ObservationError, "Previously inspected"):
            validate_protocol(case, protocol)
        case["observations"][2]["previously_inspected"] = False
        rebind(case, protocol)
        validate_case(case)
        validate_protocol(case, protocol)
        unidentified = deepcopy(case)
        unidentified["sources"][0]["media_sha256"] = None
        rebind(unidentified, protocol)
        with self.assertRaisesRegex(ObservationError, "content-bound source"):
            validate_protocol(unidentified, protocol)
        rebind(case, protocol)
        case["selection_method"] = "Changed after freeze"
        with self.assertRaisesRegex(ObservationError, "digest mismatch"):
            validate_protocol(case, protocol)

    def test_real_evidence_without_hash_verification_never_passes_as_calibration(self):
        case, protocol = fixture()
        case["evidence_class"] = "real"
        rebind(case, protocol)
        report = calibrate_rendered_cycle(case, protocol)["report"]
        self.assertEqual(report["verdict"], "blocked")
        self.assertEqual(report["complete_calibrated_battles"], 0)
        self.assertIn("unverified_frame_bytes", report["blockers"])
        case["observations"][0]["logical_event_time"] = 1.2
        with self.assertRaisesRegex(ObservationError, "logical timing"):
            validate_case(case)


if __name__ == "__main__":
    unittest.main()
