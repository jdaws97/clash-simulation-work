//! Declarative v29 model inputs formerly owned by mechanics/engine Python.
//! Keep these separate from source-resolved game numbers.

use clash_data::json::{self, Json};
use clash_data::wire::{arr, num, obj, put, string};

use super::empty;

pub(super) fn setup() -> Json {
    let mut result = json::parse(r#"{
        "modifiers": {"null":[0,0,0,0], "legend3":[0.10,0.10,0.05,0.05], "legend2":[0.15,0.15,0.10,0.10], "legend1":[0.20,0.20,0.20,0.20]},
        "inferno_artillery": {"range":12,"targets":4,"interval":3.5,"damage":210,"pool_dps":75,"pool_time":6.8,"pool_radius":2.5,"pool_gap":0.4,"pool_hits":17},
        "giga_inferno": {"13":{"dps":null,"targets":5}, "16":{"dps":300,"targets":4,"range":10,"death":1100,"death_radius":4.5,"poison_dps":180,"poison_time":12,"slow":0.5}},
        "crafted": {"cake":"Cake-A-Pult","candle":"Hot Candle","hunter":"Hero Hunter","bell":"Hero Bell","hook":"Hook Tower"},
        "ammunition": {"xbow":1500,"inferno":1000,"eagle":90,"scatter":90},
        "spell_tower_unlocks": {"rage":1,"poison":2,"invis":3,"eq":4,"quake":4,"earthquake":4},
        "gear_minimum": {"cannon":7,"at":10,"mortar":8},
        "geared_cannon_offsets": [0.62,0.66,0.66,0.70,0.70,0.72,0.74,0.76,0.76,0.76,0.76,0.76,0.76,0.76,0.76],
        "gear_archer_shots": [31.5,35,37.5,40,45,50,52.5,55,60,65,69,72.5],
        "artillery_damage": [140,157.5,175,192.5,210],
        "crafting": {"phase":4,"start":"2026-08-01","end":"2026-12-31","modes":["cake","candle","hunter"]},
        "trap_no_trigger": ["Bat","Booger","Electro Owl","Electromite","Firemite","Frostmite","Poison Lizard","Skeleton","Spell Skeleton","Totem","Yetimite"]
    }"#).expect("static v29 setup JSON");
    let pi = std::f64::consts::PI;
    put(
        &mut result,
        "facings",
        obj([
            ("N", num(-pi / 2.0)),
            ("NE", num(-pi / 4.0)),
            ("E", num(0)),
            ("SE", num(pi / 4.0)),
            ("S", num(pi / 2.0)),
            ("SW", num(3.0 * pi / 4.0)),
            ("W", num(pi)),
            ("NW", num(-3.0 * pi / 4.0)),
        ]),
    );
    let frame = 1.5 / 35.0;
    put(
        &mut result,
        "trap_fuse",
        obj([
            ("bomb", num(35.0 * frame)),
            ("giant", num(37.0 * frame)),
            ("giga", num(38.0 * frame)),
            ("airbomb", num(7.0 * frame)),
            ("seeking", num(7.0 * frame)),
            ("tornado", num(8.0 * frame)),
            ("spring", num(0.3)),
            ("skeleton", num(0.6)),
        ]),
    );
    put(
        &mut result,
        "cargo_order",
        arr(CARGO.iter().map(|name| string(*name))),
    );
    let mut loadouts = empty();
    for (hero, equipment, pet) in [
        ("Archer Queen", ["Giant Arrow", "Action Figure"], "Unicorn"),
        (
            "Barbarian King",
            ["Spiky Ball", "Earthquake Boots"],
            "Spirit Fox",
        ),
        ("Grand Warden", ["Eternal Tome", "Rage Gem"], "Electro Owl"),
        (
            "Royal Champion",
            ["Rocket Spear", "Electro Boots"],
            "L.A.S.S.I",
        ),
        ("Minion Prince", ["Dark Orb", "Meteor Staff"], "Angry Jelly"),
        ("Dragon Duke", ["Rocket Backpack", "Fire Heart"], "Phoenix"),
    ] {
        put(
            &mut loadouts,
            hero,
            obj([
                ("$type", string("HeroLoadout")),
                ("hero", string(hero)),
                ("equipment", arr(equipment.map(string))),
                ("pet", string(pet)),
            ]),
        );
    }
    put(&mut result, "default_loadouts", loadouts);
    result
}

