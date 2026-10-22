"""Run battles in the Rust engine (rust/, a bit-exact port of engine/).

Python prepares data, Rust builds and runs the battles: a batch is a set of
layouts (Layout.to_json(), with levels), constructed attack plans (dumped
engine objects) and jobs pairing them with a seed and options; the
`baselab-engine jobs` command runs them across threads and returns one
result per job. Plans do not depend on the layout, so each scenario's plan is
built once per process and reused for every layout a search scores.

evaluate.run_batch uses this when BASELAB_ENGINE=rust. The engine binary is
rust/target/release/baselab-engine(.exe), or BASELAB_ENGINE_EXE. Parity with
the Python engine is checked by tools/baselab/rust_export.py.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def engine_executable() -> Path:
    configured = os.environ.get("BASELAB_ENGINE_EXE")
    if configured:
        return Path(configured)
    directory = ROOT / "rust" / "target" / "release"
    native = directory / "baselab-engine"
    return native if native.exists() else directory / "baselab-engine.exe"


def dump(obj, depth=0):
    """JSON-able copy of engine state. Engine objects inside other objects
    become references ({"$building": id}, {"$wall": [tx, ty]}, {"$unit": id})
    so the Rust side can rebuild the links."""
    from .engine.entities import Building, Unit, Wall

    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj  # json.dumps writes Infinity/NaN, which rust/src/json.rs reads
    if depth > 0:
        if isinstance(obj, Building):
            return {"$building": obj.id}
        if isinstance(obj, Wall):
            return {"$wall": [obj.tx, obj.ty]}
        if isinstance(obj, Unit):
            return {"$unit": obj.id, "team": obj.team}
    if isinstance(obj, dict):
        return {(k if isinstance(k, str) else json.dumps(dump(k, 1))): dump(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [dump(v, depth + 1) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((dump(v, depth + 1) for v in obj), key=repr)
    if dataclasses.is_dataclass(obj):
        out = {"$type": type(obj).__name__}
        out.update({f.name: dump(getattr(obj, f.name), depth + 1) for f in dataclasses.fields(obj)})
        # runtime plan state such as _spell_stock is created after dataclass init
        for name, value in getattr(obj, "__dict__", {}).items():
            if name not in out:
                out[name] = dump(value, depth + 1)
        return out
    slots = getattr(type(obj), "__slots__", None)
    if slots is not None or hasattr(obj, "__dict__"):
        names = list(slots or []) + list(getattr(obj, "__dict__", {}))
        out = {"$type": type(obj).__name__}
        for name in names:
            if hasattr(obj, name):
                v = getattr(obj, name)
                if callable(v) and not isinstance(v, type):
                    raise TypeError(f"cannot export callable {type(obj).__name__}.{name}")
                out[name] = dump(v, depth + 1)
        return out
    raise TypeError(f"cannot export {type(obj).__name__}")


def plan_json(plan):
    """The plan as the Rust engine loads it: validated like Battle.run()."""
    validate = getattr(plan, "require_legal", None)
    if validate is not None:
        validate()
    return dump(plan)


_PLANS: dict = {}


def scenario_plan(sc, strength: float) -> str:
    """JSON text of a scored scenario's plan, built as evaluate._run_one
    builds it (make_plan, tactic, charge, strength x skill), cached."""
    key = (sc, strength)
    text = _PLANS.get(key)
    if text is None:
        from .evaluate import apply_charge, skill
        from .meta_armies import make_plan

        plan = make_plan(sc.army, sc.angle, sc.town_hall, sc.seed)
        if sc.tactic is not None:
            from .tactics import apply

            apply(plan, sc.tactic)
        if sc.charge is not None:
            apply_charge(plan, sc.charge)
        plan.strength = strength * skill(sc.seed)
        text = json.dumps(plan_json(plan))
        _PLANS[key] = text
    return text


def run_jobs_file(path: Path, threads: int | None = None) -> list[dict]:
    """Run a jobs file with the engine; one result dict per job, in order."""
    exe = engine_executable()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.jsonl"
        command = [str(exe), "jobs", str(path), str(out)]
        if threads:
            command += ["--threads", str(threads)]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode != 0:
            raise RuntimeError(f"baselab-engine failed: {run.stderr.strip()[-2000:]}")
        return [json.loads(line) for line in out.read_text().splitlines() if line.strip()]


def run_batch(jobs, threads: int | None = None):
    """evaluate.run_batch in the Rust engine. jobs: [(layout_json, Scenario,
    strength)] -> [(stars, destruction, th_destroyed, time)] in job order."""
    layouts, layout_index = [], {}
    plans, plan_index = [], {}
    entries = []
    for layout_json, sc, strength in jobs:
        lk = json.dumps(layout_json, sort_keys=True)
        if lk not in layout_index:
            layout_index[lk] = len(layouts)
            layouts.append(lk)
        pk = (sc, strength)
        if pk not in plan_index:
            plan_index[pk] = len(plans)
            plans.append(scenario_plan(sc, strength))
        entries.append({"layout": layout_index[lk], "plan": plan_index[pk], "seed": sc.seed,
                        "town_hall": layout_json.get("town_hall", 16), "modifier": sc.modifier})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "jobs.json"
        # plans are cached as JSON text: splice them in without re-encoding
        path.write_text('{"layouts": [' + ",".join(layouts) + '], "plans": [' + ",".join(plans)
                        + '], "jobs": ' + json.dumps(entries) + "}")
        results = run_jobs_file(path, threads)
    return [(r["stars"], r["destruction"], r["th_destroyed"], r["time"]) for r in results]
