"""Bounded, read-only search for complete, whitelisted game layout objects."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from inspect_layout_memory import ReadOnlyProcess
from clashlab.layout_records import find_layout_objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--maximum-mib", type=int, default=4096)
    parser.add_argument("--include-unmapped-building-ids", action="store_true")
    arguments = parser.parse_args()
    if not 1 <= arguments.maximum_mib <= 4096:
        parser.error("The read budget must be between 1 and 4096 MiB")
    scan = json.loads(arguments.scan.read_text(encoding="utf-8-sig"))
    record = next(
        item for item in scan["processes"] if item["process_id"] == arguments.process_id
    )
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    mapping = {
        entry["entity"]["dataId"]: entry["entity"]["id"]
        for entry in catalog["entries"]
        if entry["entity"].get("category")
        in {
            "defense",
            "trap",
            "army",
            "resource",
            "research",
            "other",
            "wall",
            "town-hall",
        }
        and "dataId" in entry["entity"]
    }
    process = ReadOnlyProcess(record)
    total = 0
    budget = arguments.maximum_mib * 2**20
    candidates = {}
    started = time.monotonic()
    failures = 0
    try:
        regions = sorted(process.regions(), key=lambda item: -item["size"])
        for region in regions:
            offset = 0
            while offset < region["size"] and total < budget:
                requested = min(2**20, region["size"] - offset, budget - total)
                address = region["address"] + offset
                data = process.read(address, requested)
                total += len(data)
                failures += len(data) != requested
                for match in find_layout_objects(
                    data, mapping, arguments.include_unmapped_building_ids
                ):
                    fields = match["fields"]
                    digest = hashlib.sha256(
                        json.dumps(fields, sort_keys=True).encode("ascii")
                    ).hexdigest()
                    if digest not in candidates:
                        candidates[digest] = {
                            "fields": fields,
                            "catalog_entity_candidate": mapping.get(fields["data"]),
                            "copies_seen": 0,
                            "sample_addresses": [],
                            "complete_copies_seen": 0,
                        }
                    candidate = candidates[digest]
                    candidate["copies_seen"] += 1
                    candidate["complete_copies_seen"] += match["object_complete"]
                    if len(candidate["sample_addresses"]) < 3:
                        candidate["sample_addresses"].append(
                            hex(address + match["offset"])
                        )
                # An overlap prevents missing an object crossing a read chunk.
                offset += max(requested - 8192, 1) if requested == 2**20 else requested
    finally:
        process.close()
    by_id = Counter(item["fields"]["id"] for item in candidates.values())
    report = {
        "status": "UNVERIFIED_LAYOUT_OBJECT_SET_NOT_AN_ACCOUNT_SNAPSHOT",
        "inspected_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_scan": str(arguments.scan.resolve()),
        "process_id": record["process_id"],
        "process_start_time_utc": record["process_start_time_utc"],
        "bytes_read": total,
        "incomplete_read_windows": failures,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "process_writes": False,
        "raw_memory_saved": False,
        "unique_object_ids": len(by_id),
        "ids_with_multiple_versions": sum(count > 1 for count in by_id.values()),
        "candidates": list(candidates.values()),
        "limitations": [
            "Complete object syntax does not establish account ownership or freshness.",
            "Conflicting copies are retained separately and must never be silently merged.",
            "Catalog dataId matching is a candidate identity, not live schema verification.",
            "Saved-layout slot meanings, level offsets and coordinate conventions require UI checks.",
            "Incomplete objects and inaccessible memory remain unobserved.",
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "candidates"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
