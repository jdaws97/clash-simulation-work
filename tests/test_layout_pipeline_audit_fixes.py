"""Three bounded audit controls; no whole-village simulation retries."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from clashlab.attack_spell_rules import RULES, SCOPE
from clashlab.catalog import Catalog
from clashlab.common import InputError, read_json, write_json
from clashlab.crafted_selection import selection_projection
from clashlab.higher_town_halls import synthetic_layout
from clashlab.layout_battle_bridge import build_layout_scene
from clashlab.layout_evaluation import (
    candidate_layout_sha256,
    content_sha,
    summarize_cases,
    validate_case,
)
from clashlab.layout_generation import ORIGIN, select_generated_station
from clashlab.layout_inventory import inspect_inventory, selected_inventory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_layout_ensemble as runner


class LayoutPipelineAuditFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")
        cls.craft = read_json(
            ROOT / "data/battle-policies/layout-search-crafted-experimental.json"
        )["variants"]["cake-a-pult"]

    def selected(self, th):
        layout = synthetic_layout(self.catalog, th)
        layout["generation_origin"] = ORIGIN
        return select_generated_station(
            layout, self.catalog, selection_projection(self.craft["parameters"])
        )

    def test_frozen_parent_identities_survive_worker_and_later_input_changes(self):
        for mutation in (
            "none",
            "own_bundle",
            "later_bundle",
            "manifest",
            "worker_engine",
        ):
            with self.subTest(mutation=mutation), TemporaryDirectory() as directory:
                root = Path(directory)
                fixtures = []
                for index in range(2):
                    case = {
                        "id": str(index),
                        "candidate_id": "candidate",
                        "candidate_layout_sha256": "a" * 64,
                        "mode": "ranked",
                        "attacker_town_hall": 16,
                        "defender_town_hall": 16,
                        "split": "search",
                    }
                    value = {"case": case, "audit_payload": "parent-read-original"}
                    fixtures.append(value)
                    write_json(root / f"{index}.json", value)
                original_digests = [content_sha(v) for v in fixtures]
                manifest = root / "manifest.json"
                write_json(
                    manifest,
                    {
                        "operation": "compile",
                        "timeout_seconds": 1,
                        "cases": [{"bundle": f"{i}.json"} for i in range(2)],
                    },
                )
                manifest_before = manifest.read_bytes()
                called = []

                def controlled_worker(argv, **kwargs):
                    path = Path(argv[argv.index("--worker") + 1])
                    destination = Path(argv[argv.index("--output") + 1])
                    called.append(path.name)
                    if len(called) == 1:
                        if mutation in {"own_bundle", "later_bundle"}:
                            changed = (
                                path if mutation == "own_bundle" else root / "1.json"
                            )
                            value = read_json(changed)
                            value["audit_payload"] = "worker-read-replacement"
                            write_json(changed, value)
                        elif mutation == "manifest":
                            value = read_json(manifest)
                            value["audit_change"] = True
                            write_json(manifest, value)
                    value = read_json(path)
                    write_json(
                        destination,
                        {
                            "case": value["case"],
                            "input_sha256": content_sha(value),
                            "engine_data_sha256": (
                                "forged"
                                if mutation == "worker_engine"
                                else "frozen-engine"
                            ),
                            "status": "compiled_no_outcome",
                            "outcome": None,
                            "completion_proven": False,
                        },
                    )
                    return SimpleNamespace(returncode=0)

                with (
                    patch.object(runner, "fingerprint", return_value="frozen-engine"),
                    patch.object(
                        runner.subprocess, "run", side_effect=controlled_worker
                    ),
                ):
                    runner.run(manifest, root / "output")
                receipts = [
                    read_json(root / f"output/case-{i:03d}.json") for i in range(2)
                ]
                self.assertEqual(
                    [r["input_sha256"] for r in receipts], original_digests
                )
                self.assertTrue(all(r["outcome"] is None for r in receipts))
                if mutation == "none":
                    self.assertEqual(
                        [r["status"] for r in receipts], ["compiled_no_outcome"] * 2
                    )
                else:
                    self.assertTrue(any(r["status"] == "error" for r in receipts))
                if mutation in {"later_bundle", "manifest"}:
                    self.assertEqual(called, ["0.json"])
                if mutation == "manifest":
                    self.assertEqual(
                        read_json(root / "output/summary.json")["manifest_sha256"],
                        sha256(manifest_before).hexdigest(),
                    )

    def test_case_labels_and_canonical_geometry_cannot_diverge_or_pool(self):
        layout = self.selected(18)
        layout["candidate_id"] = "candidate"
        case = {
            "id": "case",
            "candidate_id": "candidate",
            "candidate_layout_sha256": candidate_layout_sha256(layout),
            "mode": "ranked",
            "attacker_town_hall": 16,
            "defender_town_hall": 18,
            "split": "search",
            "family": "air",
            "entry_policy": "west",
            "ability_policy": "scheduled",
        }
        bundle = {
            "case": case,
            "layout": layout,
            "account": {"town_hall": 16, "effective_mode": "ranked"},
            "specification": {
                "id": "case",
                "battle_modifier_policy": {"profile_id": "legend_i"},
                "entity_scene": {"effects": []},
            },
            "deployment_policy": {
                "source": "synthetic-control",
                "state": "initial_hidden_teslas",
                "rim": "one_tile_square",
                "hero_banners_block": True,
            },
        }
        validate_case(bundle, self.catalog)
        mislabeled = deepcopy(bundle)
        mislabeled["case"]["candidate_id"] = "other"
        with self.assertRaisesRegex(InputError, "candidate label"):
            validate_case(mislabeled, self.catalog)
        changed = deepcopy(bundle)
        changed["layout"]["buildings"][0]["x"] += 1
        with self.assertRaisesRegex(InputError, "canonical candidate content"):
            validate_case(changed, self.catalog)
        conflicting = {**case, "id": "second", "candidate_layout_sha256": "b" * 64}
        with self.assertRaisesRegex(InputError, "different canonical"):
            summarize_cases([case, conflicting], [])

    def test_partial_th17_merge_selection_preserves_both_restored_defenders(self):
        layout = self.selected(17)
        policies = read_json(ROOT / "data/battle-policies/development-th16.json")
        policies["higher_town_halls"] = read_json(
            ROOT / "data/battle-policies/experimental-higher-th.json"
        )
        before = deepcopy(layout)
        control = build_layout_scene(
            layout, self.catalog, policies, self.craft, SCOPE, RULES
        )
        partial = deepcopy(layout)
        gear = next(b for b in partial["buildings"] if b["id"] == "multi-gear-tower")
        self.assertEqual((gear["x"], gear["y"]), (3, 17))
        partial["buildings"].remove(gear)
        for name, (x, y) in (("cannon", (3, 17)), ("archer-tower", (15, 32))):
            partial["buildings"].append(
                {
                    "instance": name + "-audit-restored",
                    "id": name,
                    "level": 21,
                    "x": x,
                    "y": y,
                    "mode": "normal",
                    "counts_for_destruction": True,
                }
            )
        partial["inventory_selection"]["merges"]["multi-gear-tower"] = 0
        partial["inventory"] = selected_inventory(
            self.catalog,
            17,
            partial["inventory_selection"]["merges"],
            partial["inventory_selection"]["crafted"],
        )
        self.assertEqual(
            inspect_inventory(partial, self.catalog, partial["inventory_selection"])[
                "building_count"
            ],
            471,
        )
        scene = build_layout_scene(
            partial, self.catalog, policies, self.craft, SCOPE, RULES
        )
        actors = {a["id"]: a for a in scene["entities"]}
        self.assertNotIn(gear["instance"], actors)
        self.assertEqual(actors["cannon-audit-restored"]["town_hall"], 17)
        self.assertEqual(actors["archer-tower-audit-restored"]["level"], 21)
        self.assertEqual(scene["traps"], control["traps"])
        self.assertTrue(any(t["entity"] == "giga-bomb" for t in scene["traps"]))
        self.assertEqual(layout, before)


if __name__ == "__main__":
    unittest.main()
