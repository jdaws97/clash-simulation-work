//! Ports battle.py:76-405, defense.py:145-499, traps.py:85-116,
//! heroes.py:1144-1191 and units.py:903-936. Static tables live in the catalog.

use std::collections::HashSet;
use std::sync::Arc;

use crate::battle::SpawnOptions;
use crate::catalog::Catalog;
use crate::fast_hash::FastMap as HashMap;
use crate::grid::Grid;
use crate::json::Json;
use crate::labels::{Name, Tag};
use crate::load::{self, Node};
use crate::plans::{number, set, text, truth};
use crate::pyrandom::PyRandom;
use crate::state::*;
use crate::stats::{self, Level};

fn integer(value: &Json, key: &str, default: i64) -> i64 {
    value.get(key).map_or(default, |v| Node::new(v, key).integer())
}

fn boolean(value: &Json, key: &str, default: bool) -> bool {
    value.get(key).map_or(default, Json::bool)
}

fn optional_text(value: &Json, key: &str) -> Option<String> {
    value.get(key).and_then(Json::opt_str).map(str::to_owned)
}

fn value_or<'a>(value: &'a Json, key: &str, default: &'a Json) -> &'a Json {
    value.get(key).filter(|v| !v.is_null()).unwrap_or(default)
}

fn generic(value: &Json) -> Value {
    match value {
        Json::Null => Value::Null,
        Json::Bool(v) => Value::Bool(*v),
        Json::Num(v) => Value::Number(*v),
        Json::Str(v) => Value::String(v.clone()),
        Json::Arr(v) => Value::List(v.iter().map(generic).collect()),
        Json::Obj(v) => Value::Map(
            v.iter().map(|(key, v)| (key.clone(), generic(v))).collect(),
        ),
    }
}

fn extra_map(value: &Json) -> ExtraMap {
    value
        .obj()
        .iter()
        .map(|(key, v)| (key.clone(), generic(v)))
        .collect()
}

// Battle stores a set. dump(set) sorts by Python repr, including mixed ids/keys.
fn upgrades(value: &Json) -> Vec<Value> {
    let mut items: Vec<(String, Value)> = Vec::new();
    for item in value.arr() {
        let repr = match item {
            Json::Str(value) => stats::python_string_repr(value),
            Json::Num(_) => Node::new(item, "job.upgrading").integer().to_string(),
            _ => panic!("upgrading entries must be building ids or keys"),
        };
        if !items.iter().any(|(key, _)| key == &repr) {
            items.push((repr, generic(item)));
        }
    }
    items.sort_by(|a, b| a.0.cmp(&b.0));
    items.into_iter().map(|(_, value)| value).collect()
}

fn merge_levels(first: Option<&Json>, second: Option<&Json>) -> Vec<(String, Level)> {
    let mut levels = Vec::new();
    for map in [first, second].into_iter().flatten().filter(|v| !v.is_null()) {
        for (key, value) in map.obj() {
            set(&mut levels, key.clone(), Level::from_json(value));
        }
    }
    levels
}

fn selected(levels: &[(String, Level)], key: &str) -> Option<Level> {
    levels
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, v)| v.clone())
}

fn nonzero(level: Option<Level>) -> Option<Level> {
    level.filter(|value| match value {
        Level::Int(value) => *value != 0,
        Level::Text(value) => !value.is_empty(),
    })
}

/// Both supported deployments() implementations leave the battle RNG untouched.
fn deployments(plan: &Json, margin: f64) -> Vec<Deployment> {
    match plan.at("$type").str() {
        "PlaybookPlan" => Vec::new(),
        "Stage" => {
            let mut result: Vec<_> = plan.at("drops").arr().iter().map(|drop| {
                let values = Node::new(drop, "plan.drops").tuple(5);
                Deployment {
                    time: values[0].number(),
                    name: values[1].string(),
                    x: values[2].number() + margin,
                    y: values[3].number() + margin,
                    group: "main".to_owned(),
                    level: values[4].optional_level(),
                    town_hall: Some(plan.at("town_hall").i64()),
                    source: "army".to_owned(),
                    mode: None,
                }
            }).collect();
            result.sort_by(|a, b| a.time.partial_cmp(&b.time).expect("finite deployment times"));
            result
        }
        other => panic!("unsupported plan {other}"),
    }
}

