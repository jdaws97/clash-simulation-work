//! Ports entities.py:19-292, defense.py:17-57,1099-1111,
//! battle.py:148-210 and plans.py:128-137. Vec order is Python list/dict order.

use std::collections::{HashMap, HashSet};
use std::rc::Rc;

use crate::catalog::{Catalog, UnitSpec};
use crate::geom::{edge_distance, py_hypot};
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

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum StatusSource {
    Name(String),
    Field(i64),
}

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
    pub slows: Vec<(StatusSource, (f64, f64, f64))>,
    pub unknown: ExtraMap,
}

impl Default for BuildingExtra {
    fn default() -> Self {
        Self {
            unavailable: false,
            yellow_until: 0.0,
            rubble_taken: false,
            rubble_claim: None,
            slows: Vec::new(),
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
// heroes.py:1274-1305: presence matters when pausing exported extra timers.
#[derive(Clone, Debug, Default)]
pub struct PausedTimers {
    pub horse_until: bool,
    pub vial_until: bool,
    pub tome_until: bool,
    pub torch_until: bool,
    pub haste_attack_until: bool,
    pub angry_until: bool,
    pub equipment_invisible_until: bool,
    pub phoenix_until: bool,
}

#[derive(Clone, Debug)]
pub struct UnitExtra {
    pub paused_timers: PausedTimers,
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
    pub finish_preferred: Option<BuildingId>,
    pub warden_group: bool,
    pub clone: bool,
    pub mirror_clone: bool,
    pub suicided: bool,
    pub facing: (f64, f64),
    pub heading: Option<(f64, f64)>,
    pub deployment_source: Option<String>,
    pub recalled: Option<f64>,
    pub portal: Option<(f64, f64, f64)>,
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
    pub rage_effects: Vec<(StatusSource, (f64, f64, f64))>,
    pub haste_effects: Vec<(StatusSource, (f64, f64))>,
    pub slows: Vec<(StatusSource, (f64, f64, f64))>,
    pub torches: Vec<(StatusSource, (f64, f64, f64))>,
    pub iceblocks: Vec<(StatusSource, (f64, f64))>,
    pub tomes: Vec<(StatusSource, f64)>,
    // units.py:249-568,626-847: runtime state, including later-stage branches.
    pub barrels: i64,
    pub bear_at: f64,
    pub knights: i64,
    pub mite_dmg: f64,
    pub mites: i64,
    pub next: f64,
    pub next_log: f64,
    pub next_mite: f64,
    pub next_summon: f64,
    pub queue: Vec<String>,
    pub skeletons: Vec<UnitRef>,
    pub aura_next: Option<f64>,
    pub bb: Option<UnitRef>,
    pub delivery_committed: bool,
    pub enraged: bool,
    pub next_bomb: f64,
    pub vacuum: Option<(BuildingId, f64)>,
    pub wall_pulses: Vec<(WallId, f64)>,
    pub from_druid: bool,
    pub strength: f64,
    pub heal_next: Option<f64>,
    pub healing_targets: Vec<UnitRef>,
    pub healing_sources: Vec<(UnitRef, f64)>,
    pub hide_at: Option<f64>,
    pub next_mite_damage: f64,
    pub bouncing_frostmite: bool,
    pub waiting: bool,
    pub clone_casts: Vec<(String, i64)>,
    pub poison_exit: Option<(u64, Vec<u64>, (f64, f64))>,
    // heroes.py:103-1078; pets.py:147-412: absent-key defaults.
    pub boots_next: Option<f64>,
    pub spear_base_range: Option<f64>,
    pub equipment_invisible_until: f64,
    pub tome_until: f64,
    pub torch_until: f64,
    pub torch_speed: f64,
    pub torch_reduction: f64,
    pub revenge_cd: Vec<(EntityRef, f64)>,
    pub fire_heart_done: bool,
    pub egg: bool,
    pub phoenix_until: f64,
    pub fox_next: f64,
    pub hero_present: bool,
    pub owner_defeated: bool,
    pub rampage_detached: bool,
    pub children: Vec<UnitRef>,
    pub bomb_next: Option<f64>,
    pub revivable: bool,
    pub ko_at: Option<f64>,
    pub unknown: ExtraMap,
}

impl Default for UnitExtra {
    fn default() -> Self {
        Self {
            paused_timers: PausedTimers::default(),
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
            finish_preferred: None,
            warden_group: false,
            clone: false,
            mirror_clone: false,
            suicided: false,
            facing: (0.0, 0.0),
            heading: None,
            deployment_source: None,
            recalled: None,
            portal: None,
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
            barrels: 0,
            bear_at: 1e9,
            knights: 0,
            mite_dmg: 0.0,
            mites: 0,
            next: 0.0,
            next_log: 0.0,
            next_mite: 0.0,
            next_summon: 0.0,
            queue: Vec::new(),
            skeletons: Vec::new(),
            aura_next: None,
            bb: None,
            delivery_committed: false,
            enraged: false,
            next_bomb: 0.0,
            vacuum: None,
            wall_pulses: Vec::new(),
            from_druid: false,
            strength: 1.0,
            heal_next: None,
            healing_targets: Vec::new(),
            healing_sources: Vec::new(),
            hide_at: None,
            next_mite_damage: 400.0,
            bouncing_frostmite: false,
            waiting: false,
            clone_casts: Vec::new(),
            poison_exit: None,
            boots_next: None,
            spear_base_range: None,
            equipment_invisible_until: 0.0,
            tome_until: 0.0,
            torch_until: 0.0,
            torch_speed: 0.0,
            torch_reduction: 0.0,
            revenge_cd: Vec::new(),
            fire_heart_done: false,
            egg: false,
            phoenix_until: 0.0,
            fox_next: 0.0,
            hero_present: true,
            owner_defeated: false,
            rampage_detached: false,
            children: Vec::new(),
            bomb_next: None,
            revivable: false,
            ko_at: None,
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
    pub victims: HashSet<UnitId>,
    pub boost_time: f64,
    pub defense_damage: Option<f64>,
    pub has_pulses: bool,
    pub name: Option<String>,
    pub troop: f64,
    pub time: f64,
    pub freeze: Option<f64>,
    pub town_hall: f64,
    pub unit: Option<String>,
    pub first: Option<usize>,
    pub spots: Option<Vec<(f64, f64)>>,
    pub hero: Option<UnitRef>,
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
            victims: HashSet::new(),
            boost_time: 1.0,
            defense_damage: None,
            has_pulses: false,
            name: None,
            troop: 0.0,
            time: 0.0,
            freeze: None,
            town_hall: 0.0,
            unit: None,
            first: None,
            spots: None,
            hero: None,
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
    pub summon: Option<(String, Level, String, Option<UnitRef>)>,
    pub hero_impact: Option<String>,
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
            summon: None,
            hero_impact: None,
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
    pub kit: Option<crate::heroes::Kit>,
    pub pet: Option<UnitRef>,
    pub owner: Option<UnitRef>,
    pub follow: Option<UnitRef>,
    pub home: Option<(f64, f64)>,
    pub leash: f64,
    pub ability_used: bool,
    pub decay: f64,
    pub dash: Option<crate::heroes::Dash>,
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
    pub identity: usize,
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

impl Pending {
    // entities.py:277-292: Python dataclass defaults; add_pending fills context.
    pub fn new(
        at: f64,
        x: f64,
        y: f64,
        radius: f64,
        damage: f64,
        hits_air: bool,
        hits_ground: bool,
        src: &str,
    ) -> Self {
        Self {
            at,
            x,
            y,
            radius,
            damage,
            hits_air,
            hits_ground,
            src: src.to_owned(),
            falloff: false,
            team: Team::Atk,
            extra: PendingExtra::default(),
            actor: None,
            effect: None,
            target: None,
            released_at: None,
        }
    }
}

impl Field {
    // entities.py:262-274: the default field belongs to the attacker.
    pub fn new(kind: &str, x: f64, y: f64, radius: f64, until: f64) -> Self {
        Self {
            identity: 0,
            kind: kind.to_owned(),
            x,
            y,
            radius,
            until,
            team: Team::Atk,
            value: 0.0,
            extra: FieldExtra::default(),
            started: 0.0,
        }
    }
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
    // entities.py:15-16.
    pub fn dist(&self, x: f64, y: f64) -> f64 {
        py_hypot(self.x - x, self.y - y)
    }

    pub fn edge_distance(&self, x: f64, y: f64) -> f64 {
        edge_distance(x, y, self.x, self.y, self.half_hit)
    }

    pub fn disabled(&self, t: f64) -> bool {
        t < self.frozen_until || t < self.stun_until || t < self.overgrown_until
            || t < self.extra.yellow_until
    }
}

impl Wall {
    // entities.py:15-16.
    pub fn dist(&self, x: f64, y: f64) -> f64 {
        py_hypot(self.x - x, self.y - y)
    }

    pub fn edge_distance(&self, x: f64, y: f64) -> f64 {
        edge_distance(x, y, self.x, self.y, 0.5)
    }
}

impl Unit {
    // entities.py:15-16: subtract in the same direction as Python dist().
    pub fn dist(&self, x: f64, y: f64) -> f64 {
        py_hypot(self.x - x, self.y - y)
    }

    // entities.py:182-197: needed by delayed healing impacts.
    pub fn heal(&mut self, amount: f64) -> f64 {
        if !self.alive || self.extra.recalled.is_some() {
            return 0.0;
        }
        if self.kit.as_ref().is_some_and(|kit| kit.doomed_at.is_some()) {
            return 0.0;
        }
        let gained = 0.0_f64.max(amount.min(self.max_hp - self.hp));
        self.hp += gained;
        if self.aura_bonus != 0.0 {
            self.extra.aura_hp = self.extra.aura_hp.max(self.hp - self.base_max_hp);
        }
        gained
    }

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
    Playbook(Box<crate::playbook::PlaybookPlan>),
    Stage {
        deployments: Vec<Deployment>,
        town_hall: i64,
        strength: f64,
        troop_levels: Vec<(String, Option<Level>)>,
        cc_released: bool,
        loadouts: Vec<(String, crate::heroes::HeroLoadout)>,
        hero_levels: Vec<(String, Option<Level>)>,
        equipment_levels: Vec<(String, Option<Level>)>,
        pet_levels: Vec<(String, Option<Level>)>,
        auto_ability_on_ko: bool,
        observed: bool,
    },
}

impl Plan {
    pub fn loadout(&self, name: &str) -> Option<&crate::heroes::HeroLoadout> {
        match self {
            Self::Playbook(p) => p.attack.loadouts.iter().find(|(hero, _)| hero == name).map(|(_, loadout)| loadout),
            Self::Stage { loadouts, .. } => loadouts
                .iter()
                .find(|(hero, _)| hero == name)
                .map(|(_, loadout)| loadout),
        }
    }

    pub fn equipment_level(&self, name: &str) -> Option<&Level> {
        match self {
            Self::Playbook(p) => p.attack.equipment_levels.iter().find(|(key, _)| key == name).and_then(|(_, lv)| lv.as_ref()),
            Self::Stage { equipment_levels, .. } => equipment_levels
                .iter()
                .find(|(key, _)| key == name)
                .and_then(|(_, level)| level.as_ref()),
        }
    }

    pub fn pet_level(&self, name: &str) -> Option<&Level> {
        match self {
            Self::Playbook(p) => p.attack.pet_levels.iter().find(|(key, _)| key == name).and_then(|(_, lv)| lv.as_ref()),
            Self::Stage { pet_levels, .. } => pet_levels
                .iter()
                .find(|(key, _)| key == name)
                .and_then(|(_, level)| level.as_ref()),
        }
    }

    pub fn auto_ability_on_ko(&self) -> bool {
        match self {
            Self::Playbook(p) => p.attack.auto_ability_on_ko,
            Self::Stage { auto_ability_on_ko, .. } => *auto_ability_on_ko,
        }
    }

    pub fn observed(&self) -> bool {
        match self {
            Self::Playbook(p) => p.attack.observed,
            Self::Stage { observed, .. } => *observed,
        }
    }

    pub fn town_hall(&self) -> i64 {
        match self {
            Self::Playbook(p) => p.attack.town_hall,
            Self::Stage { town_hall, .. } => *town_hall,
        }
    }

    pub fn researched_level(&self, name: &str) -> Option<&Option<Level>> {
        match self {
            Self::Playbook(p) => p.attack.troop_levels.iter().find(|(key, _)| key == name).map(|(_, lv)| lv),
            Self::Stage { troop_levels, .. } => troop_levels
                .iter()
                .find(|(key, _)| key == name)
                .map(|(_, level)| level),
        }
    }

    pub fn cc_released(&self) -> bool {
        match self {
            Self::Playbook(p) => p.attack.cc_released,
            Self::Stage { cc_released, .. } => *cc_released,
        }
    }

    pub fn release_cc(&mut self) {
        match self {
            Self::Playbook(p) => p.attack.cc_released = true,
            Self::Stage { cc_released, .. } => *cc_released = true,
        }
    }

    pub fn strength(&self) -> f64 {
        match self {
            Self::Playbook(p) => p.attack.strength,
            Self::Stage {
                strength,
                ..
            }
            => *strength,
        }
    }

    // mechanic_tests.py:43-48: Stage has no pending work and no exported callbacks.
    pub fn has_pending(&self) -> bool {
        match self {
            Self::Playbook(p) => p.has_pending(),
            Self::Stage {
                ..
            }
            => false,
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

// spells.py:882-959: insertion-ordered poison dictionary entries.
#[derive(Clone, Debug)]
pub struct PoisonState {
    pub unit: UnitRef,
    pub origin: String,
    pub source: Option<(String, i64)>,
    pub since: f64,
    pub dps: f64,
    pub ramp: bool,
    pub until: f64,
    pub slow: f64,
    pub attack: f64,
}

pub struct Battle {
    pub catalog: Rc<Catalog>,
    // battle.py:148 random.Random(seed), restored from the exported state.
    pub rng: Option<PyRandom>,
    pub dt: f64,
    pub pace: f64,
    pub pace_tap: f64,
    pub pace_switch: f64,
    pub pace_ability: f64,
    pub windup: bool,
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
    pub jump_grid: Option<Grid>,
    pub jump_grid_key: Option<(u64, Vec<(usize, u64, u64, u64, u64)>)>,
    pub buildings: Vec<Building>,
    pub walls: Vec<Wall>,
    pub traps: Vec<Trap>,
    pub attackers: Vec<Unit>,
    // Python list order, independent of stable Unit storage during pet dashes.
    pub attacker_order: Vec<UnitRef>,
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
    pub poison: Vec<PoisonState>,
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
    pub field_identity: usize,
    pub plan: Plan,
    // Hash maps are used only for lookup. Python-order iteration uses the Vecs.
    pub building_indices: HashMap<BuildingId, usize>,
    pub wall_indices: HashMap<(i32, i32), WallId>,
    pub unit_indices: HashMap<UnitId, (Team, usize)>,
    pub buckets: Vec<((i32, i32), Vec<UnitRef>)>,
    pub bucket_indices: HashMap<(i32, i32), usize>,
    pub buckets_initialized: bool,
    pub guardian: Option<UnitRef>,
    pub unknown_scalars: ExtraMap,
}

impl Battle {
    pub fn portal_units(&self) -> Vec<UnitRef> {
        self.portal_stash.iter().map(|value| {
            let Value::Ref(EntityRef::Unit(unit)) = value else {
                panic!("portal stash contains a non-unit");
            };
            *unit
        }).collect()
    }

    pub fn entity_position(&self, entity: EntityRef) -> (f64, f64) {
        match entity {
            EntityRef::Building(id) => (self.building(id).x, self.building(id).y),
            EntityRef::Wall(id) => (self.walls[id.0].x, self.walls[id.0].y),
            EntityRef::Unit(id) => (self.unit(id).x, self.unit(id).y),
            EntityRef::Trap(id) => (self.traps[id.0].x, self.traps[id.0].y),
        }
    }

    pub fn entity_alive(&self, entity: EntityRef) -> bool {
        match entity {
            EntityRef::Building(id) => self.building(id).alive,
            EntityRef::Wall(id) => self.walls[id.0].alive,
            EntityRef::Unit(id) => self.unit(id).alive,
            EntityRef::Trap(id) => self.traps[id.0].armed,
        }
    }

    pub fn entity_edge_distance(&self, entity: EntityRef, x: f64, y: f64) -> f64 {
        match entity {
            EntityRef::Building(id) => self.building(id).edge_distance(x, y),
            EntityRef::Wall(id) => self.walls[id.0].edge_distance(x, y),
            EntityRef::Unit(id) => self.unit(id).dist(x, y),
            EntityRef::Trap(id) => py_hypot(x - self.traps[id.0].x, y - self.traps[id.0].y),
        }
    }

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
        self.attacker_order
            .iter()
            .map(move |reference| self.unit(*reference))
            .filter(|unit| unit.in_pool)
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
