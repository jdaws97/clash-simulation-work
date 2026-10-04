"""Create a standalone replay from existing bound-battle results."""

import argparse
import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def pack_case(result, profile):
    scene = result["compiled"]["scene"]
    combat = result["combat"]
    events = []
    for event in combat["trace"]:
        kind = event.get("event")
        if kind in {
            "trap_trigger",
            "town_hall_activation",
            "death_effect_release",
            "garrison_released",
            "skeleton_trap_release",
            "tornado_trigger",
            "spell_tower_launch",
        }:
            events.append(
                {
                    "time_seconds": event["time_seconds"],
                    "label": kind.replace("_", " "),
                }
            )
    for actor_id, time in result["validation"]["planned_deployments"].items():
        if time <= result["outcome"]["elapsed_seconds"]:
            events.append({"time_seconds": time, "label": f"Deploy {actor_id}"})
    for actor in combat["actors"].values():
        if actor["counts_for_destruction"] and actor["death_time"] is not None:
            events.append(
                {
                    "time_seconds": actor["death_time"],
                    "label": f"Destroyed {actor['id']}",
                }
            )
    fields = []
    for effect in scene["effects"]:
        if effect["kind"] == "healing_field":
            fields.append(
                {
                    "kind": "healing",
                    "start": effect["time_seconds"],
                    "end": effect["time_seconds"]
                    + effect["first_pulse_delay_seconds"]
                    + effect["pulse_interval_seconds"] * (effect["pulse_count"] - 1),
                    **{key: effect["area"][key] for key in ("x", "y", "radius")},
                }
            )
        elif effect["kind"] == "area_freeze":
            fields.append(
                {
                    "kind": "freeze",
                    "start": effect["time_seconds"],
                    "end": effect["time_seconds"] + effect["duration_seconds"],
                    **{key: effect["area"][key] for key in ("x", "y", "radius")},
                }
            )
    for field in scene.get("buff_fields", []):
        fields.append(
            {
                "kind": "rage" if field["entity"] == "rage-spell" else "haste",
                "start": field["start_seconds"],
                "end": field["start_seconds"] + field["duration_seconds"],
                **{key: field["area"][key] for key in ("x", "y", "radius")},
            }
        )
    return {
        "profile": profile,
        "width": scene["width"],
        "height": scene["height"],
        "duration": result["outcome"]["elapsed_seconds"],
        "maximum_step_seconds": scene["maximum_step_seconds"],
        "ending_reason": result["outcome"]["end_reason"],
        "counted": result["outcome"]["counted_building_count"],
        "walls": sum(actor["kind"] == "wall" for actor in scene["actors"]),
        "traps": scene.get("traps", []),
        "army_used": result["validation"]["army"]["used"],
        "attacker_ids": list(result["validation"]["attacker_bindings"]),
        "actors": {
            actor["id"]: {
                **{
                    key: actor[key]
                    for key in ("kind", "team", "width", "height", "hitpoints")
                },
                "counted": actor["counts_for_destruction"],
                "entity": actor.get("entity_adapter", {}).get(
                    "entity", "summoned-unit"
                ),
            }
            for actor in scene["actors"]
        },
        "frames": [
            {
                "time_seconds": frame["time_seconds"],
                "actors": {
                    key: {
                        name: value
                        for name, value in state.items()
                        if name in {"x", "y", "hp", "active", "frozen_until", "builder"}
                    }
                    for key, state in frame["actors"].items()
                },
            }
            for frame in combat["frames"]
        ],
        "spells": result["resource_use"]["spell_slots"],
        "events": sorted(
            events, key=lambda item: (item["time_seconds"], item["label"])
        ),
        "fields": fields,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        choices=("bound-battle", "full-village", "full-army"),
        default="bound-battle",
    )
    arguments = parser.parse_args()
    destination = ROOT / "reports" / arguments.report
    cases = {}
    result_paths = sorted(destination.glob("*-result.json")) + sorted(
        destination.glob("*-result.json.gz")
    )
    for path in result_paths:
        identifier = path.name.removesuffix(".gz").removesuffix("-result.json")
        result = read_json(path)
        case = pack_case(result, identifier)
        case["label"] = identifier.replace("-", " ").replace("_", " ")
        case["input_file"] = f"{identifier}-input.json"
        case["result_file"] = path.name
        case["result_label"] = (
            "Complete result (compressed JSON)"
            if path.suffix == ".gz"
            else "Complete result JSON"
        )
        case["layout_file"] = "layout.json"
        case["army_file"] = "army.json"
        if arguments.report == "full-village":
            label = "war-cwl" if identifier.startswith("war-cwl-") else "ranked"
            case["layout_file"] = f"{label}-simulation-layout.json"
            draft = "War/CWL draft" if label == "war-cwl" else "Ranked draft"
            profile = "Legend I" if "legend_i" in identifier else "No modifier"
            crossover = (
                " crossover" if label == "war-cwl" and profile == "Legend I" else ""
            )
            case["label"] = f"{draft} · {profile}{crossover} · {case['duration']:g}s"
            case["label"] += f" · step {case['maximum_step_seconds']:g}"
            if "route-arrival" in identifier:
                case["label"] = "Arrival correction · " + case["label"]
            elif "range-entry" in identifier:
                case["label"] = "Range correction · " + case["label"]
            elif "defender-reachability" in identifier:
                case["label"] = "Reachability correction · " + case["label"]
            elif "integrated-v28" in identifier or "exhaustion" in identifier:
                case["label"] = "Force exhaustion · " + case["label"]
        elif arguments.report == "full-army":
            family = "Air army" if identifier.startswith("air-") else "Ground army"
            draft = "War/CWL draft" if "war-cwl" in identifier else "Ranked draft"
            profile = "Legend I" if "legend_i" in identifier else "No modifier"
            case["label"] = f"{family} · {draft} · {profile} · {case['duration']:.3f}s"
            case["label"] += f" · step {case['maximum_step_seconds']:g}"
            case["layout_file"] = f"{identifier}-layout.json"
            case["army_file"] = f"{identifier}-army.json"
            case["account_file"] = f"{identifier}-account.json"
        cases[identifier] = case
    if not cases:
        parser.error(
            "No completed simulation results were found in this report directory"
        )
    notice = (
        "A 320-space troop army and 11-space spell loadout face an underfilled TH16 "
        "inventory with 18 counted buildings. No attacking heroes, pets, siege or "
        "Clan Castle contents are selected."
    )
    if arguments.report == "full-village":
        notice = (
            "The 16-Dragon development army and 11-space spell loadout face the "
            "complete declared TH16 inventory: 467 layout objects, including 94 "
            "counted structures, 325 walls, 44 traps, four defending heroes and a "
            "50-space defending garrison. No attacking heroes, pets, siege or "
            "Clan Castle contents are selected. The padded simulation board "
            "uses an unverified deployment-margin hypothesis. Both draft layouts "
            "are tested under both profiles for comparison; actual war/CWL uses "
            "the unmodified profile."
        )
    elif arguments.report == "full-army":
        notice = (
            "Air and ground integration fixtures include a 320-space army, 11 "
            "spell spaces, four heroes with owned equipment, four pets, one siege "
            "machine, and 50+3 Clan Castle reinforcements. They face the saved "
            "467-object TH16 drafts. Potion levels and donated levels come from "
            "a saved planning account; equipment is not boosted. Selected "
            "loadouts and schedules are development candidates. Warden following, "
            "deployment geometry and several timing policies remain unverified."
        )
    metadata = {
        "notice": notice
        + " The model is uncalibrated; these results are not army or base recommendations.",
        "title": (
            "Complete TH16 inventory benchmark"
            if arguments.report in {"full-village", "full-army"}
            else "Connected army benchmark"
        ),
    }
    if arguments.report == "full-army":
        metadata["title"] = "Full-army integration benchmark"
    numerical_path = destination / "numerical-status.json"
    if numerical_path.exists():
        numerical = read_json(numerical_path)
        metadata["numerical_notice"] = numerical["summary"]
        metadata["default_case"] = numerical.get("default_case")
        metadata["numerical_comparison"] = numerical.get("trace_comparison")
    template = (ROOT / "tools/battle_replay.html").read_text(encoding="utf-8")
    encoded = json.dumps(
        {"cases": cases, "metadata": metadata}, separators=(",", ":")
    ).replace("<", "\\u003c")
    (destination / "index.html").write_text(
        template.replace("__REPLAY_DATA__", encoded), encoding="utf-8"
    )
    print(destination / "index.html")


if __name__ == "__main__":
    main()