pub fn build(
    layout: &Json,
    plan_json: &Json,
    options: &Json,
    catalog: Arc<Catalog>,
) -> Battle {
    Node::new(options, "job").keys(&[
        "layout", "plan", "seed", "town_hall", "record", "modifier", "defense_levels",
        "hero_levels", "cc_troops", "cc_level", "max_time", "defense_ammo",
        "allow_synthetic_cc", "builder_starts", "battle_mode", "upgrading",
        "crafting_phase", "crafting_date", "scouting",
    ]);
    assert!(
        !catalog.setup.is_null(),
        "catalog lacks setup tables; regenerate with rust_export.py catalog",
    );
    let empty_object = Json::Obj(Vec::new());
    let empty_array = Json::Arr(Vec::new());
    let env = catalog.setup.at("env");
    let modifiers = catalog.setup.at("modifiers").at(text(options, "modifier", "null")).arr();
    let deployments = deployments(plan_json, catalog.margin);
    let plan = load::plan(Node::new(plan_json, "plan"), &deployments);
    let mut battle = Battle {
        follow_scores_scratch: Vec::new(),
        pet_buildings_scratch: Vec::new(),
        pet_defenders_scratch: Vec::new(),
        healer_scratch: HealerScratch::default(),
        healing_source_scratch: Vec::new(),
        aura_want_scratch: Vec::new(),
        building_geometry_scratch: Vec::new(),
        wall_tiles_standard: true,
        target_pool_scratch: Vec::new(),
        actor_scratch: Vec::new(),
        entity_scratch: Vec::new(),
        wall_contact_scratch: Vec::new(),
        spare_bucket_members: Vec::new(),
        catalog: Arc::clone(&catalog),
        rng: Some(PyRandom::new(integer(options, "seed", 0))),
        dt: number(env, "dt", 0.1),
        pace: number(env, "pace", 1.0),
        pace_tap: number(env, "pace_tap", 0.133),
        pace_switch: number(env, "pace_switch", 0.6),
        pace_ability: number(env, "pace_ability", 0.3),
        windup: boolean(env, "windup", true),
        fast_end: boolean(env, "fast_end", false),
        modifier: optional_text(options, "modifier"),
        def_mult: 1.0 + modifiers[0].f64(),
        def_hero_mult: 1.0 + modifiers[1].f64(),
        guardian_mult: 1.0 + modifiers[2].f64(),
        atk_hero_mult: 1.0 - modifiers[3].f64(),
        portal_stash: Vec::new(),
        first_destroy_t: None,
        first_deploy_t: None,
        defense_ammo: extra_map(value_or(options, "defense_ammo", &empty_object)),
        allow_synthetic_cc: boolean(options, "allow_synthetic_cc", false),
        battle_mode: text(options, "battle_mode", "ranked").to_owned(),
        upgrading: upgrades(value_or(options, "upgrading", &empty_array)),
        crafting_phase: integer(options, "crafting_phase", 4),
        crafting_date: text(options, "crafting_date", "2026-10-15").to_owned(),
        builders: Vec::new(),
        builder_starts: value_or(options, "builder_starts", &empty_object).obj().iter()
            .map(|(key, v)| (key.clone(), Node::new(v, "builder_starts").pair())).collect(),
        portal_ready_at: 0.0,
        t: 0.0,
        scouting: boolean(options, "scouting", false),
        scout_time: 0.0,
        ended: false,
        town_hall: integer(options, "town_hall", 16),
        record: boolean(options, "record", false),
        max_time: number(options, "max_time", 180.0),
        log: Vec::new(),
        frames: Vec::new(),
        grid: Grid::new(catalog.world),
        jump_grid: None,
        jump_grid_key: None,
        buildings: Vec::new(),
        walls: Vec::new(),
        traps: Vec::new(),
        attacker_order: Vec::new(),
        attackers: Vec::new(),
        defenders: Vec::new(),
        fields: Vec::new(),
        pending: Vec::new(),
        deployed_housing: 0,
        monolith_housing: 0,
        uid: 0,
        cc_building: None,
        cc_queue: Vec::new(),
        cc_released: false,
        th: None,
        th_on_at: None,
        defense_levels: merge_levels(layout.get("levels"), options.get("defense_levels")),
        hero_levels: merge_levels(layout.get("hero_levels"), options.get("hero_levels")),
        wall_level: layout.get("wall_level").filter(|v| !v.is_null()).map(Level::from_json),
        cc_level: merge_levels(options.get("cc_level"), None),
        damage_by_source: Vec::new(),
        kills_by_source: Vec::new(),
        src: "?".into(),
        src_obj: None,
        effect: Tag::Attack,
        poison: Vec::new(),
        clones: Vec::new(),
        total_counted: 0,
        destroyed_counted: 0,
        banner_tiles: HashSet::new(),
        nd_version: None,
        no_deploy: HashSet::new(),
        nd_cache: HashSet::new(),
        dt_version: None,
        dt_cache: Vec::new(),
        onboard_cargo: Vec::new(),
        deployments,
        next_deploy: 0,
        next_cc_exit: 0.0,
        field_identity: 0,
        field_serial: 0,
        plan,
        building_indices: Vec::new(),
        wall_indices: HashMap::default(),
        unit_indices: Vec::new(),
        buckets: Vec::new(),
        bucket_indices: HashMap::default(),
        buckets_initialized: false,
        guardian: None,
        unknown_scalars: Vec::new(),
    };
    assert!(battle.dt.is_finite() && battle.dt > 0.0, "env.dt must be positive");
    setup_layout(&mut battle, layout, options);
    battle.total_counted = battle.buildings.iter().filter(|b| b.counted).count();
    battle.no_deploy = battle.live_no_deploy().clone();
    battle.onboard_cargo = attack_cargo(&battle, plan_json);
    battle
}

fn level_of(battle: &Battle, key: &str, name: &str) -> Level {
    let level = selected(&battle.defense_levels, key).unwrap_or_else(|| {
        Level::Int(battle.catalog.stats.max_level(name, battle.town_hall)
            .unwrap_or_else(|| panic!("{name} is unavailable at Town Hall {}", battle.town_hall)))
    });
    battle.catalog.stats.validate_level(name, &level, battle.town_hall);
    level
}

fn get(battle: &Battle, name: &str, level: &Level, keys: &[&str], default: Option<f64>) -> f64 {
    battle.catalog.stats.get(name, level, keys, default)
        .unwrap_or_else(|| panic!("missing numeric {name} level {level} {keys:?}"))
}

fn unavailable(battle: &Battle, key: &str, id: usize) -> bool {
    battle.battle_mode == "multiplayer" && key != "crafting"
        && battle.upgrading.iter().any(|value| match value {
            Value::String(value) => value == key,
            Value::Number(value) => *value == id as f64,
            _ => false,
        })
}

