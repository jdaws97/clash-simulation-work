"""Which engine code do given armies actually run? Line coverage of
src/baselab/engine/*.py and pathing.py over a set of battles (stdlib
sys.settrace; no coverage package). Scopes the Rust port: functions that
never run for an army need not be ported before it.

Usage: python tools/baselab/engine_coverage.py --armies custom:user-rr custom:user-druid-ruin \
           --out output/coverage-user.json
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("BASELAB_PLAYBOOKS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

ENGINE = ROOT / "src" / "baselab" / "engine"
FILES = sorted(str(p) for p in ENGINE.glob("*.py")) + [str(ROOT / "src" / "baselab" / "pathing.py")]
BASES = ["data/reference-bases/your-base.json", "data/reference-bases/real-l6x.json", "data/reference-bases/real-l3x.json"]


def functions(path):
    """(qualified name, first line, last line) of every function in a file."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    out = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                out.append((name, child.lineno, child.end_lineno))
                walk(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")

    walk(tree, "")
    return out


def main():
    import importlib

    from fingerprint import run_one

    # import everything first: executing `def` lines at import is not coverage
    for f in FILES:
        rel = Path(f).relative_to(ROOT / "src").with_suffix("")
        importlib.import_module(".".join(rel.parts))
    import baselab.evaluate  # noqa: F401
    import baselab.meta_armies  # noqa: F401

    ap = argparse.ArgumentParser()
    ap.add_argument("--armies", nargs="+", required=True)
    ap.add_argument("--sides", type=int, default=4)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    files = set(FILES)
    hits = {f: set() for f in FILES}

    def tracer(frame, event, arg):
        f = frame.f_code.co_filename
        if f not in files:
            return None
        lines = hits[f]

        def local(frame, event, arg):
            if event == "line":
                lines.add(frame.f_lineno)
            return local

        lines.add(frame.f_lineno)
        return local

    t0 = time.time()
    n = 0
    for army in args.armies:
        for base in BASES:
            for k in range(args.sides):
                angle = 2 * math.pi * k / args.sides + 0.1
                sys.settrace(tracer)
                try:
                    run_one(base, army, angle, 11 + k)
                finally:
                    sys.settrace(None)
                n += 1
    report = {}
    for f in FILES:
        rel = str(Path(f).relative_to(ROOT)).replace("\\", "/")
        fns = []
        for name, lo, hi in functions(f):
            ran = sorted(x for x in hits[f] if lo < x <= hi)  # body lines only
            fns.append({"name": name, "lines": [lo, hi], "ran": bool(ran), "lines_run": len(ran)})
        report[rel] = {"lines_run": len(hits[f]), "functions": fns}
    Path(args.out).write_text(json.dumps({"armies": args.armies, "battles": n, "files": report}, indent=1))
    print(f"{n} battles traced in {time.time() - t0:.0f}s -> {args.out}")
    for rel, r in report.items():
        ran = [fn for fn in r["functions"] if fn["ran"]]
        size = sum(fn["lines"][1] - fn["lines"][0] + 1 for fn in ran)
        print(f"  {rel:40s} {len(ran):4d}/{len(r['functions']):4d} functions run, ~{size} lines in them")


if __name__ == "__main__":
    main()
