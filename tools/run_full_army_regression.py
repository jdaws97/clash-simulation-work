"""Bounded synthetic lifecycle benchmark; no calibration or recommendation claims."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.common import read_json
from clashlab.development_armies import benchmark_army, build_army_scene
from clashlab.development_village import termination_policy
from clashlab.full_battle import simulate_full_battle
from clashlab.planning import planning_account
from clashlab.attack_spell_rules import RULES, SCOPE


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def inputs(family="air"):
    catalog = Catalog.load(ROOT / "data")
    owned = read_json(ROOT / "profiles/sample-th16.json")
    policies = read_json(ROOT / "data/battle-policies/development-full-army.json")
    base = read_json(ROOT / "data/battle-policies/development-th16.json")
    account = planning_account(
        owned,
        catalog,
        {
            "mode": "ranked",
            "recipient_level_rule": "unique_capacity_match",
            "super_troops": [],
        },
    )
    army = benchmark_army(account, policies, family)
    layout = {
        "id": "full-army-synthetic-distant-hall",
        "source": "synthetic-lifecycle-probe-not-game-calibration",
        "town_hall": 16,
        "width": 56,
        "height": 56,
        "inventory": {"town-hall": 1},
        "statistics_policy": {
            "kind": "conditional_pinned_snapshot",
            "snapshot_commit": catalog.snapshot["snapshotCommit"],
        },
        "buildings": [
            {
                "instance": "hall",
                "id": "town-hall",
                "level": 16,
                "x": 45,
                "y": 25,
                "mode": "gigaInferno",
                "counts_for_destruction": True,
            }
        ],
    }
    scene = build_army_scene(
        layout, catalog, base, policies, account, army, SCOPE, RULES, 16
    )
    scene["attack_spells"] = []
    scene["effects"].append(
        {
            "id": "release-synthetic-carrier",
            "kind": "siege_release",
            "time_seconds": 6,
            "target": "siege",
        }
    )
    specification = {
        "id": "full-army-synthetic-lifecycle-16s",
        "source": layout["source"],
        "time_limit_seconds": 16,
        "entity_scene": scene,
        "termination_policy": termination_policy(army, base),
    }
    return specification, account, army, layout, catalog


def run_twice():
    arguments = inputs()
    first = simulate_full_battle(*deepcopy(arguments))
    second = simulate_full_battle(*deepcopy(arguments))
    signatures = [
        fingerprint(
            {
                "outcome": result["outcome"],
                "trace": result["combat"]["trace"],
                "resource_use": result["resource_use"],
            }
        )
        for result in (first, second)
    ]
    if signatures[0] != signatures[1]:
        raise AssertionError("Identical synthetic inputs produced different results")
    code = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src/clashlab").glob("*.py"))
    }
    for path in (Path(__file__), ROOT / "tools/build_full_army_example.py"):
        code[str(path.relative_to(ROOT))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    input_files = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "profiles/sample-th16.json",
            "data/catalog.json",
            "data/secondary-raw.json",
            "data/battle-policies/development-full-army.json",
            "data/battle-policies/development-th16.json",
        )
    }
    return {
        "synthetic": True,
        "replay_calibrated": False,
        "full_game_prediction": False,
        "input_sha256": fingerprint(arguments[:4]),
        "code_sha256": fingerprint(code),
        "input_file_sha256": input_files,
        "outcome_event_resource_sha256": signatures[0],
        "identical_runs": 2,
        "outcome": first["outcome"],
        "event_count": len(first["combat"]["trace"]),
        "resource_use": first["resource_use"],
    }


if __name__ == "__main__":
    print(json.dumps(run_twice(), sort_keys=True, indent=2))
