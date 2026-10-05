"""Versioned, provenance-bound partial encounter comparison; no kernel mutation.

Visible appearance, logical events and damage are different observables. This
module never promotes a visual fit to a measured engine parameter. All bounds
are analyst envelopes, not confidence intervals. JSON numbers are parsed into
decimal rationals for clock/interval work so PTS quantization is preserved.
"""

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import re

from .replay_observations import ObservationError


CASE_VERSION = "partial-encounter-v1"
PROTOCOL_VERSION = "replay-protocol-v1"
TRACE_VERSION = "replay-predictions-v1"
BINDINGS = ("patch", "mode", "modifiers", "loadout", "geometry")
OBSERVABLES = {
    "projectile_appearance",
    "ring_appearance",
    "model_disappearance",
    "ui_counter_change",
    "actor_appearance",
}


def canonical_digest(value):
    """Content identity, including protocol choices and explicit unknowns."""
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _need(condition, message):
    if not condition:
        raise ObservationError(message)


def _number(value):
    _need(type(value) in (int, float), "Expected a finite JSON number")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ObservationError("Expected a finite JSON number") from error


def _bounds(values, nonnegative=False):
    _need(isinstance(values, list) and len(values) == 2, "Expected two bounds")
    low, high = map(_number, values)
    _need(low <= high, "Reversed interval")
    _need(not nonnegative or low >= 0, "Negative interval")
    return low, high


def _integer(value):
    _need(type(value) is int and value >= 0, "PTS must be a nonnegative integer")
    return value


def _text(value):
    _need(isinstance(value, str) and bool(value.strip()), "Expected nonempty text")
    return value


def _digest(value):
    _need(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
        "Expected lowercase SHA-256",
    )


def _index(items):
    _need(isinstance(items, list) and bool(items), "Expected nonempty record list")
    result = {}
    for item in items:
        identifier = _text(item.get("id"))
        _need(identifier not in result, "Duplicate record identifier")
        result[identifier] = item
    return result


def _refs(ids, evidence):
    _need(isinstance(ids, list) and bool(ids), "Evidence references required")
    _need(len(set(ids)) == len(ids), "Duplicate evidence reference")
    _need(all(item in evidence for item in ids), "Unknown evidence reference")


def _timebase(source):
    ratio = source.get("timebase")
    _need(isinstance(ratio, list) and len(ratio) == 2, "Timebase needs [num, den]")
    _need(all(type(n) is int and n > 0 for n in ratio), "Invalid timebase")
    return Fraction(*ratio)


def _source_identity(source):
    """Display names never establish that two recordings are independent."""
    if source.get("media_sha256") is not None:
        return "sha256", source["media_sha256"]
    return "unbound", source["id"]


def _prediction_time(value, boundaries):
    """Prefer exact rational strings; round-trip a published float boundary.

    Only the identical binary64 representation of an endpoint is canonicalized,
    never an epsilon neighborhood. Adjacent floats stay distinct. If more than
    one exact boundary shares that float, require an unambiguous rational input.
    """
    if isinstance(value, str):
        try:
            rational = Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ObservationError("Invalid rational prediction time") from error
        _need(str(rational) == value, "Prediction rational must be canonical")
        return rational
    rational = _number(value)
    if type(value) is float:
        matches = {bound for bound in boundaries if value == float(bound)}
        _need(len(matches) <= 1, "Ambiguous float endpoint; use rational seconds")
        if matches:
            return matches.pop()
    return rational


