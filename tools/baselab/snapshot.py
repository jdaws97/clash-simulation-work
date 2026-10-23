"""Archive the defensive setup live for a ranked tournament or League Day.

Examples (period bounds are UTC, start inclusive and end exclusive):
  python3 -B tools/baselab/snapshot.py add base.json --levels levels.json \
      --from 2026-10-19T05:00:00Z --to 2026-10-26T05:00:00Z \
      --notes "Tournament A" --source screenshot --confidence medium
  python3 -B tools/baselab/snapshot.py list
  python3 -B tools/baselab/snapshot.py for-battle 20261021T183738Z
  python3 -B tools/baselab/snapshot.py report

Use the effective period, not when the Home Village was edited. Ranked_Battles
wiki (data/wiki/text/Ranked_Battles.txt:25-29): changes apply next tournament;
Legend I uses the next League Day. Supply those boundaries explicitly.
Optional --provenance JSON overrides individual fields with objects containing
source (user-entered/API/screenshot), confidence (unknown/low/medium/high), and
notes. Trap levels may be levels["trap:<key>"] or a separate trap_levels map.
Hero order in the layout pairs with banners in building-list order.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "data/live/base-history.json"
BATTLES = ROOT / "data/live/battles.jsonl"
SOURCES = ("user-entered", "API", "screenshot")
CONFIDENCES = ("unknown", "low", "medium", "high")
FIELDS = (
    "layout",
    "levels",
    "wall_level",
    "wall_levels",
    "trap_levels",
    "defense_modes",
    "trap_modes",
    "cc_troops",
    "hero_levels",
    "hero_banners",
    "town_hall",
    "guardian",
)


def timestamp(value: str) -> dt.datetime:
    """Accept API timestamps, ISO timestamps with offsets, or UTC dates."""
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        result = None
        for fmt in ("%Y%m%dT%H%M%S.%fZ", "%Y%m%dT%H%M%SZ", "%Y%m%d"):
            try:
                result = dt.datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        if result is None:
            raise ValueError(f"Invalid timestamp: {value}") from None
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt.timezone.utc)
    return result.astimezone(dt.timezone.utc)


def utc(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def read_history(path: Path = HISTORY) -> dict:
    if not path.exists():
        return {"schema_version": 2, "periods": [], "snapshots": []}
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_for_battle(history: dict, battle_time: str) -> dict | None:
    """Legacy inclusive-day periods are layout hints, not frozen snapshots."""
    when = timestamp(battle_time)
    matches = [
        entry
        for entry in history.get("snapshots", [])
        if timestamp(entry["from"]) <= when
        and (entry.get("to") is None or when < timestamp(entry["to"]))
    ]
    if len(matches) > 1:
        raise ValueError(f"Overlapping snapshots at {battle_time}")
    return matches[0] if matches else None


def load_snapshot(entry: dict, root: Path = ROOT) -> dict:
    path = Path(entry["layout"])
    if not path.is_absolute():
        path = root / path
    layout = json.loads(path.read_text(encoding="utf-8"))
    if layout_hash(layout) != entry["sha256"]:
        raise ValueError(f"Snapshot has changed since recording: {path}")
    return layout


def layout_hash(layout: dict) -> str:
    payload = json.dumps(layout, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_layout(layout: dict, levels: dict) -> dict:
    """Merge only the supplied historical inputs; never consult today's account."""
    frozen = copy.deepcopy(layout)
    for key in ("name", "buildings", "heroes", "cc_troops"):
        if key not in frozen:
            raise ValueError(f"Layout must explicitly supply {key}")
    for key in ("levels", "hero_levels", "wall_level"):
        if key in levels:
            frozen[key] = copy.deepcopy(levels[key])
        if key not in frozen:
            raise ValueError(f"Levels file or layout must supply {key}")
    if "wall_levels" in levels:
        frozen["wall_levels"] = copy.deepcopy(levels["wall_levels"])
    frozen.setdefault("wall_levels", [])
    frozen.setdefault("walls", [])
    frozen.setdefault("traps", [])
    frozen.setdefault("town_hall", 16)
    frozen.setdefault("guardian", "Longshot")
    if not isinstance(frozen["levels"], dict):
        raise ValueError("levels must map names to positive integer levels")
    trap_levels = dict(layout.get("trap_levels", {}))
    trap_levels.update(
        {
            key.removeprefix("trap:"): value
            for key, value in frozen["levels"].items()
            if key.startswith("trap:")
        }
    )
    trap_levels.update(levels.get("trap_levels", {}))
    frozen["trap_levels"] = trap_levels
    # engine/traps.py:89 reads trap levels from the shared defense-level map.
    for key, value in trap_levels.items():
        frozen["levels"][f"trap:{key}"] = value
    for key in ("levels", "hero_levels", "trap_levels"):
        if not isinstance(frozen[key], dict) or any(
            type(value) is not int or value < 1 for value in frozen[key].values()
        ):
            raise ValueError(f"{key} must map names to positive integer levels")
    if frozen["wall_level"] is not None and (
        type(frozen["wall_level"]) is not int or frozen["wall_level"] < 1
    ):
        raise ValueError("wall_level must be a positive integer or null")
    wall_positions = set(map(tuple, frozen["walls"]))
    seen_walls = set()
    for wall in frozen["wall_levels"]:
        position = (wall["x"], wall["y"])
        if position not in wall_positions or position in seen_walls:
            raise ValueError(f"Invalid or repeated wall level position: {position}")
        if type(wall["level"]) is not int or wall["level"] < 1:
            raise ValueError("wall_levels must contain positive integer levels")
        seen_walls.add(position)
    banners = [b for b in frozen["buildings"] if b["key"] == "banner"]
    if len(frozen["heroes"]) > len(banners):
        raise ValueError("More defending heroes than banners")
    if len(set(frozen["heroes"])) != len(frozen["heroes"]):
        raise ValueError("Defending heroes must be unique")
    # engine/battle.py:298-300 pairs heroes with banners in building-list order.
    frozen["hero_banners"] = [
        {
            "x": banner["x"],
            "y": banner["y"],
            "hero": frozen["heroes"][i] if i < len(frozen["heroes"]) else None,
        }
        for i, banner in enumerate(banners)
    ]
    return frozen


