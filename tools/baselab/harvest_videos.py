"""Harvest attack-strategy videos and their transcripts from YouTube (text
only: no video files, no API key).

For each army family, runs several search queries through YouTube's player
search API, keeps videos published within --max-age-days (from YouTube's
relative "N weeks ago" text, so approximate), and fetches English captions
with yt_transcript.fetch. Everything lands in output/sources/:

  videos.jsonl            one row per video found (id, title, channel, age, family, query)
  transcripts/<id>.json   title, channel, description, [[seconds, text], ...]

Usage: python tools/baselab/harvest_videos.py [--families root-rider thrower ...] [--pages 2] [--max-age-days 183]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "baselab"))

from yt_transcript import OUT as TRANSCRIPTS, fetch  # noqa: E402

SOURCES = ROOT / "output" / "sources"
QUERIES = {
    "root-rider": ["th16 root rider attack strategy", "th17 root rider attack strategy", "root rider valkyrie attack guide",
                   "rc charge root rider attack", "th18 root rider attack strategy"],
    "thrower": ["th16 thrower attack strategy", "th17 thrower attack strategy", "thrower healer attack guide", "th18 thrower attack"],
    "dragon": ["th16 dragon attack strategy", "th17 hydra attack strategy", "dragon rider dragon attack guide", "rc walk dragons"],
    "electro-dragon": ["electro dragon attack th17", "edrag spam attack th16", "electro dragon th18 attack strategy"],
    "super-bowler": ["super bowler smash attack th17", "super bowler attack strategy th16"],
    "yeti": ["super yeti attack th17", "yeti smash attack strategy th16"],
    "lavaloon": ["lavaloon attack th16", "lalo attack strategy th17"],
    "meteor-golem": ["meteor golem attack strategy"],
    "druid-ruin-witch": ["ruin witch attack strategy", "druid attack strategy th16"],
    "super-minion-air": ["super minion rocket balloon attack", "rocket balloon attack strategy th16"],
}
AGE = {"second": 1 / 86400, "minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30.4, "year": 365}


def age_days(text: str | None) -> float | None:
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)", text or "")
    return int(m.group(1)) * AGE[m.group(2)] if m else None


def search(query: str, pages: int):
    body = {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20250101.00.00", "hl": "en"}}, "query": query,
            "params": "EgIQAQ%3D%3D"}  # videos only
    out, token = [], None
    for _ in range(pages):
        b = dict(body)
        if token:
            b = {"context": body["context"], "continuation": token}
        req = urllib.request.Request("https://www.youtube.com/youtubei/v1/search?prettyPrint=false", data=json.dumps(b).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        token = None

        def walk(x):
            nonlocal token
            if isinstance(x, dict):
                if "videoRenderer" in x:
                    v = x["videoRenderer"]
                    out.append({"id": v.get("videoId"), "title": "".join(r.get("text", "") for r in v.get("title", {}).get("runs", [])),
                                "channel": (v.get("ownerText", {}).get("runs") or [{}])[0].get("text"),
                                "age": (v.get("publishedTimeText") or {}).get("simpleText"),
                                "length": (v.get("lengthText") or {}).get("simpleText")})
                if "continuationCommand" in x:
                    token = x["continuationCommand"].get("token")
                for y in x.values():
                    walk(y)
            elif isinstance(x, list):
                for y in x:
                    walk(y)

        walk(d)
        if not token:
            break
        time.sleep(1.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", nargs="*", default=list(QUERIES))
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--max-age-days", type=float, default=183)
    args = ap.parse_args()
    SOURCES.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    index = SOURCES / "videos.jsonl"
    known = {}
    if index.exists():
        for line in index.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            known[r["id"]] = r
    for fam in args.families:
        found = 0
        for q in QUERIES[fam]:
            try:
                rows = search(q, args.pages)
            except Exception as e:
                print(f"search failed '{q}': {e}", flush=True)
                continue
            for r in rows:
                a = age_days(r["age"])
                if not r["id"] or a is None or a > args.max_age_days:
                    continue
                if r["id"] in known:
                    known[r["id"]].setdefault("families", [])
                    if fam not in known[r["id"]]["families"]:
                        known[r["id"]]["families"].append(fam)
                    continue
                r.update(families=[fam], query=q, age_days=round(a, 1), harvested=time.strftime("%Y-%m-%d"))
                known[r["id"]] = r
                found += 1
            time.sleep(1.0)
        print(f"{fam}: {found} new videos", flush=True)
    index.write_text("".join(json.dumps(r) + "\n" for r in known.values()), encoding="utf-8")
    todo = [vid for vid in known if not (TRANSCRIPTS / f"{vid}.json").exists()]
    print(f"{len(known)} videos indexed, fetching {len(todo)} transcripts", flush=True)
    got = 0
    for vid in todo:
        try:
            rec = fetch(vid)
        except Exception as e:
            print(f"  {vid}: failed {e}", flush=True)
            continue
        (TRANSCRIPTS / f"{vid}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        got += bool(rec["lines"])
        time.sleep(1.5)
    print(f"transcripts with text: {got}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
