//! Ports specs.py:19-48,401-503; rust_export.py:103-134 supplies all static data.

use std::collections::HashMap;
use std::fs;
use std::path::Path;

use crate::json::{self, Json};
use crate::load::Node;
use crate::stats::{Level, Stats};

#[derive(Clone, Debug)]
pub struct UnitSpec {
    pub name: String,
    pub prefer: String,
    pub walls: String,
    pub attack: String,
    pub splash: f64,
    pub splash_ground_only: bool,
    pub chain: usize,
    pub chain_range: f64,
    pub chain_decay: f64,
    pub chain_from_primary: bool,
    pub bounces: usize,
    pub bounce_gap: f64,
    pub pierce: f64,
    pub vs_walls: f64,
    pub vs_resources: f64,
    pub vs_defenses: f64,
    pub vs_heroes: f64,
    pub vs_buildings: f64,
    pub engages_units: bool,
    pub death_damage: Option<String>,
    pub death_radius: f64,
    pub death_delay: f64,
    pub death_freeze: Option<String>,
    pub death_freeze_radius: f64,
    pub death_spawn: Vec<Json>,
    pub special: Vec<String>,
    pub heal_air: bool,
    pub flying_override: Option<bool>,
    pub notes: String,
}

impl UnitSpec {
    pub fn has_special(&self, name: &str) -> bool {
        self.special.iter().any(|special| special == name)
    }