fn setup_layout(battle: &mut Battle, layout: &Json, options: &Json) {
    let catalog = Arc::clone(&battle.catalog);
    for (index, placement) in layout.at("buildings").arr().iter().enumerate() {
        let key = placement.at("key").str();
        let bt = &catalog
            .building_types
            .iter()
            .find(|(name, _)| name == key)
            .unwrap_or_else(|| panic!("unknown building type {key}"))
            .1;
        let banner = key == "banner";
        let (level, hp) = if banner {
            (None, 1.0)
        } else if key == "th" {
            let level = Level::Int(battle.town_hall);
            let hp = get(battle, "Town Hall", &level, &["hitpoints"], Some(10000.0));
            (Some(level), hp)
        } else if key == "crafting" || !bt.counted && catalog.stats.registry.get(&bt.name).is_none() {
            (Some(Level::Int(1)), 1000.0)
        } else {
            let level = level_of(battle, key, &bt.name);
            let hp = get(battle, &bt.name, &level, &["hitpoints", "Hitpoints"], Some(1000.0));
            (Some(level), hp)
        };
        let hitbox = if banner {
            1.0
        } else {
            catalog.stats.registry.get(&bt.name)
                .and_then(|_| catalog.stats.attrs(&bt.name).get("hitbox"))
                .filter(|v| truth(v)).map_or(bt.size.saturating_sub(1).max(1) as f64, Json::f64)
        };
        let mut building = Building {
            town_hall_target: key == "th",
            hidden_tesla: key == "tesla",
            resource_target: bt.kind == Tag::Resource || crate::units::RESOURCE_KEYS.contains(&key),
            source: key.into(),
            name_id: Name::from_str(&bt.name),
            id: BuildingId(index),
            key: key.to_owned(),
            name: bt.name.clone(),
            kind: if banner {
                Tag::from("other")
            } else {
                bt.kind.clone()
            },
            x: placement.at("x").f64() + catalog.margin + bt.size as f64 / 2.0,
            y: placement.at("y").f64() + catalog.margin + bt.size as f64 / 2.0,
            size: bt.size,
            half_hit: hitbox / 2.0,
            hp,
            max_hp: hp,
            alive: !banner,
            counted: !banner && bt.counted,
            is_defense: !banner && bt.kind == Tag::Defense,
            weapon: None,
            mode: if banner {
                None
            } else {
                optional_text(placement, "mode")
            },
            level,
            frozen_until: 0.0,
            stun_until: 0.0,
            overgrown_until: 0.0,
            invisible_until: 0.0,
            atk_slow_until: 0.0,
            atk_slow: 1.0,
            rage_until: 0.0,
            rage_mult: 1.0,
            eq_hits: 0,
            revealed: key != "tesla",
            active: true,
            last_hit: -100.0,
            extra: BuildingExtra::default(),
        };
        if banner {
            for dx in 0..bt.size as i32 {
                for dy in 0..bt.size as i32 {
                    battle.banner_tiles.insert((
                        placement.at("x").i64() as i32 + catalog.margin as i32 + dx,
                        placement.at("y").i64() as i32 + catalog.margin as i32 + dy,
                    ));
                }
            }
        } else {
            if bt.weapon_key.is_some() || matches!(key, "th" | "bh") {
                attach_weapon(battle, &mut building);
            }
            building.extra.unavailable = unavailable(battle, key, index);
            if key == "th" {
                battle.th = Some(building.id);
                if building.extra.unavailable {
                    battle.th_on_at = None;
                }
            }
            if key == "cc" {
                battle.cc_building = Some(building.id);
            }
            battle.grid.block_square(building.x, building.y, building.half_hit, true);
        }
        battle.building_indices.push(Some(index));
        battle.buildings.push(building);
    }
    let mut walls: Vec<_> = layout.at("walls").arr().iter().map(|value| {
        let pair = Node::new(value, "layout.walls").tuple(2);
        (pair[0].i32(), pair[1].i32())
    }).collect();
    walls.sort();
    walls.dedup();
    for (tx, ty) in walls {
        let fallback = nonzero(battle.wall_level.clone()).or_else(|| {
            catalog.stats.max_level("Wall", battle.town_hall).map(Level::Int)
        });
        let level = layout.get("wall_levels").into_iter().flat_map(Json::arr)
            .find(|entry| entry.at("x").i64() == tx as i64 && entry.at("y").i64() == ty as i64)
            .map(|entry| Level::from_json(entry.at("level"))).or(fallback).expect("wall level");
        catalog.stats.validate_level("Wall", &level, battle.town_hall);
        let hp = get(battle, "Wall", &level, &["Hitpoints"], None);
        let tx = tx + catalog.margin as i32;
        let ty = ty + catalog.margin as i32;
        let id = WallId(battle.walls.len());
        battle.walls.push(Wall {
            id,
            tx,
            ty,
            x: tx as f64 + 0.5,
            y: ty as f64 + 0.5,
            hp,
            max_hp: hp,
            alive: true,
            half_hit: 0.5,
            eq_hits: 0,
            key: "wall".to_owned(),
        });
        battle.wall_indices.insert((tx, ty), id);
        battle.grid.set_wall(tx, ty, true);
    }
    for placement in layout.at("traps").arr() {
        let trap = make_trap(battle, placement);
        battle.traps.push(trap);
    }
    let banners: Vec<_> = battle
        .buildings
        .iter()
        .filter(|b| b.key == "banner")
        .map(|b| b.id)
        .collect();
    for (name, banner) in layout.at("heroes").arr().iter().zip(banners) {
        spawn_defending_hero(battle, name.str(), banner);
    }
    if battle.town_hall >= 18 {
        if let Some(th) = battle.th {
            if let Some(name) = layout.get("guardian").filter(|v| truth(v)) {
                let guardian_upgrading = battle.upgrading.iter()
                    .any(|value| matches!(value, Value::String(key) if key == "guardian"));
                let blocked = battle.battle_mode == "multiplayer"
                    && (battle.building(th).extra.unavailable || guardian_upgrading);
                if !blocked {
                    spawn_guardian(battle, name.str(), th);
                }
            }
        }
    }
    let entries = value_or(options, "cc_troops", layout.at("cc_troops"));
    let mut levels = battle.cc_level.clone();
    for entry in entries.arr() {
        let name = cargo_name(entry);
        if selected(&levels, name).is_none() {
            levels.push((name.to_owned(), Level::Int(catalog.stats.max_level(name, 18).expect("donated unit maximum"))));
        }
    }
    battle.cc_queue = cargo_entries(battle, entries.arr(), &levels);
    if let Some(cc) = battle.cc_building.filter(|_| !battle.allow_synthetic_cc) {
        let castle_level = battle.building(cc).level.as_ref().expect("castle level").clone();
        let capacity = get(battle, "Clan Castle", &castle_level, &["Troop Capacity"], None);
        let housing: i64 = battle.cc_queue.iter().map(|e| catalog.numbers(&e.name, &e.level).housing).sum();
        assert!(housing as f64 <= capacity, "Defending Clan Castle housing {housing} exceeds {capacity}");
        for entry in &mut battle.cc_queue {
            assert!(matches!(catalog.stats.record(&entry.name).at("kind").str(), "troop" | "super_troop"), "{} cannot be donated to a Clan Castle", entry.name);
            let _ = catalog.stats.row(&entry.name, &entry.level);
            entry.level = donated_level(&catalog, &entry.name, Some(entry.level.clone()), Some(castle_level.clone()));
        }
    }
}

