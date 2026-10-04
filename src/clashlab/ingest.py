"""Fetch immutable community snapshots and verify Git blob integrity."""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from .common import InputError, write_json


PROVIDER = "chiefpansancolt/clash-of-clans-data"


def git_blob_sha(content):
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def fetch_bytes(url):
    request = Request(url, headers={"User-Agent": "ClashLab-evidence-ingest/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def refresh_snapshot(commit, destination, workers):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise InputError("Supply an immutable full40-character Git commit")
    if destination.exists():
        raise InputError("Use a new snapshot filename; preserve the prior audit trail")
    if not isinstance(workers, int) or not 1 <= workers <= 16:
        raise InputError("Download workers must be explicitly between1and16")
    tree_url = f"https://api.github.com/repos/{PROVIDER}/git/trees/{commit}?recursive=1"
    tree = json.loads(fetch_bytes(tree_url))
    if tree.get("truncated"):
        raise InputError("GitHub tree is truncated; refuse an incomplete catalog")
    files = [
        item
        for item in tree["tree"]
        if item["type"] == "blob"
        and item["path"].startswith("data/home/")
        and item["path"].endswith(".json")
    ]
    if not files:
        raise InputError("Snapshot contains no home-village JSON data")

    def fetch_entity(item):
        path = item["path"]
        content = fetch_bytes(
            f"https://raw.githubusercontent.com/{PROVIDER}/{commit}/{path}"
        )
        if git_blob_sha(content) != item["sha"]:
            raise InputError(f"Blob integrity failed: {path}")
        entity = json.loads(content)
        return {
            "path": path,
            "blobSha": item["sha"],
            "source": f"https://github.com/{PROVIDER}/blob/{commit}/{path}",
            "modified": None,
            "verification": "unverified_snapshot",
            "entity": entity,
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        entries = list(
            pool.map(fetch_entity, sorted(files, key=lambda item: item["path"]))
        )
    expanded = []
    for entry in entries:
        expanded.append(entry)
        nested = entry["entity"].get("superTroop")
        if not nested:
            continue
        super_entry = deepcopy(entry)
        super_entry["entity"] = deepcopy(nested)
        super_entry["entity"].update(
            {
                "base": "home",
                "category": "troop",
                "troopType": "super",
                "parentTroop": entry["entity"]["id"],
            }
        )
        expanded.append(super_entry)
    identifiers = [entry["entity"]["id"] for entry in expanded]
    if len(set(identifiers)) != len(identifiers):
        raise InputError("Refreshed snapshot contains duplicate identifiers")
    snapshot = {
        "schemaVersion": 1,
        "retrievedOn": datetime.now(timezone.utc).date().isoformat(),
        "snapshotCommit": commit,
        "provider": PROVIDER,
        "status": "UNVERIFIED_STATISTICS_NOT_A_GAME_ENGINE",
        "entries": expanded,
    }
    write_json(destination, snapshot)
    return {
        "destination": str(destination),
        "entities": len(expanded),
        "commit": commit,
    }
