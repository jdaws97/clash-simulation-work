//! Ports rust_export.py:47-87,190-222: strict, path-labelled exported state loading.
//! Python constructs objects; this module only restores their values and links.

use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::rc::Rc;

use crate::catalog::{Catalog, UnitSpec};
use crate::grid::Grid;
use crate::json::{self, Json};
use crate::state::*;
use crate::pyrandom::PyRandom;
use crate::stats::Level;

#[derive(Clone)]
pub struct Node<'a> {
    pub value: &'a Json,
    pub path: String,
}

impl<'a> Node<'a> {
    pub fn new(value: &'a Json, path: &str) -> Self {
        Self {
            value,
            path: path.to_owned(),
        }
    }

    pub fn fail(&self, message: &str) -> ! {
        panic!("{}: {message}", self.path)
    }

    pub fn field(&self, name: &str) -> Self {
        self.optional(name).unwrap_or_else(|| panic!("{}.{}: missing field", self.path, name))
    }

    pub fn optional(&self, name: &str) -> Option<Self> {
        self.value.get(name).map(|value| Self {
            value,
            path: format!("{}.{}", self.path, name),
        })
    }

    pub fn object(&self) -> Vec<(String, Self)> {
        let Json::Obj(items) = self.value else {
            self.fail("expected object")
        };
        items.iter().map(|(key, value)| (key.clone(), Self {
            value,
            path: format!("{}.{}", self.path, key),
        })).collect()
    }

    pub fn array(&self) -> Vec<Self> {
        let Json::Arr(items) = self.value else {
            self.fail("expected array")
        };
        items.iter().enumerate().map(|(index, value)| Self {
            value,
            path: format!("{}[{index}]", self.path),
        }).collect()
    }

    pub fn tuple(&self, length: usize) -> Vec<Self> {
        let items = self.array();
        if items.len() != length {
            self.fail(&format!("expected {length} items"));
        }
        items
    }

    pub fn keys(&self, allowed: &[&str]) {
        if let Some(tag) = self.optional("$type") {
            if !known_type(&tag.string()) {
                tag.fail("unknown $type");
            }
        }
        for (key, node) in self.object() {
            if key != "$type" && !allowed.contains(&key.as_str()) {
                node.fail("unknown field (no generic fallback)");
            }
        }
    }

    pub fn require_type(&self, expected: &str) {
        let actual = self.field("$type").string();
        if actual != expected {
            self.field("$type").fail(&format!("expected {expected}, got {actual}"));
        }
    }

    fn require_fields(&self, fields: &[&str]) {
        for field in fields {
            self.field(field);
        }
    }

    pub fn string(&self) -> String {
        let Json::Str(value) = self.value else {
            self.fail("expected string")
        };
        value.clone()
    }

    pub fn number(&self) -> f64 {
        let Json::Num(value) = self.value else {
            self.fail("expected number")
        };
        *value
    }

    pub fn integer(&self) -> i64 {
        let value = self.number();
        if !value.is_finite() || value.fract() != 0.0
            || value < i64::MIN as f64 || value >= 9_223_372_036_854_775_808.0 {
            self.fail("expected integer in i64 range");
        }
        value as i64
    }

    pub fn usize(&self) -> usize {
        let value = self.integer();
        usize::try_from(value).unwrap_or_else(|_| self.fail("expected nonnegative index"))
    }

    pub fn i32(&self) -> i32 {
        i32::try_from(self.integer()).unwrap_or_else(|_| self.fail("integer outside i32 range"))
    }

    pub fn boolean(&self) -> bool {
        let Json::Bool(value) = self.value else {
            self.fail("expected boolean")
        };
        *value
    }

    pub fn optional_string(&self) -> Option<String> {
        if self.value.is_null() {
            None
        } else {
            Some(self.string())
        }
    }

    pub fn optional_bool(&self) -> Option<bool> {
        if self.value.is_null() {
            None
        } else {
            Some(self.boolean())
        }
    }

    pub fn optional_number(&self) -> Option<f64> {
        if self.value.is_null() {
            None
        } else {
            Some(self.number())
        }
    }

    pub fn optional_integer(&self) -> Option<i64> {
        if self.value.is_null() {
            None
        } else {
            Some(self.integer())
        }
    }

    pub fn level(&self) -> Level {
        match self.value {
            Json::Num(_) => Level::Int(self.integer()),
            Json::Str(value) => Level::Text(value.clone()),
            _ => self.fail("expected integer or string level"),
        }
    }

    pub fn optional_level(&self) -> Option<Level> {
        if self.value.is_null() {
            None
        } else {
            Some(self.level())
        }
    }

    pub fn pair(&self) -> (f64, f64) {
        let items = self.tuple(2);
        (items[0].number(), items[1].number())
    }

    pub fn optional_pair(&self) -> Option<(f64, f64)> {
        if self.value.is_null() {
            None
        } else {
            Some(self.pair())
        }
    }

    pub fn optional_source(&self) -> Option<(String, i64)> {
        if self.value.is_null() {
            return None;
        }
        let pair = self.tuple(2);
        Some((pair[0].string(), pair[1].integer()))
    }

    pub fn triple(&self) -> (f64, f64, f64) {
        let items = self.tuple(3);
        (items[0].number(), items[1].number(), items[2].number())
    }

    pub fn team(&self) -> Team {
        match self.string().as_str() {
            "atk" => Team::Atk,
            "def" => Team::Def,
            _ => self.fail("unknown unit team"),
        }
    }
}

fn known_type(name: &str) -> bool {
    matches!(name, "Building" | "Wall" | "Unit" | "UnitSpec" | "Weapon" | "Trap"
        | "Field" | "Pending" | "Builder" | "Deployment" | "Stage" | "BuildingType")
}

struct Resolver {
    buildings: HashMap<BuildingId, usize>,
    walls: HashMap<(i32, i32), WallId>,
    units: HashMap<UnitId, (Team, usize)>,
    trap_count: usize,
}