fn cargo_name(entry: &Json) -> &str {
    if let Json::Str(name) = entry {
        name
    } else {
        entry.get("name").filter(|v| truth(v)).unwrap_or_else(|| entry.at("type")).str()
    }
}

// battle.py:101-122: the catalog carries required Laboratory levels, including
// the researched base troop behind each Super Troop.
fn donated_level(
    catalog: &Catalog,
    name: &str,
    level: Option<Level>,
    castle: Option<Level>,
) -> Level {
    let level = level.unwrap_or_else(|| {
        Level::Int(catalog.stats.max_level(name, 18).filter(|v| *v != 0).unwrap_or(1))
    });
    let Some(castle) = nonzero(castle) else {
        return level;
    };
    let Some(cap) = catalog.stats.get("Clan Castle", &castle, &["~Laboratory Level Cap"], None) else {
        return level;
    };
    let required = catalog.setup.at("donated_laboratory").at(name);
    let requirement = |level: &Level| required.get(&level.to_string()).and_then(Json::opt_f64);
    let mut level = level;
    while let Some(lab) = requirement(&level) {
        if lab <= cap {
            break;
        }
        let Level::Int(value) = level else {
            panic!("donated level must be an integer");
        };
        if value <= 1 {
            break;
        }
        level = Level::Int(value - 1);
    }
    level
}

fn cargo_entries(battle: &Battle, entries: &[Json], levels: &[(String, Level)]) -> Vec<CargoEntry> {
    let mut result = Vec::new();
    for entry in entries {
        let name = cargo_name(entry);
        let level = entry.get("level").filter(|v| truth(v)).map(Level::from_json)
            .or_else(|| nonzero(selected(levels, name)))
            .or_else(|| battle.catalog.stats.max_level(name, battle.town_hall).map(Level::Int))
            .expect("cargo level");
        // Python int(count) truncates; a negative count produces no entries.
        let count = entry.get("count").map_or(1, |v| v.f64() as i64);
        for _ in 0..count {
            result.push(CargoEntry {
                name: name.to_owned(),
                level: level.clone(),
                source: text(entry, "source", "clan_castle").to_owned(),
                unknown: Vec::new(),
            });
        }
    }
    let order = battle.catalog.setup.at("cargo_order").arr();
    let rank = |name: &str| order.iter().position(|v| v.str() == name).unwrap_or(order.len());
    result.sort_by(|a, b| {
        battle.catalog.numbers(&a.name, &a.level).housing
            .cmp(&battle.catalog.numbers(&b.name, &b.level).housing)
            .then_with(|| rank(&a.name).cmp(&rank(&b.name)))
            .then_with(|| match (&a.level, &b.level) {
                (Level::Int(a), Level::Int(b)) => a.cmp(b),
                (Level::Text(a), Level::Text(b)) => a.cmp(b),
                _ => panic!("incomparable cargo levels"),
            })
    });
    result
}

fn attack_cargo(battle: &Battle, plan: &Json) -> Vec<CargoEntry> {
    let attack_town_hall = plan.get("town_hall").filter(|value| truth(value))
        .map_or(battle.town_hall, Json::i64);
    let castle = plan.get("clan_castle_level").filter(|v| !v.is_null()).map(Level::from_json)
        .or_else(|| battle.catalog.stats.max_level("Clan Castle", attack_town_hall).map(Level::Int));
    let given = plan.get("cc_levels").filter(|v| truth(v));
    let mut entries = Vec::new();
    for entry in plan.get("cc_troops").filter(|v| truth(v)).into_iter().flat_map(Json::arr) {
        let name = cargo_name(entry);
        let level = entry.get("level").filter(|v| truth(v))
            .or_else(|| given.and_then(|v| v.get(name))).filter(|v| !v.is_null()).map(Level::from_json);
        let level = donated_level(&battle.catalog, name, level, castle.clone());
        let mut item = if matches!(entry, Json::Str(_)) {
            vec![("name".to_owned(), Json::Str(name.to_owned()))]
        } else {
            entry.obj().to_vec()
        };
        let value = match level {
            Level::Int(level) => Json::Num(level as f64),
            Level::Text(level) => Json::Str(level),
        };
        set(&mut item, "level".to_owned(), value);
        entries.push(Json::Obj(item));
    }
    cargo_entries(battle, &entries, &[])
}

