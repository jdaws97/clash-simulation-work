//! The stats.py precedence contract, including exact levels and balance totals.

use clash_data::json::Json;
use clash_data::wire::{arr, num, obj, put, string};

use super::{empty, entries, field, get_mut, items, object, text, truth};

/// First numeric token, matching `-?\d[\d,]*\.?\d*` (Unicode minus accepted).
pub(super) fn numeric(value: &Json) -> Option<f64> {
    match value {
        Json::Num(value) => Some(*value),
        Json::Bool(value) => Some(f64::from(u8::from(*value))),
        Json::Str(value) => {
            let value = value.replace('−', "-");
            let bytes = value.as_bytes();
            let first = bytes.iter().position(u8::is_ascii_digit)?;
            let start = if first > 0 && bytes[first - 1] == b'-' {
                first - 1
            } else {
                first
            };
            let mut end = first;
            while end < bytes.len() && (bytes[end].is_ascii_digit() || bytes[end] == b',') {
                end += 1;
            }
            if bytes.get(end) == Some(&b'.') {
                end += 1;
                while end < bytes.len() && bytes[end].is_ascii_digit() {
                    end += 1;
                }
            }
            value[start..end].replace(',', "").parse().ok()
        }
        _ => None,
    }
}

pub(super) fn exact<'a>(record: &'a Json, level: &Json) -> &'a Json {
    items(field(record, "levels"))
        .iter()
        .find(|entry| field(entry, "level") == level)
        .unwrap_or(&super::EMPTY)
}

pub(super) fn get(record: &Json, level: &Json, keys: &[&str]) -> Option<f64> {
    let entry = exact(record, level);
    let mut lower = empty();
    for (key, value) in entries(entry)
        .iter()
        .filter(|(key, _)| key != "wiki")
        .chain(entries(field(entry, "wiki")))
    {
        put(&mut lower, &key.to_lowercase(), value.clone());
    }
    for (alias, columns) in [
        ("hitpoints", &["hitpoints"][..]),
        (
            "dps",
            &[
                "damage per second",
                "damage per second*",
                "base damage per second",
            ][..],
        ),
    ] {
        if numeric(field(entry, alias)).is_some() {
            put(&mut lower, alias, field(entry, alias).clone());
        } else {
            let value = columns.iter().find_map(|column| {
                entries(field(entry, "wiki"))
                    .iter()
                    .find(|(key, value)| key.to_lowercase() == *column && numeric(value).is_some())
                    .map(|(_, value)| value)
            });
            if let Some(value) = value {
                put(&mut lower, alias, value.clone());
            }
        }
    }
    for key in keys {
        let key = key.to_lowercase();
        if let Some(fragment) = key.strip_prefix('~') {
            for (column, value) in entries(&lower) {
                if column.contains(fragment) {
                    if let Some(value) = numeric(value) {
                        return Some(value);
                    }
                }
            }
        } else if let Some(value) = numeric(field(&lower, &key)) {
            return Some(value);
        }
    }
    None
}

pub(super) fn ck_entries(raw: &Json) -> Json {
    let mut result = empty();
    for section in [
        "buildings",
        "traps",
        "troops",
        "guardians",
        "spells",
        "heroes",
        "pets",
        "equipment",
    ] {
        for entry in items(field(raw, section)) {
            if entry.get("village").map(text).unwrap_or("home") != "home" {
                continue;
            }
            let name = text(field(entry, "name"));
            if result.get(name).is_none() || !truth(field(entry, "is_seasonal")) {
                put(&mut result, name, entry.clone());
            }
        }
    }
    result
}

