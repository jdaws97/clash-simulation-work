//! Ports entities.py:19-292, defense.py:17-57,1099-1111,
//! battle.py:148-210 and plans.py:128-137. Vec order is Python list/dict order.

use std::collections::{HashMap, HashSet};
use std::rc::Rc;

use crate::catalog::{Catalog, UnitSpec};
use crate::geom::edge_distance;
use crate::grid::Grid;
use crate::pyrandom::PyRandom;
use crate::stats::Level;
use crate::trace::LogValue;

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct BuildingId(pub usize);
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct WallId(pub usize);
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct UnitId(pub usize);
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct TrapId(pub usize);

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum Team {
    Atk,
    Def,
}

impl Team {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Atk => "atk",
            Self::Def => "def",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct UnitRef {
    pub id: UnitId,
    pub team: Team,
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum EntityRef {
    Building(BuildingId),
    Wall(WallId),
    Unit(UnitRef),
    Trap(TrapId),
}

// Generic JSON fallback, extended with resolved references. Ordered maps retain
// every unknown extra key for later stages; no exported state is discarded.
#[derive(Clone, Debug)]
pub enum Value {
    Null,
    Bool(bool),
    Number(f64),
    String(String),
    List(Vec<Value>),
    Map(Vec<(String, Value)>),
    Ref(EntityRef),
}

pub type ExtraMap = Vec<(String, Value)>;

// defense.py:547-554: the Town Hall's delayed death-poison configuration.
#[derive(Clone, Debug)]
pub struct PoisonConfig {
    pub dps: f64,
    pub time: Option<f64>,
    pub slow: Option<f64>,
    pub radius: Option<f64>,
    pub atk: Option<f64>,
    pub ramp: bool,
    pub hero_mult: f64,
    pub unknown: ExtraMap,
}

#[derive(Clone, Debug)]
pub enum WeaponTrigger {
    Radius(f64),
    UnitSince(UnitRef, f64),
}

#[derive(Clone, Debug)]
pub struct SpinPosition {
    pub first: BuildingId,
    pub second: BuildingId,
    pub position: (f64, f64),
}

// entities.py:66-72; battle.py:267,543; units.py:215-220: Python extra keys and their
// absent-key defaults.
#[derive(Clone, Debug)]
pub struct BuildingExtra {
    pub unavailable: bool,
    pub yellow_until: f64,
    pub rubble_taken: bool,
    pub rubble_claim: Option<UnitId>,
    pub unknown: ExtraMap,
}

impl Default for BuildingExtra {
    fn default() -> Self {
        Self {
            unavailable: false,
            yellow_until: 0.0,
            rubble_taken: false,
            rubble_claim: None,
            unknown: Vec::new(),
        }
    }
}

// defense.py:192-462,493-497,524-1409: Python extra keys and their absent-key defaults.
#[derive(Clone, Debug)]
pub struct WeaponExtra {
    pub splash: f64,
    pub flight: f64,
    pub death: f64,
    pub death_radius: f64,
    pub death_delay: f64,
    pub bounce: f64,
    pub bounce_range: f64,
    pub gap: f64,
    pub shock: f64,
    pub shock_radius: f64,
    pub splash_max: f64,
    pub splash_min: f64,
    pub pct: f64,
    pub push: f64,
    pub repair: f64,
    pub repair_range: f64,
    pub arc: f64,
    pub secondary: f64,
    pub chain_range: f64,
    pub bomb: f64,
    pub bomb_radius: f64,
    pub bomb_delay: f64,
    pub melt1: f64,
    pub melt2: f64,
    pub poison_time: f64,
    pub dps: f64,
    pub range: f64,
    pub slow: f64,
    pub poison_dps: f64,
    pub interval: f64,
    pub damage: f64,
    pub pool_dps: f64,
    pub pool_time: f64,
    pub pool_radius: f64,
    pub pool_gap: f64,
    pub stun: f64,
    pub targets: usize,
    pub activation: usize,
    pub shells: usize,
    pub shots: usize,
    pub pierce: usize,
    pub chain: usize,
    pub poison_level: usize,
    pub pool_hits: usize,
    pub same_type: bool,
    pub inner_min: Option<f64>,
    pub wake_at: Option<f64>,
    pub ramp: Vec<(f64, f64)>,
    pub trigger: Option<WeaponTrigger>,
    pub hit_triggers: Vec<(UnitRef, f64)>,
    pub unknown: ExtraMap,
}

impl Default for WeaponExtra {
    fn default() -> Self {
        Self {
            splash: 0.0,
            flight: 0.0,
            death: 0.0,
            death_radius: 0.0,
            death_delay: 0.0,
            bounce: 0.0,
            bounce_range: 0.0,
            gap: 0.0,
            shock: 0.0,
            shock_radius: 0.0,
            splash_max: 0.0,
            splash_min: 0.0,
            pct: 0.0,
            push: 0.0,
            repair: 0.0,
            repair_range: 0.0,
            arc: 0.0,
            secondary: 0.0,
            chain_range: 0.0,
            bomb: 0.0,
            bomb_radius: 0.0,
            bomb_delay: 0.0,
            melt1: 0.0,
            melt2: 0.0,
            poison_time: 0.0,
            dps: 0.0,
            range: 0.0,
            slow: 0.0,
            poison_dps: 0.0,
            interval: 0.0,
            damage: 0.0,
            pool_dps: 0.0,
            pool_time: 0.0,
            pool_radius: 0.0,
            pool_gap: 0.0,
            stun: 0.0,
            targets: 0,
            activation: 0,
            shells: 0,
            shots: 0,
            pierce: 0,
            chain: 0,
            poison_level: 0,
            pool_hits: 0,
            same_type: false,
            inner_min: None,
            wake_at: None,
            ramp: Vec::new(),
            trigger: None,
            hit_triggers: Vec::new(),
            unknown: Vec::new(),
        }
    }
}

// entities.py:182-237; battle.py:445-1737; units.py:1200-1253,2003-2037; effects.py:31-74:
// Python extra keys and their absent-key defaults.
#[derive(Clone, Debug)]
pub struct UnitExtra {
    pub yellow_until: f64,
    pub brainwash_until: f64,
    pub armor_hp: f64,
    pub aura_hp: f64,
    pub troop_hit_at: f64,
    pub next_engage: f64,
    pub next_retarget: f64,
    pub tornado_wall_until: f64,
    pub angry_until: f64,
    pub jump_until: f64,
    pub horse_until: f64,
    pub horse_speed: f64,
    pub horse_interval: f64,
    pub horse_attack: f64,
    pub haste_attack_until: f64,
    pub haste_attack: f64,
    pub vial_until: f64,
    pub vial_bonus: f64,
    pub gauntlet_until: f64,
    pub gauntlet_radius: f64,
    pub bell_health: f64,
    pub bell_damage: f64,
    pub bell_damage_until: f64,
    pub expire_at: f64,
    pub expires_at: f64,
    pub attack_ready_at: f64,
    pub next_blocker_check: f64,
    pub suspended: bool,
    pub leaping: bool,
    pub sprung: bool,
    pub preferred_remaining: bool,
    pub finish_preferred: bool,
    pub warden_group: bool,
    pub clone: bool,
    pub mirror_clone: bool,
    pub suicided: bool,
    pub facing: (f64, f64),
    pub heading: Option<(f64, f64)>,
    pub deployment_source: Option<String>,
    pub recalled: Option<Value>,
    pub last_damage_source: Option<EntityRef>,
    pub pushed_at: Option<f64>,
    pub patrol_state: Option<String>,
    pub spin_position: Option<SpinPosition>,
    pub attack_target: Option<EntityRef>,
    pub burst_target: Option<EntityRef>,
    pub beam_target: Option<EntityRef>,
    pub beam_time: Option<f64>,
    pub beam_tick: Option<f64>,
    pub long_shots: i64,
    pub burst_left: i64,
    pub eq_n: usize,
    pub burn_tick: Option<f64>,
    pub rage_effects: Vec<(String, (f64, f64, f64))>,
    pub haste_effects: Vec<(String, (f64, f64))>,
    pub slows: Vec<(String, (f64, f64, f64))>,
    pub torches: Vec<(String, (f64, f64, f64))>,
    pub iceblocks: Vec<(String, (f64, f64))>,
    pub tomes: Vec<(String, f64)>,
    pub unknown: ExtraMap,
}

impl Default for UnitExtra {
    fn default() -> Self {
        Self {
            yellow_until: 0.0,
            brainwash_until: 0.0,
            armor_hp: 0.0,
            aura_hp: 0.0,
            troop_hit_at: f64::NEG_INFINITY,
            next_engage: 0.0,
            next_retarget: 0.0,
            tornado_wall_until: 0.0,
            angry_until: 0.0,
            jump_until: 0.0,
            horse_until: 0.0,
            horse_speed: 0.0,
            horse_interval: 0.0,
            horse_attack: 0.0,
            haste_attack_until: 0.0,
            haste_attack: 0.0,
            vial_until: 0.0,
            vial_bonus: 0.0,
            gauntlet_until: 0.0,
            gauntlet_radius: 0.0,
            bell_health: 1.0,
            bell_damage: 1.0,
            bell_damage_until: 0.0,
            expire_at: f64::INFINITY,
            expires_at: f64::INFINITY,
            attack_ready_at: 0.0,
            next_blocker_check: 0.0,
            suspended: false,
            leaping: false,
            sprung: false,
            preferred_remaining: false,
            finish_preferred: false,
            warden_group: false,
            clone: false,
            mirror_clone: false,
            suicided: false,
            facing: (0.0, 0.0),
            heading: None,
            deployment_source: None,
            recalled: None,
            last_damage_source: None,
            pushed_at: None,
            patrol_state: None,
            spin_position: None,
            attack_target: None,
            burst_target: None,
            beam_target: None,
            beam_time: None,
            beam_tick: None,
            long_shots: 0,
            burst_left: 0,
            eq_n: 0,
            burn_tick: None,
            rage_effects: Vec::new(),
            haste_effects: Vec::new(),
            slows: Vec::new(),
            torches: Vec::new(),
            iceblocks: Vec::new(),
            tomes: Vec::new(),
            unknown: Vec::new(),
        }
    }
}

// traps.py:84-110,149-342: Python extra keys and their absent-key defaults.
#[derive(Clone, Debug)]
pub struct TrapExtra {
    pub count: usize,
    pub skel_level: i64,
    pub capacity: f64,
    pub time: f64,
    pub pulses: usize,
    pub housing: f64,
    pub trigger_unit: Option<UnitRef>,
    pub state: Option<String>,
    pub projectile: Option<(f64, f64)>,
    pub unknown: ExtraMap,
}

impl Default for TrapExtra {
    fn default() -> Self {
        Self {
            count: 0,
            skel_level: 0,
            capacity: 0.0,
            time: 0.0,
            pulses: 0,
            housing: 0.0,
            trigger_unit: None,
            state: None,
            projectile: None,
            unknown: Vec::new(),
        }
    }
}

// traps.py:313-369; defense.py:1126-1140,1229: Python extra keys and their absent-key defaults.
#[derive(Clone, Debug)]
pub struct FieldExtra {
    pub pulses: usize,
    pub delivered: usize,
    pub gap: Option<f64>,
    pub atk: f64,
    pub speed: Option<f64>,
    pub slow: f64,
    pub ramp: bool,
    pub origin: Option<String>,
    pub hero_mult: f64,
    pub next_apply: Option<f64>,
    pub source: Option<(String, i64)>,
    pub unknown: ExtraMap,
}

impl Default for FieldExtra {
    fn default() -> Self {
        Self {
            pulses: 0,
            delivered: 0,
            gap: None,
            atk: 0.0,
            speed: None,
            slow: 0.0,
            ramp: false,
            origin: None,
            hero_mult: 1.0,
            next_apply: None,
            source: None,
            unknown: Vec::new(),
        }
    }
}

// battle.py:778-785,960-1075; units.py:1762-1790: Python extra keys and their absent-key defaults.
#[derive(Clone, Debug)]
pub struct PendingExtra {
    pub direct: bool,
    pub origin: Option<(f64, f64)>,
    pub min_range: f64,
    pub max_range: f64,
    pub push: f64,
    pub push_housing: f64,
    pub buildings: f64,
    pub track: Option<EntityRef>,
    pub healing: Option<f64>,
    pub poison: Option<PoisonConfig>,
    pub troop_impact: Option<String>,
    pub direction: Option<(f64, f64)>,
    pub travel: f64,
    pub speed: f64,
    pub hit: Vec<EntityRef>,
    pub unknown: ExtraMap,
}

impl Default for PendingExtra {
    fn default() -> Self {
        Self {
            direct: false,
            origin: None,
            min_range: 0.0,
            max_range: 0.0,
            push: 0.0,
            push_housing: 0.0,
            buildings: 0.0,
            track: None,
            healing: None,
            poison: None,
            troop_impact: None,
            direction: None,
            travel: 0.0,
            speed: 0.0,
            hit: Vec::new(),
            unknown: Vec::new(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct Building {
    pub id: BuildingId,
    pub key: String,
    pub name: String,
    pub kind: String,
    pub x: f64,
    pub y: f64,
    pub size: usize,
    pub half_hit: f64,
    pub hp: f64,
    pub max_hp: f64,
    pub alive: bool,
    pub counted: bool,
    pub is_defense: bool,
    pub weapon: Option<Weapon>,
    pub mode: Option<String>,
    pub level: Option<Level>,
    pub frozen_until: f64,
    pub stun_until: f64,
    pub overgrown_until: f64,
    pub invisible_until: f64,
    pub atk_slow_until: f64,
    pub atk_slow: f64,
    pub rage_until: f64,
    pub rage_mult: f64,
    pub eq_hits: usize,
    pub revealed: bool,
    pub active: bool,
    pub last_hit: f64,
    pub extra: BuildingExtra,
}

#[derive(Clone, Debug)]
pub struct Wall {
    pub id: WallId,
    pub tx: i32,
    pub ty: i32,
    pub x: f64,
    pub y: f64,
    pub hp: f64,
    pub max_hp: f64,
    pub alive: bool,
    pub half_hit: f64,
    pub eq_hits: usize,
    pub key: String,
}

#[derive(Clone, Debug)]
pub struct Weapon {
    pub owner: BuildingId,
    pub kind: String,
    pub targets: String,
    pub range: f64,
    pub min_range: f64,
    pub interval: f64,
    pub damage: f64,
    pub cooldown: f64,
    pub target: Option<UnitRef>,
    pub multi: Vec<UnitRef>,
    pub lock_time: f64,
    pub idle_until: f64,
    pub facing: f64,
    pub mode: Option<String>,
    pub extra: WeaponExtra,
    pub burst_left: i64,
    pub ammunition: Option<i64>,
    pub ammo_time: f64,
}

#[derive(Clone, Debug)]
pub struct Unit {
    pub id: UnitId,
    pub name: String,
    pub kind: String,
    pub team: Team,
    pub level: Option<Level>,
    pub x: f64,
    pub y: f64,
    pub hp: f64,
    pub max_hp: f64,
    pub base_max_hp: f64,
    pub dmg: f64,
    pub interval: f64,
    pub range: f64,
    pub speed: f64,
    pub housing: i64,
    pub flying: bool,
    pub hits_air: bool,
    pub hits_ground: bool,
    pub spec: UnitSpec,
    pub alive: bool,
    pub cooldown: f64,
    pub target: Option<EntityRef>,
    pub target_kind: Option<String>,
    pub wall_target: Option<WallId>,
    pub group: String,
    pub spawned_at: f64,
    pub active_at: f64,
    pub stuck: f64,
    pub frozen_until: f64,
    pub stun_until: f64,
    pub held_until: f64,
    pub invisible_until: f64,
    pub invuln_until: f64,
    pub move_slow: f64,
    pub move_slow_until: f64,
    pub atk_slow: f64,
    pub atk_slow_until: f64,
    pub rage_dmg: f64,
    pub rage_spd: f64,
    pub rage_until: f64,
    pub haste_spd: f64,
    pub haste_until: f64,
    pub iceblock_red: f64,
    pub iceblock_until: f64,
    pub dmg_taken_mult: f64,
    pub dmg_taken_until: f64,
    pub aura_bonus: f64,
    pub aura_dmg: f64,
    pub underground: bool,
    pub aware_until: f64,
    pub last_hit: f64,
    pub poison_stack: usize,
    pub is_hero: bool,
    pub kit: Option<Value>,
    pub pet: Option<UnitRef>,
    pub owner: Option<UnitRef>,
    pub follow: Option<UnitRef>,
    pub home: Option<(f64, f64)>,
    pub leash: f64,
    pub ability_used: bool,
    pub decay: f64,
    pub dash: Option<Value>,
    pub extra: UnitExtra,
    pub damage_dealt: f64,
    // battle.py:940-947: tombstones preserve references after list pruning.
    pub in_pool: bool,
}

#[derive(Clone, Debug)]
pub struct Trap {
    pub id: TrapId,
    pub key: String,
    pub name: String,
    pub x: f64,
    pub y: f64,
    pub level: Level,
    pub trigger: f64,
    pub radius: f64,
    pub damage: f64,
    pub air: bool,
    pub ground: bool,
    pub armed: bool,
    pub fuse_at: f64,
    pub mode: Option<String>,
    pub extra: TrapExtra,
}

#[derive(Clone, Debug)]
pub struct Field {
    pub kind: String,
    pub x: f64,
    pub y: f64,
    pub radius: f64,
    pub until: f64,
    pub team: Team,
    pub value: f64,
    pub extra: FieldExtra,
    pub started: f64,
}

#[derive(Clone, Debug)]
pub struct Pending {
    pub at: f64,
    pub x: f64,
    pub y: f64,
    pub radius: f64,
    pub damage: f64,
    pub hits_air: bool,
    pub hits_ground: bool,
    pub src: String,
    pub falloff: bool,
    pub team: Team,
    pub extra: PendingExtra,
    pub actor: Option<EntityRef>,
    pub effect: Option<String>,
    pub target: Option<EntityRef>,
    pub released_at: Option<f64>,
}

#[derive(Clone, Debug)]
pub struct Builder {
    pub owner: BuildingId,
    pub x: f64,
    pub y: f64,
    pub target: Option<BuildingId>,
    pub cooldown: f64,
    pub frozen_until: f64,
    pub stun_until: f64,
    pub repair_slow: f64,
    pub slow_until: f64,
    pub rage_until: f64,
    pub rage_speed: f64,
    pub repair_boost: f64,
}

#[derive(Clone, Debug)]
pub struct Deployment {
    pub time: f64,
    pub name: String,
    pub x: f64,
    pub y: f64,
    pub group: String,
    pub level: Option<Level>,
    pub town_hall: Option<i64>,
    pub source: String,
    pub mode: Option<String>,
}

impl Building {
    pub fn edge_distance(&self, x: f64, y: f64) -> f64 {
        edge_distance(x, y, self.x, self.y, self.half_hit)
    }

    pub fn disabled(&self, t: f64) -> bool {
        t < self.frozen_until || t < self.stun_until || t < self.overgrown_until
            || t < self.extra.yellow_until
    }
}

impl Wall {
    pub fn edge_distance(&self, x: f64, y: f64) -> f64 {
        edge_distance(x, y, self.x, self.y, 0.5)
    }
}

impl Unit {
    pub fn reference(&self) -> UnitRef {
        UnitRef {
            id: self.id,
            team: self.team,
        }
    }

    // entities.py:199-237: targetability is distinct from the ability to act.
    pub fn attached(&self, battle: &Battle) -> bool {
        self.name == "Angry Jelly" && self.owner.is_some_and(|owner| battle.unit(owner).alive)
            && battle.t < self.extra.brainwash_until
    }

    pub fn can_act(&self, t: f64) -> bool {
        !self.extra.suspended && t >= self.extra.yellow_until && t >= self.frozen_until
            && t >= self.stun_until && t >= self.active_at
    }

    pub fn indirect_targetable(&self, battle: &Battle) -> bool {
        self.alive && !self.extra.suspended && !self.underground && !self.extra.leaping
            && !self.attached(battle) && battle.t >= self.active_at
    }

    pub fn targetable(&self, battle: &Battle) -> bool {
        self.indirect_targetable(battle) && self.dash.is_none()
            && battle.t >= self.extra.yellow_until && battle.t >= self.invisible_until
    }
}

#[derive(Clone, Debug)]
pub struct CargoEntry {
    pub name: String,
    pub level: Level,
    pub source: String,
    pub unknown: ExtraMap,
}

#[derive(Clone, Debug)]
pub enum Plan {
    Stage {
        deployments: Vec<Deployment>,
        town_hall: i64,
        strength: f64,
    },
}

impl Plan {
    pub fn strength(&self) -> f64 {
        match self {
            Self::Stage { strength, .. } => *strength,
        }
    }

    // mechanic_tests.py:43-48: Stage has no pending work and no exported callbacks.
    pub fn has_pending(&self) -> bool {
        match self {
            Self::Stage { .. } => false,
        }
    }
}

#[derive(Clone, Debug)]
pub struct SnapshotUnit {
    pub name: String,
    pub x: f64,
    pub y: f64,
    pub hp_fraction: f64,
    pub team: Team,
}

#[derive(Clone, Debug)]
pub struct Snapshot {
    pub t: f64,
    pub units: Vec<SnapshotUnit>,
    pub dead: Vec<BuildingId>,
    pub walls: Vec<(i32, i32)>,
}

#[derive(Clone, Debug)]
pub struct BattleResult {
    pub stars: usize,
    pub destruction: usize,
    pub th_destroyed: bool,
    pub time: f64,
    pub destroyed_keys: Vec<(String, usize)>,
    pub surviving_defenses: Vec<String>,
    pub units_left: usize,
    pub log: Vec<Vec<LogValue>>,
}

pub struct Battle {
    pub catalog: Rc<Catalog>,
    // battle.py:148 random.Random(seed), restored from the exported state.
    pub rng: Option<PyRandom>,
    pub dt: f64,
    pub fast_end: bool,
    pub modifier: Option<String>,
    pub def_mult: f64,
    pub def_hero_mult: f64,
    pub guardian_mult: f64,
    pub atk_hero_mult: f64,
    pub portal_stash: Vec<Value>,
    pub first_destroy_t: Option<f64>,
    pub first_deploy_t: Option<f64>,
    pub defense_ammo: ExtraMap,
    pub allow_synthetic_cc: bool,
    pub battle_mode: String,
    pub upgrading: Vec<Value>,
    pub crafting_phase: i64,
    pub crafting_date: String,
    pub builders: Vec<Builder>,
    pub builder_starts: Vec<(String, (f64, f64))>,
    pub portal_ready_at: f64,
    pub t: f64,
    pub scouting: bool,
    pub scout_time: f64,
    pub ended: bool,
    pub town_hall: i64,
    pub record: bool,
    pub max_time: f64,
    pub log: Vec<Vec<LogValue>>,
    pub frames: Vec<Snapshot>,
    pub grid: Grid,
    pub buildings: Vec<Building>,
    pub walls: Vec<Wall>,
    pub traps: Vec<Trap>,
    pub attackers: Vec<Unit>,
    pub defenders: Vec<Unit>,
    pub fields: Vec<Field>,
    pub pending: Vec<Pending>,
    pub deployed_housing: i64,
    pub monolith_housing: i64,
    pub uid: usize,
    pub cc_building: Option<BuildingId>,
    pub cc_queue: Vec<CargoEntry>,
    pub cc_released: bool,
    pub th: Option<BuildingId>,
    pub th_on_at: Option<f64>,
    pub defense_levels: Vec<(String, Level)>,
    pub hero_levels: Vec<(String, Level)>,
    pub wall_level: Option<Level>,
    pub cc_level: Vec<(String, Level)>,
    pub damage_by_source: Vec<(String, f64)>,
    pub kills_by_source: Vec<(String, i64)>,
    pub src: String,
    pub src_obj: Option<EntityRef>,
    pub effect: String,
    pub poison: ExtraMap,
    pub clones: Vec<UnitRef>,
    pub total_counted: usize,
    pub destroyed_counted: usize,
    pub banner_tiles: HashSet<(i32, i32)>,
    pub nd_version: Option<u64>,
    pub no_deploy: HashSet<(i32, i32)>,
    pub nd_cache: HashSet<(i32, i32)>,
    pub dt_version: Option<u64>,
    pub dt_cache: Vec<(f64, f64)>,
    pub onboard_cargo: Vec<CargoEntry>,
    pub deployments: Vec<Deployment>,
    pub next_deploy: usize,
    pub next_cc_exit: f64,
    pub field_serial: i64,
    pub plan: Plan,
    // Hash maps are used only for lookup. Python-order iteration uses the Vecs.
    pub building_indices: HashMap<BuildingId, usize>,
    pub wall_indices: HashMap<(i32, i32), WallId>,
    pub unit_indices: HashMap<UnitId, (Team, usize)>,
    pub buckets: Vec<((i32, i32), Vec<UnitRef>)>,
    pub bucket_indices: HashMap<(i32, i32), usize>,
    pub unknown_scalars: ExtraMap,
}

impl Battle {
    pub fn building(&self, id: BuildingId) -> &Building {
        &self.buildings[self.building_indices[&id]]
    }

    pub fn building_mut(&mut self, id: BuildingId) -> &mut Building {
        let index = self.building_indices[&id];
        &mut self.buildings[index]
    }

    pub fn unit(&self, reference: UnitRef) -> &Unit {
        let (team, index) = self.unit_indices[&reference.id];
        assert_eq!(team, reference.team, "unit team mismatch");
        match team {
            Team::Atk => &self.attackers[index],
            Team::Def => &self.defenders[index],
        }
    }

    pub fn unit_mut(&mut self, reference: UnitRef) -> &mut Unit {
        let (team, index) = self.unit_indices[&reference.id];
        assert_eq!(team, reference.team, "unit team mismatch");
        match team {
            Team::Atk => &mut self.attackers[index],
            Team::Def => &mut self.defenders[index],
        }
    }

    pub fn attackers_pool(&self) -> impl Iterator<Item = &Unit> {
        self.attackers.iter().filter(|unit| unit.in_pool)
    }

    pub fn defenders_pool(&self) -> impl Iterator<Item = &Unit> {
        self.defenders.iter().filter(|unit| unit.in_pool)
    }

    pub fn rng_mut(&mut self) -> &mut PyRandom {
        self.rng.as_mut().expect(
            "battle export lacks rng seed/state; export it before porting random mechanics",
        )
    }
}