fn spawn_defending_hero(battle: &mut Battle, name: &str, banner: BuildingId) {
    let level = nonzero(selected(&battle.hero_levels, name))
        .or_else(|| battle.catalog.stats.max_level(name, battle.town_hall).map(Level::Int));
    let (x, y) = (battle.building(banner).x, battle.building(banner).y);
    let unit = battle.spawn(
        name,
        Team::Def,
        x,
        y,
        SpawnOptions {
            level,
            kind: Tag::Hero,
            ..SpawnOptions::default()
        },
    );
    let leash = if name == "Barbarian King" {
        7.0
    } else {
        battle.catalog.stats.attrs(name).get("search_radius").filter(|v| truth(v)).map_or(9.0, Json::f64)
    };
    let multiplier = battle.def_hero_mult;
    let unit = battle.unit_mut(unit);
    if multiplier != 1.0 {
        unit.hp *= multiplier;
        unit.max_hp *= multiplier;
        unit.base_max_hp *= multiplier;
        unit.dmg *= multiplier;
    }
    unit.is_hero = true;
    unit.home = Some((x, y));
    unit.leash = leash;
    if matches!(name, "Minion Prince" | "Dragon Duke") {
        unit.flying = true;
    }
}

fn spawn_guardian(battle: &mut Battle, name: &str, th: BuildingId) {
    let level = nonzero(selected(&battle.defense_levels, "guardian"))
        .or_else(|| battle.catalog.stats.max_level(name, 18).filter(|v| *v != 0).map(Level::Int))
        .unwrap_or(Level::Int(1));
    let (x, y) = (battle.building(th).x, battle.building(th).y);
    let unit = battle.spawn(
        name,
        Team::Def,
        x,
        y + 1.0,
        SpawnOptions {
            level: Some(level),
            kind: Tag::from("guardian"),
            ..SpawnOptions::default()
        },
    );
    let empty = Json::Obj(Vec::new());
    let raw = value_or(battle.catalog.stats.attrs(name), "raw", &empty);
    let leash = raw.get("Patrol Radius").filter(|v| truth(v)).or_else(|| raw.get("Search Radius"))
        .and_then(|v| stats::num(v, Some(12.0))).unwrap_or(12.0);
    let trigger = raw.get("Trigger Radius").and_then(|v| stats::num(v, Some(14.0))).unwrap_or(14.0);
    let multiplier = battle.guardian_mult;
    let guardian = battle.unit_mut(unit);
    guardian.home = Some((x, y));
    guardian.leash = leash;
    guardian.extra.unknown.push(("trigger".to_owned(), Value::Number(trigger)));
    guardian.extra.waiting = true;
    guardian.active_at = 1e9;
    if multiplier != 1.0 {
        guardian.hp *= multiplier;
        guardian.max_hp *= multiplier;
        guardian.base_max_hp *= multiplier;
        guardian.dmg *= multiplier;
    }
    battle.guardian = Some(unit);
}

fn make_trap(battle: &Battle, placement: &Json) -> Trap {
    let key = placement.at("key").str();
    let name = &battle.catalog.trap_names.iter().find(|(k, _)| k == key).expect("trap name").1;
    let level = nonzero(selected(&battle.defense_levels, &format!("trap:{key}")))
        .or_else(|| battle.catalog.stats.max_level(name, battle.town_hall).filter(|v| *v != 0).map(Level::Int))
        .unwrap_or(Level::Int(1));
    let size = battle.catalog.trap_sizes.iter().find(|(k, _)| k == key).map_or(1, |(_, size)| *size);
    let empty = Json::Obj(Vec::new());
    let raw = value_or(battle.catalog.stats.attrs(name), "raw", &empty);
    let raw_number = |key, default| {
        raw.get(key).and_then(|v| stats::num(v, Some(default))).unwrap_or(default)
    };
    let trigger = raw_number("Trigger Radius", 1.5);
    let radius = battle.catalog.stats.get(name, &level, &["Damage Radius"], None)
        .filter(|v| *v != 0.0).unwrap_or_else(|| raw_number("Damage Radius", 0.0));
    let targets = raw.get("Unit Type Targeted").filter(|v| truth(v))
        .map_or("Ground", Json::str).to_lowercase();
    let mut trap = Trap {
        id: TrapId(battle.traps.len()),
        key: key.to_owned(),
        name: name.clone(),
        x: placement.at("x").f64() + battle.catalog.margin + size as f64 / 2.0,
        y: placement.at("y").f64() + battle.catalog.margin + size as f64 / 2.0,
        level: level.clone(),
        trigger,
        radius,
        damage: get(battle, name, &level, &["damage", "Damage"], Some(0.0)),
        air: targets.contains("air"),
        ground: targets.contains("ground"),
        armed: true,
        fuse_at: -1.0,
        mode: optional_text(placement, "mode"),
        extra: TrapExtra::default(),
    };
    match key {
        "skeleton" => {
            trap.air = trap.mode.as_deref() == Some("air");
            trap.ground = !trap.air;
            trap.extra.count = get(battle, name, &level, &["Spawned Units"], Some(4.0)) as usize;
            trap.extra.skel_level = get(battle, name, &level, &["Skeleton Level"], Some(1.0)) as i64;
        }
        "spring" => trap.extra.capacity = get(battle, name, &level, &["Spring Capacity"], Some(18.0)),
        "tornado" => {
            trap.air = true;
            trap.ground = true;
            trap.radius = if radius == 0.0 { 3.0 } else { radius };
            trap.extra.time = get(battle, name, &level, &["Duration"], Some(7.0));
            trap.extra.pulses = get(battle, name, &level, &["Total Damage"], None) as usize;
        }
        "giga" => {
            trap.air = true;
            trap.ground = true;
            trap.extra.housing = raw_number("Trigger Housing Space", 18.0);
        }
        _ => {}
    }
    trap
}

