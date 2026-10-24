//! Ports plans.py: AttackPlan deployments, phased runtime and shared fallbacks.
//! Python constructs the inventory; runtime dictionaries retain insertion order.

use std::rc::Rc;

use crate::geom::{py_atan2, py_cos, py_hypot, py_sin, round_half_even};
use crate::heroes::{self, HeroLoadout};
use crate::json::Json;
use crate::labels::{Name, Tag};
use crate::shared::SharedVec;
use crate::spells;
use crate::state::*;
use crate::stats::Level;
use crate::trace::round_decimal;

#[path = "attacker.rs"]
mod attacker;
pub use attacker::{band_hit, ClusterCache, DefenseSnipe, ScoutingContext};

pub const SPELL_NAMES: &[(&str, &str)] = &[
    ("lightning", "Lightning Spell"),
    ("heal", "Healing Spell"),
    ("rage", "Rage Spell"),
    ("jump", "Jump Spell"),
    ("freeze", "Freeze Spell"),
    ("clone", "Clone Spell"),
    ("invis", "Invisibility Spell"),
    ("recall", "Recall Spell"),
    ("revive", "Revive Spell"),
    ("totem", "Totem Spell"),
    ("poison", "Poison Spell"),
    ("eq", "Earthquake Spell"),
    ("haste", "Haste Spell"),
    ("skeleton", "Skeleton Spell"),
    ("bat", "Bat Spell"),
    ("overgrowth", "Overgrowth Spell"),
    ("iceblock", "Ice Block Spell"),
    ("angry", "Angry Spell"),
    ("santa", "Santa's Surprise"),
    ("frostmites", "Bag of Frostmites"),
    ("birthday", "Birthday Boom"),
    ("yellow", "Yellow Card"),
];

pub fn spell_key(name: &str) -> Option<&'static str> {
    SPELL_NAMES.iter().find(|(_, value)| *value == name).map(|(key, _)| *key)
}

pub fn spell_name(key: &str) -> &'static str {
    SPELL_NAMES.iter().find(|(name, _)| *name == key).expect("known spell key").1
}

pub fn is_hero(name: &str) -> bool {
    matches!(
        name,
        "Barbarian King"
            | "Archer Queen"
            | "Grand Warden"
            | "Royal Champion"
            | "Minion Prince"
            | "Dragon Duke"
    )
}

// plans.py:90-91: tank membership only; iteration never consumes this set.
fn is_tank(name: &str) -> bool {
    matches!(
        name,
        "Ice Golem"
            | "Golem"
            | "Lava Hound"
            | "Ice Hound"
            | "Giant"
            | "Super Giant"
            | "Electro Titan"
            | "P.E.K.K.A"
            | "Yeti"
            | "Meteor Golem"
            | "Headhunter"
    )
}

pub fn threat(key: &str, default: f64) -> f64 {
    match key {
        "th" => 6.0,
        "inferno" => 10.0,
        "scatter" => 8.0,
        "eagle" => 7.0,
        "xbow" | "mono" | "mgt" | "swt" => 5.0,
        "firespitter" | "revenge" | "ad" | "ric" => 4.0,
        "mat" | "wt" | "st" => 3.0,
        "bt" | "at" | "tesla" => 2.0,
        "cannon" | "bh" | "mortar" | "sweeper" => 1.0,
        _ => default,
    }
}

pub fn count(items: &[(String, i64)], key: &str) -> i64 {
    items.iter().find(|(name, _)| name == key).map_or(0, |(_, n)| *n)
}

pub fn set<K: PartialEq, V>(items: &mut Vec<(K, V)>, key: K, value: V) {
    if let Some((_, previous)) = items.iter_mut().find(|(name, _)| *name == key) {
        *previous = value;
    } else {
        items.push((key, value));
    }
}

pub fn number(value: &Json, key: &str, default: f64) -> f64 {
    value.get(key).filter(|v| !v.is_null()).map_or(default, Json::f64)
}

pub fn text<'a>(value: &'a Json, key: &str, default: &'a str) -> &'a str {
    value.get(key).filter(|v| !v.is_null()).map_or(default, Json::str)
}

pub fn truth(value: &Json) -> bool {
    match value {
        Json::Null => false,
        Json::Bool(v) => *v,
        Json::Num(v) => *v != 0.0,
        Json::Str(v) => !v.is_empty(),
        Json::Arr(v) => !v.is_empty(),
        Json::Obj(v) => !v.is_empty(),
    }
}

pub fn flag(value: &Json, key: &str) -> bool {
    value.get(key).is_some_and(truth)
}

pub fn levels(value: &Json, key: &str) -> Vec<(String, Option<Level>)> {
    value.get(key).filter(|v| !v.is_null()).map_or_else(Vec::new, |v| {
        v.obj().iter().map(|(name, lv)| {
            (name.clone(), (!lv.is_null()).then(|| Level::from_json(lv)))
        }).collect()
    })
}

pub fn counts(value: &Json, key: &str) -> Vec<(String, i64)> {
    value.get(key).map_or_else(Vec::new, |v| {
        v.obj().iter().map(|(name, n)| (name.clone(), n.i64())).collect()
    })
}

pub fn times(value: &Json, key: &str) -> Vec<(String, f64)> {
    value.get(key).map_or_else(Vec::new, |v| {
        v.obj().iter().map(|(name, n)| (name.clone(), n.f64())).collect()
    })
}

#[derive(Clone, Debug)]
pub struct SpellStock {
    pub name: String,
    pub origin: String,
    pub remaining: i64,
    pub level: Option<Level>,
}

#[derive(Clone, Copy, PartialEq)]
enum ZapCast {
    Pending(usize),
    Field(usize),
}

struct ZapTarget {
    id: BuildingId,
    hp: f64,
    eq_hits: usize,
}

#[derive(Clone, Debug)]
struct Wave {
    units: Vec<(String, i64)>,
    spread: f64,
}

#[derive(Clone, Debug)]
struct LaterDrop {
    time: f64,
    name: String,
    x: f64,
    y: f64,
    group: String,
    jitter: f64,
}

// plans.py:1197-1231: cargo and support steps are fixed at construction time.
fn supported_cargo(plan: &Json) -> SharedVec<String> {
    let Some(siege) = plan.get("siege")
        .and_then(Json::opt_str)
        .filter(|name| !name.is_empty())
    else {
        return SharedVec::default();
    };
    let cargo = plan.get("cc_troops").map_or(&[][..], Json::arr);
    let steps = plan.get("steps").map_or(&[][..], Json::arr);
    let initial_clone = ["_spells0", "_cc_spells0"].iter().any(|key| {
        plan.get(key)
            .and_then(|stock| stock.get("clone"))
            .is_some_and(truth)
    });
    let mut supported = SharedVec::default();
    for entry in cargo {
        let name = match entry {
            Json::Str(name) => name.as_str(),
            _ => entry
                .get("name")
                .filter(|name| truth(name))
                .unwrap_or_else(|| entry.at("type"))
                .str(),
        };
        let explicit = steps.iter().any(|step| {
            if text(step, "action", "") != "spell"
                || !matches!(text(step, "what", ""), "Clone Spell" | "Invisibility Spell")
            {
                return false;
            }
            let at = text(step, "at", "");
            matches!(at, "group:cargo" | "group:cc")
                || at.strip_prefix("unit:").or_else(|| at.strip_prefix("unit_ahead:"))
                    == Some(name)
        });
        if matches!(name, "Super Archer" | "Super Wizard")
            || siege == "Battle Blimp" && initial_clone && name == "Balloon"
            || explicit
        {
            supported.push(name.to_owned());
        }
    }
    supported
}

// plans.py:930-945: estimate damage without changing any live battle state.
fn account_zap(
    battle: &Battle,
    field: &Field,
    hits: f64,
    cast: ZapCast,
    targets: &mut [ZapTarget],
    cast_hits: &mut Vec<(ZapCast, BuildingId, usize)>,
) {
    for target in targets {
        let building = battle.building(target.id);
        if building.edge_distance(field.x, field.y) > field.radius {
            continue;
        }
        if field.kind == Tag::Lightning {
            target.hp -= field.value;
        } else {
            let count = if let Some((_, _, count)) = cast_hits
                .iter()
                .find(|(key, id, _)| *key == cast && *id == target.id)
            {
                *count
            } else {
                let previous = field
                    .extra
                    .quake_hits
                    .iter()
                    .find(|(key, _)| *key == EntityRef::Building(target.id))
                    .map(|(_, count)| *count);
                let count = if let Some(count) = previous {
                    count
                } else {
                    target.eq_hits += 1;
                    target.eq_hits
                };
                cast_hits.push((cast, target.id, count));
                count
            };
            target.hp -= building.max_hp * field.value * hits / (2 * count - 1) as f64;
        }
    }
}

