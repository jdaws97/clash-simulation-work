use clash_data::json::Json;
use clash_data::wire::{self, num, obj, put, string};

use super::csv::Tables;
use super::stats::{self, numeric};
use super::{empty, entries, field, items, merge, object, registry, specs, tables, text, Sources};

pub(super) fn catalog(sources: &Sources) -> Result<Json, String> {
    let raw = wire::read(&sources.root.join("data/source/clashking-static-data.json"))?;
    let mut reg = registry::build(&raw, &sources.wiki)?;
    let csv = Tables::load(&sources.root)?;
    registry::repair_inferno(&mut reg, &csv)?;
    // The frozen Windows exporter hashed this generated intermediate as CRLF.
    let registry_hash = wire::sha256(
        super::encoding::registry(&reg)
            .replace('\n', "\r\n")
            .as_bytes(),
    );
    let overrides = wire::read(&sources.root.join("data/source/balance-overrides.json"))?;
    stats::augment(&mut reg);
    stats::apply_overrides(&mut reg, &overrides, false)?;
    let mut ck = stats::ck_entries(&raw);
    stats::apply_overrides(&mut ck, &overrides, true)?;
    let flyer_range =
        std::env::var("BASELAB_FLYER_RANGE").unwrap_or_else(|_| "gamedata".to_owned());
    let mut units = empty();
    let mut numbers = empty();
    let mut pet_ranges = empty();
    let mut pet_speeds = empty();
    let mut labs = empty();
    for (name, record) in entries(&reg) {
        let kind = text(field(record, "kind"));
        let common = stats::ck(&reg, &ck, name);
        if kind == "pet" {
            let range = numeric(field(field(record, "attrs"), "range_ck"))
                .or_else(|| specs::reach(record, common));
            put(&mut pet_ranges, name, range.map_or(Json::Null, num));
            put(
                &mut pet_speeds,
                name,
                num(specs::movement(name, record, common, &csv)),
            );
        }
        if ![
            "troop",
            "super_troop",
            "siege",
            "hero",
            "pet",
            "summon",
            "spell",
        ]
        .contains(&kind)
            && specs::explicit(name).is_none()
        {
            continue;
        }
        let Some(spec) = specs::spec(name, record) else {
            continue;
        };
        put(
            &mut units,
            name,
            obj([
                ("spec", spec.clone()),
                ("summon_spec", specs::summon(name, &spec)),
            ]),
        );
        let mut required_labs = empty();
        for entry in items(field(record, "levels")) {
            let level = field(entry, "level");
            let Json::Num(level_number) = level else {
                continue;
            };
            let level_number = *level_number as i64;
            put(
                &mut numbers,
                &format!("{name}|{level_number}"),
                specs::unit_numbers(name, record, common, &csv, level_number, &flyer_range),
            );
            put(
                &mut required_labs,
                &level_number.to_string(),
                stats::required_lab(&reg, name, level).map_or(Json::Null, num),
            );
        }
        put(&mut labs, name, required_labs);
    }
    let mut abilities = empty();
    for (name, csv_name, index) in [
        ("Fire Heart", "DragonCrownRegeneration", 1),
        ("Noble Iron", "MPTurboStart", 0),
        ("Giant Arrow", "ArcherQueenPierceProjectile", 0),
        ("Eternal Tome", "GrandWardenInvulnerability", 0),
        ("Heroic Torch", "GWHeroicTorch", 0),
        ("Rocket Backpack", "DragonDukeDeadlyDashMapCenter", 0),
        ("Rage Vial", "BarbarianKingRage", 0),
    ] {
        for entry in items(field(field(&reg, name), "levels")) {
            let Json::Num(level) = field(entry, "level") else {
                continue;
            };
            let level = *level as i64;
            let ck_level = stats::exact(stats::ck(&reg, &ck, name), &num(level as f64));
            let ability = items(field(ck_level, "abilities"))
                .get(index)
                .unwrap_or(&super::EMPTY);
            let ability_level =
                numeric(field(ability, "Level")).unwrap_or((level / 3 + 1) as f64) as i64;
            let mut resolved = csv
                .row("special_abilities", csv_name, ability_level)
                .clone();
            merge(&mut resolved, ability);
            put(&mut abilities, &format!("{name}|{level}"), resolved);
        }
    }
    let mut spell_radii = empty();
    let mut zap_radii = empty();
    for (name, default) in [
        ("Lightning Spell", 2.0),
        ("Earthquake Spell", 4.7),
        ("Jump Spell", 3.5),
        ("Haste Spell", 4.0),
        ("Skeleton Spell", 2.25),
        ("Bat Spell", 2.25),
        ("Totem Spell", 5.0),
    ] {
        for entry in items(field(field(&reg, name), "levels")) {
            let Json::Num(level) = field(entry, "level") else {
                continue;
            };
            let level = *level as i64;
            put(
                &mut spell_radii,
                &format!("{name}|{level}"),
                num(radius(&reg, &ck, &csv, name, level, default)),
            );
            if ["Lightning Spell", "Earthquake Spell"].contains(&name) {
                put(
                    &mut zap_radii,
                    &format!("{name}|{level}"),
                    num(radius(&reg, &ck, &csv, name, level, 0.0)),
                );
            }
        }
    }
    let mut revenge = empty();
    let mut scatter = empty();
    for entry in items(field(field(&reg, "Revenge Deck"), "levels")) {
        let Json::Num(level) = field(entry, "level") else {
            continue;
        };
        let current = stats::exact(stats::ck(&reg, &ck, "Revenge Deck"), &num(*level));
        let ability = items(field(current, "abilities"))
            .first()
            .ok_or("missing Revenge Deck ability")?;
        let range = numeric(field(ability, "ReflectedRange"))
            .ok_or("missing Revenge Deck ReflectedRange")?;
        put(
            &mut revenge,
            &(*level as i64).to_string(),
            num(range / 100.0),
        );
    }
    for entry in items(field(field(&reg, "Scattershot"), "levels")) {
        let Json::Num(level) = field(entry, "level") else {
            continue;
        };
        let current = stats::exact(stats::ck(&reg, &ck, "Scattershot"), &num(*level));
        let interval =
            numeric(field(current, "attack_speed")).ok_or("missing Scattershot attack_speed")?;
        put(
            &mut scatter,
            &(*level as i64).to_string(),
            num(interval / 1000.0),
        );
    }
    let mut tower = empty();
    for level in 1..=4 {
        let current = stats::exact(stats::ck(&reg, &ck, "Spell Tower"), &num(level));
        put(
            &mut tower,
            &level.to_string(),
            obj([
                (
                    "range",
                    num(numeric(field(current, "attack_range")).unwrap_or(900.0) / 100.0),
                ),
                (
                    "interval",
                    num(numeric(field(current, "attack_speed")).unwrap_or(70000.0) / 1000.0),
                ),
            ]),
        );
    }
    let mut mortar = empty();
    for entry in items(field(field(&reg, "Mortar"), "levels")) {
        let Json::Num(level) = field(entry, "level") else {
            continue;
        };
        if *level < 8.0 {
            continue;
        }
        let current = object(
            stats::exact(stats::ck(&reg, &ck, "Mortar"), &num(*level)),
            "alt",
        );
        let row = csv.row("buildings", "Mortar", *level as i64);
        let interval = numeric(field(current, "attack_speed"))
            .or_else(|| numeric(field(row, "AltAttackSpeed")))
            .ok_or("missing Mortar alternate interval")?;
        let dps = numeric(field(current, "dps"))
            .or_else(|| numeric(field(row, "AltDPS")))
            .ok_or("missing Mortar alternate DPS")?;
        put(
            &mut mortar,
            &(*level as i64).to_string(),
            obj([("interval", num(interval / 1000.0)), ("dps", num(dps))]),
        );
    }
    let mut setup = tables::setup();
    put(&mut setup, "donated_laboratory", labs);
    put(
        &mut setup,
        "siege_donation_caps",
        siege_caps(&sources.wiki)?,
    );
    put(
        &mut setup,
        "env",
        obj([
            ("dt", num(environment_number("BASELAB_DT", 0.1)?)),
            (
                "fast_end",
                Json::Bool(std::env::var("BASELAB_FAST_END").is_ok_and(|value| value == "1")),
            ),
            (
                "windup",
                Json::Bool(std::env::var("BASELAB_WINDUP").map_or(true, |value| value != "0")),
            ),
            ("flyer_range", string(flyer_range)),
            ("pace", num(environment_number("BASELAB_PACE", 1.0)?)),
            ("pace_tap", num(0.133)),
            ("pace_switch", num(0.6)),
            ("pace_ability", num(0.3)),
        ]),
    );
    Ok(obj([
        ("game_data", csv.data),
        (
            "note",
            string("Rust engine catalog, exported by tools/baselab/rust_export.py catalog"),
        ),
        ("registry", reg),
        ("units", units),
        ("unit_numbers", numbers),
        ("building_types", tables::buildings()),
        ("new_target_delays", csv.delays),
        (
            "warden_weights",
            wire::read(&sources.root.join("data/source/warden-weights.json"))?,
        ),
        ("poison_ramp", num(4)),
        ("game_ranges", csv.ranges),
        ("pet_spawn_ranges", pet_ranges),
        (
            "resolved",
            obj([
                (
                    "source_hashes",
                    obj([
                        ("registry", string(registry_hash)),
                        (
                            "balance_overrides",
                            string(wire::file_hash(
                                &sources.root.join("data/source/balance-overrides.json"),
                            )?),
                        ),
                    ]),
                ),
                ("equipment_abilities", abilities),
                ("revenge_ranges", revenge),
                ("scatter_intervals", scatter),
                ("spell_radii", spell_radii),
                ("zap_radii", zap_radii),
                ("pet_spawn_speeds", pet_speeds),
                ("spell_tower_profiles", tower),
                ("mortar_alternates", mortar),
            ]),
        ),
        (
            "trap_names",
            obj([
                ("giga", string("Giga Bomb")),
                ("bomb", string("Bomb")),
                ("spring", string("Spring Trap")),
                ("giant", string("Giant Bomb")),
                ("airbomb", string("Air Bomb")),
                ("seeking", string("Seeking Air Mine")),
                ("skeleton", string("Skeleton Trap")),
                ("tornado", string("Tornado Trap")),
            ]),
        ),
        ("trap_sizes", obj([("giant", num(2)), ("giga", num(2))])),
        ("world", num(50)),
        ("margin", num(3)),
        ("setup", setup),
    ]))
}