// defense.py:17-57: all weapon defaults, including independent ammo clocks.
fn weapon(
    building: &Building,
    kind: &str,
    targets: &str,
    range: f64,
    min_range: f64,
    interval: f64,
    damage: f64,
) -> Weapon {
    Weapon {
        owner: building.id,
        kind: Tag::from(kind),
        targets: Tag::from(targets),
        range,
        min_range,
        interval,
        damage,
        cooldown: 0.0,
        target: None,
        multi: Default::default(),
        lock_time: 0.0,
        idle_until: 0.0,
        facing: 0.0,
        mode: building.mode.as_deref().map(Tag::from),
        extra: WeaponExtra::default(),
        burst_left: 0,
        ammunition: None,
        ammo_time: 0.0,
    }
}

fn attach_weapon(battle: &mut Battle, building: &mut Building) {
    let catalog = Arc::clone(&battle.catalog);
    let key = building.key.clone();
    let name = building.name.clone();
    let level = building.level.clone().expect("weapon level");
    let s = |keys: &[&str], default: Option<f64>| {
        catalog.stats.get(&name, &level, keys, default)
            .unwrap_or_else(|| panic!("missing numeric {name} level {level} {keys:?}"))
    };
    let damage = |interval| {
        catalog.stats.get(&name, &level, &["Damage per Shot", "Damage per Hit", "Damage per Attack"], None)
            .unwrap_or_else(|| s(&["dps", "Damage per Second"], Some(0.0)) * interval)
    };
    let mode = building.mode.as_deref();
    if key == "th" {
        if battle.town_hall >= 18 {
            return;
        }
        if battle.town_hall >= 17 {
            let ia = catalog.setup.at("inferno_artillery");
            let selected = selected(&battle.defense_levels, "th:weapon").unwrap_or(Level::Int(5));
            let Level::Int(selected) = selected else {
                panic!("Inferno Artillery level must be between 1 and 5");
            };
            let shots = catalog.setup.at("artillery_damage").arr();
            assert!(selected >= 1 && selected as usize <= shots.len(), "Inferno Artillery level must be between 1 and 5");
            let mut w = weapon(
                building,
                "inferno_artillery",
                "both",
                ia.at("range").f64(),
                0.0,
                ia.at("interval").f64(),
                shots[selected as usize - 1].f64(),
            );
            w.extra = load::setup_weapon_extra(ia);
            building.weapon = Some(w);
            battle.th_on_at = Some(f64::NEG_INFINITY);
            building.is_defense = true;
        } else if battle.town_hall >= 13 {
            let g = catalog.setup.at("giga_inferno").at("16");
            let mut w = weapon(
                building,
                "giga_inferno",
                "both",
                g.at("range").f64(),
                0.0,
                0.128,
                g.at("dps").f64() * 0.128,
            );
            w.extra = load::setup_weapon_extra(g);
            building.weapon = Some(w);
            building.is_defense = true;
        }
        return;
    }
    if key == "crafting" {
        attach_crafted(battle, building);
        // Crafted names also drive fast target/source labels.
        building.name_id = Name::from_str(&building.name);
        return;
    }
    let mut w = match key.as_str() {
        "ad" => weapon(building, "single", "air", 10.0, 0.0, 1.0, damage(1.0)),
        "at" => weapon(building, "single", "both", 10.0, 0.0, 0.5, damage(0.5)),
        "cannon" => weapon(building, "single", "ground", 9.0, 0.0, 0.8, damage(0.8)),
        "mat" => weapon(
            building,
            "multi_archer",
            "both",
            10.0,
            0.0,
            0.6,
            s(&["Damage per Hit", "Damage per Shot"], None),
        ),
        "ric" => {
            let mut w = weapon(
                building,
                "ricochet",
                "ground",
                9.0,
                0.0,
                0.8,
                s(&["Damage per Shot (Primary Target)"], Some(312.0)),
            );
            w.extra.bounce = s(&["Secondary Chain Damage"], Some(218.4));
            w.extra.bounce_range = 3.5;
            w
        }
        "bt" => {
            let mut w = weapon(building, "splash", "ground", 6.0, 0.0, 1.1, damage(1.1));
            w.extra.splash = 1.5;
            w.extra.death = s(&["Damage when destroyed"], Some(600.0));
            w.extra.death_radius = 2.75;
            w.extra.death_delay = 1.0;
            w
        }
        "wt" => {
            let mut w = weapon(building, "splash", "both", 7.0, 0.0, 1.3, damage(1.3));
            w.extra.splash = 1.0;
            w.extra.same_type = true;
            w
        }
        "mortar" => {
            let mut w = weapon(
                building,
                "mortar",
                "ground",
                11.0,
                4.0,
                5.0,
                s(&["Damage per Hit", "Damage per Shot"], None),
            );
            w.extra.splash = 1.5;
            w.extra.flight = 1.5;
            w
        }
        "xbow" => {
            let both = mode == Some("both");
            weapon(
                building,
                "single",
                if both { "both" } else { "ground" },
                if both { 11.5 } else { 14.0 },
                0.0,
                0.128,
                damage(0.128),
            )
        }
        "tesla" => {
            let mut w = weapon(building, "single", "both", 7.0, 0.0, 0.6, damage(0.6));
            w.extra.trigger = Some(WeaponTrigger::Radius(6.0));
            w
        }
        "inferno" if mode == Some("multi") => {
            let mut w = weapon(
                building,
                "inferno_multi",
                "both",
                10.0,
                0.0,
                0.128,
                s(&["Damage per Second per Target"], Some(120.0)) * 0.128,
            );
            w.extra.targets = s(&["Number of Targets"], None) as usize;
            w
        }
        "inferno" => {
            let mut w = weapon(building, "inferno_single", "both", 9.0, 0.0, 0.128, 0.0);
            w.extra.ramp = vec![
                (0.0, s(&["Damage per Second / Initial"], Some(120.0))),
                (1.5, s(&["Damage per Second / After 1.5s"], Some(260.0))),
                (5.25, s(&["Damage per Second / After 5.25s"], Some(2600.0))),
            ].into();
            w
        }
        "eagle" => {
            let mut w = weapon(
                building,
                "eagle",
                "both",
                50.0,
                7.0,
                10.0,
                s(&["Damage per Hit"], Some(525.0)),
            );
            w.extra.activation = 200;
            w.extra.shells = 3;
            w.extra.gap = 0.75;
            w.extra.shock = s(&["Shockwave Damage"], Some(50.0));
            w.extra.splash = 0.75;
            w.extra.shock_radius = 3.0;
            w
        }
        "scatter" => {
            let mut w = weapon(
                building,
                "scatter",
                "both",
                10.0,
                3.0,
                3.2,
                s(&["Damage per Shot*"], Some(576.0)),
            );
            w.extra.splash_max = 420.0;
            w.extra.splash_min = 150.0;
            let range = |key: &str| {
                catalog.stats.text(&name, &level, &[key], None).and_then(|v| {
                    if let Json::Str(v) = v {
                        if v.contains('-') {
                            let parts: Vec<_> = v.split('-').map(|part| stats::num(&Json::Str(part.to_owned()), None).expect("scatter range")).collect();
                            assert_eq!(parts.len(), 2, "scatter range");
                            return Some((parts[0], parts[1]));
                        }
                    }
                    None
                })
            };
            if let Some((low, high)) = range("Damage per Shot*") {
                w.damage = high;
                w.extra.inner_min = Some(low);
            }
            if let Some((low, high)) = range("Splash Damage**") {
                w.extra.splash_min = low;
                w.extra.splash_max = high;
            }
            w
        }
        "mono" => {
            let mut w = weapon(
                building,
                "monolith",
                "both",
                11.0,
                0.0,
                1.5,
                s(&["Base Damage per Shot"], Some(289.5)),
            );
            w.extra.pct = s(&["Bonus Damage per Shot"], Some(13.0)) / 100.0;
            w
        }
        "sweeper" => {
            let mut w = weapon(building, "sweeper", "air", 15.0, 1.0, 5.0, 0.0);
            w.extra.push = s(&["Push Strength"], Some(4.0));
            w.facing = catalog.setup.at("facings").get(mode.unwrap_or("E")).map_or(0.0, Json::f64);
            w
        }
        "bh" => {
            if level == Level::Int(1) {
                building.is_defense = false;
                return;
            }
            let mut w = weapon(building, "single", "both", 7.0, 0.0, 0.4, damage(0.4));
            w.extra.repair = s(&["Repair per Second"], Some(85.0));
            w.extra.repair_range = 7.0;
            building.is_defense = true;
            let (x, y) = if battle.battle_mode == "multiplayer" {
                battle.builder_starts.iter().find(|(key, _)| key == &building.id.0.to_string()).map_or((building.x, building.y), |(_, position)| *position)
            } else {
                (building.x, building.y)
            };
            battle.builders.push(Builder {
                owner: building.id,
                x,
                y,
                target: None,
                cooldown: 0.0,
                frozen_until: 0.0,
                stun_until: 0.0,
                repair_slow: 1.0,
                slow_until: 0.0,
                rage_until: 0.0,
                rage_speed: 0.0,
                repair_boost: 1.0,
            });
            w
        }
        "st" => {
            let mut w = weapon(building, "spell_tower", "both", 9.0, 0.0, 70.0, 0.0);
            let mode = mode.filter(|s| !s.is_empty()).unwrap_or("rage");
            let unlocks = catalog.setup.at("spell_tower_unlocks");
            let required = unlocks.get(mode).unwrap_or_else(|| panic!("Spell Tower mode is not unlocked")).i64();
            assert!(matches!(level, Level::Int(lv) if lv >= required), "Spell Tower mode is not unlocked");
            assert!(required != 4 || battle.town_hall >= 17, "Earthquake Spell Towers require Town Hall 17");
            w.mode = Some(Tag::from(mode));
            w
        }
        "mgt" if mode == Some("long") => weapon(
            building,
            "single",
            "both",
            12.0,
            0.0,
            1.0,
            s(&["Damage per Hit"], Some(390.0)),
        ),
        "mgt" => {
            let mut w = weapon(
                building,
                "burst",
                "both",
                8.0,
                0.0,
                0.383,
                s(&["Damage per Hit**"], Some(170.4)),
            );
            w.extra.shots = 4;
            w.extra.gap = 0.192;
            w
        }
        "firespitter" => {
            assert!(matches!(mode, None | Some("N" | "E" | "S" | "W")), "Firespitter facing must be N, E, S or W");
            let mut w = weapon(
                building,
                "firespitter",
                "both",
                16.0,
                0.0,
                1.0,
                s(&["Damage per Hit**"], Some(51.07)),
            );
            w.extra.shots = 20;
            w.extra.gap = 0.064;
            w.extra.pierce = 2;
            // math.radians(75): CPython multiplies by the radians conversion.
            w.extra.arc = 75.0 * (std::f64::consts::PI / 180.0);
            w.facing = catalog.setup.at("facings").at(mode.unwrap_or("E")).f64();
            w
        }
        "swt" => {
            let mut w = weapon(
                building,
                "super_wizard",
                "both",
                8.0,
                0.0,
                1.3,
                s(&["Damage per Hit (Primary)"], Some(416.0)),
            );
            w.extra.secondary = s(&["Damage per Hit (Secondary)"], Some(166.4));
            w.extra.chain = 15;
            w.extra.chain_range = 4.0;
            w
        }
        "revenge" => weapon(
            building,
            "revenge",
            "both",
            11.0,
            0.0,
            1.2,
            s(&["Damage per Shot"], Some(500.0)),
        ),
        // Python leaves weapon_key=None decorations and nonweapon types alone.
        _ => return,
    };
    if matches!(key.as_str(), "at" | "cannon" | "mortar") {
        gear_up(battle, building, &mut w);
    }
    if let Some(capacity) = catalog.setup.at("ammunition").get(&key) {
        let capacity = capacity.i64();
        let value = battle.defense_ammo.iter().find(|(key, _)| key == &building.id.0.to_string())
            .or_else(|| battle.defense_ammo.iter().find(|(name, _)| name == &key)).map(|(_, v)| v);
        let rounds = match value {
            None => capacity,
            Some(Value::Number(value)) if value.is_finite() && value.fract() == 0.0 => *value as i64,
            Some(Value::Bool(value)) => i64::from(u8::from(*value)),
            _ => panic!("Illegal {} ammunition", building.name),
        };
        assert!(0 <= rounds && rounds <= capacity, "Illegal {} ammunition: {rounds}", building.name);
        w.ammunition = Some(rounds);
    }
    building.weapon = Some(w);
}