#[derive(Clone, Debug)]
pub struct AttackPlan {
    pub snipe_exposed: bool,
    pub snipe_mode: String,
    pub snipe_log: SharedVec<Json>,
    pub snipe_deployed: SharedVec<String>,
    pub snipe_assignments: SharedVec<(String, DefenseSnipe)>,
    pub snipe_claimed: SharedVec<BuildingId>,
    pub snipe_lightning: Option<DefenseSnipe>,
    pub snipe_lightning_at: f64,
    pub snipe_lightning_left: i64,
    pub busy_until: f64,
    pub scouting_context: Option<ScoutingContext>,
    pub fallback: bool,
    pub cluster_casts: SharedVec<(String, f64, f64)>,
    pub angle: f64,
    pub town_hall: i64,
    pub strength: f64,
    pub ground: bool,
    pub loadouts: SharedVec<(String, HeroLoadout)>,
    pub troop_levels: SharedVec<(String, Option<Level>)>,
    pub hero_levels: SharedVec<(String, Option<Level>)>,
    pub equipment_levels: SharedVec<(String, Option<Level>)>,
    pub account_equipment: bool,
    pub pet_levels: SharedVec<(String, Option<Level>)>,
    pub spell_levels: SharedVec<(String, Option<Level>)>,
    pub auto_ability_on_ko: bool,
    pub observed: bool,
    pub spells: SharedVec<(String, i64)>,
    pub cc_spells: SharedVec<(String, i64)>,
    pub stock: SharedVec<SpellStock>,
    pub pol: SharedVec<(String, f64)>,
    pub auto_revive: bool,
    pub revive_delay: f64,
    pub freeze_first: SharedVec<String>,
    pub zap_ad: (i64, i64),
    pub zap_done: bool,
    pub zap_left: Option<[i64; 2]>,
    pub fallback_quakes: SharedVec<(f64, f64)>,
    pub cc_released: bool,
    pub siege_donated: bool,
    pub siege: Option<String>,
    // plans.py:1197-1231: derived from the fixed cargo, initial spells and steps.
    pub supported_cargo: SharedVec<String>,
    pub cargo_wait_since: Option<f64>,
    pub clan_castle_level: Option<i64>,
    pub main_at: f64,
    pub cast_log: SharedVec<(f64, String)>,
    pub totem_casts: SharedVec<(f64, f64, f64)>,
    pub breakers: SharedVec<(String, i64)>,
    pub cleanup: SharedVec<(String, i64)>,
    pub distracts: i64,
    pub snipe_t: Option<f64>,
    pub snipe_points: SharedVec<(f64, f64)>,
    funnel_heroes: SharedVec<(String, f64)>,
    flank: SharedVec<(String, i64, f64)>,
    main: SharedVec<Wave>,
    support: SharedVec<Wave>,
    push_heroes: SharedVec<String>,
    cc_names: SharedVec<String>,
    main_min: f64,
    main_max: f64,
    charge_hero: Option<String>,
    charge_n: i64,
    charge_lat: f64,
    charge_at: f64,
    charge_recall_hp: f64,
    charge_len: f64,
    recall_funnel: bool,
    split_main: f64,
    recalled: SharedVec<String>,
    later: SharedVec<LaterDrop>,
    phase: String,
    entry: Option<(f64, f64)>,
    next_brain: f64,
    lured: bool,
    battle_portal: bool,
}

impl AttackPlan {
    pub fn load(p: &Json) -> Self {
        let snipe_mode = text(p, "snipe_mode", "value");
        assert!(
            matches!(snipe_mode, "off" | "value" | "aggressive"),
            "Unknown snipe mode {snipe_mode}"
        );
        let pairs = |key: &str| -> Vec<(String, i64)> {
            p.at(key)
                .arr()
                .iter()
                .map(|v| (v.arr()[0].str().to_owned(), v.arr()[1].i64()))
                .collect()
        };
        let waves = |key: &str| -> SharedVec<Wave> {
            p.at(key)
                .arr()
                .iter()
                .map(|wave| Wave {
                    units: wave.at("units")
                        .arr()
                        .iter()
                        .map(|unit| (unit.arr()[0].str().to_owned(), unit.arr()[1].i64()))
                        .collect(),
                    spread: wave.at("spread").f64(),
                })
                .collect()
        };
        let stock: Vec<_> = p.at("_spell_stock").arr().iter().map(|v| {
            assert_eq!(v.at("$type").str(), "SpellStock");
            let remaining = v.at("remaining").i64();
            let level = v
                .get("level")
                .filter(|v| !v.is_null())
                .map(Level::from_json);
            assert!(
                remaining <= 0 || level.is_some(),
                "export live spell stock after resolving its constructed level"
            );
            SpellStock {
                name: v.at("name").str().to_owned(),
                origin: v.at("origin").str().to_owned(),
                remaining,
                level,
            }
        }).collect();
        Self {
            snipe_exposed: p.get("snipe_exposed").is_none_or(truth),
            snipe_mode: snipe_mode.to_owned(),
            snipe_log: p.get("snipe_log").map_or_else(SharedVec::default, |v| {
                v.arr().to_vec().into()
            }),
            snipe_deployed: p.get("_snipe_deployed").map_or_else(SharedVec::default, |v| {
                v.arr().iter().map(|v| v.str().to_owned()).collect()
            }),
            snipe_assignments: p.get("_snipe_assignments").map_or_else(SharedVec::default, |v| {
                v.obj()
                    .iter()
                    .map(|(name, value)| (name.clone(), DefenseSnipe::load(value)))
                    .collect()
            }),
            snipe_claimed: p.get("_snipe_claimed").map_or_else(SharedVec::default, |v| {
                v.arr().iter().map(|v| BuildingId(v.usize())).collect()
            }),
            snipe_lightning: p.get("_snipe_lightning")
                .filter(|v| !v.is_null())
                .map(DefenseSnipe::load),
            snipe_lightning_at: number(p, "_snipe_lightning_at", 0.0),
            snipe_lightning_left: number(p, "_snipe_lightning_left", 0.0) as i64,
            busy_until: number(p, "_busy_until", 0.0),
            scouting_context: None,
            // plans.py:1117/1296 leave _fallback set (False) after a scan
            fallback: p.get("_fallback").is_some_and(|v| v.bool()),
            cluster_casts: p.get("_cluster_casts").map_or_else(SharedVec::default, |v| {
                v.arr()
                    .iter()
                    .map(|v| {
                        (
                            v.arr()[0].str().to_owned(),
                            v.arr()[1].f64(),
                            v.arr()[2].f64(),
                        )
                    })
                    .collect()
            }),
            angle: p.at("angle").f64(),
            town_hall: p.at("town_hall").i64(),
            strength: p.at("strength").f64(),
            ground: p.at("ground").bool(),
            loadouts: p.at("loadouts").obj().iter().map(|(name, v)| {
                (name.clone(), HeroLoadout {
                    hero: v.at("hero").str().to_owned(),
                    equipment: v.at("equipment")
                        .arr()
                        .iter()
                        .map(|s| s.str().to_owned())
                        .collect(),
                    pet: v.at("pet").opt_str().map(str::to_owned),
                })
            }).collect(),
            troop_levels: levels(p, "troop_levels").into(),
            hero_levels: levels(p, "hero_levels").into(),
            equipment_levels: levels(p, "equipment_levels").into(),
            account_equipment: flag(p, "account_equipment"),
            pet_levels: levels(p, "pet_levels").into(),
            spell_levels: levels(p, "spell_levels").into(),
            auto_ability_on_ko: p.at("auto_ability_on_ko").bool(),
            observed: flag(p, "observed"),
            spells: counts(p, "spells").into(),
            cc_spells: counts(p, "cc_spells").into(),
            stock: stock.into(),
            pol: p.at("pol")
                .obj()
                .iter()
                .filter(|(_, v)| !v.is_null())
                .map(|(key, v)| (key.clone(), v.f64()))
                .collect(),
            auto_revive: flag(p, "auto_revive"),
            revive_delay: number(p, "revive_delay", 1.5),
            freeze_first: p.at("freeze_first").arr().iter().map(|v| v.str().to_owned()).collect(),
            zap_ad: (p.at("zap_ad").arr()[0].i64(), p.at("zap_ad").arr()[1].i64()),
            zap_done: flag(p, "_zap_done"),
            zap_left: p
                .get("_zap_left")
                .map(|v| [v.arr()[0].i64(), v.arr()[1].i64()]),
            fallback_quakes: p.get("_fallback_quakes").map_or_else(
                SharedVec::default,
                |v| {
                    v.arr()
                        .iter()
                        .map(|point| (point.arr()[0].f64(), point.arr()[1].f64()))
                        .collect()
                },
            ),
            cc_released: flag(p, "_cc_released"),
            siege_donated: flag(p, "siege_donated"),
            siege: p.get("siege").and_then(Json::opt_str).map(str::to_owned),
            supported_cargo: supported_cargo(p),
            cargo_wait_since: p.get("_cargo_wait_since").map(Json::f64),
            clan_castle_level: p
                .get("clan_castle_level")
                .filter(|v| !v.is_null())
                .map(Json::i64),
            main_at: number(p, "_main_at", 0.0),
            cast_log: p.at("_cast_log")
                .arr()
                .iter()
                .map(|v| (v.arr()[0].f64(), v.arr()[1].str().to_owned()))
                .collect(),
            totem_casts: p.get("_totem_casts").map_or_else(SharedVec::default, |casts| {
                casts
                    .arr()
                    .iter()
                    .map(|cast| {
                        (
                            cast.arr()[0].f64(),
                            cast.arr()[1].f64(),
                            cast.arr()[2].f64(),
                        )
                    })
                    .collect()
            }),
            breakers: pairs("breakers").into(),
            cleanup: pairs("cleanup").into(),
            distracts: number(p, "_distracts", 0.0) as i64,
            snipe_t: p.get("_snipe_t").filter(|v| !v.is_null()).map(Json::f64),
            snipe_points: p.get("_snipe_pts").map_or_else(SharedVec::default, |v| {
                v.arr()
                    .iter()
                    .map(|point| (point.arr()[0].f64(), point.arr()[1].f64()))
                    .collect()
            }),
            funnel_heroes: p.at("funnel_heroes")
                .arr()
                .iter()
                .map(|entry| (entry.arr()[0].str().to_owned(), entry.arr()[1].f64()))
                .collect(),
            flank: p.at("flank")
                .arr()
                .iter()
                .map(|entry| {
                    (
                        entry.arr()[0].str().to_owned(),
                        entry.arr()[1].i64(),
                        entry.arr()[2].f64(),
                    )
                })
                .collect(),
            main: waves("main"),
            support: waves("support"),
            push_heroes: p.at("push_heroes")
                .arr()
                .iter()
                .map(|v| v.str().to_owned())
                .collect(),
            cc_names: p.at("cc_troops")
                .arr()
                .iter()
                .map(|entry| match entry {
                    Json::Str(name) => name.clone(),
                    _ => entry.get("name")
                        .filter(|v| truth(v))
                        .unwrap_or_else(|| entry.at("type"))
                        .str()
                        .to_owned(),
                })
                .collect(),
            main_min: number(p, "main_min", 8.0),
            main_max: number(p, "main_max", 22.0),
            charge_hero: p.get("charge_hero")
                .and_then(Json::opt_str)
                .map(str::to_owned),
            charge_n: number(p, "_charge_n", 0.0) as i64,
            charge_lat: number(p, "charge_lat", 0.0),
            charge_at: number(p, "charge_at", 0.0),
            charge_recall_hp: number(p, "charge_recall_hp", 0.35),
            charge_len: number(p, "charge_len", 25.0),
            recall_funnel: flag(p, "recall_funnel"),
            split_main: number(p, "split_main", 0.0),
            // plans.py:871: cleanup uses only names from the legacy recall tuples.
            recalled: p.at("recalled")
                .arr()
                .iter()
                .map(|v| v.arr()[0].str().to_owned())
                .collect(),
            later: p.get("_later").map_or_else(SharedVec::default, |v| {
                v.arr()
                    .iter()
                    .map(|entry| {
                        let values = entry.arr();
                        LaterDrop {
                            time: values[0].f64(),
                            name: values[1].str().to_owned(),
                            x: values[2].f64(),
                            y: values[3].f64(),
                            group: values[4].str().to_owned(),
                            jitter: values[5].f64(),
                        }
                    })
                    .collect()
            }),
            phase: text(p, "_phase", "funnel").to_owned(),
            entry: p.get("_entry")
                .filter(|v| !v.is_null())
                .map(|v| (v.arr()[0].f64(), v.arr()[1].f64())),
            next_brain: number(p, "_next_brain", 0.0),
            lured: flag(p, "_lured"),
            battle_portal: flag(p, "_battle_portal"),
        }
    }

