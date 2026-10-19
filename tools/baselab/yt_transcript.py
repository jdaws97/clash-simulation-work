"""Fetch a YouTube video's caption transcript (no video download, no API key).

Uses YouTube's player API with the Android client, which returns caption
track URLs that work without the web player's token (checked 2026-10-18:
the web watch page's track URLs return 404). Prefers English captions,
human-made over auto-generated.

Output: output/sources/transcripts/<id>.json with title, channel, date,
description and [[seconds, text], ...] lines.

Usage: python tools/baselab/yt_transcript.py VIDEO_ID [VIDEO_ID ...]
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "sources" / "transcripts"
UA = "com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip"


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_timedtext(xml: str) -> list:
    """format-3 timedtext: <p t="ms"> with words in <s> or direct text."""
    root = ET.fromstring(xml)
    out = []
    for p in root.iter("p"):
        words = "".join((s.text or "") for s in p.iter("s")) or (p.text or "")
        words = re.sub(r"\s+", " ", words).strip()
        if words:
            out.append([round(int(p.get("t", "0")) / 1000.0, 1), words])
    return out


def fetch(video_id: str) -> dict:
    d = _post("https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
              {"context": {"client": {"clientName": "ANDROID", "clientVersion": "20.10.38", "hl": "en"}}, "videoId": video_id})
    vd = d.get("videoDetails", {})
    tracks = d.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    en = [t for t in tracks if t.get("languageCode", "").startswith("en")]
    en.sort(key=lambda t: t.get("kind") == "asr")  # human captions first
    rec = {"id": video_id, "title": vd.get("title"), "channel": vd.get("author"), "length_s": int(vd.get("lengthSeconds") or 0),
           "description": vd.get("shortDescription", ""), "status": d.get("playabilityStatus", {}).get("status"),
           "caption_kind": None, "lines": []}
    if en:
        rec["caption_kind"] = en[0].get("kind") or "manual"
        rec["lines"] = parse_timedtext(_get(en[0]["baseUrl"]))
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for vid in sys.argv[1:]:
        try:
            rec = fetch(vid)
        except Exception as e:  # network or format change: report and go on
            print(f"{vid}: FAILED {e}")
            continue
        (OUT / f"{vid}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"{vid}: {rec['status']} '{rec['title']}' by {rec['channel']}, {len(rec['lines'])} lines ({rec['caption_kind']})")
        time.sleep(1.5)  # be gentle


if __name__ == "__main__":
    main()