def validate_case(case, frame_root=None):
    """Validate structure and optionally hash every retained evidence frame.

    A source-media hash identifies the file observed today. It does not retroactively
    prove old extractions came from those bytes; extraction continuity is separate.
    """
    _need(case.get("schema_version") == CASE_VERSION, "Unsupported encounter schema")
    _text(case.get("id"))
    _need(
        case.get("evidence_class") in {"real", "synthetic"}, "Evidence class required"
    )
    _text(case.get("selection_method"))
    sources = _index(case.get("sources"))
    evidence = _index(case.get("evidence"))
    segments = _index(case.get("clock_segments"))
    observations = _index(case.get("observations"))
    for source in sources.values():
        _timebase(source)
        if source.get("media_sha256") is not None:
            _digest(source["media_sha256"])
        _text(source.get("extraction_continuity"))
    source_clocks = {}
    for source in sources.values():
        identity, timebase = _source_identity(source), _timebase(source)
        _need(
            identity not in source_clocks or source_clocks[identity] == timebase,
            "Aliases of the same media must share its timebase",
        )
        source_clocks[identity] = timebase
    root = Path(frame_root).resolve() if frame_root is not None else None
    for item in evidence.values():
        _need(item.get("source_id") in sources, "Unknown frame source")
        _integer(item.get("pts"))
        _digest(item.get("sha256"))
        path = Path(_text(item.get("path")))
        win = PureWindowsPath(str(path))
        _need(
            not path.is_absolute()
            and not win.drive
            and not win.root
            and ".." not in win.parts,
            "Evidence path must stay inside frame root",
        )
        if root is not None:
            target = (root / path).resolve()
            _need(target.is_relative_to(root), "Evidence path escapes frame root")
            _need(target.is_file(), f"Missing evidence frame: {path}")
            _need(
                sha256(target.read_bytes()).hexdigest() == item["sha256"],
                f"Modified evidence frame: {path}",
            )
    for segment in segments.values():
        _need(segment.get("source_id") in sources, "Unknown clock source")
        start, end = map(_integer, segment["pts_bounds"])
        _need(start < end, "Clock segment needs positive duration")
        origin = _integer(segment.get("origin_pts"))
        _need(start <= origin <= end, "Clock origin outside segment")
        _bounds(segment.get("origin_game_seconds"), nonnegative=True)
        speed = _bounds(segment.get("speed"), nonnegative=True)
        _need(speed[0] > 0, "Paused clock cannot establish an event time")
        _need(
            segment.get("clock_kind") == "local_relative", "Only local clocks supported"
        )
        _text(segment.get("encounter_id"))
        _text(segment.get("assumption"))
        _refs(segment.get("evidence_ids"), evidence)
    source_key = lambda s: _source_identity(sources[s["source_id"]])
    ordered = sorted(segments.values(), key=lambda s: (source_key(s), s["pts_bounds"]))
    for left, right in zip(ordered, ordered[1:]):
        _need(
            source_key(left) != source_key(right)
            or left["pts_bounds"][1] < right["pts_bounds"][0],
            "Clock segments overlap or share an ambiguous boundary",
        )
    bindings = case.get("bindings", {})
    _need(set(bindings) == set(BINDINGS), "All five binding categories required")
    for binding in bindings.values():
        _need(
            binding.get("status") in {"exact", "partial", "unknown"}, "Binding status"
        )
        _text(binding.get("reason"))
        if binding["status"] == "unknown":
            _need(binding.get("value") is None, "Unknown binding must have null value")
        else:
            _need(binding.get("value") is not None, "Known binding requires value")
            _refs(binding.get("evidence_ids"), evidence)
            if binding["status"] == "exact":
                value = binding["value"]
                _need(isinstance(value, dict), "Exact binding needs a snapshot")
                _text(value.get("scope_id"))
                _need(
                    value["scope_id"] == case["id"],
                    "Binding scope differs from encounter case",
                )
                _need(
                    value.get("complete_for_scope") is True,
                    "Exact binding must cover its scope",
                )
                _need(
                    bool(value.get("snapshot")),
                    "Exact binding snapshot cannot be empty",
                )
                _need(
                    value.get("snapshot_sha256") == canonical_digest(value["snapshot"]),
                    "Binding snapshot digest mismatch",
                )
    keys = set()
    for observation in observations.values():
        _need(observation.get("clock_id") in segments, "Unknown observation clock")
        _need(
            observation.get("observable") in OBSERVABLES,
            "Unsupported visual observable",
        )
        _text(observation.get("entity_id"))
        _need("target_id" in observation, "Observation target must be explicit")
        if observation["target_id"] is None:
            _need(
                observation.get("target_status") in {"unknown", "not_applicable"},
                "Null target requires unknown or not_applicable status",
            )
        else:
            _text(observation["target_id"])
        _need(
            type(observation.get("occurrence")) is int
            and observation["occurrence"] > 0,
            "Occurrence must be positive integer",
        )
        key = tuple(
            observation[f]
            for f in ("clock_id", "entity_id", "observable", "occurrence")
        )
        _need(key not in keys, "Duplicate visual event key")
        keys.add(key)
        _need(
            observation.get("logical_event_time") is None,
            "Visual event cannot assert logical timing",
        )
        _text(observation.get("limitation"))
        _need(
            type(observation.get("previously_inspected")) is bool,
            "Review status required",
        )
        refs = observation.get("evidence_ids")
        _refs(refs, evidence)
        segment = segments[observation["clock_id"]]
        low, high = map(_integer, observation["pts_interval"])
        _need(
            segment["pts_bounds"][0] <= low <= high <= segment["pts_bounds"][1],
            "Observation crosses clock segment",
        )
        _need(type(observation.get("left_open")) is bool, "Interval closure required")
        _need(not observation["left_open"] or low < high, "Empty open interval")
        frames = [evidence[ref] for ref in refs]
        _need(
            all(f["source_id"] == segment["source_id"] for f in frames),
            "Cross-source observation",
        )
        _need(
            {low, high} <= {f["pts"] for f in frames},
            "Bounds must reference actual frames",
        )
        _bounds(observation.get("annotation_error_seconds"), nonnegative=True)
    return {
        "case_sha256": canonical_digest(case),
        "verified_frame_count": len(evidence) if root is not None else 0,
        "binding_gaps": [
            name for name in BINDINGS if bindings[name]["status"] != "exact"
        ],
        "observation_count": len(observations),
    }


