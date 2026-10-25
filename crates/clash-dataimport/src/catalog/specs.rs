//! Behavior declarations ported from engine/specs.py, not runtime catalog data.
use clash_data::json::Json;
use clash_data::wire::{arr, num, obj, string};

use super::csv::Tables;
use super::stats::{self, numeric};
use super::{field, merge, text, truth, EMPTY};

pub(super) fn spec(name: &str, record: &Json) -> Option<Json> {
    if ["Royal Ghost", "Battle Ram", "M.E.C.H.A"].contains(&name) {
        return None;
    }
    let mut result = obj([
        ("$type", string("UnitSpec")),
        ("name", string(name)),
        ("prefer", string("any")),
        ("walls", string("normal")),
        ("attack", string("single")),
        ("splash", num(0)),
        ("splash_ground_only", Json::Bool(false)),
        ("chain", num(0)),
        ("chain_range", num(3)),
        ("chain_decay", num(0.8)),
        ("chain_from_primary", Json::Bool(false)),
        ("bounces", num(0)),
        ("bounce_gap", num(3)),
        ("pierce", num(0)),
        ("vs_walls", num(1)),
        ("vs_resources", num(1)),
        ("vs_defenses", num(1)),
        ("vs_heroes", num(1)),
        ("vs_buildings", num(1)),
        ("engages_units", Json::Bool(true)),
        ("death_damage", Json::Null),
        ("death_radius", num(0)),
        ("death_delay", num(0)),
        ("death_freeze", Json::Null),
        ("death_freeze_radius", num(0)),
        ("death_spawn", arr([])),
        ("special", arr([])),
        ("heal_air", Json::Bool(false)),
        ("flying_override", Json::Null),
        ("notes", string("")),
    ]);
    let attributes = field(record, "attrs");
    let overrides = explicit(name).unwrap_or_else(|| {
        let prefer = text(field(attributes, "preferred_target")).to_lowercase();
        let prefer = if prefer.contains("defense") {
            "defense"
        } else if prefer.contains("resource") {
            "resource"
        } else if prefer.contains("wall") {
            "wall"
        } else {
            "any"
        };
        let splash = text(field(attributes, "attack_type"))
            .to_lowercase()
            .contains("splash");
        obj([
            ("prefer", string(prefer)),
            (
                "walls",
                string(if truth(field(attributes, "is_flying")) {
                    "fly"
                } else {
                    "normal"
                }),
            ),
            ("attack", string(if splash { "splash" } else { "single" })),
            ("splash", num(if splash { 1 } else { 0 })),
            ("notes", string("generic")),
        ])
    });
    merge(&mut result, &overrides);
    Some(result)
}

pub(super) fn summon(name: &str, spec: &Json) -> Json {
    let mut result = spec.clone();
    match name {
        "Henchman" | "Booger" => clash_data::wire::put(&mut result, "walls", string("fly")),
        "Lavaloon" => clash_data::wire::put(&mut result, "prefer", string("air_defense")),
        "Frostmite" => merge(
            &mut result,
            &obj([
                ("prefer", string("defense")),
                ("walls", string("ignore")),
                ("engages_units", Json::Bool(false)),
            ]),
        ),
        _ => {}
    }
    result
}

pub(super) fn movement(name: &str, record: &Json, common: &Json, tables: &Tables) -> f64 {
    if let Some(speed) = numeric(field(common, "movement_speed")) {
        return speed / 100.0;
    }
    if let Some(speed) = numeric(field(tables.unit(name, 1), "Speed")) {
        return speed / 100.0;
    }
    match name {
        "Giant Giant" => 1.65,
        "Mighty Yak" => 2.5,
        "Log Launcher" => 0.625,
        "Flame Flinger" => 0.75,
        _ => numeric(field(field(record, "attrs"), "speed"))
            .or_else(|| {
                numeric(field(field(record, "attrs"), "speed_display")).map(|speed| speed / 8.0)
            })
            .unwrap_or(0.0),
    }
}