fn gear_up(battle: &Battle, building: &Building, weapon: &mut Weapon) {
    if matches!(building.mode.as_deref(), None | Some("normal")) {
        return;
    }
    assert!(matches!(building.mode.as_deref(), Some("geared" | "burst" | "fast")), "Unknown {} mode", building.name);
    let Level::Int(level) = building.level.as_ref().expect("gear-up level") else {
        panic!("Geared Mortar supercharge eligibility is unresolved");
    };
    let minimum = battle.catalog.setup.at("gear_minimum").at(&building.key).i64();
    assert!(*level >= minimum, "{} is below its gear-up level", building.name);
    match building.key.as_str() {
        "at" => {
            weapon.range = 8.0;
            weapon.interval = 0.25;
            weapon.damage = battle.catalog.setup.at("gear_archer_shots").arr()[(*level - minimum) as usize].f64();
        }
        "cannon" => {
            weapon.kind = Tag::Burst;
            weapon.range = 7.0;
            weapon.interval = 1.6;
            weapon.damage = get(battle, &building.name, &Level::Int(*level), &["Damage per Hit**"], None);
            weapon.extra.shots = 4;
            weapon.extra.gap = 0.192;
        }
        _ => {
            weapon.kind = Tag::from("mortar_burst");
            weapon.interval = 4.0;
            weapon.damage = get(battle, &building.name, &Level::Int(*level), &["Damage per Shot"], None);
            weapon.extra.shots = 3;
            weapon.extra.gap = 0.5;
        }
    }
}