def _mapped(case, observation):
    segment = next(
        s for s in case["clock_segments"] if s["id"] == observation["clock_id"]
    )
    source = next(s for s in case["sources"] if s["id"] == segment["source_id"])
    speed = _bounds(segment["speed"])
    offsets = [
        (p - segment["origin_pts"]) * _timebase(source)
        for p in observation["pts_interval"]
    ]
    products = [offset * rate for offset in offsets for rate in speed]
    origin = _bounds(segment["origin_game_seconds"])
    error = _bounds(observation["annotation_error_seconds"])
    # A varying speed and origin envelope conservatively closes the time bounds.
    opened = (
        observation["left_open"]
        and speed[0] == speed[1]
        and origin[0] == origin[1]
        and error == (0, 0)
    )
    return (
        min(products) + origin[0] - error[0],
        max(products) + origin[1] + error[1],
    ), opened


def map_observation(case, observation_id):
    validate_case(case)
    observation = next(o for o in case["observations"] if o["id"] == observation_id)
    interval, opened = _mapped(case, observation)
    return {
        "seconds": list(map(float, interval)),
        "exact_seconds": list(map(str, interval)),
        "left_open": opened,
    }


def validate_protocol(case, protocol):
    validate_case(case)
    _need(
        protocol.get("schema_version") == PROTOCOL_VERSION,
        "Unsupported protocol schema",
    )
    _need(
        protocol.get("case_sha256") == canonical_digest(case),
        "Protocol case digest mismatch",
    )
    _text(protocol.get("id"))
    fit, validation = protocol.get("fit_ids"), protocol.get("validation_ids")
    _need(
        isinstance(fit, list) and isinstance(validation, list) and fit and validation,
        "Fit and validation partitions required",
    )
    selected = fit + validation
    _need(len(set(selected)) == len(selected), "Fit/validation overlap or duplicate")
    observations = _index(case["observations"])
    _need(
        set(selected) == set(observations),
        "Protocol must account for every observation",
    )
    segments = _index(case["clock_segments"])
    evidence = _index(case["evidence"])
    sources = _index(case["sources"])
    frame_keys = lambda ids: {
        (
            _source_identity(sources[evidence[ref]["source_id"]]),
            evidence[ref]["pts"] * _timebase(sources[evidence[ref]["source_id"]]),
        )
        for identifier in ids
        for ref in observations[identifier]["evidence_ids"]
    }
    _need(
        not frame_keys(fit) & frame_keys(validation),
        "Fit/validation source frame leakage",
    )
    frame_hashes = lambda ids: {
        evidence[ref]["sha256"]
        for identifier in ids
        for ref in observations[identifier]["evidence_ids"]
    }
    _need(
        not frame_hashes(fit) & frame_hashes(validation),
        "Fit/validation retained frame hash leakage",
    )
    design = protocol.get("validation_design")
    _need(
        design in {"retrospective_same_encounter", "held_out_encounter"},
        "Validation design required",
    )
    if design == "held_out_encounter":
        _need(
            all(
                sources[segments[observations[i]["clock_id"]]["source_id"]].get(
                    "media_sha256"
                )
                for i in selected
            ),
            "Held-out comparison requires content-bound source identity",
        )
        groups = lambda ids: {
            segments[observations[i]["clock_id"]]["encounter_id"] for i in ids
        }
        _need(not groups(fit) & groups(validation), "Held-out encounter leakage")
        _need(
            all(not observations[i]["previously_inspected"] for i in validation),
            "Previously inspected evidence is retrospective, not pristine held-out",
        )
    _need(
        protocol.get("target_layer") in {"rendered", "engine"}, "Target layer required"
    )
    _text(protocol.get("falsification_rule"))
    tolerance = _number(protocol.get("tolerance_seconds"))
    _need(tolerance >= 0, "Negative tolerance")
    _need(
        protocol.get("missing_prediction_policy") == "incomplete",
        "Missing events cannot pass",
    )
    _text(protocol.get("tolerance_rationale"))
    _need(
        _number(protocol.get("max_prediction_width_seconds")) >= 0,
        "Prediction uncertainty cap must be nonnegative",
    )
    if protocol["target_layer"] == "engine":
        _digest(protocol.get("model_sha256"))
        _digest(protocol.get("input_sha256"))
    return canonical_digest(protocol)