pub(super) fn buildings() -> Json {
    let mut result = empty();
    for &(key, name, size, count, kind, weapon) in BUILDINGS {
        let building = obj([
            ("$type", string("BuildingType")),
            ("key", string(key)),
            ("name", string(name)),
            ("size", num(size)),
            ("count", num(count)),
            ("kind", string(kind)),
            ("counted", Json::Bool(key != "banner")),
            ("weapon_key", if weapon { string(key) } else { Json::Null }),
        ]);
        put(&mut result, key, building);
    }
    result
}

const BUILDINGS: &[(&str, &str, i32, i32, &str, bool)] = &[
    ("th", "Town Hall", 4, 1, "townhall", true),
    ("cc", "Clan Castle", 3, 1, "castle", false),
    ("ad", "Air Defense", 3, 4, "defense", true),
    ("sweeper", "Air Sweeper", 2, 2, "defense", true),
    ("at", "Archer Tower", 3, 4, "defense", true),
    ("mat", "Multi-Archer Tower", 3, 2, "defense", true),
    ("cannon", "Cannon", 3, 3, "defense", true),
    ("ric", "Ricochet Cannon", 3, 2, "defense", true),
    ("bt", "Bomb Tower", 3, 2, "defense", true),
    ("bh", "Builder's Hut", 2, 5, "defense", true),
    ("eagle", "Eagle Artillery", 4, 1, "defense", true),
    ("tesla", "Hidden Tesla", 2, 5, "defense", true),
    ("inferno", "Inferno Tower", 2, 3, "defense", true),
    ("mono", "Monolith", 3, 1, "defense", true),
    ("mortar", "Mortar", 3, 4, "defense", true),
    ("scatter", "Scattershot", 3, 2, "defense", true),
    ("st", "Spell Tower", 2, 2, "defense", true),
    ("wt", "Wizard Tower", 3, 5, "defense", true),
    ("xbow", "X-Bow", 3, 4, "defense", true),
    ("gm", "Gold Mine", 3, 7, "resource", false),
    ("ec", "Elixir Collector", 3, 7, "resource", false),
    ("dd", "Dark Elixir Drill", 3, 3, "resource", false),
    ("gs", "Gold Storage", 3, 4, "resource", false),
    ("es", "Elixir Storage", 3, 4, "resource", false),
    ("ds", "Dark Elixir Storage", 3, 1, "resource", false),
    ("camp", "Army Camp", 4, 4, "army", false),
    ("barracks", "Barracks", 3, 1, "army", false),
    ("dbarracks", "Dark Barracks", 3, 1, "army", false),
    ("sf", "Spell Factory", 3, 1, "army", false),
    ("dsf", "Dark Spell Factory", 3, 1, "army", false),
    ("lab", "Laboratory", 3, 1, "army", false),
    ("workshop", "Workshop", 4, 1, "army", false),
    ("pethouse", "Pet House", 3, 1, "army", false),
    ("smith", "Blacksmith", 3, 1, "army", false),
    ("herohall", "Hero Hall", 4, 1, "army", false),
    ("helper", "Helper Hut", 3, 1, "other", false),
    ("bob", "B.O.B's Hut", 2, 1, "other", false),
    ("banner", "Hero Banner", 2, 4, "other", false),
    ("mgt", "Multi-Gear Tower", 3, 0, "defense", true),
    ("firespitter", "Firespitter", 3, 0, "defense", true),
    ("swt", "Super Wizard Tower", 3, 0, "defense", true),
    ("revenge", "Revenge Tower", 3, 0, "defense", true),
    ("crafting", "Crafting Station", 3, 0, "defense", true),
];

const CARGO: &[&str] = &[
    "Barbarian",
    "Archer",
    "Goblin",
    "Wall Breaker",
    "Minion",
    "Sneaky Goblin",
    "Wizard",
    "Giant",
    "Balloon",
    "Hog Rider",
    "Super Barbarian",
    "Bowler",
    "Miner",
    "Headhunter",
    "Valkyrie",
    "Super Wall Breaker",
    "Rocket Balloon",
    "Baby Dragon",
    "Super Giant",
    "Super Wizard",
    "Witch",
    "Super Archer",
    "Super Minion",
    "Super Hog Rider",
    "Healer",
    "Ice Golem",
    "Inferno Dragon",
    "Druid",
    "Thrower",
    "Yeti",
    "Furnace",
    "Dragon",
    "Super Valkyrie",
    "Apprentice Warden",
    "Root Rider",
    "Super Miner",
    "P.E.K.K.A",
    "Dragon Rider",
    "Golem",
    "Lava Hound",
    "Electro Dragon",
    "Super Bowler",
    "Electro Titan",
    "Super Yeti",
    "Meteor Golem",
    "Super Witch",
    "Ice Hound",
    "Super Dragon",
];
