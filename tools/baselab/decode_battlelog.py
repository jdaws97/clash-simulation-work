"""Decode army share codes from a Clash API battle log into readable armies."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab import gamedata  # noqa: E402

OFFSETS = {
    "troop": 4000000,
    "spell": 26000000,
    "hero": 28000000,
    "pet": 73000000,
    "equipment": 90000000,
}


def _names():
    raw = gamedata.raw()
    table = {}
    for section, kind in [("troops", "troop"), ("spells", "spell"), ("heroes", "hero"), ("pets", "pet"), ("equipment", "equipment")]:
        for entry in raw[section]:
            table[(kind, entry["_id"] - OFFSETS[kind])] = entry["name"]
    return table


NAMES = _names()


def name(kind, idx):
    return NAMES.get((kind, idx), f"{kind}#{idx}")


def decode(code: str) -> dict:
    sections = dict(re.findall(r"([hiuds])([^hiuds]*)", code))
    out = {}
    if "h" in sections:
        heroes = []
        for part in sections["h"].split("-"):
            # hero, then optional mode (the Grand Warden's "m1", e.g.
            # "2m1p2e4_34"), pet and equipment; the whole part must parse,
            # or pet and equipment after an unknown letter would be lost
            m = re.fullmatch(r"(\d+)(?:m(\d+))?(?:p(\d+))?(?:e([\d_]+))?", part)
            if not m:
                heroes.append({"hero": f"unparsed:{part}", "pet": None, "equipment": []})
                continue
            h, mode, p, e = m.groups()
            heroes.append(
                {
                    "hero": name("hero", int(h)),
                    "mode": int(mode) if mode else None,
                    "pet": name("pet", int(p)) if p else None,
                    "equipment": [name("equipment", int(x)) for x in e.split("_")] if e else [],
                }
            )
        out["heroes"] = heroes
    for key, label, kind in [("u", "troops", "troop"), ("s", "spells", "spell"), ("i", "cc_troops", "troop"), ("d", "cc_spells", "spell")]:
        if key in sections and sections[key]:
            items = []
            for part in sections[key].split("-"):
                n, idx = part.split("x")
                items.append((int(n), name(kind, int(idx))))
            out[label] = items
    return out


def main(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for b in data["items"]:
        if b.get("battleType") != "ranked":
            continue
        army = decode(b.get("armyShareCode", ""))
        side = "ATTACK" if b["attack"] else "DEFENSE"
        print(f"{side} vs TH{b['opponentTownHallLevel']}  {b['stars']}* {b['destructionPercentage']}%  {b['battleTime']}s  {b['battleTimestamp'][:8]}")
        troops = ", ".join(f"{n} {t}" for n, t in army.get("troops", []))
        spells = ", ".join(f"{n} {t}" for n, t in army.get("spells", []))
        cc = ", ".join(f"{n} {t}" for n, t in army.get("cc_troops", []) + army.get("cc_spells", []))
        heroes = "; ".join(
            f"{h['hero']} ({', '.join(h['equipment'])}{', ' + h['pet'] if h['pet'] else ''})" for h in army.get("heroes", [])
        )
        print(f"   troops: {troops}\n   spells: {spells}\n   cc: {cc}\n   heroes: {heroes}")


if __name__ == "__main__":
    main(sys.argv[1])