def _intersects(left, right, left_open=False):
    return max(left[0], right[0]) <= min(left[1], right[1]) and not (
        left_open and right[1] == left[0]
    )


def compare_replay(case, protocol, trace, frame_root=None, allow_experimental=False):
    """Pure deterministic report; exact matching only, no nearest-event matching.

    Engine predictions require all exact context values and a preregistered
    per-observable rendering-delay envelope. Rendered predictions bypass no
    engine gates: their result is explicitly limited to visual compatibility.
    """
    integrity = validate_case(case, frame_root)
    protocol_hash = validate_protocol(case, protocol)
    _need(trace.get("schema_version") == TRACE_VERSION, "Unsupported prediction schema")
    _need(
        trace.get("case_sha256") == integrity["case_sha256"],
        "Trace case digest mismatch",
    )
    _need(
        trace.get("protocol_sha256") == protocol_hash, "Trace protocol digest mismatch"
    )
    _need(trace.get("layer") == protocol["target_layer"], "Prediction layer mismatch")
    _text(trace.get("producer"))
    _digest(trace.get("input_sha256"))
    _digest(trace.get("model_sha256"))
    blockers = []
    if case["evidence_class"] == "real" and frame_root is None:
        blockers.append("unverified_frame_bytes")
    if trace["layer"] == "engine":
        for name in ("model_sha256", "input_sha256"):
            _need(trace[name] == protocol[name], "Frozen engine " + name + " mismatch")
        blockers.extend("binding:" + name for name in integrity["binding_gaps"])
        for name in BINDINGS:
            if trace.get("bindings", {}).get(name) != case["bindings"][name]["value"]:
                blockers.append("context_mismatch:" + name)
        _need(
            isinstance(protocol.get("rendering_delays"), dict),
            "Rendering delay contracts required",
        )
    observations = _index(case["observations"])
    predictions = {}
    tolerance = _number(protocol["tolerance_seconds"])
    for prediction in trace.get("events", []):
        identifier = prediction.get("observation_id")
        _need(
            identifier in observations and identifier not in predictions,
            "Unknown/duplicate predicted observation",
        )
        observation = observations[identifier]
        for field in ("clock_id", "entity_id", "observable", "occurrence"):
            _need(
                prediction.get(field) == observation[field],
                "Prediction identity mismatch: " + field,
            )
        _need("target_id" in prediction, "Prediction target_id required")
        _need(
            prediction["target_id"] == observation["target_id"],
            "Prediction identity mismatch: target_id",
        )
        delay_bounds = (Fraction(0), Fraction(0))
        if trace["layer"] == "engine":
            delay = protocol["rendering_delays"].get(observation["observable"])
            if delay is None:
                blockers.append("unbound_rendering_delay:" + observation["observable"])
            else:
                _text(delay.get("evidence"))
                _need(
                    delay.get("basis") in {"measured", "experimental"},
                    "Projection basis required",
                )
                _text(delay.get("engine_event_kind"))
                _need(
                    prediction.get("engine_event_kind") == delay["engine_event_kind"],
                    "Engine-to-visual event mapping mismatch",
                )
                if delay["basis"] == "experimental" and not allow_experimental:
                    blockers.append("experimental_projection_requires_opt_in")
                delay_bounds = _bounds(delay.get("seconds"))
        interval, _ = _mapped(case, observation)
        comparison_boundaries = (
            *interval,
            interval[0] - tolerance,
            interval[1] + tolerance,
        )
        raw_seconds = prediction.get("seconds")
        _need(
            isinstance(raw_seconds, list) and len(raw_seconds) == 2,
            "Prediction needs two seconds bounds",
        )
        raw_when = tuple(
            _prediction_time(value, (bound - delay for bound in comparison_boundaries))
            for value, delay in zip(raw_seconds, delay_bounds)
        )
        _need(raw_when[0] <= raw_when[1], "Reversed prediction interval")
        when = tuple(value + delay for value, delay in zip(raw_when, delay_bounds))
        _need(
            when[1] - when[0] <= _number(protocol["max_prediction_width_seconds"]),
            "Predicted uncertainty exceeds frozen cap",
        )
        predictions[identifier] = when
    rows = []
    for identifier in sorted(observations):
        observation = observations[identifier]
        interval, opened = _mapped(case, observation)
        allowed = (interval[0] - tolerance, interval[1] + tolerance)
        row = dict(
            id=identifier,
            partition="fit" if identifier in protocol["fit_ids"] else "validation",
            observed_seconds=list(map(float, interval)),
            observed_exact_seconds=list(map(str, interval)),
            left_open=opened,
            predicted_seconds=None,
            predicted_exact_seconds=None,
            residual_seconds=None,
            status="missing_prediction",
        )
        if identifier in predictions:
            when = predictions[identifier]
            compatible = _intersects(allowed, when, opened and tolerance == 0)
            residual = (
                when[1] - interval[0]
                if when[1] < interval[0]
                else max(Fraction(0), when[0] - interval[1])
            )
            row.update(
                predicted_seconds=list(map(float, when)),
                predicted_exact_seconds=list(map(str, when)),
                residual_seconds=float(residual),
                status="compatible" if compatible else "falsified",
            )
        rows.append(row)
    statuses = {r["status"] for r in rows}
    verdict = (
        "falsified"
        if "falsified" in statuses
        else "incomplete" if "missing_prediction" in statuses else "compatible"
    )
    return {
        "schema_version": "replay-comparison-v1",
        "status": "BLOCKED" if blockers else "PARTIAL_COMPARISON_ONLY",
        "verdict": "blocked" if blockers else verdict,
        "layer": trace["layer"],
        "experimental_projection_opt_in": allow_experimental,
        "evidence_class": case["evidence_class"],
        "case_sha256": integrity["case_sha256"],
        "protocol_sha256": protocol_hash,
        "trace_sha256": canonical_digest(trace),
        "integrity": integrity,
        "blockers": sorted(set(blockers)),
        "events": rows,
        "validation_design": protocol["validation_design"],
        "falsification_rule": protocol["falsification_rule"],
        "complete_calibrated_battles": 0,
        "measured_engine_parameters": {},
        "population_win_rate": None,
    }