    // plans.py:227-229; policy defaults used by runtime helpers.
    pub fn p(&self, name: &str) -> f64 {
        if let Some((_, v)) = self.pol.iter().find(|(key, _)| key == name) {
            return *v;
        }
        match name {
            "commit_progress" => 3.0,
            "freeze_min_threat" => 5.0,
            "freeze_reach" => 1.5,
            "freeze_min_units" => 0.0,
            "totem_min_threats" => 3.0,
            "totem_gap" => 5.0,
            "og_min_score" => 18.0,
            "rage_engaged" => 0.5,
            "rage_gap" => 9.0,
            "heal_hp" | "invis_hp" | "duke_hp" => 0.6,
            "invis_hot" => 2.0,
            "invis_gap" => 4.5,
            "recall_after" => 12.0,
            "recall_hp" | "warden_hp" => 0.4,
            "haste_after" => 3.0,
            "haste_gap" => 8.0,
            "poison_min" => 3.0,
            "hero_hp" => 0.5,
            "hero_time" => 25.0,
            "warden_hurt" => 1.0 / 3.0,
            "arrow_aim" | "dash_aim" | "angry_min" | "skeleton_on" | "bat_on"
            | "eq_core_dist" | "distract_reach" | "deep_drop" | "tank_lead" => 0.0,
            "lure_time" => -1.0,
            "arrow_reach" => 12.0,
            "arrow_threat" | "dash_threat" => 7.0,
            "dash_reach" | "distract_threat" => 8.0,
            "eq_core_n" | "distract_max" => 2.0,
            _ => panic!("unknown runtime policy {name}"),
        }
    }

    pub fn last(&self, kind: &str) -> f64 {
        self.cast_log.iter().rev().find(|(_, k)| k == kind).map_or(-100.0, |(t, _)| *t)
    }

    // plans.py:423-446: retain first matching stock, including donated level.
    pub fn cast_spell(
        &mut self,
        battle: &mut Battle,
        name: &str,
        x: f64,
        y: f64,
        level: Option<&Level>,
        origin: Option<&str>,
    ) -> usize {
        let index = self.stock.iter().position(|s| {
            s.name == name && s.remaining > 0
                && origin.is_none_or(|origin| s.origin == origin)
                && level.is_none_or(|level| s.level.as_ref() == Some(level))
        }).unwrap_or_else(|| panic!("No matching {name} remaining"));
        let selected = self.stock[index]
            .level
            .clone()
            .expect("live spell stock needs its exported level");
        let field = spells::cast_effect(battle, name, x, y, Some(selected));
        self.stock[index].remaining -= 1;
        let key = spell_key(name).expect("spell name");
        let remaining = count(&self.spells, key) - 1;
        set(&mut self.spells, key.to_owned(), remaining);
        battle.deployed_housing += 5 * battle.catalog.stats.attrs(name).at("housing").i64();
        self.cast_log.push((round_decimal(battle.t, 1), key.to_owned()));
        // plans.py:524-526: retain the unrounded time and original cast point.
        if key == "totem" {
            self.totem_casts.push((battle.t, x, y));
        }
        field
    }

    pub fn use_spell(&mut self, battle: &mut Battle, kind: &str, x: f64, y: f64) -> usize {
        self.cast_spell(battle, spell_name(kind), x, y, None, None)
    }

    // plans.py:540-548. Construction resolves donated siege caps in the catalog.
    fn level(&self, battle: &Battle, name: &str) -> Option<Level> {
        let levels = if is_hero(name) {
            &self.hero_levels
        } else {
            &self.troop_levels
        };
        if let Some((_, level)) = levels.iter().find(|(key, _)| key == name) {
            return level.clone();
        }
        if self.siege_donated && self.siege.as_deref() == Some(name) {
            let castle = self.clan_castle_level.unwrap_or_else(|| {
                battle.catalog.stats
                    .max_level("Clan Castle", self.town_hall)
                    .unwrap_or(0)
            });
            let cap = battle.catalog.setup
                .at("siege_donation_caps")
                .at(name)
                .get(&castle.min(13).to_string())
                .map_or(0, Json::i64);
            return Some(Level::Int(cap));
        }
        None
    }

    // plans.py:596-615: opening drops do not consume random draws or clamp points.
    pub fn deployments(&mut self, battle: &mut Battle) -> Vec<Deployment> {
        let mut out = self.opening_deployments(battle);
        let mut add = |battle: &Battle, time, name: &str, x, y, group: &str| {
            out.push(Deployment {
                time,
                name: name.to_owned(),
                x,
                y,
                group: group.to_owned(),
                level: self.level(battle, name),
                town_hall: Some(self.town_hall),
                source: "army".to_owned(),
                mode: None,
            });
        };
        for (name, lateral) in &self.funnel_heroes {
            if self.snipe_deployed.contains(name) {
                continue;
            }
            let (x, y) = if name == "Dragon Duke" && self.has_backpack(battle) {
                self.backpack_point(battle, self.angle, *lateral)
            } else {
                edge_point(battle, self.angle, *lateral)
            };
            add(battle, 0.0, name, x, y, "funnel");
        }
        if let Some(hero) = &self.charge_hero {
            let mut point = self.charge_point(battle, self.angle, self.charge_lat);
            if hero == "Dragon Duke" && self.has_backpack(battle) {
                point = self.backpack_point(battle, self.angle, self.charge_lat);
            } else if self.p("deep_drop") > 0.5 {
                point = self.deep_charge_point(battle, point);
            }
            add(battle, self.charge_at, hero, point.0, point.1, "charge");
            for k in 0..self.charge_n {
                add(
                    battle,
                    self.charge_at + 0.6 + 0.1 * k as f64,
                    "Healer",
                    point.0,
                    point.1,
                    "charge",
                );
            }
        }
        let mut t = 0.5;
        for (name, count, lateral) in &self.flank {
            for k in 0..*count {
                let (x, y) = edge_point(
                    battle,
                    self.angle,
                    *lateral + (k as f64 - *count as f64 / 2.0) * 0.6,
                );
                add(battle, t, name, x, y, "funnel");
                t += 0.15;
            }
        }
        out.sort_by(|a, b| a.time.partial_cmp(&b.time).expect("deployment time"));
        out
    }