def field_provenance(frozen: dict, args) -> dict:
    fields = {
        key: {"source": args.source, "confidence": args.confidence} for key in FIELDS
    }
    missing = {
        "trap_levels": {t["key"] for t in frozen["traps"]}
        - frozen["trap_levels"].keys(),
        "hero_levels": set(frozen["heroes"]) - frozen["hero_levels"].keys(),
        "levels": {b["key"] for b in frozen["buildings"]}
        - {"th", "banner"}
        - frozen["levels"].keys(),
    }
    if frozen["wall_level"] is None:
        missing["wall_level"] = set(map(tuple, frozen["walls"])) - {
            (wall["x"], wall["y"]) for wall in frozen["wall_levels"]
        }
    for key, absent in missing.items():
        if absent:
            fields[key] = {
                "source": args.source,
                "confidence": "unknown",
                "notes": "Missing levels; engine uses Town Hall maxima: "
                + ", ".join(map(str, sorted(absent))),
            }
    if args.provenance:
        overrides = json.loads(Path(args.provenance).read_text(encoding="utf-8"))
        for key, value in overrides.items():
            if key not in fields:
                raise ValueError(f"Unknown provenance field: {key}")
            if value.get("source") not in SOURCES:
                raise ValueError(f"Invalid source for {key}")
            if value.get("confidence") not in CONFIDENCES:
                raise ValueError(f"Invalid confidence for {key}")
            if missing.get(key) and value["confidence"] != "unknown":
                raise ValueError(f"Missing {key} must have unknown confidence")
            fields[key] = {**fields[key], **value}
    return fields


def add_snapshot(args) -> dict:
    history = read_history(args.history)
    start = timestamp(args.start)
    end = timestamp(args.end) if args.end else None
    if end is not None and end <= start:
        raise ValueError("--to must be after --from (end is exclusive)")
    layout = json.loads(Path(args.layout).read_text(encoding="utf-8"))
    levels = json.loads(Path(args.levels).read_text(encoding="utf-8"))
    frozen = freeze_layout(layout, levels)
    fields = field_provenance(frozen, args)
    snapshots = history.setdefault("snapshots", [])
    # An ongoing period closes only when the next effective period is recorded.
    for previous in snapshots:
        old_start = timestamp(previous["from"])
        old_end = timestamp(previous["to"]) if previous.get("to") else None
        if old_end is None and old_start < start:
            previous["to"] = utc(start)
            old_end = start
        if (end is None or old_start < end) and (old_end is None or start < old_end):
            raise ValueError(f"Period overlaps snapshot {previous['id']}")
    digest = layout_hash(frozen)
    name = f"{start.date().isoformat()}-{digest[:12]}"
    archive = args.history.parent / "snapshots" / f"{name}.json"
    try:
        layout_path = str(archive.resolve().relative_to(ROOT))
    except ValueError:
        layout_path = str(archive.resolve())
    entry = {
        "id": f"{utc(start)}-{digest[:12]}",
        "from": utc(start),
        "to": utc(end) if end else None,
        "period": args.period,
        "layout": layout_path,
        "sha256": digest,
        "fields": fields,
        "notes": args.notes,
    }
    if archive.exists():
        if layout_hash(json.loads(archive.read_text(encoding="utf-8"))) != digest:
            raise ValueError(f"Refusing to overwrite changed snapshot: {archive}")
    else:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(frozen, indent=1) + "\n")
    snapshots.append(entry)
    snapshots.sort(key=lambda item: timestamp(item["from"]))
    history["schema_version"] = 2
    temporary = args.history.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(history, indent=1) + "\n", encoding="utf-8")
    temporary.replace(args.history)
    return entry


def read_battles(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)["items"]


def ranked_defenses(battles: list[dict]) -> list[dict]:
    seen = set()
    defenses = []
    for battle in battles:
        if battle.get("battleType") != "ranked" or battle.get("attack") is not False:
            continue
        key = (timestamp(battle["battleTimestamp"]), battle.get("opponentPlayerTag"))
        if key not in seen:
            seen.add(key)
            defenses.append(battle)
    return defenses