pub(super) fn reach(record: &Json, common: &Json) -> Option<f64> {
    if let Some(reach) = numeric(field(common, "attack_range")) {
        return Some(reach / 100.0);
    }
    let attrs = field(record, "attrs");
    for key in ["Range", "Attack Range"] {
        if let Some(reach) = numeric(field(field(attrs, "raw"), key)) {
            return Some(reach);
        }
    }
    numeric(field(attrs, "range")).or_else(|| numeric(field(attrs, "range_ck")))
}

pub(super) fn unit_numbers(
    name: &str,
    record: &Json,
    common: &Json,
    tables: &Tables,
    level: i64,
    flyer_range: &str,
) -> Json {
    let level_json = num(level as f64);
    let current = stats::exact(record, &level_json);
    let attrs = field(record, "attrs");
    let mut hp = stats::get(record, &level_json, &["hitpoints", "Hitpoints"]).unwrap_or(0.0);
    let first = tables.unit(name, 1);
    let game_level = level - numeric(field(first, "VisualLevel")).unwrap_or(1.0) as i64 + 1;
    let candidate = if game_level > 0 {
        tables.unit(name, game_level)
    } else {
        &EMPTY
    };
    let row = if numeric(field(candidate, "VisualLevel")).unwrap_or(0.0) as i64 == level {
        candidate
    } else {
        &EMPTY
    };
    if field(current, "hitpoints").is_null() {
        hp = numeric(field(row, "Hitpoints")).unwrap_or(hp);
    }
    let mut interval = numeric(field(attrs, "attack_interval_ck"))
        .or_else(|| numeric(field(attrs, "attack_interval")))
        .unwrap_or(1.0);
    if let Some(speed) = numeric(field(common, "attack_speed")) {
        interval = speed / 1000.0;
    } else if let Some(speed) = numeric(field(row, "AttackSpeed")) {
        interval = speed / 1000.0;
    }
    let wiki_dps = stats::get(
        record,
        &level_json,
        &[
            "Damage per Second",
            "Damage per Second / Initial",
            "~damage per second",
        ],
    );
    let mut dps = stats::get(record, &level_json, &["dps"]);
    if field(current, "dps").is_null() {
        dps = numeric(field(row, "DPS")).or(dps);
    }
    let dps = dps.or(wiki_dps);
    let mut damage = stats::get(
        record,
        &level_json,
        &[
            "Damage per Hit",
            "Damage per Attack",
            "Damage per Hit (Primary Target)",
            "Damage per Hit (Primary)",
            "Damage per Hit / Hitbox 1",
            "Damage per Hit*",
            "Damage per Shot",
            "Damage",
        ],
    );
    if damage.is_none() {
        damage = dps.map(|dps| dps.abs() * interval);
    } else if let (Some(hit), Some(dps), Some(wiki)) = (damage, dps, wiki_dps) {
        if wiki != 0.0 && dps > 0.0 && (dps - wiki).abs() > 1.0_f64.max(0.02 * dps) {
            damage = Some(hit * (dps / wiki));
        }
    }
    if let (Some(hit), Some(dps)) = (damage, dps) {
        if dps > 0.0
            && (hit - dps * interval).abs() > 1.0_f64.max(0.02 * dps * interval)
            && numeric(field(tables.unit(name, level), "BurstCount")).unwrap_or(1.0) == 1.0
        {
            damage = Some(dps * interval);
        }
        if dps < 0.0 {
            damage = Some(0.0);
        }
    }
    let mut range = reach(record, common);
    match name {
        "Booger" => range = Some(0.9),
        "Bear" => range = Some(0.6),
        "Healer" => {
            range = Some(5.0);
            interval = 0.7;
        }
        "Druid" => interval = numeric(field(field(attrs, "raw"), "Heal Speed")).unwrap_or(interval),
        _ => {}
    }
    let mut housing = numeric(field(attrs, "housing"))
        .or_else(|| numeric(field(attrs, "housing_ck")))
        .unwrap_or(0.0);
    if let Some((_, value)) = SUBTROOP_HOUSING.iter().find(|(key, _)| *key == name) {
        housing = f64::from(*value);
    }
    let flying = field(attrs, "is_flying");
    let mut air = field(attrs, "is_air_targeting").clone();
    let mut ground = field(attrs, "is_ground_targeting").clone();
    if flying.is_null() || air.is_null() {
        let attack = format!(
            "{} {}",
            text(field(attrs, "attack_type")),
            text(field(attrs, "targets_text"))
        )
        .to_lowercase();
        if air.is_null() {
            air = Json::Bool(attack.contains("air"));
        }
        if ground.is_null() {
            ground = Json::Bool(attack.contains("ground") || !attack.contains("air"));
        }
    }
    if name == "Yetimite" {
        air = Json::Bool(true);
        ground = Json::Bool(true);
    }
    if flyer_range == "gamedata" {
        let game = numeric(field(common, "attack_range"))
            .map(|reach| reach / 100.0)
            .or_else(|| numeric(field(&tables.ranges, name)));
        if game.is_some() {
            range = game;
        }
    }
    obj([
        ("hp", num(hp)),
        ("dmg", num(damage.unwrap_or(0.0))),
        ("dps", num(dps.unwrap_or(0.0))),
        ("interval", num(interval)),
        ("range", num(range.unwrap_or(0.5))),
        ("speed", num(movement(name, record, common, tables))),
        ("housing", num(housing as i64 as f64)),
        ("flying", Json::Bool(truth(flying))),
        ("hits_air", Json::Bool(truth(&air))),
        ("hits_ground", Json::Bool(truth(&ground))),
    ])
}