    // plans.py:617-662: only non-Healer reserves keep a wiped offense alive.
    pub fn has_offensive_pending(&self, battle: &Battle) -> bool {
        if self.auto_revive
            && self.have("revive")
            && battle.attackers_pool().any(|hero| !hero.alive && hero.extra.revivable)
        {
            return true;
        }
        if battle.portal_units().any(|r| battle.unit(r).name_id != Name::Healer)
            || self.recalled.iter().any(|name| name != "Healer")
            || self.later.iter().any(|drop| drop.name != "Healer")
            || self.cleanup
                .iter()
                .chain(self.breakers.iter())
                .any(|(name, n)| name != "Healer" && *n > 0)
        {
            return true;
        }
        if self.phase == "funnel" {
            if self.siege.as_ref().is_some_and(|name| !name.is_empty())
                || !self.push_heroes.is_empty()
                || self.cc_names.iter().any(|name| name != "Healer")
                || self.main.iter().any(|wave| {
                    wave.units.iter().any(|(name, n)| name != "Healer" && *n > 0)
                })
            {
                return true;
            }
        }
        matches!(self.phase.as_str(), "funnel" | "support")
            && self.support.iter().any(|wave| {
                wave.units.iter().any(|(name, n)| name != "Healer" && *n > 0)
            })
    }

    // plans.py:664-665: the portal list snapshot lasts until the next plan tick.
    pub fn has_pending(&self) -> bool {
        self.phase != "done" || self.battle_portal
    }

    fn have(&self, kind: &str) -> bool {
        count(&self.spells, kind) > 0
    }

    // plans.py:526-538: iterate the original attacker order, even after a revival.
    pub fn revive_knocked_out(
        &mut self,
        battle: &mut Battle,
        have: &impl Fn(&Self, &str) -> bool,
        single_cast: bool,
    ) {
        if !self.auto_revive {
            return;
        }
        let heroes: Vec<_> = battle.attackers_pool().map(Unit::reference).collect();
        for reference in heroes {
            let hero = battle.unit(reference);
            if !hero.alive
                && hero.extra.revivable
                && have(self, "revive")
                && battle.t >= hero.extra.ko_at.expect("KO time") + self.revive_delay
            {
                let (x, y) = (hero.x, hero.y);
                self.use_spell(battle, "revive", x, y);
                if single_cast {
                    return;
                }
            }
        }
    }

    // plans.py:667-692. Jitter consumes x before y, even when deployment relocates.
    pub fn drop(
        &self,
        battle: &mut Battle,
        name: &str,
        x: f64,
        y: f64,
        group: &str,
        jitter: f64,
    ) {
        let at = battle.t;
        self.drop_at(battle, name, x, y, group, jitter, at);
    }

    // plans.py:667-692: jitter draws happen when scheduling, in step order.
    pub fn drop_at(
        &self,
        battle: &mut Battle,
        name: &str,
        x: f64,
        y: f64,
        group: &str,
        jitter: f64,
        at: f64,
    ) {
        self.drop_fixed_at(battle, name, x, y, group, jitter, at, false);
    }

    pub fn drop_fixed_at(
        &self,
        battle: &mut Battle,
        name: &str,
        mut x: f64,
        mut y: f64,
        group: &str,
        jitter: f64,
        at: f64,
        fixed_point: bool,
    ) {
        if jitter != 0.0 {
            let jitter_x = battle.rng.as_mut().expect("battle rng").uniform(-jitter, jitter);
            let jitter_y = battle.rng.as_mut().expect("battle rng").uniform(-jitter, jitter);
            if !fixed_point {
                x += jitter_x;
                y += jitter_y;
            }
        }
        let world = battle.catalog.world as f64;
        if !fixed_point {
            x = (world - 0.6).min(0.6_f64.max(x));
            y = (world - 0.6).min(0.6_f64.max(y));
        }
        let level = self.level(battle, name);
        let deployment = Deployment {
            time: at,
            name: name.to_owned(),
            x,
            y,
            group: group.to_owned(),
            level,
            town_hall: Some(self.town_hall),
            source: "army".to_owned(),
            mode: None,
        };
        if deployment.time > battle.t {
            battle.deployments.push(deployment);
            // Stable sorting keeps existing equal-time drops before new taps.
            battle.deployments[battle.next_deploy..].sort_by(|a, b| {
                a.time.partial_cmp(&b.time).expect("deployment time")
            });
        } else {
            battle.deploy(deployment);
        }
    }

    // plans.py:694-743: stable first minimum over edges, holes, then sectors.
    fn entry_score(battle: &Battle, x: f64, y: f64, lateral: f64) -> Option<f64> {
        let center = battle.catalog.world as f64 / 2.0;
        let mut nearest = None;
        let mut distance = 1e9;
        for building in &battle.buildings {
            if building.alive && building.counted {
                let d = building.edge_distance(x, y);
                if d < distance {
                    distance = d;
                    nearest = Some(building);
                }
            }
        }
        nearest.map(|building| {
            let cheb = (building.x - center).abs().max((building.y - center).abs());
            0.5 * cheb + 2.0 * 0.0_f64.max(distance - 1.5) + 0.3 * lateral.abs()
        })
    }

    fn best_entry(&mut self, battle: &mut Battle) -> (f64, f64) {
        let mut best: Option<(f64, f64, f64)> = None;
        for lateral in -5..=5 {
            let (x, y) = edge_point(battle, self.angle, lateral as f64);
            if let Some(score) = Self::entry_score(battle, x, y, lateral as f64) {
                if best.is_none_or(|previous| score < previous.0) {
                    best = Some((score, x, y));
                }
            }
        }
        let spots = battle.inside_spots();
        for &(x, y) in spots.iter().step_by(1.max(spots.len() / 40)) {
            if let Some(score) = Self::entry_score(battle, x, y, 0.0) {
                if best.is_none_or(|previous| score < previous.0) {
                    best = Some((score, x, y));
                }
            }
        }
        if self.p("deep_drop") > 0.5 {
            for &(x, y) in Self::sector_tiles(battle, self.angle, 0.7).iter().step_by(3) {
                if let Some(score) = Self::entry_score(battle, x, y, 0.0) {
                    if best.is_none_or(|previous| score < previous.0) {
                        best = Some((score, x, y));
                    }
                }
            }
        }
        best.map(|entry| (entry.1, entry.2))
            .unwrap_or_else(|| edge_point(battle, self.angle, 0.0))
    }

    // plans.py:746-752: Python's positive-divisor floating remainder.
    fn sector_tiles(battle: &mut Battle, angle: f64, half_width: f64) -> Vec<(f64, f64)> {
        let center = battle.catalog.world as f64 / 2.0;
        let pi = std::f64::consts::PI;
        battle.deploy_tiles()
            .iter()
            .copied()
            .filter(|&(x, y)| {
                let a = py_atan2(y - center, x - center);
                ((a - angle + pi).rem_euclid(2.0 * pi) - pi).abs() <= half_width
            })
            .collect()
    }

    // plans.py:754-764: first highest threat, then nearest default.
    fn deep_charge_point(&self, battle: &mut Battle, default: (f64, f64)) -> (f64, f64) {
        let center = battle.catalog.world as f64 / 2.0;
        let pi = std::f64::consts::PI;
        let angle = py_atan2(default.1 - center, default.0 - center);
        let mut target: Option<(f64, f64, f64, f64)> = None;
        for b in &battle.buildings {
            if !b.alive || b.weapon.is_none() || threat(&b.key, 0.0) < 5.0 {
                continue;
            }
            let difference = (py_atan2(b.y - center, b.x - center) - angle + pi)
                .rem_euclid(2.0 * pi) - pi;
            if !(difference.abs() <= 0.8) {
                continue;
            }
            let weight = threat(&b.key, 0.0);
            let distance = -py_hypot(b.x - default.0, b.y - default.1);
            if target.is_none_or(|old| (weight, distance) > (old.0, old.1)) {
                target = Some((weight, distance, b.x, b.y));
            }
        }
        let tiles = Self::sector_tiles(battle, angle, 0.6);
        let Some((_, _, tx, ty)) = target else {
            return default;
        };
        let mut best = None;
        for (x, y) in tiles {
            let distance = py_hypot(x - tx, y - ty);
            if best.is_none_or(|(d, _, _)| distance < d) {
                best = Some((distance, x, y));
            }
        }
        best.map_or(default, |(_, x, y)| (x, y))
    }

    // plans.py:766-768: destroyed counted buildings near the approach edge.
    fn funnel_progress(&self, battle: &mut Battle) -> usize {
        let (x, y) = edge_point(battle, self.angle, 0.0);
        battle.buildings
            .iter()
            .filter(|b| !b.alive && b.counted && py_hypot(b.x - x, b.y - y) < 10.0)
            .count()
    }

