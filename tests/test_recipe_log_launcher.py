"""A rolling log remains released offense after its paid carrier is spent."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from clashlab.catalog import Catalog
from clashlab.full_battle import simulate_full_battle
from test_siege_machines import siege_instance, release_command
from test_siege_integration import reinforcement_battle

ROOT = Path(__file__).resolve().parents[1]


class RecipeLogLauncherTests(unittest.TestCase):
    def test_released_log_survives_manual_release_and_payload_spends_once(self):
        catalog = Catalog.load(ROOT / "data")
        launcher = siege_instance()
        launcher["entity"] = "log-launcher"
        launcher["siege_parameters"] = json.loads(
            (ROOT / "data/battle-policies/recipe-log-launcher.json").read_text()
        )
        launcher["siege_parameters"]["range_tiles"] = 20
        launcher["siege_parameters"]["behavior"]["speed_tiles_per_second"] = 20
        inputs = reinforcement_battle(catalog, launcher, duration=2)
        inputs[0]["entity_scene"]["effects"] = [release_command(time=0.1)]
        result = simulate_full_battle(*inputs, catalog)
        trace = result["combat"]["trace"]
        releases = [
            event for event in trace if event.get("event") == "siege_terminated"
        ]
        hits = [
            event for event in trace if event.get("event") == "extended_siege_impact"
        ]
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["reason"], "manual_release")
        self.assertTrue(hits)
        self.assertTrue(all(event["time_seconds"] > 0.1 for event in hits))
        self.assertEqual(
            result["resource_use"]["deployed_attacker_ids"], ["payload", "siege"]
        )
        self.assertTrue(result["resource_use"]["clan_castle_delivery"]["spent"])
        self.assertEqual(
            sum(event.get("event") == "extended_siege_launch" for event in trace), 1
        )


if __name__ == "__main__":
    unittest.main()