impl Resolver {
    fn new(root: &Node<'_>) -> Self {
        let mut buildings = HashMap::new();
        for (index, n) in root.field("buildings").array().into_iter().enumerate() {
            n.require_type("Building");
            let id = BuildingId(n.field("id").usize());
            if buildings.insert(id, index).is_some() {
                n.field("id").fail("duplicate building id");
            }
        }
        let mut walls = HashMap::new();
        for (index, n) in root.field("walls").array().into_iter().enumerate() {
            n.require_type("Wall");
            let key = (n.field("tx").i32(), n.field("ty").i32());
            if walls.insert(key, WallId(index)).is_some() {
                n.fail("duplicate wall coordinates");
            }
        }
        let mut units = HashMap::new();
        for (pool, team) in [("attackers", Team::Atk), ("defenders", Team::Def)] {
            for (index, n) in root.field(pool).array().into_iter().enumerate() {
                n.require_type("Unit");
                if n.field("team").team() != team {
                    n.field("team").fail("unit in wrong pool");
                }
                let id = UnitId(n.field("id").usize());
                if units.insert(id, (team, index)).is_some() {
                    n.field("id").fail("duplicate shared unit id");
                }
            }
        }
        Self {
            buildings,
            walls,
            units,
            trap_count: root.field("traps").array().len(),
        }
    }

    fn reference(&self, n: Node<'_>) -> EntityRef {
        if n.value.get("$building").is_some() {
            n.keys(&["$building"]);
            let id = BuildingId(n.field("$building").usize());
            if !self.buildings.contains_key(&id) {
                n.fail("unknown building reference");
            }
            EntityRef::Building(id)
        } else if n.value.get("$wall").is_some() {
            n.keys(&["$wall"]);
            let pair = n.field("$wall").tuple(2);
            let key = (pair[0].i32(), pair[1].i32());
            EntityRef::Wall(*self.walls.get(&key).unwrap_or_else(|| n.fail("unknown wall reference")))
        } else if n.value.get("$unit").is_some() {
            n.keys(&["$unit", "team"]);
            let id = UnitId(n.field("$unit").usize());
            let team = n.field("team").team();
            match self.units.get(&id) {
                Some((actual, _)) if *actual == team => EntityRef::Unit(UnitRef { id, team }),
                _ => n.fail("unknown unit reference or wrong team"),
            }
        } else if n.value.get("$trap").is_some() {
            n.keys(&["$trap"]);
            let id = TrapId(n.field("$trap").usize());
            if id.0 >= self.trap_count {
                n.fail("unknown trap reference");
            }
            EntityRef::Trap(id)
        } else {
            n.fail("expected entity reference")
        }
    }

    fn optional_ref(&self, n: Node<'_>) -> Option<EntityRef> {
        if n.value.is_null() {
            None
        } else {
            Some(self.reference(n))
        }
    }

    fn building_ref(&self, n: Node<'_>) -> BuildingId {
        let EntityRef::Building(id) = self.reference(n.clone()) else {
            n.fail("expected building reference")
        };
        id
    }

    fn optional_building_ref(&self, n: Node<'_>) -> Option<BuildingId> {
        if n.value.is_null() {
            None
        } else {
            Some(self.building_ref(n))
        }
    }

    fn unit_ref(&self, n: Node<'_>) -> UnitRef {
        let EntityRef::Unit(id) = self.reference(n.clone()) else {
            n.fail("expected unit reference")
        };
        id
    }

    fn optional_unit_ref(&self, n: Node<'_>) -> Option<UnitRef> {
        if n.value.is_null() {
            None
        } else {
            Some(self.unit_ref(n))
        }
    }

    fn optional_wall_ref(&self, n: Node<'_>) -> Option<WallId> {
        if n.value.is_null() {
            return None;
        }
        let EntityRef::Wall(id) = self.reference(n.clone()) else {
            n.fail("expected wall reference")
        };
        Some(id)
    }

    fn value(&self, n: Node<'_>) -> Value {
        match n.value {
            Json::Null => Value::Null,
            Json::Bool(value) => Value::Bool(*value),
            Json::Num(value) => Value::Number(*value),
            Json::Str(value) => Value::String(value.clone()),
            Json::Arr(_) => Value::List(n.array().into_iter().map(|item| self.value(item)).collect()),
            Json::Obj(items) => {
                if items.iter().any(|(key, _)| key.starts_with('$') && key != "$type") {
                    return Value::Ref(self.reference(n));
                }
                if let Some(tag) = n.optional("$type") {
                    match tag.string().as_str() {
                        "Building" | "Wall" | "Unit" | "UnitSpec" | "Weapon" | "Trap"
                        | "Field" | "Pending" | "Builder" | "Deployment" | "Stage"
                        | "BuildingType" => {}
                        _ => tag.fail("unknown $type"),
                    }
                }
                Value::Map(self.map(n))
            }
        }
    }

    fn optional_value(&self, n: Node<'_>) -> Option<Value> {
        if n.value.is_null() {
            None
        } else {
            Some(self.value(n))
        }
    }

    fn map(&self, n: Node<'_>) -> ExtraMap {
        n.object().into_iter().map(|(key, value)| (key, self.value(value))).collect()
    }

    fn trigger(&self, n: Node<'_>) -> Option<WeaponTrigger> {
        if n.value.is_null() {
            return None;
        }
        if let Json::Num(value) = n.value {
            return Some(WeaponTrigger::Radius(*value));
        }
        let pair = n.tuple(2);
        Some(WeaponTrigger::UnitSince(self.unit_ref(pair[0].clone()), pair[1].number()))
    }

    fn hit_triggers(&self, n: Node<'_>) -> Vec<(UnitRef, f64)> {
        n.object().into_iter().map(|(key, value)| {
            // rust_export.py:64 encodes non-string dict keys with json.dumps.
            let reference = json::parse(&key).unwrap_or_else(|_| value.fail("invalid encoded unit key"));
            let unit = self.unit_ref(Node::new(&reference, &format!("{}.<key>", value.path)));
            (unit, value.number())
        }).collect()
    }

    fn spin_position(&self, n: Node<'_>) -> Option<SpinPosition> {
        if n.value.is_null() {
            return None;
        }
        let items = n.tuple(3);
        Some(SpinPosition {
            first: self.building_ref(items[0].clone()),
            second: self.building_ref(items[1].clone()),
            position: items[2].pair(),
        })
    }