fn attach_crafted(battle: &Battle, building: &mut Building) {
    let catalog = &battle.catalog;
    let crafting = catalog.setup.at("crafting");
    assert!(battle.crafting_phase == crafting.at("phase").i64()
        && crafting.at("start").str() <= battle.crafting_date.as_str()
        && battle.crafting_date.as_str() <= crafting.at("end").str(), "Only crafting phase 4 is supported");
    let mode = building.mode.as_deref();
    if matches!(mode, None | Some("none")) {
        building.hp = 1000.0;
        building.max_hp = 1000.0;
        return;
    }
    let mode = mode.expect("crafted mode");
    assert!(crafting.at("modes").arr().iter().any(|v| v.str() == mode), "Crafted defense is unavailable in phase 4");
    let name = catalog.setup.at("crafted").at(mode).str();
    let mut cap = 1;
    for entry in catalog.stats.record(name).at("levels").arr() {
        if let Json::Num(level) = entry.at("level") {
            let row = catalog.stats.row(name, &Level::Int(*level as i64));
            let required = row.iter().find(|(key, _)| key == "Town Hall Level Required")
                .and_then(|(_, v)| stats::num(v, Some(99.0))).unwrap_or(99.0);
            if required <= battle.town_hall as f64 {
                cap = cap.max(*level as i64);
            }
        }
    }
    let level = selected(&battle.defense_levels, "crafting").unwrap_or(Level::Int(cap));
    let hp = selected(&battle.defense_levels, "crafting:hitpoints").unwrap_or(level.clone());
    let damage = selected(&battle.defense_levels, "crafting:damage").unwrap_or(level.clone());
    let effect = selected(&battle.defense_levels, "crafting:effect").unwrap_or(level);
    for selected in [&hp, &damage, &effect] {
        assert!(matches!(selected, Level::Int(level) if 1 <= *level && *level <= cap), "Illegal {name} module level: {selected}");
    }
    building.name = name.to_owned();
    building.level = Some(damage.clone());
    building.hp = get(battle, name, &hp, &["Hitpoints"], None);
    building.max_hp = building.hp;
    let s = |keys: &[&str]| get(battle, name, &damage, keys, None);
    let e = |keys: &[&str]| get(battle, name, &effect, keys, None);
    let w = match mode {
        "cake" => {
            let mut w = weapon(building, "cake", "both", 12.0, 3.0, 3.0, s(&["Damage per Hit"]));
            w.extra.splash = 2.5;
            w.extra.bomb = e(&["Explosion Damage"]);
            w.extra.bomb_radius = 2.5;
            w.extra.bomb_delay = 3.0;
            w
        }
        "candle" => {
            let damage = s(&["Damage per Hit"]);
            let dps = s(&["Damage per Second per Flame"]);
            let mut w = weapon(building, "candle", "both", 10.5, 0.0, damage / dps, damage);
            w.extra.targets = 6;
            w.extra.melt1 = e(&["Total Seconds Active / First Decay"]);
            w.extra.melt2 = e(&["Total Seconds Active / Second Decay"]);
            w
        }
        _ => {
            let mut w = weapon(building, "hunter", "both", 9.5, 0.0, 0.6, s(&["Damage per Hit"]));
            w.extra.poison_level = e(&["Poison Spell Level"]) as usize;
            w.extra.poison_time = 3.0;
            w
        }
    };
    building.weapon = Some(w);
}
