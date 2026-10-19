"""Verify the game-data values Codex found for missing numbers
(output/checks/numbers/*.md) against the downloaded game data tables
(data/gamecsv/v18.200.9, from github.com/Enjoyop2/Clash-of-Clans-data-assets
at commit 26587c9, 2026-08-24).

Each table row cites fields like `Super Miner.Speed=400`. A row is verified
when every cited field holds exactly that value in some level row of that
entity in any table. Writes output/checks/numbers/verified.md.

Usage: python tools/baselab/verify_numbers.py
"""

from __future__ import annotations

import csv
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV_DIR = ROOT / "data" / "gamecsv" / "v18.200.9"


def load_tables():
    """entity name -> list of row dicts (level rows inherit the name)."""
    ents: dict = {}
    for f in CSV_DIR.glob("*.csv"):
        with open(f, encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(csv.reader(fh))
        if len(rows) < 3:
            continue
        head = rows[0]
        name = None
        for r in rows[2:]:  # row 1 holds the column types
            if r and r[0].strip():
                name = r[0].strip()
            if name is None:
                continue
            ents.setdefault(name, []).append({h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(head)})
    return ents


CITE = re.compile(r"`([^`=]+?)\.([A-Za-z0-9_]+)=([^`]+)`")


def main():
    ents = load_tables()
    out = ["# Missing numbers: verification against game data", "",
           "Source: data/gamecsv/v18.200.9 (Enjoyop2/Clash-of-Clans-data-assets, 26587c9, 2026-08-24).", "",
           "| id | parameter | value | cited fields | result |", "|---|---|---|---|---|"]
    tally = {"verified": 0, "mismatch": 0, "not in tables": 0, "no field cited": 0}
    for f in sorted(glob.glob(str(ROOT / "output" / "checks" / "numbers" / "*.md"))):
        if f.endswith("verified.md"):
            continue
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or "game-data" not in line:
                continue
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) < 6 or cols[0].startswith("id"):
                continue
            cites = CITE.findall(" ".join(cols[3:5]))
            if not cites:
                res = "no field cited"
            else:
                res = "verified"
                for ent, field, val in cites:
                    rows = ents.get(ent.strip())
                    if not rows:
                        res = "not in tables"
                        break
                    vals = {r.get(field, None) for r in rows}
                    if val.strip() not in vals:
                        res = "mismatch" if any(v not in (None, "") for v in vals) else "not in tables"
                        break
            tally[res] += 1
            fields = "; ".join(f"{e}.{k}={v}" for e, k, v in cites)
            out.append(f"| {cols[0]} | {cols[1]} | {cols[2]} | {fields} | {res} |")
    Path(ROOT / "output" / "checks" / "numbers" / "verified.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(tally)


if __name__ == "__main__":
    main()