    fn poison_config(&self, n: Node<'_>) -> Option<PoisonConfig> {
        if n.value.is_null() {
            return None;
        }
        let unknown = n.object().into_iter()
            .filter(|(key, _)| !["dps", "time", "slow", "radius", "atk", "ramp", "hero_mult"]
                .contains(&key.as_str()))
            .map(|(key, value)| (key, self.value(value)))
            .collect();
        Some(PoisonConfig {
            dps: n.field("dps").number(),
            time: n.optional("time").and_then(|value| value.optional_number()),
            slow: n.optional("slow").and_then(|value| value.optional_number()),
            radius: n.optional("radius").and_then(|value| value.optional_number()),
            atk: n.optional("atk").and_then(|value| value.optional_number()),
            ramp: n.optional("ramp").is_some_and(|value| value.boolean()),
            hero_mult: n.optional("hero_mult").map_or(1.0, |value| value.number()),
            unknown,
        })
    }
}

pub fn load(path: &Path, catalog: Rc<Catalog>) -> Result<Battle, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    let value = json::parse(&text)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    Ok(from_json(&value, catalog, &path.display().to_string()))
}
// Restore each exported slot explicitly; defaults apply only to absent extra keys.

impl Resolver {
    // entities.py:66-72; battle.py:267,543; units.py:215-220. Unknown keys use the ordered
    // generic JSON fallback.
    fn building_extra(&self, n: Node<'_>) -> BuildingExtra {
        let mut extra = BuildingExtra::default();
        for (key, v) in n.object() {
            match key.as_str() {
                "unavailable" => extra.unavailable = v.boolean(),
                "yellow_until" => extra.yellow_until = v.number(),
                "rubble_taken" => extra.rubble_taken = v.boolean(),
                "rubble_claim" => {
                    extra.rubble_claim = if v.value.is_null() {
                        None
                    } else {
                        Some(UnitId(v.usize()))
                    };
                }
                _ => extra.unknown.push((key, self.value(v))),
            }
        }
        extra
    }

    // defense.py:192-462,493-497,524-1409. Unknown keys use the ordered generic JSON fallback.
    fn weapon_extra(&self, n: Node<'_>) -> WeaponExtra {
        let mut extra = WeaponExtra::default();
        for (key, v) in n.object() {
            match key.as_str() {
                "splash" => extra.splash = v.number(),
                "flight" => extra.flight = v.number(),
                "death" => extra.death = v.number(),
                "death_radius" => extra.death_radius = v.number(),
                "death_delay" => extra.death_delay = v.number(),
                "bounce" => extra.bounce = v.number(),
                "bounce_range" => extra.bounce_range = v.number(),
                "gap" => extra.gap = v.number(),
                "shock" => extra.shock = v.number(),
                "shock_radius" => extra.shock_radius = v.number(),
                "splash_max" => extra.splash_max = v.number(),
                "splash_min" => extra.splash_min = v.number(),
                "pct" => extra.pct = v.number(),
                "push" => extra.push = v.number(),
                "repair" => extra.repair = v.number(),
                "repair_range" => extra.repair_range = v.number(),
                "arc" => extra.arc = v.number(),
                "secondary" => extra.secondary = v.number(),
                "chain_range" => extra.chain_range = v.number(),
                "bomb" => extra.bomb = v.number(),
                "bomb_radius" => extra.bomb_radius = v.number(),
                "bomb_delay" => extra.bomb_delay = v.number(),
                "melt1" => extra.melt1 = v.number(),
                "melt2" => extra.melt2 = v.number(),
                "poison_time" => extra.poison_time = v.number(),
                "dps" => extra.dps = v.number(),
                "range" => extra.range = v.number(),
                "slow" => extra.slow = v.number(),
                "poison_dps" => extra.poison_dps = v.number(),
                "interval" => extra.interval = v.number(),
                "damage" => extra.damage = v.number(),
                "pool_dps" => extra.pool_dps = v.number(),
                "pool_time" => extra.pool_time = v.number(),
                "pool_radius" => extra.pool_radius = v.number(),
                "pool_gap" => extra.pool_gap = v.number(),
                "stun" => extra.stun = v.number(),
                "targets" => extra.targets = v.usize(),
                "activation" => extra.activation = v.usize(),
                "shells" => extra.shells = v.usize(),
                "shots" => extra.shots = v.usize(),
                "pierce" => extra.pierce = v.usize(),
                "chain" => extra.chain = v.usize(),
                "poison_level" => extra.poison_level = v.usize(),
                "pool_hits" => extra.pool_hits = v.usize(),
                "same_type" => extra.same_type = v.boolean(),
                "inner_min" => extra.inner_min = v.optional_number(),
                "wake_at" => extra.wake_at = v.optional_number(),
                "ramp" => extra.ramp = v.array().iter().map(Node::pair).collect(),
                "trigger" => extra.trigger = self.trigger(v),
                "hit_triggers" => extra.hit_triggers = self.hit_triggers(v),
                _ => extra.unknown.push((key, self.value(v))),
            }
        }
        extra
    }