const SUBTROOP_HOUSING: &[(&str, i32)] = &[
    ("Spell Skeleton", 1),
    ("Bat", 1),
    ("Frostmite", 1),
    ("Yetimite", 2),
    ("Meteormite", 20),
    ("Golemite", 6),
    ("Skeleton", 1),
    ("Lava Pup", 1),
    ("Bear", 10),
    ("Firemite", 1),
    ("Big Boy", 20),
    ("Witch Golem Big Boy", 20),
    ("Super Hog", 5),
    ("Super Rider", 5),
    ("Electromite", 3),
    ("Ice Pup", 1),
    ("Lavaloon Pup", 1),
    ("Witch Golem Skeleton", 1),
];

pub(super) fn explicit(name: &str) -> Option<Json> {
    let fields = match name {
        "Barbarian" => super::empty(),
        "Archer" => super::empty(),
        "Giant" => obj(vec![("prefer", string("defense"))]),
        "Goblin" => obj(vec![
            ("prefer", string("resource")),
            ("vs_resources", num(2.0)),
        ]),
        "Wall Breaker" => obj(vec![
            ("prefer", string("wall")),
            ("attack", string("suicide")),
            ("splash", num(0.8)),
            ("vs_walls", num(40.0)),
            ("death_damage", string("Damage when destroyed")),
            ("death_radius", num(1.5)),
        ]),
        "Balloon" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(1.2)),
            ("splash_ground_only", Json::Bool(true)),
            ("engages_units", Json::Bool(false)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(1.2)),
            ("death_delay", num(0.416)),
        ]),
        "Wizard" => obj(vec![("attack", string("splash")), ("splash", num(0.3))]),
        "Healer" => obj(vec![
            ("prefer", string("support")),
            ("walls", string("fly")),
            ("attack", string("heal")),
            ("splash", num(1.5)),
            ("engages_units", Json::Bool(false)),
        ]),
        "Dragon" => obj(vec![
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(0.3)),
        ]),
        "P.E.K.K.A" => super::empty(),
        "Baby Dragon" => obj(vec![
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(0.3)),
            ("special", arr([string("tantrum")])),
        ]),
        "Miner" => obj(vec![
            ("walls", string("ignore")),
            ("special", arr([string("burrow")])),
        ]),
        "Electro Dragon" => obj(vec![
            ("walls", string("fly")),
            ("attack", string("chain")),
            ("chain", num(4)),
            ("chain_range", num(3.0)),
            ("chain_decay", num(0.8)),
            ("special", arr([string("death_bolts")])),
        ]),
        "Yeti" => obj(vec![("special", arr([string("yetimites")]))]),
        "Dragon Rider" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("engages_units", Json::Bool(false)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(2.0)),
            ("death_delay", num(0.6)),
        ]),
        "Electro Titan" => obj(vec![("special", arr([string("titan_aura")]))]),
        "Root Rider" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("smash")),
            ("engages_units", Json::Bool(false)),
        ]),
        "Thrower" => super::empty(),
        "Minion" => obj(vec![("walls", string("fly"))]),
        "Hog Rider" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
            ("engages_units", Json::Bool(false)),
        ]),
        "Valkyrie" => obj(vec![("attack", string("spin")), ("splash", num(1.0))]),
        "Golem" => obj(vec![
            ("prefer", string("defense")),
            ("engages_units", Json::Bool(false)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(1.5)),
            (
                "death_spawn",
                arr([string("Golemite"), string("Golemites spawned Upon Death")]),
            ),
        ]),
        "Witch" => obj(vec![
            ("attack", string("splash")),
            ("splash", num(0.3)),
            ("special", arr([string("witch_skeletons")])),
        ]),
        "Lava Hound" => obj(vec![
            ("prefer", string("air_defense")),
            ("walls", string("fly")),
            ("engages_units", Json::Bool(false)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(1.2)),
            (
                "death_spawn",
                arr([
                    string("Lava Pup"),
                    string("Lava Pups Spawned (After Death) / On Offense"),
                ]),
            ),
        ]),
        "Bowler" => obj(vec![
            ("attack", string("bounce")),
            ("splash", num(0.3)),
            ("bounces", num(1)),
            ("bounce_gap", num(4.0)),
        ]),
        "Ice Golem" => obj(vec![
            ("prefer", string("defense")),
            ("engages_units", Json::Bool(false)),
            (
                "death_freeze",
                string("Freeze Time After Death / On Offense"),
            ),
            ("death_freeze_radius", num(7.5)),
            ("special", arr([string("chill")])),
        ]),
        "Headhunter" => obj(vec![
            ("prefer", string("heroes")),
            ("walls", string("ignore")),
            ("vs_heroes", num(4.0)),
            ("special", arr([string("hh_poison")])),
        ]),
        "Apprentice Warden" => obj(vec![
            ("prefer", string("follow")),
            ("walls", string("ignore")),
            ("special", arr([string("life_aura")])),
        ]),
        "Druid" => obj(vec![
            ("prefer", string("support")),
            ("walls", string("ignore")),
            ("attack", string("heal_chain")),
            ("chain", num(3)),
            ("heal_air", Json::Bool(true)),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("bear_after")])),
        ]),
        "Furnace" => obj(vec![
            ("prefer", string("none")),
            ("attack", string("none")),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("furnace")])),
        ]),
        "Meteor Golem" => obj(vec![
            ("attack", string("splash")),
            ("splash", num(1.0)),
            ("vs_walls", num(5.0)),
            ("special", arr([string("meteormites")])),
        ]),
        "Ruin Witch" => obj(vec![
            ("prefer", string("rubble")),
            ("attack", string("none")),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("ruin_witch")])),
        ]),
        "Super Barbarian" => obj(vec![("special", arr([string("start_rage")]))]),
        "Super Archer" => obj(vec![("attack", string("pierce")), ("pierce", num(11.5))]),
        "Super Giant" => obj(vec![("prefer", string("defense")), ("vs_walls", num(5.0))]),
        "Sneaky Goblin" => obj(vec![
            ("prefer", string("resource")),
            ("vs_resources", num(2.0)),
            ("special", arr([string("cloak")])),
        ]),
        "Super Wall Breaker" => obj(vec![
            ("prefer", string("wall")),
            ("attack", string("suicide")),
            ("splash", num(0.8)),
            ("vs_walls", num(40.0)),
            ("death_damage", string("Damage when destroyed")),
            ("death_radius", num(1.6)),
            ("special", arr([string("mega_bomb")])),
        ]),
        "Rocket Balloon" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(1.2)),
            ("splash_ground_only", Json::Bool(true)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(1.2)),
            ("death_delay", num(0.416)),
            ("special", arr([string("boosters")])),
        ]),
        "Super Wizard" => obj(vec![
            ("attack", string("chain")),
            ("chain", num(9)),
            ("chain_range", num(3.0)),
            ("chain_decay", num(0.4)),
            ("chain_from_primary", Json::Bool(true)),
        ]),
        "Super Dragon" => obj(vec![
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(1.6)),
            ("special", arr([string("burst")])),
        ]),
        "Inferno Dragon" => obj(vec![("walls", string("fly")), ("attack", string("beam"))]),
        "Super Minion" => obj(vec![
            ("walls", string("fly")),
            ("special", arr([string("long_shot")])),
        ]),
        "Super Valkyrie" => obj(vec![
            ("attack", string("spin")),
            ("splash", num(1.0)),
            ("special", arr([string("death_rage")])),
        ]),
        "Super Witch" => obj(vec![
            ("attack", string("splash")),
            ("splash", num(0.3)),
            ("special", arr([string("big_boy")])),
        ]),
        "Ice Hound" => obj(vec![
            ("prefer", string("air_defense")),
            ("walls", string("fly")),
            ("death_freeze", string("Freeze Time when Destroyed")),
            ("death_freeze_radius", num(4.0)),
            (
                "death_spawn",
                arr([string("Ice Pup"), string("Ice Pups Spawned / On Offense")]),
            ),
            ("special", arr([string("ice_chill")])),
        ]),
        "Super Bowler" => obj(vec![
            ("attack", string("bounce")),
            ("splash", num(0.6)),
            ("bounces", num(2)),
            ("bounce_gap", num(3.0)),
        ]),
        "Super Miner" => obj(vec![
            ("walls", string("ignore")),
            ("attack", string("beam")),
            ("special", arr([string("burrow")])),
            ("death_damage", string("Damage when Destroyed")),
            ("death_radius", num(2.0)),
            ("death_delay", num(1.0)),
        ]),
        "Super Hog Rider" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
            ("special", arr([string("hog_split")])),
        ]),
        "Super Yeti" => obj(vec![("special", arr([string("electromites")]))]),
        "Wall Wrecker" => obj(vec![
            ("prefer", string("th")),
            ("attack", string("splash")),
            ("splash", num(1.5)),
            ("vs_walls", num(10.0)),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("siege_cc")])),
        ]),
        "Battle Blimp" => obj(vec![
            ("prefer", string("th")),
            ("walls", string("fly")),
            ("attack", string("none")),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("siege_cc"), string("blimp_bombs")])),
            ("death_damage", string("Damage when Destroyed")),
            ("death_radius", num(3.0)),
            ("death_delay", num(0.7)),
        ]),
        "Stone Slammer" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(1.0)),
            ("engages_units", Json::Bool(false)),
            ("death_damage", string("Damage when Destroyed")),
            ("death_radius", num(3.0)),
            ("death_delay", num(0.416)),
            ("special", arr([string("siege_cc")])),
        ]),
        "Siege Barracks" => obj(vec![
            ("prefer", string("none")),
            ("attack", string("none")),
            ("engages_units", Json::Bool(false)),
            (
                "special",
                arr([string("siege_cc"), string("siege_barracks")]),
            ),
        ]),
        "Log Launcher" => obj(vec![
            ("prefer", string("th")),
            ("attack", string("none")),
            ("vs_walls", num(4.0)),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("siege_cc"), string("logs")])),
        ]),
        "Flame Flinger" => obj(vec![
            ("prefer", string("defense")),
            ("attack", string("splash")),
            ("splash", num(1.0)),
            ("vs_walls", num(8.0)),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("siege_cc"), string("flinger")])),
        ]),
        "Battle Drill" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
            ("engages_units", Json::Bool(false)),
            (
                "special",
                arr([string("siege_cc"), string("burrow"), string("drill_stun")]),
            ),
        ]),
        "Troop Launcher" => obj(vec![
            ("prefer", string("none")),
            ("attack", string("none")),
            ("engages_units", Json::Bool(false)),
            (
                "special",
                arr([string("siege_cc"), string("troop_launcher")]),
            ),
        ]),
        "Sky Wagon" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("attack", string("none")),
            ("engages_units", Json::Bool(false)),
            ("special", arr([string("siege_cc"), string("sky_wagon")])),
        ]),
        "Lava Pup" => obj(vec![("walls", string("fly"))]),
        "Golemite" => obj(vec![
            ("prefer", string("defense")),
            ("engages_units", Json::Bool(false)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(1.2)),
        ]),
        "Yetimite" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
            ("attack", string("splash")),
            ("splash", num(0.8)),
            ("vs_defenses", num(4.0)),
            ("vs_resources", num(0.5)),
        ]),
        "Electromite" => obj(vec![
            ("prefer", string("building")),
            ("walls", string("ignore")),
            ("attack", string("chain")),
            ("chain", num(2)),
            ("chain_range", num(3.0)),
            ("chain_decay", num(0.8)),
            ("vs_buildings", num(4.0)),
        ]),
        "Big Boy" => super::empty(),
        "Ruin Knight" => obj(vec![("vs_walls", num(3.0))]),
        "Firemite" => obj(vec![
            ("walls", string("ignore")),
            ("attack", string("splash")),
            ("splash", num(0.1)),
        ]),
        "Bear" => obj(vec![("prefer", string("defense"))]),
        "Longshot" => obj(vec![
            ("attack", string("splash")),
            ("splash", num(1.0)),
            ("death_damage", string("Damage Upon Death")),
            ("death_radius", num(3.5)),
            ("death_delay", num(0.2)),
            ("special", arr([string("guardian")])),
        ]),
        "Smasher" => obj(vec![
            ("attack", string("splash")),
            ("splash", num(2.5)),
            ("special", arr([string("guardian"), string("smasher")])),
        ]),
        "Logger" => obj(vec![
            ("attack", string("splash")),
            ("splash", num(1.5)),
            ("special", arr([string("guardian"), string("logger")])),
        ]),
        "Ice Pup" => obj(vec![
            ("walls", string("fly")),
            ("special", arr([string("ice_chill")])),
        ]),
        "Meteormite" => obj(vec![("walls", string("ignore"))]),
        "Frostmite" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
            ("splash", num(0.8)),
        ]),
        "Skeleton" => super::empty(),
        "Spell Skeleton" => super::empty(),
        "Bat" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("engages_units", Json::Bool(false)),
        ]),
        "Snake" => obj(vec![("walls", string("ignore"))]),
        "Super Rider" => obj(vec![("vs_walls", num(2.0))]),
        "Super Hog" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
        ]),
        "Henchman" => obj(vec![("walls", string("ignore"))]),
        "Lavaloon" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("fly")),
            ("attack", string("splash")),
            ("splash", num(1.8)),
            ("engages_units", Json::Bool(false)),
        ]),
        "Booger" => super::empty(),
        "Giant Giant" => obj(vec![
            ("prefer", string("defense")),
            ("attack", string("splash")),
            ("splash", num(1.5)),
            ("engages_units", Json::Bool(true)),
            ("vs_walls", num(2.0)),
        ]),
        "Barbarian King" => super::empty(),
        "Archer Queen" => super::empty(),
        "Grand Warden" => obj(vec![
            ("prefer", string("follow")),
            ("walls", string("ignore")),
        ]),
        "Royal Champion" => obj(vec![
            ("prefer", string("defense")),
            ("walls", string("ignore")),
        ]),
        "Minion Prince" => obj(vec![("walls", string("fly"))]),
        "Dragon Duke" => obj(vec![
            ("walls", string("fly")),
            ("special", arr([string("royal_rampage")])),
        ]),
        _ => return None,
    };
    Some(fields)
}