    // plans.py:770-806: jitter is drawn in wave order when scheduling taps.
    fn launch_main(&mut self, battle: &mut Battle) {
        let (ex, ey) = self.best_entry(battle);
        self.entry = Some((ex, ey));
        if let Some(siege) = self.siege.as_deref().filter(|name| !name.is_empty()) {
            if !self.snipe_deployed.iter().any(|name| name == siege) {
                self.drop(battle, siege, ex, ey, "main", 0.0);
            }
        } else if !self.cc_names.is_empty() && !self.cc_released {
            crate::units::release_cc_at(battle, ex, ey, "main", false);
        }
        let second = (self.split_main > 0.05)
            .then(|| edge_point(battle, self.angle + self.split_main, 0.0));
        let mut k = 0;
        let mut tank_k = 0;
        let mut damage_k = 0;
        let lead = self.p("tank_lead");
        for wave in &self.main {
            for (name, count) in &wave.units {
                for _ in 0..*count {
                    let (x, y) = second.filter(|_| k % 2 != 0).unwrap_or((ex, ey));
                    let at = if lead > 0.3 && is_tank(name) {
                        let at = battle.t + tank_k as f64 * 0.133;
                        tank_k += 1;
                        at
                    } else if lead > 0.3 {
                        let at = battle.t + lead + damage_k as f64 * 0.133;
                        damage_k += 1;
                        at
                    } else {
                        battle.t + k as f64 * 0.133
                    };
                    self.drop_at(battle, name, x, y, "main", wave.spread, at);
                    k += 1;
                }
            }
        }
        for hero in &self.push_heroes {
            if self.snipe_deployed.contains(hero) {
                continue;
            }
            self.drop(battle, hero, ex, ey, "main", 0.5);
        }
        if self.charge_hero.is_some() && !battle.portal_stash.is_empty() {
            heroes::portal_redeploy(battle, ex, ey);
        }
        self.main_at = battle.t;
        self.phase = "support".to_owned();
    }

    // plans.py:551-568: Invisibility precedes Recall on the same brain tick.
    fn charge_spells(&mut self, battle: &mut Battle, charge: &[UnitRef]) {
        let hero = charge.iter().copied().find(|r| {
            let u = battle.unit(*r);
            u.is_hero && self.charge_hero.as_deref() == Some(u.name.as_str())
        });
        let Some(reference) = hero else {
            return;
        };
        let hero = battle.unit(reference);
        let frac = hero.hp / 1.0_f64.max(hero.max_hp);
        let (x, y, invisible_until) = (hero.x, hero.y, hero.invisible_until);
        let locked = battle.buildings.iter().any(|b| {
            b.alive
                && b.weapon.as_ref().is_some_and(|w| w.target == Some(reference))
                && threat(&b.key, 0.0) >= 4.0
        });
        let t = battle.t;
        if self.have("invis")
            && t - self.last("invis") > self.p("invis_gap")
            && t >= invisible_until
            && (locked || frac < 0.6)
        {
            self.use_spell(battle, "invis", x, y);
        }
        let done = t - self.charge_at > self.charge_len;
        if self.have("recall")
            && self.last("recall_charge") < 0.0
            && (frac < self.charge_recall_hp || done)
        {
            self.use_spell(battle, "recall", x, y);
            self.cast_log.push((round_decimal(t, 1), "recall_charge".to_owned()));
        }
    }

    // plans.py:827-905: phases advance once per tick, before the half-second brain.
    pub fn on_tick(&mut self, battle: &mut Battle) {
        let t = battle.t;
        let opening = self.opening_actions(battle);
        self.revive_knocked_out(battle, &Self::have, false);
        // Python retains the old list when portal_redeploy replaces the stash.
        self.battle_portal = !battle.portal_stash.is_empty();
        let due: Vec<_> = self.later
            .iter()
            .filter(|drop| drop.time <= t)
            .cloned()
            .collect();
        self.later.retain(|drop| drop.time > t);
        for drop in due {
            self.drop(battle, &drop.name, drop.x, drop.y, &drop.group, drop.jitter);
        }
        let mut hold = self.charge_hero.is_some()
            && self.phase == "funnel"
            && !self.recall_funnel;
        if !battle.portal_stash.is_empty()
            && t >= battle.portal_ready_at
            && self.recall_funnel
            && self.charge_hero.is_some()
            && self.phase == "funnel"
        {
            let lateral = if self.charge_lat.abs() > 1.0 {
                -self.charge_lat
            } else {
                8.0
            };
            let (x, y) = edge_point(battle, self.angle, lateral);
            heroes::portal_redeploy(battle, x, y);
            hold = true;
        }
        if !battle.portal_stash.is_empty() && t >= battle.portal_ready_at && !hold {
            let (x, y) = self.portal_point(battle);
            heroes::portal_redeploy(battle, x, y);
        }
        if self.phase == "funnel" {
            if !opening && t >= self.busy_until && !self.zap_done && self.zap_ad != (0, 0) {
                self.zap(battle, &Self::have, false, &[]);
            }
            if t >= self.main_max
                || (t >= self.main_min
                    && self.funnel_progress(battle) as f64 >= self.p("commit_progress"))
            {
                self.launch_main(battle);
            }
        } else if self.phase == "support" && t >= self.main_at + 2.0 {
            let (x, y) = self.entry.expect("main entry before support");
            let mut k = 0;
            for wave in &self.support {
                for (name, count) in &wave.units {
                    for _ in 0..*count {
                        self.drop_at(
                            battle,
                            name,
                            x,
                            y,
                            "main",
                            wave.spread,
                            t + k as f64 * 0.133,
                        );
                        k += 1;
                    }
                }
            }
            self.phase = "push".to_owned();
        } else if self.phase == "push" && t >= self.main_at + 25.0 {
            self.deploy_cleanup(battle);
            self.phase = "done".to_owned();
        }
        if !self.lured && self.p("lure_time") >= 0.0 && t >= self.p("lure_time") {
            self.lured = true;
            let cc = battle.buildings
                .iter()
                .find(|b| b.key == "cc" && b.alive)
                .map(|b| (b.x, b.y));
            if let Some((x, y)) = cc {
                if let Some(name) = self.spare_troop() {
                    let (x, y) = self.snipe_point(battle, x, y);
                    self.drop(battle, &name, x, y, "cleanup", 0.2);
                    self.cast_log.push((round_decimal(t, 1), "lure".to_owned()));
                }
            }
        }
        if t >= self.next_brain && t >= self.busy_until {
            self.next_brain = t + 0.5;
            self.hero_abilities(battle);
            if self.charge_hero.is_some() && self.last("recall_charge") < 0.0 {
                let charge = main_units(battle, "charge");
                if !charge.is_empty() {
                    self.charge_spells(battle, &charge);
                    if self.phase == "funnel" {
                        self.generic_spells(battle, &charge, &Self::have, None, false, 0);
                    }
                }
            }
            if matches!(self.phase.as_str(), "support" | "push" | "done") {
                let units = main_units(battle, "main");
                self.generic_spells(battle, &units, &Self::have, None, false, 0);
            }
        }
    }

    // plans.py:867-884: clear reserves before deploying the distant ring.
    fn deploy_cleanup(&mut self, battle: &mut Battle) {
        let mut names = Vec::new();
        for (name, count) in &self.cleanup {
            for _ in 0..*count {
                names.push(name.clone());
            }
        }
        names.extend(self.recalled.iter().cloned());
        self.cleanup.clear();
        self.recalled.clear();
        let army = main_units(battle, "main");
        let center = battle.catalog.world as f64 / 2.0;
        let (cx, cy) = if army.is_empty() {
            (center, center)
        } else {
            centroid(battle, &army)
        };
        let mut far: Vec<_> = battle.buildings
            .iter()
            .filter(|b| b.alive && b.counted)
            .map(|b| (b.x, b.y))
            .collect();
        far.sort_by(|a, b| {
            (-py_hypot(a.0 - cx, a.1 - cy)).total_cmp(&(-py_hypot(b.0 - cx, b.1 - cy)))
        });
        for (k, name) in names.iter().enumerate() {
            let (x, y) = if far.is_empty() {
                edge_point(battle, self.angle + std::f64::consts::PI, 0.0)
            } else {
                let targets = far.len().min(1.max(names.len() / 2 + 1));
                let target = far[k % targets];
                self.snipe_point(battle, target.0, target.1)
            };
            self.drop(battle, name, x, y, "cleanup", 0.3);
        }
    }

    // plans.py:1411-1417: consume the first positive cleanup reserve.
    fn spare_troop(&mut self) -> Option<String> {
        let entry = self.cleanup.iter_mut().find(|(_, n)| *n > 0)?;
        entry.1 -= 1;
        Some(entry.0.clone())
    }

    // plans.py:817-825: first maximum over the sixteen candidate edges.
    pub fn portal_point(&self, battle: &mut Battle) -> (f64, f64) {
        let mut best = (0.0, 0.0);
        let mut score = None;
        for k in 0..16 {
            let point = edge_point(battle, self.angle + 2.0 * std::f64::consts::PI * k as f64 / 16.0, 0.0);
            let n = battle.buildings.iter()
                .filter(|b| b.alive && b.counted && b.dist(point.0, point.1) < 11.0)
                .count();
            if score.is_none_or(|s| n > s) {
                best = point;
                score = Some(n);
            }
        }
        best
    }