    // entities.py:182-237; battle.py:445-1737; units.py:1200-1253,2003-2037;
    // effects.py:31-74. Unknown keys use the ordered generic JSON fallback.
    fn unit_extra(&self, n: Node<'_>) -> UnitExtra {
        let mut extra = UnitExtra::default();
        for (key, v) in n.object() {
            match key.as_str() {
                "yellow_until" => extra.yellow_until = v.number(),
                "brainwash_until" => extra.brainwash_until = v.number(),
                "armor_hp" => extra.armor_hp = v.number(),
                "aura_hp" => extra.aura_hp = v.number(),
                "troop_hit_at" => extra.troop_hit_at = v.number(),
                "next_engage" => extra.next_engage = v.number(),
                "next_retarget" => extra.next_retarget = v.number(),
                "tornado_wall_until" => extra.tornado_wall_until = v.number(),
                "angry_until" => extra.angry_until = v.number(),
                "jump_until" => extra.jump_until = v.number(),
                "horse_until" => extra.horse_until = v.number(),
                "horse_speed" => extra.horse_speed = v.number(),
                "horse_interval" => extra.horse_interval = v.number(),
                "horse_attack" => extra.horse_attack = v.number(),
                "haste_attack_until" => extra.haste_attack_until = v.number(),
                "haste_attack" => extra.haste_attack = v.number(),
                "vial_until" => extra.vial_until = v.number(),
                "vial_bonus" => extra.vial_bonus = v.number(),
                "gauntlet_until" => extra.gauntlet_until = v.number(),
                "gauntlet_radius" => extra.gauntlet_radius = v.number(),
                "bell_health" => extra.bell_health = v.number(),
                "bell_damage" => extra.bell_damage = v.number(),
                "bell_damage_until" => extra.bell_damage_until = v.number(),
                "expire_at" => extra.expire_at = v.number(),
                "expires_at" => extra.expires_at = v.number(),
                "attack_ready_at" => extra.attack_ready_at = v.number(),
                "next_blocker_check" => extra.next_blocker_check = v.number(),
                "suspended" => extra.suspended = v.boolean(),
                "leaping" => extra.leaping = v.boolean(),
                "sprung" => extra.sprung = v.boolean(),
                "preferred_remaining" => extra.preferred_remaining = v.boolean(),
                "finish_preferred" => extra.finish_preferred = v.boolean(),
                "warden_group" => extra.warden_group = v.boolean(),
                "clone" => extra.clone = v.boolean(),
                "mirror_clone" => extra.mirror_clone = v.boolean(),
                "suicided" => extra.suicided = v.boolean(),
                "facing" => extra.facing = v.pair(),
                "heading" => extra.heading = v.optional_pair(),
                "deployment_source" => extra.deployment_source = v.optional_string(),
                "recalled" => extra.recalled = Some(self.value(v)),
                "last_damage_source" => extra.last_damage_source = self.optional_ref(v),
                "pushed_at" => extra.pushed_at = v.optional_number(),
                "patrol_state" => extra.patrol_state = v.optional_string(),
                "spin_position" => extra.spin_position = self.spin_position(v),
                "attack_target" => extra.attack_target = self.optional_ref(v),
                "burst_target" => extra.burst_target = self.optional_ref(v),
                "beam_target" => extra.beam_target = self.optional_ref(v),
                "beam_time" => extra.beam_time = v.optional_number(),
                "beam_tick" => extra.beam_tick = v.optional_number(),
                "long_shots" => extra.long_shots = v.integer(),
                "burst_left" => extra.burst_left = v.integer(),
                "eq_n" => extra.eq_n = v.usize(),
                "burn_tick" => extra.burn_tick = v.optional_number(),
                "rage_effects" => {
                    extra.rage_effects = v.object().into_iter()
                        .map(|(key, value)| (key, value.triple()))
                        .collect();
                }
                "haste_effects" => {
                    extra.haste_effects = v.object().into_iter()
                        .map(|(key, value)| (key, value.pair()))
                        .collect();
                }
                "slows" => {
                    extra.slows = v.object().into_iter()
                        .map(|(key, value)| (key, value.triple()))
                        .collect();
                }
                "torches" => {
                    extra.torches = v.object().into_iter()
                        .map(|(key, value)| (key, value.triple()))
                        .collect();
                }
                "iceblocks" => {
                    extra.iceblocks = v.object().into_iter()
                        .map(|(key, value)| (key, value.pair()))
                        .collect();
                }
                "tomes" => {
                    extra.tomes = v.object().into_iter()
                        .map(|(key, value)| (key, value.number()))
                        .collect();
                }
                _ => extra.unknown.push((key, self.value(v))),
            }
        }
        extra
    }

    // traps.py:84-110,149-342. Unknown keys use the ordered generic JSON fallback.
    fn trap_extra(&self, n: Node<'_>) -> TrapExtra {
        let mut extra = TrapExtra::default();
        for (key, v) in n.object() {
            match key.as_str() {
                "count" => extra.count = v.usize(),
                "skel_level" => extra.skel_level = v.integer(),
                "capacity" => extra.capacity = v.number(),
                "time" => extra.time = v.number(),
                "pulses" => extra.pulses = v.usize(),
                "housing" => extra.housing = v.number(),
                "trigger_unit" => extra.trigger_unit = self.optional_unit_ref(v),
                "state" => extra.state = v.optional_string(),
                "projectile" => extra.projectile = v.optional_pair(),
                _ => extra.unknown.push((key, self.value(v))),
            }
        }
        extra
    }

    // traps.py:313-369; defense.py:1126-1140,1229. Unknown keys use the ordered generic
    // JSON fallback.
    fn field_extra(&self, n: Node<'_>) -> FieldExtra {
        let mut extra = FieldExtra::default();
        for (key, v) in n.object() {
            match key.as_str() {
                "pulses" => extra.pulses = v.usize(),
                "delivered" => extra.delivered = v.usize(),
                "gap" => extra.gap = v.optional_number(),
                "atk" => extra.atk = v.number(),
                "speed" => extra.speed = v.optional_number(),
                "slow" => extra.slow = v.number(),
                "ramp" => extra.ramp = v.boolean(),
                "origin" => extra.origin = v.optional_string(),
                "hero_mult" => extra.hero_mult = v.number(),
                "next_apply" => extra.next_apply = v.optional_number(),
                "source" => extra.source = v.optional_source(),
                _ => extra.unknown.push((key, self.value(v))),
            }
        }
        extra
    }

    // battle.py:778-785,960-1075; units.py:1762-1790. Unknown keys use the ordered generic
    // JSON fallback.
    fn pending_extra(&self, n: Node<'_>) -> PendingExtra {
        let mut extra = PendingExtra::default();
        for (key, v) in n.object() {
            match key.as_str() {
                "direct" => extra.direct = v.boolean(),
                "origin" => extra.origin = v.optional_pair(),
                "min_range" => extra.min_range = v.number(),
                "max_range" => extra.max_range = v.number(),
                "push" => extra.push = v.number(),
                "push_housing" => extra.push_housing = v.number(),
                "buildings" => extra.buildings = v.number(),
                "track" => extra.track = self.optional_ref(v),
                "healing" => extra.healing = v.optional_number(),
                "poison" => extra.poison = self.poison_config(v),
                "troop_impact" => extra.troop_impact = v.optional_string(),
                "direction" => extra.direction = v.optional_pair(),
                "travel" => extra.travel = v.number(),
                "speed" => extra.speed = v.number(),
                "hit" => extra.hit = v.array().into_iter().map(|item| self.reference(item)).collect(),
                _ => extra.unknown.push((key, self.value(v))),
            }
        }
        extra
    }