def defender_trophies(stars: int, pct: float) -> int:
    # Ranked_Battles.txt:32-38; mirror evaluate.py without importing the engine.
    if stars == 0:
        return 40
    if stars >= 3:
        return 0
    if stars == 2:
        return 40 - (16 + max(0, int((pct - 50) // 3)))
    return 40 - min(15, 5 + int(max(0.0, pct - 1) // 9))


def report(history: dict, battles: list[dict]) -> tuple[list[dict], int]:
    grouped = {entry["id"]: [] for entry in history.get("snapshots", [])}
    uncovered = 0
    for battle in ranked_defenses(battles):
        entry = snapshot_for_battle(history, battle["battleTimestamp"])
        if entry is None:
            uncovered += 1
            continue
        grouped[entry["id"]].append(
            defender_trophies(battle["stars"], battle["destructionPercentage"])
        )
    rows = []
    for entry in sorted(
        history.get("snapshots", []), key=lambda e: timestamp(e["from"])
    ):
        values = grouped[entry["id"]]
        mean = statistics.mean(values) if values else None
        interval = None
        if len(values) >= 2:
            margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
            interval = [max(0.0, mean - margin), min(40.0, mean + margin)]
        rows.append(
            {
                "id": entry["id"],
                "from": entry["from"],
                "to": entry.get("to"),
                "layout": entry["layout"],
                "ranked_defenses": len(values),
                "mean_defender_trophies": mean,
                "interval_95": interval,
            }
        )
    return rows, uncovered


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)
    add = sub.add_parser(
        "add", help="record a setup at its effective tournament/League Day boundary"
    )
    add.add_argument("layout")
    add.add_argument("--levels", required=True)
    add.add_argument(
        "--from", dest="start", required=True, help="effective start, inclusive (UTC)"
    )
    add.add_argument(
        "--to", dest="end", help="effective end, exclusive (UTC); otherwise ongoing"
    )
    add.add_argument(
        "--period", choices=("tournament", "league-day"), default="tournament"
    )
    add.add_argument("--notes", required=True)
    add.add_argument("--source", choices=SOURCES, default="user-entered")
    add.add_argument("--confidence", choices=CONFIDENCES, default="unknown")
    add.add_argument(
        "--provenance", help="JSON with source/confidence/notes overrides per field"
    )
    listing = sub.add_parser(
        "list", help="list frozen snapshots; legacy periods remain separate"
    )
    battle = sub.add_parser(
        "for-battle", help="find the snapshot for a battle in the archive"
    )
    battle.add_argument("timestamp")
    summary = sub.add_parser(
        "report", help="observed ranked defenses and trophies per snapshot"
    )
    summary.add_argument("--json", action="store_true")
    for command in (add, listing, battle, summary):
        command.add_argument("--history", type=Path, default=HISTORY)
    for command in (battle, summary):
        command.add_argument("--battles", type=Path, default=BATTLES)
    args = ap.parse_args()
    try:
        if args.command == "add":
            print(json.dumps(add_snapshot(args), indent=1))
            return
        history = read_history(args.history)
        if args.command == "list":
            entries = sorted(
                history.get("snapshots", []), key=lambda e: timestamp(e["from"])
            )
            print(json.dumps(entries, indent=1))
            return
        battles = read_battles(args.battles)
        if args.command == "for-battle":
            when = timestamp(args.timestamp)
            matches = [
                b
                for b in ranked_defenses(battles)
                if timestamp(b["battleTimestamp"]) == when
            ]
            if not matches:
                raise ValueError(
                    f"No ranked defense at {args.timestamp} in {args.battles}"
                )
            entry = snapshot_for_battle(history, args.timestamp)
            print(
                json.dumps({"battleTimestamp": utc(when), "snapshot": entry}, indent=1)
            )
            if entry is None:
                print(
                    "WARNING: no frozen snapshot covers this defense; today's levels would be a fallback.",
                    file=sys.stderr,
                )
            return
        rows, uncovered = report(history, battles)
        if args.json:
            print(
                json.dumps(
                    {"snapshots": rows, "uncovered_defenses": uncovered}, indent=1
                )
            )
            return
        for row in rows:
            mean = row["mean_defender_trophies"]
            interval = row["interval_95"]
            mean_text = f"{mean:.2f}" if mean is not None else "n/a"
            ci_text = (
                f"[{interval[0]:.2f}, {interval[1]:.2f}]"
                if interval
                else "n/a (fewer than 2 defenses)"
            )
            print(
                f"{row['id']}  n={row['ranked_defenses']}  mean={mean_text}  95% CI={ci_text}"
            )
        print(f"Uncovered ranked defenses: {uncovered} (excluded; no frozen snapshot)")
        print(
            "95% CI: mean +/- 1.96 sample SD/sqrt(n), clipped to [0, 40]; assumes independent defenses."
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        ap.error(str(error))


if __name__ == "__main__":
    main()
