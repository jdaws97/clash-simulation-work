"""Create a local comparison report from whitelisted memory observations."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.layout_import import (
    available_layout_slots,
    preview_layout,
    resolve_layout_objects,
    select_home_observations,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--level-offset", type=int, required=True)
    parser.add_argument("--coordinate-offset", type=int, required=True)
    parser.add_argument("--board-size", type=int, required=True)
    arguments = parser.parse_args()
    if not 1 <= arguments.board_size <= 100:
        parser.error("Board size must be between 1 and 100")
    observations = [
        json.loads(path.read_text(encoding="utf-8")) for path in arguments.observations
    ]
    process_keys = {
        (item["process_id"], item["process_start_time_utc"]) for item in observations
    }
    if len(process_keys) != 1:
        parser.error("Do not combine observations from different process lifetimes")
    catalog = Catalog.load(ROOT / "data")
    candidates = [
        candidate for item in observations for candidate in item["candidates"]
    ]
    home_candidates = select_home_observations(candidates, catalog)
    # Numeric object IDs are reused between home and builder villages. Scope by
    # the known data namespace before reconciling identities or coordinates.
    objects = resolve_layout_objects(home_candidates)
    inventory = json.loads(
        (ROOT / "profiles/target-max-th16-inventory.json").read_text(encoding="utf-8")
    )["inventory"]
    transform = {
        "level_offset": arguments.level_offset,
        "coordinate_offset": arguments.coordinate_offset,
        "board_size": arguments.board_size,
    }
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "LAYOUT_COMPARISON_ONLY_NOT_BATTLE_INPUT",
        "observations_at_utc": [item["inspected_at_utc"] for item in observations],
        "unique_object_ids": len(objects),
        "excluded_unmapped_or_other_village_observations": len(candidates)
        - len(home_candidates),
        "objects_with_field_conflicts": sum(
            bool(item["conflicts"]) for item in objects
        ),
        "process_writes": False,
        "raw_memory_saved": False,
        "notes": [
            "Memory can contain stale copies; agreement does not prove freshness or ownership.",
            "Slot names are raw keys; this report does not identify the active war or ranked slot.",
            "Level and coordinate offsets are explicit hypotheses; catalog footprints are unverified.",
            "Missing records are never filled from another layout or from assumed symmetry.",
        ],
        "layouts": [
            preview_layout(objects, catalog, inventory, slot, transform)
            for slot in available_layout_slots(objects)
        ],
    }
    arguments.output.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, ensure_ascii=True, indent=2)
    (arguments.output / "memory-layout-preview.json").write_text(
        encoded + "\n", encoding="utf-8"
    )
    template = (ROOT / "tools/layout_preview.html").read_text(encoding="utf-8")
    safe_json = (
        encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    (arguments.output / "memory-layout-preview.html").write_text(
        template.replace("__LAYOUT_DATA__", safe_json), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "objects": len(objects),
                "conflicting_objects": report["objects_with_field_conflicts"],
                "layouts": [
                    {
                        "slot": layout["slot"],
                        "records": len(layout["records"]),
                        "missing": layout["missing_inventory"],
                        "overlaps": len(layout["catalog_footprint_overlaps"]),
                        "outside": len(layout["out_of_bounds"]),
                    }
                    for layout in report["layouts"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