def calibrate_rendered_cycle(case, protocol, frame_root=None):
    """Fit two successive appearances; predict third without using its bounds.

    This fits only a conditional constant *rendered* interval. Finite interval
    arithmetic gives a conservative next-appearance envelope. All three must
    be same-actor/same-target appearances with consecutive occurrence numbers.
    Target attribution and no missed appearance remain explicit visual assumptions.
    """
    validate_case(case, frame_root)
    protocol_hash = validate_protocol(case, protocol)
    _need(protocol["target_layer"] == "rendered", "Cycle fit is rendered only")
    _need(
        len(protocol["fit_ids"]) == 2 and len(protocol["validation_ids"]) == 1,
        "Cycle fit requires two fit appearances and one retrospective check",
    )
    observations = _index(case["observations"])
    selected = [
        observations[i] for i in protocol["fit_ids"] + protocol["validation_ids"]
    ]
    first, second, third = selected
    _need(
        all(o["observable"] == "projectile_appearance" for o in selected),
        "Cycle fit needs projectile appearances",
    )
    _need(
        all(
            o["clock_id"] == first["clock_id"]
            and o["entity_id"] == first["entity_id"]
            and o.get("target_id") == first.get("target_id")
            for o in selected
        ),
        "Cycle fit actor, target or clock differs",
    )
    _text(first.get("target_id"))
    _need(
        [o["occurrence"] for o in selected]
        == list(range(first["occurrence"], first["occurrence"] + 3)),
        "Cycle fit requires consecutive occurrences",
    )
    a, b = _mapped(case, first)[0], _mapped(case, second)[0]
    period = (b[0] - a[1], b[1] - a[0])
    _need(period[0] > 0, "Fit appearances overlap")
    forecast = (2 * b[0] - a[1], 2 * b[1] - a[0])
    model = {
        "name": "constant_rendered_cycle",
        "period_seconds": list(map(str, period)),
        "fit_ids": protocol["fit_ids"],
        "target_id": first["target_id"],
    }
    trace = {
        "schema_version": TRACE_VERSION,
        "case_sha256": canonical_digest(case),
        "protocol_sha256": protocol_hash,
        "layer": "rendered",
        "producer": "calibrate_rendered_cycle/v1",
        "input_sha256": canonical_digest([first, second]),
        "model_sha256": canonical_digest(model),
        "events": [
            {
                "observation_id": o["id"],
                **{
                    k: o[k]
                    for k in (
                        "clock_id",
                        "entity_id",
                        "target_id",
                        "observable",
                        "occurrence",
                    )
                },
                "seconds": list(map(str, bounds)),
            }
            for o, bounds in zip(selected, (a, b, forecast))
        ],
    }
    report = compare_replay(case, protocol, trace, frame_root)
    report["rendered_cycle_fit"] = {
        **model,
        "next_appearance_seconds": list(map(str, forecast)),
        "not_measured": [
            "base_attack_period",
            "damage",
            "windup",
            "projectile_release",
            "logical_invisibility",
        ],
        "fit_event_residuals_are_in_sample": True,
    }
    return {"trace": trace, "report": report}