    fn building(&self, n: Node<'_>) -> Building {
        n.require_type("Building");
        n.keys(&[
            "id",
            "key",
            "name",
            "kind",
            "x",
            "y",
            "size",
            "half_hit",
            "hp",
            "max_hp",
            "alive",
            "counted",
            "is_defense",
            "weapon",
            "mode",
            "level",
            "frozen_until",
            "stun_until",
            "overgrown_until",
            "invisible_until",
            "atk_slow_until",
            "atk_slow",
            "rage_until",
            "rage_mult",
            "eq_hits",
            "revealed",
            "active",
            "last_hit",
            "extra",
        ]);
        let result = Building {
            id: BuildingId(n.field("id").usize()),
            key: n.field("key").string(),
            name: n.field("name").string(),
            kind: n.field("kind").string(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            size: n.field("size").usize(),
            half_hit: n.field("half_hit").number(),
            hp: n.field("hp").number(),
            max_hp: n.field("max_hp").number(),
            alive: n.field("alive").boolean(),
            counted: n.field("counted").boolean(),
            is_defense: n.field("is_defense").boolean(),
            weapon: if n.field("weapon").value.is_null() {
                None
            } else {
                Some(self.weapon(n.field("weapon")))
            },
            mode: n.field("mode").optional_string(),
            level: n.field("level").optional_level(),
            frozen_until: n.field("frozen_until").number(),
            stun_until: n.field("stun_until").number(),
            overgrown_until: n.field("overgrown_until").number(),
            invisible_until: n.field("invisible_until").number(),
            atk_slow_until: n.field("atk_slow_until").number(),
            atk_slow: n.field("atk_slow").number(),
            rage_until: n.field("rage_until").number(),
            rage_mult: n.field("rage_mult").number(),
            eq_hits: n.field("eq_hits").usize(),
            revealed: n.field("revealed").boolean(),
            active: n.field("active").boolean(),
            last_hit: n.field("last_hit").number(),
            extra: self.building_extra(n.field("extra")),
        };
        if result.weapon.as_ref().is_some_and(|weapon| weapon.owner != result.id) {
            n.field("weapon").field("owner").fail("weapon owner disagrees with building id");
        }
        if result.key == "bh" && result.weapon.is_some() {
            n.field("weapon").field("extra").require_fields(&["repair", "repair_range"]);
        }
        result
    }

    fn wall(&self, n: Node<'_>, id: WallId) -> Wall {
        n.require_type("Wall");
        n.keys(&[
            "tx",
            "ty",
            "x",
            "y",
            "hp",
            "max_hp",
            "alive",
            "half_hit",
            "eq_hits",
            "key",
            "id",
        ]);
        let identity = n.field("id").tuple(3);
        if identity[0].string() != "wall"
            || identity[1].i32() != n.field("tx").i32()
            || identity[2].i32() != n.field("ty").i32() {
            n.field("id").fail("wall identity disagrees with coordinates");
        }
        let result = Wall {
            id,
            tx: n.field("tx").i32(),
            ty: n.field("ty").i32(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            hp: n.field("hp").number(),
            max_hp: n.field("max_hp").number(),
            alive: n.field("alive").boolean(),
            half_hit: n.field("half_hit").number(),
            eq_hits: n.field("eq_hits").usize(),
            key: n.field("key").string(),
        };
        result
    }

    fn weapon(&self, n: Node<'_>) -> Weapon {
        n.require_type("Weapon");
        // defense.py:225-448: required setup keys have no Python absent-key default.
        let extra = n.field("extra");
        let required: &[&str] = match n.field("kind").string().as_str() {
            "splash" => &["splash"],
            "mortar" => &["splash", "flight"],
            "ricochet" => &["bounce", "bounce_range"],
            "inferno_single" => &["ramp"],
            "inferno_multi" => &["targets"],
            "giga_inferno" => &["dps", "targets", "range", "death", "death_radius",
                "poison_dps", "poison_time", "slow"],
            "inferno_artillery" => &["range", "targets", "interval", "damage", "pool_dps",
                "pool_time", "pool_radius", "pool_gap", "pool_hits"],
            "eagle" => &["activation", "shells", "gap", "shock", "splash", "shock_radius"],
            "scatter" => &["splash_max", "splash_min"],
            "monolith" => &["pct"],
            "sweeper" => &["push"],
            "burst" => &["shots", "gap"],
            "firespitter" => &["shots", "gap", "pierce", "arc"],
            "super_wizard" => &["secondary", "chain", "chain_range"],
            "cake" => &["splash", "bomb", "bomb_radius", "bomb_delay"],
            "candle" => &["targets", "melt1", "melt2"],
            "hunter" => &["poison_level", "poison_time"],
            "hook" => &["stun"],
            _ => &[],
        };
        extra.require_fields(required);
        n.keys(&[
            "owner",
            "kind",
            "targets",
            "range",
            "min_range",
            "interval",
            "damage",
            "cooldown",
            "target",
            "multi",
            "lock_time",
            "idle_until",
            "facing",
            "mode",
            "extra",
            "burst_left",
            "ammunition",
            "ammo_time",
        ]);
        let result = Weapon {
            owner: self.building_ref(n.field("owner")),
            kind: n.field("kind").string(),
            targets: n.field("targets").string(),
            range: n.field("range").number(),
            min_range: n.field("min_range").number(),
            interval: n.field("interval").number(),
            damage: n.field("damage").number(),
            cooldown: n.field("cooldown").number(),
            target: self.optional_unit_ref(n.field("target")),
            multi: n.field("multi").array().into_iter().map(|v| self.unit_ref(v)).collect(),
            lock_time: n.field("lock_time").number(),
            idle_until: n.field("idle_until").number(),
            facing: n.field("facing").number(),
            mode: n.field("mode").optional_string(),
            extra: self.weapon_extra(n.field("extra")),
            burst_left: n.field("burst_left").integer(),
            ammunition: n.field("ammunition").optional_integer(),
            ammo_time: n.field("ammo_time").number(),
        };
        result
    }

    fn unit(&self, n: Node<'_>) -> Unit {
        n.require_type("Unit");
        n.keys(&[
            "id",
            "name",
            "kind",
            "team",
            "level",
            "x",
            "y",
            "hp",
            "max_hp",
            "base_max_hp",
            "dmg",
            "interval",
            "range",
            "speed",
            "housing",
            "flying",
            "hits_air",
            "hits_ground",
            "spec",
            "alive",
            "cooldown",
            "target",
            "target_kind",
            "wall_target",
            "group",
            "spawned_at",
            "active_at",
            "stuck",
            "frozen_until",
            "stun_until",
            "held_until",
            "invisible_until",
            "invuln_until",
            "move_slow",
            "move_slow_until",
            "atk_slow",
            "atk_slow_until",
            "rage_dmg",
            "rage_spd",
            "rage_until",
            "haste_spd",
            "haste_until",
            "iceblock_red",
            "iceblock_until",
            "dmg_taken_mult",
            "dmg_taken_until",
            "aura_bonus",
            "aura_dmg",
            "underground",
            "aware_until",
            "last_hit",
            "poison_stack",
            "is_hero",
            "kit",
            "pet",
            "owner",
            "follow",
            "home",
            "leash",
            "ability_used",
            "decay",
            "dash",
            "extra",
            "damage_dealt",
        ]);
        let result = Unit {
            id: UnitId(n.field("id").usize()),
            name: n.field("name").string(),
            kind: n.field("kind").string(),
            team: n.field("team").team(),
            level: n.field("level").optional_level(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            hp: n.field("hp").number(),
            max_hp: n.field("max_hp").number(),
            base_max_hp: n.field("base_max_hp").number(),
            dmg: n.field("dmg").number(),
            interval: n.field("interval").number(),
            range: n.field("range").number(),
            speed: n.field("speed").number(),
            housing: n.field("housing").integer(),
            flying: n.field("flying").boolean(),
            hits_air: n.field("hits_air").boolean(),
            hits_ground: n.field("hits_ground").boolean(),
            spec: UnitSpec::load(n.field("spec")),
            alive: n.field("alive").boolean(),
            cooldown: n.field("cooldown").number(),
            target: self.optional_ref(n.field("target")),
            target_kind: n.field("target_kind").optional_string(),
            wall_target: self.optional_wall_ref(n.field("wall_target")),
            group: n.field("group").string(),
            spawned_at: n.field("spawned_at").number(),
            active_at: n.field("active_at").number(),
            stuck: n.field("stuck").number(),
            frozen_until: n.field("frozen_until").number(),
            stun_until: n.field("stun_until").number(),
            held_until: n.field("held_until").number(),
            invisible_until: n.field("invisible_until").number(),
            invuln_until: n.field("invuln_until").number(),
            move_slow: n.field("move_slow").number(),
            move_slow_until: n.field("move_slow_until").number(),
            atk_slow: n.field("atk_slow").number(),
            atk_slow_until: n.field("atk_slow_until").number(),
            rage_dmg: n.field("rage_dmg").number(),
            rage_spd: n.field("rage_spd").number(),
            rage_until: n.field("rage_until").number(),
            haste_spd: n.field("haste_spd").number(),
            haste_until: n.field("haste_until").number(),
            iceblock_red: n.field("iceblock_red").number(),
            iceblock_until: n.field("iceblock_until").number(),
            dmg_taken_mult: n.field("dmg_taken_mult").number(),
            dmg_taken_until: n.field("dmg_taken_until").number(),
            aura_bonus: n.field("aura_bonus").number(),
            aura_dmg: n.field("aura_dmg").number(),
            underground: n.field("underground").boolean(),
            aware_until: n.field("aware_until").number(),
            last_hit: n.field("last_hit").number(),
            poison_stack: n.field("poison_stack").usize(),
            is_hero: n.field("is_hero").boolean(),
            kit: self.optional_value(n.field("kit")),
            pet: self.optional_unit_ref(n.field("pet")),
            owner: self.optional_unit_ref(n.field("owner")),
            follow: self.optional_unit_ref(n.field("follow")),
            home: n.field("home").optional_pair(),
            leash: n.field("leash").number(),
            ability_used: n.field("ability_used").boolean(),
            decay: n.field("decay").number(),
            dash: self.optional_value(n.field("dash")),
            extra: self.unit_extra(n.field("extra")),
            damage_dealt: n.field("damage_dealt").number(),
            in_pool: true,
        };
        result
    }

    fn trap(&self, n: Node<'_>, id: TrapId) -> Trap {
        n.require_type("Trap");
        // traps.py:95-110: these are supplied by make_trap(), not Rust setup.
        let required: &[&str] = match n.field("key").string().as_str() {
            "skeleton" => &["count", "skel_level"],
            "spring" => &["capacity"],
            "tornado" => &["time", "pulses"],
            "giga" => &["housing"],
            _ => &[],
        };
        n.field("extra").require_fields(required);
        n.keys(&[
            "key",
            "name",
            "x",
            "y",
            "level",
            "trigger",
            "radius",
            "damage",
            "air",
            "ground",
            "armed",
            "fuse_at",
            "mode",
            "extra",
        ]);
        let result = Trap {
            id,
            key: n.field("key").string(),
            name: n.field("name").string(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            level: n.field("level").level(),
            trigger: n.field("trigger").number(),
            radius: n.field("radius").number(),
            damage: n.field("damage").number(),
            air: n.field("air").boolean(),
            ground: n.field("ground").boolean(),
            armed: n.field("armed").boolean(),
            fuse_at: n.field("fuse_at").number(),
            mode: n.field("mode").optional_string(),
            extra: self.trap_extra(n.field("extra")),
        };
        result
    }

    fn field(&self, n: Node<'_>) -> Field {
        n.require_type("Field");
        n.keys(&["kind", "x", "y", "radius", "until", "team", "value", "extra", "started"]);
        let result = Field {
            kind: n.field("kind").string(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            radius: n.field("radius").number(),
            until: n.field("until").number(),
            team: n.field("team").team(),
            value: n.field("value").number(),
            extra: self.field_extra(n.field("extra")),
            started: n.field("started").number(),
        };
        result
    }

    fn pending(&self, n: Node<'_>) -> Pending {
        n.require_type("Pending");
        n.keys(&[
            "at",
            "x",
            "y",
            "radius",
            "damage",
            "hits_air",
            "hits_ground",
            "src",
            "falloff",
            "team",
            "extra",
            "actor",
            "effect",
            "target",
            "released_at",
        ]);
        let result = Pending {
            at: n.field("at").number(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            radius: n.field("radius").number(),
            damage: n.field("damage").number(),
            hits_air: n.field("hits_air").boolean(),
            hits_ground: n.field("hits_ground").boolean(),
            src: n.field("src").string(),
            falloff: n.field("falloff").boolean(),
            team: n.field("team").team(),
            extra: self.pending_extra(n.field("extra")),
            actor: self.optional_ref(n.field("actor")),
            effect: n.field("effect").optional_string(),
            target: self.optional_ref(n.field("target")),
            released_at: n.field("released_at").optional_number(),
        };
        result
    }

    fn builder(&self, n: Node<'_>) -> Builder {
        n.require_type("Builder");
        n.keys(&[
            "owner",
            "x",
            "y",
            "target",
            "cooldown",
            "frozen_until",
            "stun_until",
            "repair_slow",
            "slow_until",
            "rage_until",
            "rage_speed",
            "repair_boost",
        ]);
        let result = Builder {
            owner: self.building_ref(n.field("owner")),
            x: n.field("x").number(),
            y: n.field("y").number(),
            target: self.optional_building_ref(n.field("target")),
            cooldown: n.field("cooldown").number(),
            frozen_until: n.field("frozen_until").number(),
            stun_until: n.field("stun_until").number(),
            repair_slow: n.field("repair_slow").number(),
            slow_until: n.field("slow_until").number(),
            rage_until: n.field("rage_until").number(),
            rage_speed: n.field("rage_speed").number(),
            repair_boost: n.field("repair_boost").number(),
        };
        result
    }

    fn deployment(&self, n: Node<'_>) -> Deployment {
        n.require_type("Deployment");
        n.keys(&["time", "name", "x", "y", "group", "level", "town_hall", "source", "mode"]);
        let result = Deployment {
            time: n.field("time").number(),
            name: n.field("name").string(),
            x: n.field("x").number(),
            y: n.field("y").number(),
            group: n.field("group").string(),
            level: n.field("level").optional_level(),
            town_hall: n.field("town_hall").optional_integer(),
            source: n.field("source").string(),
            mode: n.field("mode").optional_string(),
        };
        result
    }

    fn cargo(&self, n: Node<'_>) -> CargoEntry {
        let unknown = n.object().into_iter()
            .filter(|(key, _)| !["name", "level", "source"].contains(&key.as_str()))
            .map(|(key, value)| (key, self.value(value))).collect();
        CargoEntry {
            name: n.field("name").string(),
            level: n.field("level").level(),
            source: n.field("source").string(),
            unknown,
        }
    }
}

fn tiles(n: Node<'_>) -> std::collections::HashSet<(i32, i32)> {
    n.array().into_iter().map(|item| {
        let pair = item.tuple(2);
        (pair[0].i32(), pair[1].i32())
    }).collect()
}

fn levels(n: Node<'_>) -> Vec<(String, Level)> {
    n.object().into_iter().map(|(key, value)| (key, value.level())).collect()
}

pub fn from_json(value: &Json, catalog: Rc<Catalog>, path: &str) -> Battle {
    let root = Node::new(value, path);
    root.keys(&[
        "rng_state",
        "env",
        "scalars",
        "buildings",
        "walls",
        "traps",
        "attackers",
        "defenders",
        "fields",
        "pending",
        "deployments",
        "plan",
        "plan_type",
    ]);
    let resolver = Resolver::new(&root);
    // Validate tags/references even in fields retained by a generic fallback.
    resolver.value(root.clone());
    let s = root.field("scalars");
    let buildings: Vec<_> = root.field("buildings").array().into_iter()
        .map(|n| resolver.building(n)).collect();
    let walls: Vec<_> = root.field("walls").array().into_iter().enumerate()
        .map(|(index, n)| resolver.wall(n, WallId(index))).collect();
    let traps = root.field("traps").array().into_iter().enumerate()
        .map(|(index, n)| resolver.trap(n, TrapId(index))).collect();
    let attackers = root.field("attackers").array().into_iter()
        .map(|n| resolver.unit(n)).collect();
    let defenders = root.field("defenders").array().into_iter()
        .map(|n| resolver.unit(n)).collect();
    let fields = root.field("fields").array().into_iter()
        .map(|n| resolver.field(n)).collect();
    let pending = root.field("pending").array().into_iter()
        .map(|n| resolver.pending(n)).collect();
    let deployments: Vec<_> = root.field("deployments").array().into_iter()
        .map(|n| resolver.deployment(n)).collect();
    if deployments.windows(2).any(|pair| pair[1].time < pair[0].time) {
        root.field("deployments").fail("deployments must retain Python's stable time order");
    }
    let p = root.field("plan");
    if root.field("plan_type").string() != "Stage" {
        root.field("plan_type").fail("unsupported plan (TASK 1a supports Stage)");
    }
    p.require_type("Stage");
    p.keys(&["drops", "ticks", "town_hall", "strength", "loadouts", "revives_left"]);
    for drop in p.field("drops").array() {
        let parts = drop.tuple(5);
        parts[0].number();
        parts[1].string();
        parts[2].number();
        parts[3].number();
        let _ = parts[4].optional_level();
    }
    if !p.field("ticks").array().is_empty() || !p.field("loadouts").object().is_empty()
        || p.field("revives_left").integer() != 0 {
        p.fail("Stage callbacks, hero loadouts and revives are unsupported in stage 1");
    }
    let plan = Plan::Stage {
        deployments: deployments.clone(),
        town_hall: p.field("town_hall").integer(),
        strength: p.field("strength").number(),
    };
    let mut grid = Grid::new(catalog.world);
    // battle.py:248-281: dead banners never block. Walls are restored in file order.
    for building in &buildings {
        if building.alive {
            grid.block_square(building.x, building.y, building.half_hit, true);
        }
    }
    for wall in &walls {
        grid.set_wall(wall.tx, wall.ty, wall.alive);
    }
    let nd_version = s.field("_nd_version").optional_integer().map(|version| {
        u64::try_from(version).unwrap_or_else(|_| s.field("_nd_version").fail("negative grid version"))
    });
    // The cache itself is excluded from the export. Recompute it on first use.
    let no_deploy = tiles(s.field("no_deploy"));
    // The Python process's switches (BASELAB_DT, BASELAB_FAST_END, ...) are
    // exported with the battle so both engines run the same settings.
    let env = root.field("env");
    let dt = env.field("dt").number();
    assert!(dt.is_finite() && dt > 0.0, "env.dt must be finite and positive");
    // random.Random.getstate()[1]: 624 state words, then the index.
    let words: Vec<u32> = root
        .field("rng_state")
        .array()
        .iter()
        .map(|w| u32::try_from(w.integer()).unwrap_or_else(|_| w.fail("rng word out of range")))
        .collect();
    let mut battle = Battle {
        catalog,
        rng: Some(PyRandom::from_state(&words)),
        dt,
        fast_end: env.field("fast_end").boolean(),
        modifier: s.field("modifier").optional_string(),
        def_mult: s.field("def_mult").number(),
        def_hero_mult: s.field("def_hero_mult").number(),
        guardian_mult: s.field("guardian_mult").number(),
        atk_hero_mult: s.field("atk_hero_mult").number(),
        portal_stash: s.field("portal_stash").array().into_iter().map(|n| resolver.value(n)).collect(),
        first_destroy_t: s.field("first_destroy_t").optional_number(),
        first_deploy_t: s.field("first_deploy_t").optional_number(),
        defense_ammo: resolver.map(s.field("defense_ammo")),
        allow_synthetic_cc: s.field("allow_synthetic_cc").boolean(),
        battle_mode: s.field("battle_mode").string(),
        upgrading: s.field("upgrading").array().into_iter().map(|n| resolver.value(n)).collect(),
        crafting_phase: s.field("crafting_phase").integer(),
        crafting_date: s.field("crafting_date").string(),
        builders: s.field("builders").array().into_iter().map(|n| resolver.builder(n)).collect(),
        builder_starts: s.field("builder_starts").object().into_iter()
            .map(|(key, n)| (key, n.pair()))
            .collect(),
        portal_ready_at: s.field("portal_ready_at").number(),
        t: s.field("t").number(),
        scouting: s.field("scouting").boolean(),
        scout_time: s.field("scout_time").number(),
        ended: s.field("ended").boolean(),
        town_hall: s.field("town_hall").integer(),
        record: s.field("record").boolean(),
        max_time: s.field("max_time").number(),
        log: Vec::new(),
        frames: Vec::new(),
        grid,
        buildings,
        walls,
        traps,
        attackers,
        defenders,
        fields,
        pending,
        deployed_housing: s.field("deployed_housing").integer(),
        monolith_housing: s.field("monolith_housing").integer(),
        uid: s.field("_uid").usize(),
        cc_building: resolver.optional_building_ref(s.field("cc_building")),
        cc_queue: s.field("cc_queue").array().into_iter().map(|n| resolver.cargo(n)).collect(),
        cc_released: s.field("cc_released").boolean(),
        th: resolver.optional_building_ref(s.field("th")),
        th_on_at: s.field("_th_on_at").optional_number(),
        defense_levels: levels(s.field("defense_levels")),
        hero_levels: levels(s.field("hero_levels")),
        wall_level: s.field("wall_level").optional_level(),
        cc_level: levels(s.field("cc_level")),
        damage_by_source: s.field("damage_by_source").object().into_iter()
            .map(|(key, n)| (key, n.number()))
            .collect(),
        kills_by_source: s.field("kills_by_source").object().into_iter()
            .map(|(key, n)| (key, n.integer()))
            .collect(),
        src: s.field("_src").string(),
        src_obj: resolver.optional_ref(s.field("_src_obj")),
        effect: s.field("_effect").string(),
        poison: resolver.map(s.field("_poison")),
        clones: s.field("_clones").array().into_iter().map(|n| resolver.unit_ref(n)).collect(),
        total_counted: s.field("total_counted").usize(),
        destroyed_counted: s.field("destroyed_counted").usize(),
        banner_tiles: tiles(s.field("_banner_tiles")),
        nd_version,
        nd_cache: no_deploy.clone(),
        no_deploy,
        dt_version: None,
        dt_cache: Vec::new(),
        onboard_cargo: s.field("_onboard_cargo").array().into_iter().map(|n| resolver.cargo(n)).collect(),
        deployments,
        next_deploy: s.field("_next_deploy").usize(),
        next_cc_exit: s.optional("_next_cc_exit").map_or(0.0, |n| n.number()),
        field_serial: s.optional("_field_serial").map_or(0, |n| n.integer()),
        plan,
        building_indices: resolver.buildings.clone(),
        wall_indices: resolver.walls.clone(),
        unit_indices: resolver.units.clone(),
        buckets: Vec::new(),
        bucket_indices: HashMap::new(),
        unknown_scalars: Vec::new(),
    };
    let known_scalars = &[
        "modifier",
        "def_mult",
        "def_hero_mult",
        "guardian_mult",
        "atk_hero_mult",
        "portal_stash",
        "first_destroy_t",
        "first_deploy_t",
        "defense_ammo",
        "allow_synthetic_cc",
        "battle_mode",
        "upgrading",
        "crafting_phase",
        "crafting_date",
        "builders",
        "builder_starts",
        "portal_ready_at",
        "t",
        "scouting",
        "scout_time",
        "ended",
        "town_hall",
        "record",
        "max_time",
        "deployed_housing",
        "monolith_housing",
        "_uid",
        "cc_building",
        "cc_queue",
        "cc_released",
        "th",
        "_th_on_at",
        "defense_levels",
        "hero_levels",
        "wall_level",
        "cc_level",
        "damage_by_source",
        "kills_by_source",
        "_src",
        "_src_obj",
        "_effect",
        "_poison",
        "_clones",
        "total_counted",
        "destroyed_counted",
        "_banner_tiles",
        "_nd_version",
        "no_deploy",
        "_onboard_cargo",
        "_next_deploy",
        "_next_cc_exit",
        "_field_serial",
    ];
    for (key, node) in s.object() {
        if !known_scalars.contains(&key.as_str()) {
            battle.unknown_scalars.push((key, resolver.value(node)));
        }
    }
    if battle.nd_version != Some(battle.grid.version) {
        battle.nd_version = None;
    }
    if battle.next_deploy > battle.deployments.len() {
        s.field("_next_deploy").fail("deployment cursor outside list");
    }
    if battle.unit_indices.keys().any(|id| id.0 > battle.uid) {
        s.field("_uid").fail("shared unit counter precedes an exported unit id");
    }
    battle
}