fn environment_number(name: &str, fallback: f64) -> Result<f64, String> {
    std::env::var(name).map_or(Ok(fallback), |value| {
        let number = value
            .parse::<f64>()
            .map_err(|error| format!("{name}: {error}"))?;
        if !number.is_finite() {
            return Err(format!("{name}: requires a finite number"));
        }
        Ok(number)
    })
}

fn radius(reg: &Json, ck: &Json, csv: &Tables, name: &str, level: i64, default: f64) -> f64 {
    let record = field(reg, name);
    let mut radius = stats::get(record, &num(level as f64), &["radius", "Radius"])
        .filter(|value| *value != 0.0)
        .or_else(|| numeric(field(field(field(record, "attrs"), "raw"), "Radius")))
        .unwrap_or(default);
    if let Some(value) = numeric(field(csv.row("spells", name, level), "Radius")) {
        radius = value / 100.0;
    }
    if let Some(current) = numeric(field(
        stats::exact(stats::ck(reg, ck, name), &num(level as f64)),
        "radius",
    )) {
        if radius == 0.0 || (radius - current).abs() > 0.05 + 1e-9 {
            return current;
        }
    }
    if radius == 0.0 {
        default
    } else {
        radius
    }
}

fn siege_caps(wiki: &std::path::Path) -> Result<Json, String> {
    let page = wire::read(&wiki.join("tables/Clan_Castle.json"))?;
    let table = items(field(&page, "tables"))
        .iter()
        .find(|table| text(field(table, "heading")) == "Siege Machine Level Cap")
        .ok_or("missing Clan Castle Siege Machine Level Cap wiki table")?;
    let mut result = empty();
    for row in items(field(table, "rows")) {
        let row = items(row);
        let Some(name) = row.first() else {
            continue;
        };
        let mut caps = empty();
        for (castle, value) in (6..14).zip(row.iter().skip(1)) {
            put(
                &mut caps,
                &castle.to_string(),
                num(numeric(value).unwrap_or(0.0) as i64 as f64),
            );
        }
        put(&mut result, text(name), caps);
    }
    Ok(result)
}

#[cfg(test)]
mod environment_tests {
    use super::environment_number;

    #[test]
    fn numeric_environment_options_reject_nonfinite_values() {
        // A dedicated variable avoids racing other catalog tests' environment.
        let name = "CLASH_H1_SYNTHETIC_ENV_NUMBER";
        for value in ["NaN", "inf", "-inf", "Infinity", "1e999"] {
            std::env::set_var(name, value);
            assert!(environment_number(name, 0.1)
                .unwrap_err()
                .contains("finite"));
        }
        std::env::set_var(name, "0.125");
        assert_eq!(environment_number(name, 0.1).unwrap(), 0.125);
        std::env::remove_var(name);
        assert_eq!(environment_number(name, 0.1).unwrap(), 0.1);
    }
}
