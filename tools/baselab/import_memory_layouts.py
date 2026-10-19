"""Convert Codex's memory-recovered layout candidates into baselab layouts.

The source file (legacy Codex workspace) holds several candidate layout slots
read from game memory on 2026-10-04 with *unverified* coordinate/level
encodings. This tool converts every slot and renders it, so each candidate can
be checked by eye against the user's defense replay videos before use.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.layout import Layout, Placement, TrapPlacement  # noqa: E402
from baselab.render import render  # noqa: E402

ID_TO_KEY = {
    "town-hall": "th",
    "clan-castle": "cc",
    "air-defense": "ad",
    "air-sweeper": "sweeper",
    "archer-tower": "at",
    "multi-archer-tower": "mat",
    "cannon": "cannon",
    "ricochet-cannon": "ric",
    "bomb-tower": "bt",
    "builders-hut": "bh",
    "eagle-artillery": "eagle",
    "hidden-tesla": "tesla",
    "inferno-tower": "inferno",
    "monolith": "mono",
    "mortar": "mortar",
    "scattershot": "scatter",
    "spell-tower": "st",
    "wizard-tower": "wt",
    "x-bow": "xbow",
    "gold-mine": "gm",
    "elixir-collector": "ec",
    "dark-elixir-drill": "dd",
    "gold-storage": "gs",
    "elixir-storage": "es",
    "dark-elixir-storage": "ds",
    "army-camp": "camp",
    "barracks": "barracks",
    "dark-barracks": "dbarracks",
    "spell-factory": "sf",
    "dark-spell-factory": "dsf",
    "laboratory": "lab",
    "workshop": "workshop",
    "pet-house": "pethouse",
    "blacksmith": "smith",
    "hero-hall": "herohall",
    "helper-hut": "helper",
    "bobs-hut": "bob",
    "hero-banner": "banner",
}
TRAP_IDS = {
    "bomb": "bomb",
    "spring-trap": "spring",
    "giant-bomb": "giant",
    "air-bomb": "airbomb",
    "seeking-air-mine": "seeking",
    "skeleton-trap": "skeleton",
    "tornado-trap": "tornado",
}


def convert(slot: dict) -> tuple[Layout, list[str]]:
    lay = Layout(name=f"memory-{slot['slot']}")
    skipped = []
    for r in slot["records"]:
        rid, x, y = r["id"], r["x"], r["y"]
        if rid == "wall":
            lay.walls.add((x, y))
        elif rid in TRAP_IDS:
            lay.traps.append(TrapPlacement(TRAP_IDS[rid], x, y))
        elif rid in ID_TO_KEY:
            lay.buildings.append(Placement(ID_TO_KEY[rid], x, y))
        else:
            skipped.append(rid)
    return lay, skipped


def main(src: str, out_dir: str):
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for slot in data["layouts"]:
        lay, skipped = convert(slot)
        problems = lay.problems(require_full=False)
        lay.save(out / f"{lay.name}.json")
        render(lay, out / f"{lay.name}.png", title=f"{lay.name}  ({len(lay.buildings)} bldg, {len(lay.walls)} walls)")
        print(f"{lay.name:22} buildings={len(lay.buildings)} walls={len(lay.walls)} traps={len(lay.traps)} skipped={sorted(set(skipped))} problems={problems[:4]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