pub(super) fn apply_overrides(
    records: &mut Json,
    overrides: &Json,
    clashking: bool,
) -> Result<(), String> {
    if field(overrides, "schema_version") != &num(1) {
        return Err("unsupported balance override schema".to_owned());
    }
    for change in items(field(overrides, "overrides")) {
        let name = text(field(change, "entity"));
        if records.get(name).is_none() {
            if clashking {
                continue;
            }
            return Err(format!("balance override has no entity: {name}"));
        }
        let record = get_mut(records, name);
        let key = text(field(change, "field"));
        let value = field(change, "new_value");
        let level = field(change, "level");
        if text(level) == "all" {
            if clashking {
                let (key, value) = match key {
                    "housing" => ("housing_space", value.clone()),
                    "movement_speed" => ("movement_speed", num(value.f64() * 100.0 / 8.0)),
                    _ => return Err(format!("unsupported entity-wide balance field: {key}")),
                };
                put(record, key, value);
            } else {
                let attrs = get_mut(record, "attrs");
                if attrs.get("raw").is_none() {
                    put(attrs, "raw", empty());
                }
                match key {
                    "housing" => {
                        put(attrs, "housing", value.clone());
                        put(get_mut(attrs, "raw"), "Housing Space", value.clone());
                    }
                    "movement_speed" => {
                        put(attrs, "speed_display", value.clone());
                        put(attrs, "speed", num(value.f64() / 8.0));
                        put(get_mut(attrs, "raw"), "Movement Speed", value.clone());
                    }
                    _ => return Err(format!("unsupported entity-wide balance field: {key}")),
                }
            }
            continue;
        }
        let Json::Arr(levels) = get_mut(record, "levels") else {
            return Err(format!("missing balance levels: {name}"));
        };
        let Some(entry) = levels
            .iter_mut()
            .find(|entry| field(entry, "level") == level)
        else {
            if clashking {
                continue;
            }
            return Err(format!("balance override has no level: {name} {level:?}"));
        };
        if !clashking {
            let wiki_key = match key {
                "hitpoints" => "Hitpoints",
                "dps" => "Damage per Second",
                "damage_per_attack" => "Damage per Attack",
                "bonus_hitpoints" => "Hero Boosts / Hitpoint Increase",
                "bonus_dps" => "Hero Boosts / Damage per Second Increase",
                "regeneration" => "Hero Boosts / Self Healing Per Second",
                "slow_percent" => "Ability Attributes / Slow Down",
                _ => return Err(format!("unsupported balance field: {key}")),
            };
            if entry.get("wiki").is_none() {
                put(entry, "wiki", empty());
            }
            put(get_mut(entry, "wiki"), wiki_key, value.clone());
        }
        match key {
            "hitpoints" | "dps" => put(entry, key, value.clone()),
            "bonus_dps" => put(entry, "dps", value.clone()),
            "regeneration" | "slow_percent" if clashking => {
                let Json::Arr(abilities) = get_mut(entry, "abilities") else {
                    return Err(format!("missing abilities: {name}"));
                };
                let (index, key) = if key == "regeneration" {
                    (1, "Regeneration")
                } else {
                    (0, "FrostOnHitPercent")
                };
                let ability = abilities
                    .get_mut(index)
                    .ok_or_else(|| format!("missing balance ability: {name}"))?;
                put(ability, key, value.clone());
            }
            _ => {}
        }
    }
    Ok(())
}

