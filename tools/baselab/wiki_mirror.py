"""Mirror the Clash of Clans Fandom wiki pages the simulator relies on.

Content is CC-BY-SA (clashofclans.fandom.com). Pages are saved verbatim under
data/wiki/pages/ (wikitext + rendered HTML) with retrieval metadata, then
`wiki_tables.py` parses their tables into structured JSON.

Usage:
    python tools/baselab/wiki_mirror.py categories   # list candidate categories
    python tools/baselab/wiki_mirror.py fetch        # mirror all pages (resumable)
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "wiki"
API = "https://clashofclans.fandom.com/api.php"
UA = "clash-lab base research (personal, rate-limited)"

CATEGORIES = [
    "Home Village",
    "Troops",
    "Elixir Troops",
    "Dark Elixir Troops",
    "Super Troops",
    "Heroes",
    "Hero Equipment",
    "Pets",
    "Spells",
    "Elixir Spells",
    "Dark Elixir Spells",
    "Siege Machines",
    "Defensive Buildings",
    "Defenses",
    "Traps",
    "Guardians",
    "Town Hall",
    "Mechanics",
    "Game Mechanics",
    "Gameplay",
    "Battle",
    "Clan Castle",
    "Crafted Defenses",
]
EXTRA_PAGES = [
    "Ranked Battles",
    "Battle",
    "Walls/Home Village",
    "Clan Castle/Home Village",
    "Town Hall/Home Village",
    "Hero Hall",
    "Hero Banner",
    "Builder's Hut/Home Village",
    "Battle Modifiers",
    "Supercharge",
    "Building Merging",
    "Troop Targeting",
    "Pathfinding",
    "Destruction",
    "Stars",
]
# Builder Base / Clan Capital pages are out of scope
SKIP = re.compile(r"/(Builder Base|Clan Capital)$|Builder Base|Clan Capital|Capital|Gallery|Skins|Scenery|Achievements", re.I)


def api(params: dict) -> dict:
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            time.sleep(2 + 3 * attempt)
            err = e
    raise RuntimeError(f"API failed for {params}: {err}")


def category_members(cat: str) -> list[str]:
    titles = []
    cont = {}
    while True:
        data = api({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{cat}", "cmlimit": 500, **cont})
        titles += [m["title"] for m in data.get("query", {}).get("categorymembers", []) if m["ns"] == 0]
        if "continue" not in data:
            break
        cont = {"cmcontinue": data["continue"]["cmcontinue"]}
        time.sleep(0.3)
    return titles


def safe(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")


def fetch_page(title: str) -> dict:
    data = api({"action": "parse", "page": title, "prop": "wikitext|text|revid|categories", "redirects": 1})
    if "error" in data:
        return {"title": title, "error": data["error"]}
    p = data["parse"]
    return {
        "title": p["title"],
        "requested": title,
        "revid": p.get("revid"),
        "categories": [c["*"] for c in p.get("categories", [])],
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"https://clashofclans.fandom.com/wiki/{urllib.parse.quote(p['title'].replace(' ', '_'))}",
        "license": "CC-BY-SA 3.0 (Clash of Clans Wiki contributors)",
        "wikitext": p["wikitext"]["*"],
        "html": p["text"]["*"],
    }


def main(cmd: str):
    OUT.mkdir(parents=True, exist_ok=True)
    pages_dir = OUT / "pages"
    pages_dir.mkdir(exist_ok=True)
    if cmd == "categories":
        for cat in CATEGORIES:
            print(cat, len(category_members(cat)))
        return
    titles: set[str] = set(EXTRA_PAGES)
    for cat in CATEGORIES:
        try:
            members = category_members(cat)
        except RuntimeError:
            members = []
        titles.update(m for m in members if not SKIP.search(m))
        time.sleep(0.3)
    titles = sorted(titles)
    (OUT / "index.json").write_text(json.dumps({"titles": titles, "categories": CATEGORIES}, indent=1), encoding="utf-8")
    print(f"{len(titles)} pages to mirror", flush=True)
    done = 0
    for title in titles:
        path = pages_dir / f"{safe(title)}.json"
        if path.exists():
            continue
        try:
            page = fetch_page(title)
        except RuntimeError as e:
            print("FAILED", title, e, flush=True)
            continue
        path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        done += 1
        if done % 25 == 0:
            print(f"  {done} fetched", flush=True)
        time.sleep(0.35)
    print("done", done)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fetch")