    // plans.py:791-823.
    pub fn hero_abilities(&mut self, battle: &mut Battle) {
        let t = battle.t;
        let units: Vec<_> = battle.attackers_pool().map(Unit::reference).collect();
        for reference in units {
            if t < self.busy_until {
                break;
            }
            let u = battle.unit(reference);
            let Some(kit) = &u.kit else {
                continue;
            };
            if !u.alive || !u.is_hero || u.ability_used {
                continue;
            }
            let frac = u.hp / 1.0_f64.max(u.max_hp);
            let engaged = u.target.is_some() && t - u.spawned_at > 2.0;
            let mut fire = false;
            if u.name_id == Name::MinionPrince && kit.has("Portal Pendant") {
                let near: Vec<_> = battle.attackers_near(u.x, u.y, 7.0).into_iter().filter(|r| {
                    let a = battle.unit(*r);
                    !a.is_hero && a.kind != Tag::Pet && a.name_id != Name::Totem
                }).collect();
                if !near.is_empty() {
                    let (cx, cy) = centroid(battle, &near);
                    let work = battle.buildings.iter()
                        .any(|b| b.alive && b.counted && b.edge_distance(cx, cy) < 7.0);
                    let hurt = near.iter().map(|r| {
                        let a = battle.unit(*r);
                        a.hp / a.max_hp
                    }).sum::<f64>() / near.len() as f64;
                    fire = near.len() >= 6 && (!work || hurt < 0.45) && t - u.spawned_at > 15.0;
                } else {
                    fire = frac < 0.35;
                }
            } else if u.name_id == Name::GrandWarden {
                let near: Vec<_> = battle.attackers_near(u.x, u.y, 7.0).into_iter().filter(|r| {
                    let a = battle.unit(*r);
                    a.name_id != Name::Totem && !a.is_hero
                }).collect();
                let hurt = near.iter().filter(|r| {
                    let a = battle.unit(**r);
                    a.hp < 0.55 * a.max_hp
                }).count();
                fire = near.len() >= 5
                    && hurt as i64 >= (near.len() as f64 * self.p("warden_hurt") + 1e-9) as i64
                    || frac < self.p("warden_hp");
                if !fire && kit.has("Fireball") {
                    self.cluster_ability(battle, reference, false);
                    continue;
                }
            } else if u.name_id == Name::RoyalChampion
                && (kit.has("Rocket Spear") || kit.has("Seeking Shield"))
            {
                self.cluster_ability(battle, reference, frac < self.p("hero_hp"));
                continue;
            } else if kit.has("Giant Arrow") {
                self.line_ability(battle, reference, frac < self.p("hero_hp"), None);
                continue;
            } else if u.name_id == Name::DragonDuke {
                if engaged && (frac < self.p("duke_hp")
                    || u.target.is_some_and(|r| entity_is_defense(battle, r)))
                {
                    self.fire_aimed(battle, reference, None);
                }
                continue;
            } else if frac < self.p("hero_hp")
                || engaged
                && t - u.spawned_at > self.p("hero_time") {
                fire = true;
            }
            if fire {
                heroes::activate(battle, reference, false);
            }
        }
    }

    // plans.py:911-975: budget falling bottles and unresolved quake impacts.
    pub fn zap(
        &mut self,
        battle: &mut Battle,
        allowed: &impl Fn(&Self, &str) -> bool,
        single_cast: bool,
        reserved: &[BuildingId],
    ) {
        if self.zap_done {
            return;
        }
        self.zap_left.get_or_insert([self.zap_ad.0, self.zap_ad.1]);
        let (ex, ey) = edge_point(battle, self.angle, 0.0);
        let mut targets: Vec<_> = battle
            .buildings
            .iter()
            .filter(|b| b.alive && b.key == "ad" && !reserved.contains(&b.id) && !self.snipe_claimed.contains(&b.id))
            .map(|b| ZapTarget {
                id: b.id,
                hp: b.hp,
                eq_hits: b.eq_hits,
            })
            .collect();
        targets.sort_by(|a, b| {
            battle.building(a.id).dist(ex, ey)
                .total_cmp(&battle.building(b.id).dist(ex, ey))
        });
        if targets.is_empty() {
            self.zap_done = reserved.is_empty();
            return;
        }
        let mut cast_hits = Vec::new();
        for pending in &battle.pending {
            if let Some(shared) = &pending.extra.quake {
                let field = shared.borrow();
                if field.kind == Tag::Quake {
                    let cast = ZapCast::Pending(Rc::as_ptr(shared) as usize);
                    account_zap(battle, &field, 1.0, cast, &mut targets, &mut cast_hits);
                }
            }
        }
        for (index, field) in battle.fields.iter().enumerate() {
            if matches!(field.kind, Tag::Lightning | Tag::Quake) {
                let hits = if field.kind == Tag::Quake { 5.0 } else { 1.0 };
                account_zap(
                    battle,
                    field,
                    hits,
                    ZapCast::Field(index),
                    &mut targets,
                    &mut cast_hits,
                );
            }
        }
        while self.zap_left.expect("zap budget").iter().any(|n| *n != 0) {
            let Some(mut target) = targets.iter().find(|target| target.hp > 1e-9) else {
                break;
            };
            let (index, kind) = if self.zap_left.expect("zap budget")[1] != 0 {
                (1, "eq")
            } else {
                (0, "lightning")
            };
            if !allowed(self, kind) {
                self.zap_left.as_mut().expect("zap budget")[index] = 0;
                continue;
            }
            if !reserved.is_empty() {
                let stock = self.stock.iter()
                    .find(|stock| stock.name == spell_name(kind) && stock.remaining > 0)
                    .expect("live zap stock");
                let level = stock.level.as_ref().expect("resolved spell level");
                let radius = battle.catalog.resolved
                    .at("zap_radii")
                    .at(&format!("{}|{level}", stock.name))
                    .f64();
                let safe = targets.iter().find(|target| {
                    let b = battle.building(target.id);
                    target.hp > 1e-9 && battle.buildings.iter().all(|r| {
                        !r.alive
                            || !reserved.contains(&r.id)
                            || r.edge_distance(b.x, b.y) > radius
                    })
                });
                let Some(safe) = safe else {
                    break;
                };
                target = safe;
            }
            let b = battle.building(target.id);
            let (x, y) = (b.x, b.y);
            let field_index = self.use_spell(battle, kind, x, y);
            self.zap_left.as_mut().expect("zap budget")[index] -= 1;
            let hits = if kind == "eq" { 5.0 } else { 1.0 };
            account_zap(
                battle,
                &battle.fields[field_index],
                hits,
                ZapCast::Field(field_index),
                &mut targets,
                &mut cast_hits,
            );
            if single_cast {
                self.zap_done = self.zap_left.expect("zap budget").iter().all(|n| *n == 0)
                    || reserved.is_empty() && targets.iter().all(|target| target.hp <= 1e-9);
                return;
            }
        }
        self.zap_done = self.zap_left.expect("zap budget").iter().all(|n| *n == 0)
            || reserved.is_empty();
    }

    // plans.py:1104-1118: living Totems and casts within 5 s cover their radius.
    pub fn totem_covered(&self, battle: &Battle, x: f64, y: f64) -> bool {
        let radius = totem_radius(battle);
        if battle.attackers_pool().any(|unit| {
            unit.alive
                && unit.name_id == Name::Totem
                && py_hypot(unit.x - x, unit.y - y) <= radius
        }) {
            return true;
        }
        self.totem_casts.iter().any(|&(time, tx, ty)| {
            battle.t - time <= 5.0 && py_hypot(tx - x, ty - y) <= radius
        })
    }

    // plans.py:1120-1141: both candidate and score loops retain threat order.
    pub fn totem_targets(
        &self,
        battle: &Battle,
        threats: &[(BuildingId, f64)],
    ) -> Vec<(BuildingId, f64, f64)> {
        let radius = totem_radius(battle);
        let uncovered: Vec<_> = threats
            .iter()
            .copied()
            .filter(|&(id, _)| {
                let building = battle.building(id);
                battle.building_targetable(id)
                    && !self.totem_covered(battle, building.x, building.y)
            })
            .collect();
        let mut targets = Vec::new();
        for &(id, distance) in &uncovered {
            let building = battle.building(id);
            let mut score = 0.0;
            for &(other_id, _) in &uncovered {
                let other = battle.building(other_id);
                if py_hypot(other.x - building.x, other.y - building.y) <= radius {
                    score += threat(&other.key, 1.0);
                }
            }
            targets.push((id, distance, score));
        }
        targets
    }

    // plans.py:1007-1040: breakers precede Jump and paced Earthquakes.
    fn breach(
        &mut self,
        battle: &mut Battle,
        units: &[UnitRef],
        have: &impl Fn(&Self, &str) -> bool,
        inventory: Option<&mut Vec<(String, i64)>>,
        single_cast: bool,
    ) {
        let stuck: Vec<_> = units.iter()
            .copied()
            .filter(|u| battle.unit(*u).wall_target.is_some_and(|w| battle.walls[w.0].alive))
            .collect();
        if stuck.len() < 2 {
            return;
        }
        let w = battle.walls[battle.unit(stuck[0]).wall_target.expect("wall").0].clone();
        let together = stuck.iter().filter(|r| {
            let other = &battle.walls[battle.unit(**r).wall_target.expect("wall").0];
            (other.x - w.x).abs() + (other.y - w.y).abs() <= 3.0
        }).count();
        if together < 2 {
            return;
        }
        let (cx, cy) = centroid(battle, &stuck);
        let breaker = self
            .breakers
            .iter()
            .enumerate()
            .find_map(|(index, (name, amount))| {
                let left = inventory
                    .as_deref()
                    .map_or(*amount, |stock| count(stock, name));
                (left > 0).then_some((index, left))
            });
        if let Some((index, left)) = breaker {
            let n = left.min(3);
            self.breakers[index].1 = left - n;
            if let Some(stock) = inventory {
                set(stock, self.breakers[index].0.clone(), left - n);
            }
            for _ in 0..n {
                self.drop(battle, &self.breakers[index].0, cx, cy, "breach", 0.4);
            }
            self.cast_log.push((round_decimal(battle.t, 1), "breach".to_owned()));
            return;
        }
        if have(self, "jump") {
            self.use_spell(battle, "jump", w.x, w.y);
            self.cast_log.push((round_decimal(battle.t, 1), "breach".to_owned()));
        } else if count(&self.spells, "eq") >= 4 {
            if single_cast {
                self.fallback_quakes = vec![(w.x, w.y); 3].into();
            }
            let casts = if single_cast { 1 } else { 4 };
            for _ in 0..casts {
                self.use_spell(battle, "eq", w.x, w.y);
            }
            self.cast_log.push((round_decimal(battle.t, 1), "breach".to_owned()));
        }
    }

