"""Unified entity registry: game-file stats merged with wiki attributes.

Every home-village troop, super troop, siege machine, spell, hero, pet, hero
equipment, trap, guardian and building gets one record:

    {
      "name", "kind", "source": {...},
      "attrs":  {...}   # parsed wiki infobox: range, speed, splash, targets...
      "levels": [...]   # per level: ClashKing stats merged with wiki columns
      "max_level": {"16": n, "17": n, "18": n},
      "notes":  [...]   # wiki sentences describing behaviour
    }

ClashKing (game files) is authoritative for numbers it has; wiki columns fill
everything else (ability values, death damage, freeze times, ...). Conflicts
between the two are recorded in record["conflicts"].

Build:  python -m baselab.registry   (writes data/registry.json)
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import gamedata

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "data" / "wiki"
OUT = ROOT / "data" / "registry.json"

SEASONAL_TROOPS = set()  # filled from ClashKing "is_seasonal"

# Sub-units summoned by troops, spells, equipment and pets (wiki subpages).
SUMMONS = {
    "Lava Pup": "Lava Hound/Lava Pup",
    "Golemite": "Golem/Golemite",
    "Yetimite": "Yeti/Yetimite",
    "Electromite": "Super Yeti/Electromite",
    "Big Boy": "Super Witch/Big Boy",
    "Ruin Knight": "Ruin Witch/Ruin Knight",
    "Firemite": "Furnace/Firemite",
    "Bear": "Druid/Bear",
    "Ice Pup": "Ice Hound/Ice Pup",
    "Meteormite": "Meteor Golem/Meteormite",
    "Frostmite": "Frosty/Frostmite",
    "Skeleton": "Witch/Skeleton",
    "Spell Skeleton": "Skeleton Spell/Skeleton",
    "Bat": "Bat Spell/Bat",
    "Snake": "Snake Bracelet/Snake",
    "Super Rider": "Super Hog Rider/Super Rider",
    "Super Hog": "Super Hog Rider/Super Hog",
    "Henchman": "Henchmen Puppet/Henchmen",
    "Lavaloon": "Lavaloon Puppet/Lavaloon",
    "Booger": "Sneezy/Booger",
    "Giant Giant": "Giant Giant",
}


def _safe(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")


def wiki_page(name: str):
    for cand in (f"{name}/Home Village", name):
        p = WIKI / "tables" / f"{_safe(cand)}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            text_path = WIKI / "text" / f"{_safe(cand)}.txt"
            text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
            return data, text
    return None, ""


NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def num(value: str):
    if value is None:
        return None
    m = NUM.search(str(value).replace("−", "-"))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_attrs(infoboxes: list[dict]) -> dict:
    """Normalise the wiki infobox fields we use."""
    a: dict = {}
    for box in infoboxes:
        for k, v in box.items():
            key = k.strip().lower()
            if key in ("date", "patch", "description", "captions", "sound effect"):
                continue
            a.setdefault("raw", {})[k] = v
            low = v.lower()
            if key == "preferred target" or key == "favorite target":
                a["preferred_target"] = v
            elif key in ("attack type", "damage type", "effect type"):
                a["attack_type"] = v
                m = re.search(r"([\d.]+)\s*tiles?\s*radius|splash\s*-?\s*([\d.]+)\s*tiles?|([\d.]+)\s*tile radius", low)
                if m:
                    a["splash_radius"] = float(next(g for g in m.groups() if g))
                if "ground only" in low:
                    a["hits"] = "ground"
                elif "air only" in low:
                    a["hits"] = "air"
                elif "ground & air" in low or "ground and air" in low:
                    a["hits"] = "both"
            elif key == "range":
                rng = re.findall(r"[\d.]+", v)
                if len(rng) >= 2 and "-" in v:
                    a["min_range"], a["range"] = float(rng[0]), float(rng[1])
                elif rng:
                    a["range"] = float(rng[0])
            elif key == "movement speed":
                n = num(v)
                if n is not None:
                    a["speed_display"] = n
            elif key in ("attack speed", "heal speed", "healing speed"):
                n = num(v)
                if n is not None:
                    a["attack_interval"] = n
            elif key == "housing space":
                a["housing"] = num(v)
            elif key in ("unit type targeted", "targets", "healing targets"):
                a["targets_text"] = v
            elif key in ("trigger radius", "activation radius"):
                a["trigger_radius"] = num(v)
            elif key in ("damage radius", "radius", "effect radius", "spell radius"):
                a.setdefault("radius", num(v))
            elif key == "death damage radius":
                a["death_radius"] = num(v)
            elif key == "number of targets":
                a["targets"] = num(v)
            elif key == "chain distance":
                a["chain_distance"] = num(v)
            elif key == "chain damage decay":
                a["chain_decay"] = num(v)
            elif key == "search radius":
                a["search_radius"] = num(v)
            elif key == "size":
                a["size"] = v
            elif key == "special ability":
                a["special_ability"] = v
            elif key in ("spell duration", "duration", "lifetime"):
                a.setdefault("duration", num(v))
            elif key == "hp decay per second" or key == "hitpoint decay per second":
                a["hp_decay"] = num(v)
    return a


def wiki_level_rows(tables: list[dict]) -> dict:
    """Merge every stats table keyed by its first column (Level / Charge)."""
    out: dict = {}
    for t in tables:
        if t.get("kind") != "stats":
            continue
        if t.get("heading") == "As Temporary Troop":
            # Wiki: Meteor Golem and Meteor Golem/Meteormite, the event-troop
            # table (levels by Town Hall) is a different unit; merging it gave
            # the troop levels 1-3 "Town Hall Level Required" 6-8 and fake
            # levels 4-13.
            continue
        cols = t["columns"]
        first = cols[0].lower()
        if first not in ("level", "charge", "charge level"):
            continue
        prefix = "charge:" if first.startswith("charge") else ""
        for row in t["rows"]:
            if not row:
                continue
            lvl = num(row[0])
            if lvl is None:
                continue
            key = f"{prefix}{int(lvl)}"
            entry = out.setdefault(key, {})
            for c, v in zip(cols[1:], row[1:]):
                if c and c not in entry:
                    entry[c] = v
    return out


def sentences(text: str, limit: int = 40) -> list[str]:
    keep = []
    kw = re.compile(
        r"target|splash|chain|radius|range|tiles|second|wall|jump|ignore|immune|stun|freeze|slow|heal|invisib|"
        r"retarget|trigger|death|spawn|summon|aura|push|pierce|priorit|nearest|closest|percent|%",
        re.I,
    )
    for line in text.splitlines():
        if line.startswith("## "):
            if re.search(r"History|Gallery|Trivia|Skins|Audio|Video|Appearance", line, re.I):
                break
            continue
        if kw.search(line) and 25 < len(line) < 700 and line not in keep:
            keep.append(line)
        if len(keep) >= limit:
            break
    return keep


def _ck_level(entry, kind):
    rows = []
    for lvl in entry.get("levels", []):
        r = {"level": lvl["level"], "required_townhall": lvl.get("required_townhall")}
        for k in ("hitpoints", "dps", "damage", "duration", "radius"):
            if k in lvl and lvl[k] is not None:
                r[k] = lvl[k]
        rows.append(r)
    return rows


def _max_levels(levels, kind):
    out = {}
    for th in (14, 15, 16, 17, 18):
        ok = [l["level"] for l in levels if (l.get("required_townhall") or 0) <= th]
        if kind == "building" and levels and levels[0].get("_th_offset"):
            ok = [l["level"] for l in levels if l["level"] <= th]
        out[str(th)] = max(ok) if ok else None
    return out


def build() -> dict:
    raw = gamedata.raw()
    records: dict = {}

    def add(name, kind, ck_entry, page=None):
        tables, text = wiki_page(page or name)
        rec = {
            "name": name,
            "kind": kind,
            "seasonal": bool(ck_entry.get("is_seasonal")) if ck_entry else False,
            "super": bool(ck_entry.get("super_troop")) if ck_entry else False,
            "source": {"clashking": bool(ck_entry), "wiki": tables["source"] if tables else None, "wiki_rev": tables["revid"] if tables else None},
        }
        ck_levels = _ck_level(ck_entry, kind) if ck_entry else []
        attrs = parse_attrs([t["fields"] for t in (tables or {}).get("tables", []) if t["kind"] == "infobox"])
        if ck_entry:
            for k_src, k_dst, scale in (
                ("movement_speed", "speed", 0.01),
                ("attack_range", "range_ck", 0.01),
                ("attack_speed", "attack_interval_ck", 0.001),
                ("housing_space", "housing_ck", 1),
                ("width", "width", 1),
                ("hitbox_width", "hitbox", 1),
                ("trigger_radius", "trigger_ck", 0.01),
                ("damage_radius", "damage_radius_ck", 0.01),
            ):
                if ck_entry.get(k_src) is not None:
                    attrs[k_dst] = ck_entry[k_src] * scale
            for flag in ("is_flying", "is_air_targeting", "is_ground_targeting", "air_trigger", "ground_trigger"):
                if flag in ck_entry:
                    attrs[flag] = bool(ck_entry[flag])
        wl = wiki_level_rows((tables or {}).get("tables", []))
        levels = []
        conflicts = []
        seen = set()
        for r in ck_levels:
            w = wl.get(str(r["level"]), {})
            merged = dict(r)
            merged["wiki"] = w
            hp_w = num(w.get("Hitpoints")) if w else None
            if hp_w is not None and r.get("hitpoints") and abs(hp_w - r["hitpoints"]) > 0.5:
                conflicts.append(f"L{r['level']} HP: game {r['hitpoints']} vs wiki {hp_w}")
            levels.append(merged)
            seen.add(str(r["level"]))
        for k, w in wl.items():
            if k not in seen:
                lv = num(k.split(":")[-1])
                levels.append({"level": k if k.startswith("charge") else int(lv), "wiki": w, "wiki_only": True})
        if not levels and tables:
            # single-level wiki units (summons): fold stat infoboxes into level 1
            flat = {}
            for t in tables.get("tables", []):
                if t["kind"] == "infobox":
                    flat.update(t["fields"])
            if any(k in flat for k in ("Hitpoints", "Damage per Second", "Damage per Attack")):
                levels.append({"level": 1, "wiki": flat, "wiki_only": True})
        rec["attrs"] = attrs
        rec["levels"] = levels
        rec["conflicts"] = conflicts
        rec["notes"] = sentences(text)
        rec["max_level"] = _max_levels([l for l in ck_levels], kind) if ck_levels else {}
        records[name] = rec

    sections = [("troops", "troop"), ("spells", "spell"), ("heroes", "hero"), ("pets", "pet"), ("equipment", "equipment"), ("traps", "trap"), ("guardians", "guardian")]
    for sec, kind in sections:
        for e in raw[sec]:
            if e.get("village", "home") != "home":
                continue
            k = kind
            if kind == "troop" and e.get("production_building") == "Workshop":
                k = "siege"
            elif kind == "troop" and e.get("super_troop"):
                k = "super_troop"
            add(e["name"], k, e)
    for e in raw["buildings"]:
        if e.get("village") != "home":
            continue
        add(e["name"], "building", e)
    for name, page in SUMMONS.items():
        add(name, "summon", None, page=page)
    # crafted defenses only exist on the wiki
    for t in sorted((WIKI / "tables").glob("*.json")):
        data = json.loads(t.read_text(encoding="utf-8"))
        title = data["title"]
        if title in records or "/" in title:
            continue
        cats = json.loads((WIKI / "pages" / t.name).read_text(encoding="utf-8")).get("categories", [])
        if any(c in ("Crafted_Defenses", "Crafted_Defense", "Crafted_Buildings") for c in cats) and "Defenses" in cats:
            add(title, "crafted_defense", None)
        elif any(c in ("Hero_Equipment", "Epic_Hero_Equipment", "Common_Hero_Equipment") for c in cats):
            # released after the ClashKing export (e.g. Portal Pendant, Oct 2026)
            add(title, "equipment", None)
    return records


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8"))


def level_row(name: str, level: int) -> dict:
    for row in load()[name]["levels"]:
        if row.get("level") == level:
            return row
    raise KeyError(f"{name} L{level}")


if __name__ == "__main__":
    recs = build()
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds: dict = {}
    for r in recs.values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("wrote", OUT, len(recs), "records", kinds)
    conflicts = {n: r["conflicts"] for n, r in recs.items() if r["conflicts"]}
    print("records with game/wiki conflicts:", len(conflicts))
    for n, c in list(conflicts.items())[:30]:
        print("  ", n, c[:3])
