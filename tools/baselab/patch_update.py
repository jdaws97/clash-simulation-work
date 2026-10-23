"""After a game patch: what changed, and what in the simulator is now stale.

Subcommands
  cites [--csv DIR]       Check every hard-coded value the engine cites as
                          `game data vX: Entity.Field=Value` against a game
                          data folder (default: the current one). A mismatch
                          names the file:line to update.
  csv OLD NEW             Changed, added and removed entity/field values
                          between two game-data folders (e.g. v18.200.9 and
                          the next release).
  registry OLD NEW        Changes between two registry.json builds, plus new
                          entities the engine has no model for.
  plan --csv NEW          Print rebuild commands and invalidations; run nothing.
  report --csv NEW [--registry-old FILE]
                          All of the above against NEW, then the known-answer
                          mechanic checks and the coverage run; writes
                          docs/patch-report-<date>.md.

Typical patch day (each download asks the user first):
  1. put the new game data tables in data/gamecsv/<version>/ (source:
     github.com/Enjoyop2/Clash-of-Clans-data-assets)
  2. python tools/baselab/wiki_mirror.py fetch   (refresh the wiki mirror)
  3. copy data/registry.json aside, then python -m baselab.registry
  4. python tools/baselab/patch_update.py report --csv data/gamecsv/<version> --registry-old <copy>
  5. fix what the report flags, then rerun calibration and the SIM_ACCURACY
     checks and re-score the saved best bases and armies.

Use plan --csv NEW for the complete local rebuild sequence, including Rust and
manifest provenance. The existing report command still runs its mechanic checks.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

import verify_numbers  # noqa: E402

CURRENT = ROOT / "data" / "gamecsv" / "v18.200.9"
CITE = re.compile(r"game data v([\d.]+):\s*([^=\n:]+?)\.([A-Za-z0-9_]+)=([-\w.]+)")


def tables(folder: Path) -> dict:
    verify_numbers.CSV_DIR = Path(folder)
    return verify_numbers.load_tables()


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9*]", "", name.lower())


def _rows(ents: dict, cited: str):
    """Row groups (one per entity) for a cited entity, tolerant of how
    citations are written: an optional file prefix ("Traps.csv
    SkeletonTrap"), names with or without spaces, "Bomb/GiantBomb" (every
    one must exist) and a trailing "*" wildcard (every entity with that
    prefix). None when a named entity is missing."""
    name = re.sub(r"^\S+\.csv\s+", "", cited.strip())
    index = getattr(_rows, "_index", None)
    if index is None or index[0] is not ents:
        index = (ents, {})
        for k, v in ents.items():
            index[1].setdefault(_key(k), []).extend(v)
        _rows._index = index
    out = []
    for part in name.split("/"):
        k = _key(part)
        if k.endswith("*"):
            hit = [rs for kk, rs in index[1].items() if kk.startswith(k[:-1])]
        else:
            hit = [index[1][k]] if index[1].get(k) else []
        if not hit:
            return None
        out += hit
    return out


def _holds(groups, field, val) -> bool:
    """A cite holds when every cited entity that sets the field has the
    value in some level row (not just one of "Bomb/GiantBomb"), and at
    least one does."""
    sets = [{r.get(field) for r in g} - {None, ""} for g in groups]
    return any(sets) and all(val in s for s in sets if s)


def cmd_cites(folder: Path, out: list) -> int:
    ents = tables(folder)
    bad = checked = 0
    unparsed = []
    for f in sorted((ROOT / "src").rglob("*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            found = CITE.findall(line)
            if not found and "game data v" in line:
                unparsed.append(f"{f.relative_to(ROOT)}:{n}")
            for _, ent, field, val in found:
                checked += 1
                groups = _rows(ents, ent)
                if not groups or not _holds(groups, field, val.rstrip(".")):
                    bad += 1
                    vals = (
                        set().union(*({r.get(field) for r in g} for g in groups))
                        if groups
                        else set()
                    )
                    now = (
                        sorted(v for v in vals if v not in (None, ""))[:6]
                        if groups
                        else "entity not found"
                    )
                    out.append(
                        f"| {f.relative_to(ROOT)}:{n} | {ent.strip()}.{field} | cited {val} | now {now} |"
                    )
    out.insert(
        0,
        f"Hard-coded values checked: {checked}, stale or not found: {bad}\n\n| where | field | cited | in {Path(folder).name} |\n|---|---|---|---|",
    )
    if unparsed:
        # prose cites ("game data vX Traps.csv ActionFrame ... Bomb=35") the
        # pattern cannot read: listed so a patch day checks them by hand
        out.append(
            f"\nLines citing game data in a form this check cannot read ({len(unparsed)}, check by hand): "
            + ", ".join(unparsed)
        )
    return bad


def cmd_csv(old: Path, new: Path, out: list):
    a, b = tables(old), tables(new)
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    out.append(f"Entities added: {len(added)}, removed: {len(removed)}")
    if added:
        out.append("Added: " + ", ".join(added[:80]))
    if removed:
        out.append("Removed: " + ", ".join(removed[:80]))
    changes = []
    for ent in sorted(set(a) & set(b)):
        ra, rb = a[ent], b[ent]
        for lvl, (x, y) in enumerate(zip(ra, rb), 1):
            diff = {
                k: (x.get(k), y.get(k)) for k in set(x) | set(y) if x.get(k) != y.get(k)
            }
            if diff:
                changes.append(
                    f"| {ent} | row {lvl} | "
                    + "; ".join(
                        f"{k}: {v[0]} -> {v[1]}" for k, v in sorted(diff.items())[:8]
                    )
                    + " |"
                )
        if len(ra) != len(rb):
            changes.append(
                f"| {ent} | rows | {len(ra)} -> {len(rb)} (levels added or removed) |"
            )
    out.append(
        f"\nChanged rows: {len(changes)}\n\n| entity | row | changes |\n|---|---|---|"
    )
    out += changes[:1500]


def _engine_names():
    from baselab.engine import heroes, specs
    from baselab.engine.plans import SPELL_NAMES

    names = set(getattr(specs, "SPECS", {}) or {})
    for attr in ("SPECS", "UNIT_SPECS", "ALL"):
        v = getattr(specs, attr, None)
        if isinstance(v, dict):
            names |= set(v)
    names |= set(heroes.HEROES) | set(SPELL_NAMES.values())
    return names


def cmd_registry(old: Path, new: Path, out: list):
    a = json.loads(Path(old).read_text(encoding="utf-8"))
    b = json.loads(Path(new).read_text(encoding="utf-8"))
    added = sorted(set(b) - set(a))
    out.append(
        f"Registry entities added: {len(added)}"
        + (": " + ", ".join(added) if added else "")
    )
    changed = []
    for k in sorted(set(a) & set(b)):
        la, lb = a[k].get("levels", []), b[k].get("levels", [])
        if la != lb or a[k].get("max_level") != b[k].get("max_level"):
            changed.append(k)
    out.append(
        f"Registry entities with changed levels or caps: {len(changed)}"
        + (": " + ", ".join(changed[:120]) if changed else "")
    )
    try:
        known = _engine_names()
        new_units = [
            k
            for k in added
            if b[k].get("kind")
            in ("troop", "super_troop", "siege", "spell", "hero", "pet", "equipment")
        ]
        missing = [k for k in new_units if k not in known]
        out.append(
            f"New content the engine may not model yet: {missing or 'none'} (check engine_coverage.py)"
        )
    except Exception as e:  # the engine import is a convenience here
        out.append(f"(engine name check skipped: {e})")


def cmd_plan(folder: Path, out: list):
    out.append(f"\n## Updating derived data after {folder.name}\n")
    out.append("Commands to run after reviewing the patch (printed only):\n")
    out.append(
        "The registry uses ClashKing plus parsed wiki data, not CSVs directly "
        "(src/baselab/registry.py). Refresh those sources as appropriate. "
        "A new CSV folder does not change the engine's pinned CSV version; "
        "review and update these reader pins before exporting:"
    )
    for name in (
        "src/baselab/engine/specs.py",
        "src/baselab/engine/units.py",
        "tools/baselab/verify_numbers.py",
        "tools/baselab/patch_update.py",
    ):
        for number, line in enumerate(
            (ROOT / name).read_text(encoding="utf-8").splitlines(), 1
        ):
            if re.search(r"[\"\']v\d+(?:\.\d+)+[\"\']", line):
                out.append(f"- {name}:{number}: {line.strip()}")
    # docs/GAP_ANALYSIS.md:152: registry, catalog and winners need one data chain.
    commands = (
        "python3 -B tools/baselab/wiki_mirror.py fetch",
        "python3 -B tools/baselab/wiki_tables.py",
        "PYTHONPATH=src python3 -B -m baselab.registry",
        "python3 -B tools/baselab/rust_export.py catalog --out rust/data/catalog.json",
        "python3 -B tools/baselab/data_manifest.py build "
        "--record-derived data/registry.json --record-derived rust/data/catalog.json",
        "python3 -B tools/baselab/data_manifest.py check",
    )
    out.append("\n```sh\n" + "\n".join(commands) + "\n```")
    out.append(
        "Use --record-derived only after actually regenerating that artifact. "
        "Manifest build alone preserves old bindings and does not certify legacy data."
    )
    out.append(
        "\nInvalidate calibration fits against the previous engine/data (retain archives as historical):"
    )
    calibrations = sorted(
        set((ROOT / "data").glob("meta-calibration*.json"))
        | set((ROOT / "data").glob("baselab-calibration*.json"))
    )
    out.extend(f"- {path.relative_to(ROOT).as_posix()}" for path in calibrations)
    out.append(
        "\nInvalidate saved scores/rankings in output/, including winner/best "
        "evaluations and hold-out/red-team reports. data_manifest.py check names "
        "results carrying older manifest_hash values; results without a hash "
        "remain unverified. Keep layouts, but re-score them before reuse."
    )
    out.append(
        "\nRun the proof checks before recalibration, result re-scoring or any "
        "search (python -B verify.py when available, mechanic_tests.py and "
        "engine_coverage.py). After the proof gate passes, refit the active "
        "calibration with calibrate.py/calibrate_meta.py as appropriate, record "
        "its exact path with data_manifest.py build --record-derived PATH, "
        "then re-score saved finalists and store the new manifest_hash in results. "
        "No calibration or search is run by this plan."
    )


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cites")
    c.add_argument("--csv", default=str(CURRENT))
    d = sub.add_parser("csv")
    d.add_argument("old")
    d.add_argument("new")
    r = sub.add_parser("registry")
    r.add_argument("old")
    r.add_argument("new")
    p = sub.add_parser("report")
    p.add_argument("--csv", required=True)
    p.add_argument("--registry-old")
    plan = sub.add_parser("plan")
    plan.add_argument("--csv", required=True)
    args = ap.parse_args()
    out: list = []
    if args.cmd == "cites":
        bad = cmd_cites(Path(args.csv), out)
        print("\n".join(out))
        sys.exit(1 if bad else 0)
    if args.cmd == "csv":
        cmd_csv(Path(args.old), Path(args.new), out)
        cmd_plan(Path(args.new), out)
        print("\n".join(out))
        return
    if args.cmd == "registry":
        cmd_registry(Path(args.old), Path(args.new), out)
        print("\n".join(out))
        return
    if args.cmd == "plan":
        cmd_plan(Path(args.csv), out)
        print("\n".join(out))
        return
    day = datetime.date.today().isoformat()
    out.append(
        f"# Patch report {day}\n\nNew game data: `{args.csv}` (compared with `{CURRENT.relative_to(ROOT)}`)\n"
    )
    out.append("## Hard-coded engine values\n")
    sec: list = []
    cmd_cites(Path(args.csv), sec)
    out += sec
    out.append("\n## Game data changes\n")
    sec = []
    cmd_csv(CURRENT, Path(args.csv), sec)
    out += sec
    if args.registry_old:
        out.append("\n## Registry changes\n")
        sec = []
        cmd_registry(Path(args.registry_old), ROOT / "data" / "registry.json", sec)
        out += sec
    sec = []
    cmd_plan(Path(args.csv), sec)
    out += sec
    print("\n".join(sec))
    py = sys.executable
    for title, cmd in (
        ("Mechanic checks", [py, "tools/baselab/mechanic_tests.py"]),
        (
            "Coverage",
            [py, "tools/baselab/engine_coverage.py", "--out", "output/coverage.json"],
        ),
    ):
        res = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tail = "\n".join((res.stdout or res.stderr).strip().splitlines()[-15:])
        out.append(f"\n## {title}\n\n```\n{tail}\n```")
    path = ROOT / "docs" / f"patch-report-{day}.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