    // plans.py:1197-1251: None falls back; an empty group holds support for cargo.
    pub fn cargo_support(&mut self, battle: &Battle) -> Option<Vec<UnitRef>> {
        if self.supported_cargo.is_empty() {
            return None;
        }
        let delivered: Vec<_> = battle.attackers_pool()
            .filter(|unit| {
                self.supported_cargo.contains(&unit.name)
                    && unit.extra.deployment_source.as_deref() == Some("siege")
            })
            .collect();
        let cargo: Vec<_> = battle.attackers_pool()
            .filter(|unit| {
                unit.alive
                    && self.supported_cargo.contains(&unit.name)
                    && (unit.extra.deployment_source.as_deref() == Some("siege")
                        || unit.extra.clone
                            && delivered.iter().any(|source| source.group == unit.group))
            })
            .map(Unit::reference)
            .collect();
        if !cargo.is_empty() {
            return Some(cargo);
        }
        // Callbacks can release cargo while this tick's plan copy is running.
        if !delivered.is_empty() || self.cc_released || battle.plan.cc_released() {
            return None;
        }
        let mut carriers = battle.attackers_pool()
            .filter(|unit| self.siege.as_deref() == Some(unit.name.as_str()))
            .peekable();
        if carriers.peek().is_some() && !carriers.any(|unit| unit.alive) {
            return None;
        }
        let since = self.cargo_wait_since.get_or_insert(battle.t);
        (battle.t - *since < 30.0).then(Vec::new)
    }

    // plans.py:1253-1351. 'have' implements PlaybookPlan's fallback reservations.
    pub fn generic_spells(
        &mut self,
        battle: &mut Battle,
        units: &[UnitRef],
        have: &impl Fn(&Self, &str) -> bool,
        inventory: Option<&mut Vec<(String, i64)>>,
        single_cast: bool,
        _lightning_reserved: i64,
    ) {
        if battle.t < self.busy_until {
            return;
        }
        if self.spare_lightning_cluster(battle) && single_cast {
            return;
        }
        if self.spare_quake(battle) && single_cast {
            return;
        }
        if units.is_empty() {
            return;
        }
        let cargo = self.cargo_support(battle);
        let t = battle.t;
        if t - self.last("breach") > 3.0 {
            let before = self.cast_log.len();
            self.breach(battle, units, have, inventory, single_cast);
            if single_cast && self.cast_log.len() > before {
                return;
            }
        }
        let (cx, cy) = centroid(battle, units);
        let avg_hp = units.iter().map(|r| {
            let u = battle.unit(*r);
            u.hp / u.max_hp
        }).sum::<f64>() / units.len() as f64;
        let engaged = units.iter().filter(|r| {
            let u = battle.unit(**r);
            u.target.is_some() && u.cooldown > 0.0
        }).count();
        if have(self, "freeze") {
            let priority = |key: &str| self.freeze_first.iter()
                .position(|k| k == key)
                .map(|i| 100.0 - i as f64);
            let mut threats = threats_near(battle, cx, cy, 12.0);
            threats.sort_by(|(a, _), (b, _)| {
                let a = &battle.building(*a).key;
                let b = &battle.building(*b).key;
                let pa = priority(a).filter(|v| *v != 0.0).unwrap_or_else(|| threat(a, 1.0));
                let pb = priority(b).filter(|v| *v != 0.0).unwrap_or_else(|| threat(b, 1.0));
                pb.total_cmp(&pa)
            });
            for (id, d) in threats {
                let b = battle.building(id);
                let w = b.weapon.as_ref().expect("weapon");
                if (priority(&b.key).is_some() || threat(&b.key, 0.0) >= self.p("freeze_min_threat"))

                    && d <= w.range + self.p("freeze_reach")
                    && (w.target.is_some()
                    || !w.multi.is_empty()) {
                    if self.p("freeze_min_units") > 0.0 {
                        let in_range = units.iter()
                            .filter(|r| battle.unit(**r).dist(b.x, b.y) <= w.range)
                            .count();
                        if (in_range as f64) < self.p("freeze_min_units") {
                            continue;
                        }
                    }
                    let (x, y) = (b.x, b.y);
                    self.use_spell(battle, "freeze", x, y);
                    if single_cast {
                        return;
                    }
                    break;
                }
            }
        }
        if have(self, "totem")
            && t - self.last("totem") > self.p("totem_gap") {
            let hot = threats_near(battle, cx, cy, 10.0);
            if hot.len() as f64 >= self.p("totem_min_threats") {
                // plans.py:1324-1330: max(score, -distance), first complete tie.
                let mut best: Option<(BuildingId, f64, f64)> = None;
                for target in self.totem_targets(battle, &hot) {
                    if best.is_none_or(|previous| {
                        (target.2, -target.1) > (previous.2, -previous.1)
                    }) {
                        best = Some(target);
                    }
                }
                if let Some((id, _, _)) = best {
                    let building = battle.building(id);
                    let (x, y) = (building.x, building.y);
                    self.use_spell(battle, "totem", x, y);
                    if single_cast {
                        return;
                    }
                }
            }
        }
        if have(self, "overgrowth") {
            let mut best = None;
            for (id, _) in threats_near(battle, cx, cy, 13.0) {
                let b = battle.building(id);
                if threat(&b.key, 0.0) < 4.0 {
                    continue;
                }
                let score = threats_near(battle, b.x, b.y, 6.0)
                    .iter()
                    .map(|(b, _)| threat(&battle.building(*b).key, 1.0))
                    .sum::<f64>();
                if best.is_none_or(|(s, _)| score > s) {
                    best = Some((score, id));
                }
            }
            if let Some((score, id)) = best {
                if score >= self.p("og_min_score") {
                    let b = battle.building(id);
                    let (x, y) = (b.x, b.y);
                    self.use_spell(battle, "overgrowth", x, y);
                    if single_cast {
                        return;
                    }
                }
            }
        }
        if have(self, "rage") && engaged >= 2
            .max((units.len() as f64 * self.p("rage_engaged")) as usize)
            && t - self.last("rage") > self.p("rage_gap") {
            self.use_spell(battle, "rage", cx, cy);
            if single_cast {
                return;
            }
        }
        if have(self, "heal")
            && avg_hp < self.p("heal_hp")
            && t - self.last("heal") > 6.0 {
            self.use_spell(battle, "heal", cx, cy);
            if single_cast {
                return;
            }
        }
        if have(self, "invis")
            && t - self.last("invis") > self.p("invis_gap")
            && cargo.as_ref().is_none_or(|units| !units.is_empty()) {
            let hot = threats_near(battle, cx, cy, 11.0).iter().filter(|(id, _)| {
                let b = battle.building(*id);
                let w = b.weapon.as_ref().expect("weapon");
                threat(&b.key, 0.0) >= 4.0 && (w.target.is_some() || !w.multi.is_empty())
            }).count();
            if cargo.as_ref().is_some_and(|units| !units.is_empty())
                || avg_hp < self.p("invis_hp") || hot as f64 >= self.p("invis_hot") {
                let (x, y) = cargo.as_ref().filter(|units| !units.is_empty())
                    .map_or((cx, cy), |units| centroid(battle, units));
                self.use_spell(battle, "invis", x, y);
                if single_cast {
                    return;
                }
            }
        }
        if have(self, "recall")
            && t - self.last("recall") > 6.0
            && t - self.main_at > self.p("recall_after") {
            let work = battle.buildings.iter()
                .any(|b| b.alive && b.counted && b.edge_distance(cx, cy) < 7.0);
            if units.len() >= 6 && (!work || avg_hp < self.p("recall_hp")) {
                self.use_spell(battle, "recall", cx, cy);
                if single_cast {
                    return;
                }
            }
        }
        if have(self, "clone")
            && t - self.main_at > 1.0
            && t - self.last("clone") > 1.0 {
            let big: Vec<_> = cargo.as_deref().unwrap_or(units).iter().copied().filter(|r| {
                let u = battle.unit(*r);
                (cargo.is_some() || u.housing >= 10) && !u.extra.clone
            }).collect();
            if !big.is_empty() {
                let (x, y) = centroid(battle, &big);
                self.use_spell(battle, "clone", x, y);
                if single_cast {
                    return;
                }
            }
        }
        if have(self, "haste")
            && t - self.main_at > self.p("haste_after")
            && t - self.last("haste") > self.p("haste_gap") {
            self.use_spell(battle, "haste", cx, cy);
            if single_cast {
                return;
            }
        }
        if have(self, "iceblock") && avg_hp < 0.45 && t - self.last("iceblock") > 8.0 {
            self.use_spell(battle, "iceblock", cx, cy);
            if single_cast {
                return;
            }
        }
        if have(self, "poison") {
            let foes: Vec<_> = battle.defenders_pool()
                .filter(|d| d.alive && t >= d.active_at && d.dist(cx, cy) < 7.0)
                .map(Unit::reference)
                .collect();
            if foes.len() as f64 >= self.p("poison_min") || foes.iter()
                .any(|r| battle.unit(*r).is_hero) {
                let x = foes.iter().map(|r| battle.unit(*r).x).sum::<f64>() / foes.len() as f64;
                let y = foes.iter().map(|r| battle.unit(*r).y).sum::<f64>() / foes.len() as f64;
                self.use_spell(battle, "poison", x, y);
                if single_cast {
                    return;
                }
            }
        }
        self.learned_plays(battle, units, cx, cy, have, single_cast);
    }