    pub fn load(n: Node<'_>) -> Self {
        n.require_type("UnitSpec");
        n.keys(&[
            "name",
            "prefer",
            "walls",
            "attack",
            "splash",
            "splash_ground_only",
            "chain",
            "chain_range",
            "chain_decay",
            "chain_from_primary",
            "bounces",
            "bounce_gap",
            "pierce",
            "vs_walls",
            "vs_resources",
            "vs_defenses",
            "vs_heroes",
            "vs_buildings",
            "engages_units",
            "death_damage",
            "death_radius",
            "death_delay",
            "death_freeze",
            "death_freeze_radius",
            "death_spawn",
            "special",
            "heal_air",
            "flying_override",
            "notes",
        ]);
        Self {
            name: n.field("name").string(),
            prefer: n.field("prefer").string(),
            walls: n.field("walls").string(),
            attack: n.field("attack").string(),
            splash: n.field("splash").number(),
            splash_ground_only: n.field("splash_ground_only").boolean(),
            chain: n.field("chain").usize(),
            chain_range: n.field("chain_range").number(),
            chain_decay: n.field("chain_decay").number(),
            chain_from_primary: n.field("chain_from_primary").boolean(),
            bounces: n.field("bounces").usize(),
            bounce_gap: n.field("bounce_gap").number(),
            pierce: n.field("pierce").number(),
            vs_walls: n.field("vs_walls").number(),
            vs_resources: n.field("vs_resources").number(),
            vs_defenses: n.field("vs_defenses").number(),
            vs_heroes: n.field("vs_heroes").number(),
            vs_buildings: n.field("vs_buildings").number(),
            engages_units: n.field("engages_units").boolean(),
            death_damage: n.field("death_damage").optional_string(),
            death_radius: n.field("death_radius").number(),
            death_delay: n.field("death_delay").number(),
            death_freeze: n.field("death_freeze").optional_string(),
            death_freeze_radius: n.field("death_freeze_radius").number(),
            death_spawn: n.field("death_spawn").array().iter().map(|v| v.value.clone()).collect(),
            special: n.field("special").array().iter().map(|v| v.string()).collect(),
            heal_air: n.field("heal_air").boolean(),
            flying_override: n.field("flying_override").optional_bool(),
            notes: n.field("notes").string(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct UnitNumbers {
    pub hp: f64,
    pub dmg: f64,
    pub dps: f64,
    pub interval: f64,
    pub range: f64,
    pub speed: f64,
    pub housing: i64,
    pub flying: bool,
    pub hits_air: bool,
    pub hits_ground: bool,
}

impl UnitNumbers {
    fn load(n: Node<'_>) -> Self {
        n.keys(&[
            "hp",
            "dmg",
            "dps",
            "interval",
            "range",
            "speed",
            "housing",
            "flying",
            "hits_air",
            "hits_ground",
        ]);
        Self {
            hp: n.field("hp").number(),
            dmg: n.field("dmg").number(),
            dps: n.field("dps").number(),
            interval: n.field("interval").number(),
            range: n.field("range").number(),
            speed: n.field("speed").number(),
            housing: n.field("housing").integer(),
            flying: n.field("flying").boolean(),
            hits_air: n.field("hits_air").boolean(),
            hits_ground: n.field("hits_ground").boolean(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct CatalogUnit {
    pub spec: UnitSpec,
    pub summon_spec: UnitSpec,
}

#[derive(Clone, Debug)]
pub struct BuildingType {
    pub key: String,
    pub name: String,
    pub size: usize,
    pub count: usize,
    pub kind: String,
    pub counted: bool,
    pub weapon_key: Option<String>,
}

pub struct Catalog {
    pub stats: Stats,
    pub units: HashMap<String, CatalogUnit>,
    pub unit_numbers: HashMap<String, UnitNumbers>,
    pub building_types: Vec<(String, BuildingType)>,
    pub trap_names: Vec<(String, String)>,
    pub trap_sizes: Vec<(String, usize)>,
    /// units.py _new_target_delays: NewTargetAttackDelay seconds per unit.
    pub new_target_delays: HashMap<String, f64>,
    /// specs.py _game_ranges: AttackRange tiles per unit.
    pub game_ranges: HashMap<String, f64>,
    /// units.py warden_weights(): data/warden-weights.json as read.
    pub warden_weights: Json,
    pub world: usize,
    pub margin: f64,
}

impl Catalog {
    pub fn load(path: &Path) -> Result<Self, String> {
        let text = fs::read_to_string(path)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        let value = json::parse(&text)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        Ok(Self::from_json(&value, &path.display().to_string()))
    }

    pub fn from_json(value: &Json, path: &str) -> Self {
        let n = Node::new(value, path);
        n.keys(&[
            "note",
            "registry",
            "units",
            "unit_numbers",
            "building_types",
            "trap_names",
            "trap_sizes",
            "new_target_delays",
            "warden_weights",
            "game_ranges",
            "world",
            "margin",
        ]);
        n.field("note").string();
        let stats = Stats::new(n.field("registry").value.clone());
        let units = n.field("units").object().into_iter().map(|(name, node)| {
            node.keys(&["spec", "summon_spec"]);
            let unit = CatalogUnit {
                spec: UnitSpec::load(node.field("spec")),
                summon_spec: UnitSpec::load(node.field("summon_spec")),
            };
            (name, unit)
        }).collect();
        let unit_numbers = n.field("unit_numbers").object().into_iter()
            .map(|(name, node)| (name, UnitNumbers::load(node))).collect();
        let building_types = n.field("building_types").object().into_iter()
            .map(|(key, node)| {
                node.require_type("BuildingType");
                node.keys(&["key", "name", "size", "count", "kind", "counted", "weapon_key"]);
                let item = BuildingType {
                    key: node.field("key").string(),
                    name: node.field("name").string(),
                    size: node.field("size").usize(),
                    count: node.field("count").usize(),
                    kind: node.field("kind").string(),
                    counted: node.field("counted").boolean(),
                    weapon_key: node.field("weapon_key").optional_string(),
                };
                (key, item)
            }).collect();
        let trap_names = n.field("trap_names").object().into_iter()
            .map(|(key, node)| (key, node.string())).collect();
        let trap_sizes = n.field("trap_sizes").object().into_iter()
            .map(|(key, node)| (key, node.usize())).collect();
        let number_map = |field: &str| -> HashMap<String, f64> {
            n.field(field).object().into_iter().map(|(k, v)| (k, v.number())).collect()
        };
        Self {
            stats,
            units,
            unit_numbers,
            building_types,
            trap_names,
            trap_sizes,
            new_target_delays: number_map("new_target_delays"),
            game_ranges: number_map("game_ranges"),
            warden_weights: n.field("warden_weights").value.clone(),
            world: n.field("world").usize(),
            margin: n.field("margin").number(),
        }
    }

    pub fn numbers(&self, name: &str, level: &Level) -> &UnitNumbers {
        let key = format!("{name}|{level}");
        self.unit_numbers.get(&key)
            .unwrap_or_else(|| panic!("catalog.unit_numbers[{key:?}]: missing unit numbers"))
    }

    pub fn unit(&self, name: &str) -> &CatalogUnit {
        self.units.get(name)
            .unwrap_or_else(|| panic!("catalog.units[{name:?}]: missing unit spec"))
    }
}

impl UnitSpec {
    // spells.py:1163 and specs.py:19-48: a dynamically constructed UnitSpec.
    pub fn totem() -> Self {
        Self {
            name: "Totem".to_owned(),
            prefer: "none".to_owned(),
            walls: "fly".to_owned(),
            attack: "single".to_owned(),
            splash: 0.0,
            splash_ground_only: false,
            chain: 0,
            chain_range: 3.0,
            chain_decay: 0.8,
            chain_from_primary: false,
            bounces: 0,
            bounce_gap: 3.0,
            pierce: 0.0,
            vs_walls: 1.0,
            vs_resources: 1.0,
            vs_defenses: 1.0,
            vs_heroes: 1.0,
            vs_buildings: 1.0,
            engages_units: true,
            death_damage: None,
            death_radius: 0.0,
            death_delay: 0.0,
            death_freeze: None,
            death_freeze_radius: 0.0,
            death_spawn: Vec::new(),
            special: Vec::new(),
            heal_air: false,
            flying_override: None,
            notes: String::new(),
        }
    }
}
