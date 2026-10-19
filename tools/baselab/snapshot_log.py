"""Append the user's live battle log to a growing archive (the API only
keeps ~50 recent battles). Read-only public data, no API key.

Each battle is stored once (keyed by timestamp, opponent and side) with the
fetch date, in data/live/battles.jsonl. tools/baselab/replay_log.py reads
the archive like a battle log file.

Usage: python tools/baselab/snapshot_log.py [--tag #PLAYERTAG]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROXY = "https://proxy.clashk.ing/v1/players/"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "clash-lab snapshot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="#PLAYERTAG")
    args = ap.parse_args()
    tag = urllib.parse.quote(args.tag, safe="")
    log = fetch(PROXY + tag + "/battlelog")
    player = fetch(PROXY + tag)
    out_dir = ROOT / "data" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    arch = out_dir / "battles.jsonl"
    seen = set()
    if arch.exists():
        for line in arch.read_text(encoding="utf-8").splitlines():
            b = json.loads(line)
            seen.add((b["battleTimestamp"], b["opponentPlayerTag"], b["attack"]))
    today = dt.date.today().isoformat()
    league = (player.get("leagueTier") or {}).get("name")
    added = 0
    with arch.open("a", encoding="utf-8") as f:
        for b in log.get("items", []):
            key = (b["battleTimestamp"], b["opponentPlayerTag"], b["attack"])
            if key in seen:
                continue
            b["fetched"] = today
            b["player_league"] = league
            b["player_trophies"] = player.get("trophies")
            f.write(json.dumps(b) + "\n")
            seen.add(key)
            added += 1
    (out_dir / "player-latest.json").write_text(json.dumps(player, indent=1), encoding="utf-8")
    total = len(seen)
    print(f"{today}: added {added} battles, archive {total}, league {league}, trophies {player.get('trophies')}")


if __name__ == "__main__":
    main()