    // plans.py:1133-1190: learned casts share the one-action fallback limit.
    fn learned_plays(
        &mut self,
        battle: &mut Battle,
        units: &[UnitRef],
        cx: f64,
        cy: f64,
        have: &impl Fn(&Self, &str) -> bool,
        single_cast: bool,
    ) {
        let t = battle.t;
        if self.p("angry_min") > 0.0
            && have(self, "angry")
            && t - self.last("angry") > 6.0 {
            let astray: Vec<_> = units.iter().copied().filter(|r| {
                let u = battle.unit(*r);
                u.target.is_some_and(|target| matches!(target, EntityRef::Building(_))
                    && !entity_is_defense(battle, target))
                    && battle.buildings.iter()
                    .any(|b| b.alive && b.weapon.is_some() && b.dist(u.x, u.y) < 7.0)
            }).collect();
            if astray.len() as f64 >= self.p("angry_min") {
                let (x, y) = centroid(battle, &astray);
                self.use_spell(battle, "angry", x, y);
                if single_cast {
                    return;
                }
            }
        }
        if self.p("skeleton_on") > 0.5
            && have(self, "skeleton")
            && t - self.last("skeleton") > 8.0 {
            for (id, _) in threats_near(battle, cx, cy, 12.0) {
                let b = battle.building(id);
                let w = b.weapon.as_ref().expect("weapon");
                if threat(&b.key, 0.0) >= 5.0 && w.target.is_some() && w.multi.is_empty() {
                    let (x, y) = (b.x + (cx - b.x) * 0.25, b.y + (cy - b.y) * 0.25);
                    self.use_spell(battle, "skeleton", x, y);
                    if single_cast {
                        return;
                    }
                    break;
                }
            }
        }
        if self.p("bat_on") > 0.5
            && have(self, "bat")
            && t - self.last("bat") > 6.0 {
            let hot = threats_near(battle, cx, cy, 10.0);
            if hot.len() >= 2 {
                let x = hot.iter()
                    .map(|(b, _)| battle.building(*b).x)
                    .sum::<f64>() / hot.len() as f64;
                let y = hot.iter()
                    .map(|(b, _)| battle.building(*b).y)
                    .sum::<f64>() / hot.len() as f64;
                self.use_spell(battle, "bat", x, y);
                if single_cast {
                    return;
                }
            }
        }
        let d_core = self.p("eq_core_dist");
        let n_eq = round_half_even(self.p("eq_core_n")) as i64;
        if d_core > 2.0
            && count(&self.spells, "eq") >= n_eq
            && self.last("eq_core") < 0.0 {
            if let Some(th) = battle.th.map(|id| battle.building(id)).filter(|b| b.alive) {
                if th.dist(cx, cy) <= d_core + 4.0 {
                    let (x, y) = (cx + (th.x - cx) * 0.6, cy + (th.y - cy) * 0.6);
                    if single_cast {
                        self.fallback_quakes = vec![(x, y); (n_eq - 1).max(0) as usize].into();
                    }
                    let casts = if single_cast { 1 } else { n_eq };
                    for _ in 0..casts {
                        self.use_spell(battle, "eq", x, y);
                    }
                    self.cast_log.push((round_decimal(t, 1), "eq_core".to_owned()));
                    if single_cast {
                        return;
                    }
                }
            }
        }
        let reach = self.p("distract_reach");
        if reach > 2.0
            && self.distracts < round_half_even(self.p("distract_max")) as i64
            && t - self.last("distract") > 3.0 {
            for (id, d) in threats_near(battle, cx, cy, 16.0) {
                let b = battle.building(id);
                let w = b.weapon.as_ref().expect("weapon");
                if threat(&b.key, 0.0) >= self.p("distract_threat")
                    && w.range < d
                    && d <= w.range + reach {
                    let (x, y) = (b.x + (b.x - cx), b.y + (b.y - cy));
                    let Some(name) = self.spare_troop() else {
                        break;
                    };
                    let point = self.snipe_point(battle, x, y);
                    self.drop(battle, &name, point.0, point.1, "cleanup", 0.3);
                    self.distracts += 1;
                    self.cast_log.push((round_decimal(t, 1), "distract".to_owned()));
                    break;
                }
            }
        }
    }

    // plans.py:1043-1047.
    fn snipe_point(&mut self, battle: &mut Battle, x: f64, y: f64) -> (f64, f64) {
        if self.snipe_t != Some(battle.t) {
            self.snipe_points = (0..64)
                .map(|k| edge_point(battle, 2.0 * std::f64::consts::PI * k as f64 / 64.0, 0.0))
                .collect();
            self.snipe_points.extend(battle.inside_spots());
            self.snipe_t = Some(battle.t);
        }
        let mut best = self.snipe_points[0];
        let mut d = py_hypot(best.0 - x, best.1 - y);
        for &point in &self.snipe_points[1..] {
            let distance = py_hypot(point.0 - x, point.1 - y);
            if distance < d {
                best = point;
                d = distance;
            }
        }
        best
    }
}

// plans.py:140-157. Every trigonometric call uses CPython's C runtime.
pub fn edge_point(battle: &mut Battle, angle: f64, lateral: f64) -> (f64, f64) {
    let world = battle.catalog.world as f64;
    let center = world / 2.0;
    let (dx, dy) = (py_cos(angle), py_sin(angle));
    let (px, py) = (-dy, dx);
    let mut last = None;
    let mut r = world;
    while r > 0.0 {
        let x = center + px * lateral + dx * r;
        let y = center + py * lateral + dy * r;
        if 0.5 <= x && x < world - 0.5 && 0.5 <= y && y < world - 0.5 {
            if battle.can_deploy(x, y) {
                last = Some((x, y));
            } else if last.is_some() {
                break;
            }
        }
        r -= 0.5;
    }
    last.unwrap_or((
        (world - 1.0).min(1.0_f64.max(center + dx * 24.0)),
        (world - 1.0).min(1.0_f64.max(center + dy * 24.0)),
    ))
}

// plans.py:879-880.
pub fn main_units(battle: &Battle, group: &str) -> Vec<UnitRef> {
    battle.attackers_pool()
        .filter(|u| u.alive
        && u.group == group
        && u.name_id != Name::Totem
        && u.kind != Tag::Pet)
        .map(Unit::reference)
        .collect()
}

// plans.py:883-885.
pub fn centroid(battle: &Battle, units: &[UnitRef]) -> (f64, f64) {
    let w = units.iter().map(|r| battle.unit(*r).housing.max(1)).sum::<i64>() as f64;
    let x = units.iter().map(|r| {
        let u = battle.unit(*r);
        u.x * u.housing.max(1) as f64
    }).sum::<f64>() / w;
    let y = units.iter().map(|r| {
        let u = battle.unit(*r);
        u.y * u.housing.max(1) as f64
    }).sum::<f64>() / w;
    (x, y)
}

// spells.py:27-56, plans.py:1106-1107: _lvl(None) and exported _radius(..., 5.0).
pub fn totem_radius(battle: &Battle) -> f64 {
    let level = battle
        .plan
        .attack()
        .and_then(|plan| {
            plan.spell_levels
                .iter()
                .find(|(name, _)| name == "Totem Spell")
                .and_then(|(_, level)| level.clone())
        })
        .filter(|level| match level {
            Level::Int(value) => *value != 0,
            Level::Text(value) => !value.is_empty(),
        })
        .unwrap_or_else(|| {
            Level::Int(
                battle
                    .catalog
                    .stats
                    .max_level("Totem Spell", battle.plan.town_hall())
                    .expect("Totem spell max level"),
            )
        });
    battle
        .catalog
        .resolved
        .at("spell_radii")
        .at(&format!("Totem Spell|{level}"))
        .f64()
}

// plans.py:888-897.
pub fn threats_near(battle: &Battle, x: f64, y: f64, radius: f64) -> Vec<(BuildingId, f64)> {
    battle.buildings.iter().filter_map(|b| {
        if !b.alive || b.weapon.is_none() || b.disabled(battle.t)
            || battle.plan.attack().is_some_and(|plan| plan.snipe_claimed.contains(&b.id))
        {
            return None;
        }
        let d = b.dist(x, y);
        (d <= radius).then_some((b.id, d))
    }).collect()
}

pub fn entity_is_defense(battle: &Battle, target: EntityRef) -> bool {
    matches!(target, EntityRef::Building(id) if battle.building(id).is_defense)
}
