"""Build a reviewable digest of every mechanic the simulator models.

For each topic page it prints the infobox fields, the stat table columns with
the TH16/TH17/TH18-relevant rows, and the body sentences that describe
behaviour (targeting, splash, chaining, timings, special abilities). The digest
is what mechanics.py is reconciled against.

Usage: python tools/baselab/wiki_digest.py > docs/WIKI_DIGEST.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "data" / "wiki"

TOPICS = {
    "Defenses": [
        "Town Hall/Home Village", "Air Defense/Home Village", "Air Sweeper", "Archer Tower/Home Village",
        "Multi-Archer Tower", "Cannon/Home Village", "Ricochet Cannon", "Bomb Tower", "Builder's Hut/Home Village",
        "Eagle Artillery", "Hidden Tesla/Home Village", "Inferno Tower/Home Village", "Monolith", "Mortar/Home Village",
        "Scattershot", "Spell Tower", "Wizard Tower/Home Village", "X-Bow/Home Village", "Clan Castle/Home Village",
        "Walls/Home Village", "Firespitter", "Multi-Gear Tower", "Super Wizard Tower", "Revenge Tower",
    ],
    "Traps": ["Bomb/Home Village", "Giant Bomb", "Air Bomb", "Seeking Air Mine", "Spring Trap/Home Village", "Skeleton Trap", "Tornado Trap", "Giga Bomb"],
    "Troops": [
        "Barbarian/Home Village", "Archer/Home Village", "Giant/Home Village", "Wall Breaker/Home Village", "Balloon/Home Village",
        "Wizard/Home Village", "Healer/Home Village", "Dragon/Home Village", "P.E.K.K.A/Home Village", "Baby Dragon/Home Village",
        "Miner/Home Village", "Electro Dragon", "Yeti", "Dragon Rider", "Electro Titan", "Root Rider", "Thrower",
        "Minion/Home Village", "Hog Rider/Home Village", "Valkyrie/Home Village", "Golem/Home Village", "Witch/Home Village",
        "Lava Hound", "Bowler/Home Village", "Ice Golem", "Headhunter", "Apprentice Warden", "Druid", "Furnace",
        "Super Barbarian", "Super Wall Breaker", "Rocket Balloon", "Super Dragon", "Inferno Dragon", "Super Yeti",
        "Super Minion", "Super Bowler", "Super Valkyrie", "Ice Hound", "Meteor Golem", "Ruin Witch",
    ],
    "Heroes": ["Barbarian King/Home Village", "Archer Queen/Home Village", "Grand Warden/Home Village", "Royal Champion", "Minion Prince", "Dragon Duke"],
    "Spells": [
        "Lightning Spell", "Healing Spell", "Rage Spell", "Jump Spell", "Freeze Spell", "Clone Spell", "Invisibility Spell",
        "Recall Spell", "Revive Spell", "Totem Spell", "Poison Spell", "Earthquake Spell", "Haste Spell", "Skeleton Spell",
        "Bat Spell", "Overgrowth Spell", "Ice Block Spell", "Angry Spell",
    ],
    "Sieges": ["Wall Wrecker", "Battle Blimp", "Stone Slammer", "Siege Barracks", "Log Launcher", "Flame Flinger", "Battle Drill", "Troop Launcher", "Sky Wagon"],
}

KEYWORDS = re.compile(
    r"target|splash|chain|bounce|radius|range|tiles|second|seconds|wall|jump|ignore|immune|stun|freeze|slow|heal|"
    r"invisib|retarget|trigger|damage|hitpoint|% |percent|aura|summon|spawn|death|destroy|pierce|knock|push|"
    r"priority|preferred|favorite|nearest|closest",
    re.I,
)


def safe(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")


def load(title):
    for cand in (title, title.split("/")[0]):
        p = WIKI / "tables" / f"{safe(cand)}.json"
        t = WIKI / "text" / f"{safe(cand)}.txt"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")), t.read_text(encoding="utf-8")
    return None, None


def main():
    out = sys.stdout
    out.write("# Wiki digest for simulator mechanics\n\nGenerated from the local wiki mirror (CC-BY-SA, Clash of Clans Wiki).\n")
    for section, titles in TOPICS.items():
        out.write(f"\n\n# {section}\n")
        for title in titles:
            data, text = load(title)
            if data is None:
                out.write(f"\n## {title}\n(missing from mirror)\n")
                continue
            out.write(f"\n## {data['title']}  (rev {data['revid']})\n")
            for t in data["tables"]:
                if t["kind"] == "infobox":
                    f = t["fields"]
                    if any(k in f for k in ("Date", "Patch", "Capital Hall Level")):
                        continue
                    out.write("- info: " + "; ".join(f"{k}: {v}" for k, v in f.items())[:600] + "\n")
            for t in data["tables"]:
                if t["kind"] == "stats":
                    cols = t["columns"]
                    if cols[0].lower() == "town hall level":
                        continue
                    rows = t["rows"]
                    keep = rows[-4:] if len(rows) > 4 else rows
                    out.write("- stats: " + " | ".join(cols) + "\n")
                    for r in keep:
                        out.write("    " + " | ".join(r) + "\n")
            sentences = []
            for line in text.splitlines()[3:]:
                if line.startswith("##"):
                    if re.search(r"History|Gallery|Trivia|Patch|Skins|Audio|Video", line, re.I):
                        break
                    continue
                if KEYWORDS.search(line) and 20 < len(line) < 600:
                    sentences.append(line)
            for s in sentences[:18]:
                out.write(f"  * {s}\n")


if __name__ == "__main__":
    main()
