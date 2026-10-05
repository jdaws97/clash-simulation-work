"""Small source-bound aura family checks, requiring reviewed factor bindings."""

from copy import deepcopy
from collections import defaultdict
from pathlib import Path
import unittest

from clashlab.buffs import damage_multiplier
from clashlab.catalog import Catalog
from clashlab.damage_receipts import DamageReceipts
from clashlab.equipment_auras import POLICIES, EquipmentAuraCombat, compile_equipment
from clashlab.rates import attack_rate, movement_speed
from clashlab.spatial import _load_actors, _apply_health

from test_spatial import synthetic_unit, synthetic_structure


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "synthetic-moving-equipment-field-not-game-calibration"


def gear(entity, classes=None):
    return {
        "entity": entity,
        "level": 27 if entity == "heroic-torch" else 18,
        "parameters": {
            "source": SOURCE,
            **POLICIES,
            "radius_tiles": 3,
            "recipient_classes": ["troop"] if classes is None else classes,
            "include_owner": False,
        },
    }


def definitions(catalog, names):
    models = [
        compile_equipment(
            gear(name), {"entity": "grand-warden", "town_hall": 18}, catalog, 8
        )[0]
        for name in names
    ]
    warden = synthetic_unit(
        "warden",
        x=4,
        y=4,
        hitpoints=1000,
        buff_class="hero",
        hero_model={"entity": "grand-warden", "equipment": models},
        wall_behavior={"kind": "avoid", "source": SOURCE},
    )
    troop = synthetic_unit(
        "troop",
        x=5,
        y=4,
        hitpoints=1000,
        damage=100,
        buff_class="troop",
        wall_behavior={"kind": "avoid", "source": SOURCE},
    )
    actors = _load_actors({"actors": [warden, troop]}, 20, 20)
    return actors, EquipmentAuraCombat(actors)


@unittest.skipUnless(
    attack_rate({"_equipment_field_attack_rate": 2}) == 2,
    "Requires the separately reviewed central aura-factor integration patch",
)
class EquipmentAuraFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT / "data")

    def test_rage_life_entry_exit_source_loss_and_pair_order(self):
        for names in (("rage-gem", "life-gem"), ("life-gem", "rage-gem")):
            actors, runtime = definitions(self.catalog, names)
            actors["troop"]["hp"] = 400
            trace = []
            runtime.prepare(actors, 0, trace)
            self.assertEqual(actors["troop"]["maximum_hp"], 2200)
            self.assertAlmostEqual(actors["troop"]["hp"], 880)
            _apply_health(actors, defaultdict(float), defaultdict(float), 0)
            self.assertAlmostEqual(actors["troop"]["hp"], 880)
            self.assertEqual(damage_multiplier(actors["troop"]), 1.5)
            self.assertEqual(attack_rate(actors["warden"]), 1.22)
            actors["troop"]["x"] = 10
            runtime.prepare(actors, 1, trace)
            self.assertEqual(actors["troop"]["maximum_hp"], 1000)
            self.assertAlmostEqual(actors["troop"]["hp"], 400)
            self.assertEqual(damage_multiplier(actors["troop"]), 1)
            actors["troop"]["x"] = 5
            actors["warden"]["hp"] = 0
            runtime.prepare(actors, 2, trace)
            self.assertAlmostEqual(actors["troop"]["hp"], 400)
            actors["troop"]["hp"] = 0
            actors["warden"]["hp"] = 1
            runtime.prepare(actors, 3, trace)
            self.assertEqual(actors["troop"]["hp"], 0)

    def test_moving_source_contact_preserves_exact_crossing_side(self):
        actors, runtime = definitions(self.catalog, ("rage-gem",))
        actors["troop"]["x"] = 10
        trace = []
        runtime.prepare(actors, 0, trace)
        delay = runtime.first_crossing_delay(
            actors, {"warden": [(10, 4)]}, {"warden": 2}, 0, 5
        )
        self.assertAlmostEqual(delay, 1.5)
        actors["warden"]["x"] = 7
        runtime.prepare(actors, delay, trace)
        self.assertEqual(damage_multiplier(actors["troop"]), 1.5)
        delay = runtime.first_crossing_delay(
            actors, {"warden": [(14, 4)]}, {"warden": 2}, 1.5, 5
        )
        self.assertAlmostEqual(delay, 3)
        actors["warden"]["x"] = 13
        runtime.prepare(actors, 4.5, trace)
        self.assertEqual(damage_multiplier(actors["troop"]), 1)

    def test_torch_damage_receipt_recall_expiry_and_wall_egress(self):
        actors, runtime = definitions(self.catalog, ("heroic-torch",))
        wall = synthetic_structure("wall", kind="wall", x=5, y=4, hitpoints=1000)
        actors.update(_load_actors({"actors": [wall]}, 20, 20))
        # The runtime uses the complete predeclared actor inventory.
        runtime = EquipmentAuraCombat(actors)
        trace = []
        runtime.activate("warden", actors, 0, trace)
        runtime.prepare(actors, 0, trace)
        self.assertEqual(actors["troop"]["wall_behavior"]["kind"], "jump_enemy_walls")
        self.assertAlmostEqual(
            movement_speed(actors["troop"]), actors["troop"]["speed"] + 9 / 8
        )
        receipts = DamageReceipts()
        self.assertEqual(
            receipts.register(
                actors["troop"],
                100,
                0,
                source_id="enemy",
                source_team="defense",
                origin="weapon",
            ),
            85,
        )
        self.assertEqual(
            receipts.register(
                actors["warden"],
                200,
                0,
                source_id="enemy",
                source_team="defense",
                origin="weapon",
            ),
            63,
        )
        actors["warden"]["_recalled"] = True
        runtime.prepare(actors, 1, trace)
        self.assertEqual(actors["troop"]["_equipment_field_incoming_multiplier"], 1)
        self.assertEqual(actors["troop"]["wall_behavior"]["kind"], "jump_enemy_walls")
        actors["troop"]["x"] = 6
        runtime.prepare(actors, 2, trace)
        self.assertEqual(actors["troop"]["wall_behavior"]["kind"], "avoid")
        actors["warden"]["_recalled"] = False
        runtime.prepare(actors, 27.5, trace)
        self.assertEqual(actors["troop"]["_equipment_field_movement_bonus"], 0)


if __name__ == "__main__":
    unittest.main()