pub(super) fn augment(registry: &mut Json) {
    let additions = [
        (
            "Birthday Boom",
            2,
            obj([
                ("Damage", num(500)),
                ("Damage vs Town Hall", num(350)),
                ("Radius", num(2.5)),
                ("Freeze Duration", num(2)),
            ]),
        ),
        (
            "Yellow Card",
            1,
            obj([("Duration", num(15)), ("Radius", num(7))]),
        ),
    ];
    for (name, housing, wiki) in additions {
        if registry.get(name).is_none() {
            put(
                registry,
                name,
                obj([
                    ("name", string(name)),
                    ("kind", string("spell")),
                    ("seasonal", Json::Bool(true)),
                    (
                        "attrs",
                        obj([
                            ("housing", num(housing)),
                            ("raw", obj([("Spell Factory Level Required", num(1))])),
                        ]),
                    ),
                    ("levels", arr([obj([("level", num(1)), ("wiki", wiki)])])),
                ]),
            );
        }
    }
    if registry.get("Lavaloon Pup").is_none() {
        let damage = [10, 13, 16, 19, 22, 25, 28, 31, 34, 37, 40, 42, 44];
        let health = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70];
        let levels = damage
            .into_iter()
            .zip(health)
            .enumerate()
            .map(|(index, (hit, hp))| {
                obj([
                    ("level", num((index + 1) as f64)),
                    (
                        "wiki",
                        obj([
                            ("Hitpoints", num(hp)),
                            ("Damage per Attack", num(hit)),
                            ("Damage per Second", num(hit)),
                        ]),
                    ),
                ])
            });
        put(
            registry,
            "Lavaloon Pup",
            obj([
                ("name", string("Lavaloon Pup")),
                ("kind", string("summon")),
                (
                    "attrs",
                    obj([
                        ("housing", num(1)),
                        ("speed_display", num(32)),
                        ("attack_interval", num(1)),
                        ("range", num(2)),
                        ("is_flying", Json::Bool(true)),
                        ("is_air_targeting", Json::Bool(true)),
                        ("is_ground_targeting", Json::Bool(true)),
                    ]),
                ),
                ("levels", arr(levels)),
            ]),
        );
    }
    for (name, health, profile) in [
        (
            "Monolith",
            [5959, 6161],
            obj([
                ("Base Damage per Shot", num(352.5)),
                ("Bonus Damage per Shot", num(15)),
            ]),
        ),
        (
            "Multi-Gear Tower",
            [4350, 4500],
            obj([
                ("Damage per Hit", num(400)),
                ("Damage per Hit**", num(172.8)),
            ]),
        ),
    ] {
        let Json::Arr(levels) = get_mut(get_mut(registry, name), "levels") else {
            unreachable!()
        };
        for (index, hp) in health.into_iter().enumerate() {
            let level = string(format!("charge:{}", index + 1));
            if levels.iter().any(|entry| field(entry, "level") == &level) {
                continue;
            }
            let mut wiki = profile.clone();
            put(&mut wiki, "Hitpoints", num(hp));
            put(&mut wiki, "Town Hall Level Required", num(18));
            levels.push(obj([
                ("level", level),
                ("wiki", wiki),
                ("wiki_only", Json::Bool(true)),
            ]));
        }
    }
}

pub(super) fn ck<'a>(registry: &Json, entries: &'a Json, name: &str) -> &'a Json {
    if registry.get(name).is_some()
        && !truth(field(object(field(registry, name), "source"), "clashking"))
    {
        return &super::EMPTY;
    }
    object(entries, name)
}

pub(super) fn required_lab(registry: &Json, name: &str, level: &Json) -> Option<f64> {
    let mut name = name;
    let record = field(registry, name);
    if text(field(record, "kind")) == "super_troop" {
        for (column, _) in entries(field(field(record, "attrs"), "raw")) {
            if let Some(base) = column.strip_suffix(" Level Required") {
                if text(field(field(registry, base), "kind")) == "troop" {
                    name = base;
                    break;
                }
            }
        }
    }
    let record = field(registry, name);
    if let Some(required) = get(record, level, &["Laboratory Level Required"]) {
        return Some(required);
    }
    let th = get(
        record,
        level,
        &["Town Hall Level Required", "required_townhall"],
    )
    .unwrap_or(0.0) as i64;
    let lab = field(registry, "Laboratory");
    let maximum = field(field(lab, "max_level"), &th.to_string());
    if let Some(maximum) = numeric(maximum) {
        return Some(maximum);
    }
    items(field(lab, "levels"))
        .iter()
        .filter(|row| {
            get(
                lab,
                field(row, "level"),
                &["Town Hall Level Required", "required_townhall"],
            )
            .unwrap_or(0.0)
                <= th as f64
        })
        .filter_map(|row| numeric(field(row, "level")))
        .reduce(f64::max)
}
