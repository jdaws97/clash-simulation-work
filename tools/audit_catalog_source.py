"""Write the independent extracted-statistics comparison without changing data."""

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.common import read_json, write_json
from clashlab.source_audit import audit_extracted_source


def main():
    report = audit_extracted_source(
        Catalog.load(ROOT / "data"),
        read_json(ROOT / "data/clashking-static-data.json"),
        read_json(ROOT / "data/clashking-static-source.json"),
    )
    output = ROOT / "reports/source-audit.json"
    write_json(output, report)
    print(
        json.dumps(
            {
                "output": str(output),
                "comparisons": report["mapped_comparisons"],
                "differences": len(report["differences"]),
                "differences_by_entity": dict(
                    Counter(row["entity"] for row in report["differences"])
                ),
                "unmatched": report["unmatched_catalog_entities"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
