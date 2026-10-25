//! Registry construction from normalized wiki tables and ClashKing records.

use std::path::Path;

use clash_data::json::Json;
use clash_data::wire::{arr, num, obj, put, read, string};

use super::stats::numeric;
use super::{empty, entries, field, items, merge, object, required_text, text, truth};

pub(super) const SUMMONS: &[(&str, &str)] = &[
    ("Lava Pup", "Lava Hound/Lava Pup"),
    ("Golemite", "Golem/Golemite"),
    ("Yetimite", "Yeti/Yetimite"),
    ("Electromite", "Super Yeti/Electromite"),
    ("Big Boy", "Super Witch/Big Boy"),
    ("Ruin Knight", "Ruin Witch/Ruin Knight"),
    ("Firemite", "Furnace/Firemite"),
    ("Bear", "Druid/Bear"),
    ("Ice Pup", "Ice Hound/Ice Pup"),
    ("Meteormite", "Meteor Golem/Meteormite"),
    ("Frostmite", "Frosty/Frostmite"),
    ("Skeleton", "Witch/Skeleton"),
    ("Spell Skeleton", "Skeleton Spell/Skeleton"),
    ("Bat", "Bat Spell/Bat"),
    ("Snake", "Snake Bracelet/Snake"),
    ("Super Rider", "Super Hog Rider/Super Rider"),
    ("Super Hog", "Super Hog Rider/Super Hog"),
    ("Henchman", "Henchmen Puppet/Henchmen"),
    ("Lavaloon", "Lavaloon Puppet/Lavaloon"),
    ("Booger", "Sneezy/Booger"),
    ("Giant Giant", "Giant Giant"),
];

fn safe(title: &str) -> String {
    let mut result = String::new();
    for ch in title.chars() {
        if ch.is_ascii_alphanumeric() || "._-".contains(ch) {
            result.push(ch);
        } else if !result.ends_with('_') {
            result.push('_');
        }
    }
    result.trim_matches('_').to_owned()
}

fn page(wiki: &Path, name: &str) -> Result<(Json, String), String> {
    for title in [format!("{name}/Home Village"), name.to_owned()] {
        let stem = safe(&title);
        let path = wiki.join("tables").join(format!("{stem}.json"));
        if path.exists() {
            let table = read(&path)?;
            let notes = required_text(&wiki.join("text").join(format!("{stem}.txt")))?;
            return Ok((table, notes));
        }
    }
    Err(format!(
        "missing required wiki table for {name}: {}",
        wiki.join("tables").display()
    ))
}

fn numbers(source: &str) -> Vec<f64> {
    source
        .split(|ch: char| !ch.is_ascii_digit() && ch != '.')
        .filter_map(|part| part.parse().ok())
        .collect()
}

// Match the frozen infobox regex in left-to-right order. Parentheses and
// semicolons between "splash" and its number deliberately do not match.
fn splash_radius(source: &str) -> Option<f64> {
    let mut candidates = Vec::new();
    let bytes = source.as_bytes();
    for (start, _) in source
        .char_indices()
        .filter(|(_, ch)| ch.is_ascii_digit() || *ch == '.')
    {
        let end = (start..bytes.len())
            .find(|index| !bytes[*index].is_ascii_digit() && bytes[*index] != b'.')
            .unwrap_or(bytes.len());
        let suffix = source[end..].trim_start();
        if let Some(rest) = suffix.strip_prefix("tile") {
            let rest = rest.strip_prefix('s').unwrap_or(rest).trim_start();
            if rest.starts_with("radius") {
                if let Ok(value) = source[start..end].parse::<f64>() {
                    candidates.push((start, value));
                }
            }
        }
    }
    for (start, _) in source.match_indices("splash") {
        let tail = source[start + "splash".len()..].trim_start();
        let tail = tail.strip_prefix('-').unwrap_or(tail).trim_start();
        let end = tail
            .find(|ch: char| !ch.is_ascii_digit() && ch != '.')
            .unwrap_or(tail.len());
        if tail[end..].trim_start().starts_with("tile") {
            if let Ok(value) = tail[..end].parse::<f64>() {
                candidates.push((start, value));
            }
        }
    }
    candidates
        .into_iter()
        .min_by_key(|(start, _)| *start)
        .map(|(_, value)| value)
}

pub(super) fn attrs(tables: &[Json]) -> Json {
    let mut result = empty();
    for table in tables {
        if text(field(table, "kind")) != "infobox" {
            continue;
        }
        for (key, value) in entries(field(table, "fields")) {
            let lower = key.trim().to_lowercase();
            if ["date", "patch", "description", "captions", "sound effect"]
                .contains(&lower.as_str())
            {
                continue;
            }
            if result.get("raw").is_none() {
                put(&mut result, "raw", empty());
            }
            put(super::get_mut(&mut result, "raw"), key, value.clone());
            let source = text(value);
            let low = source.to_lowercase();
            let number = numeric(value).map_or(Json::Null, num);
            let destination = match lower.as_str() {
                "preferred target" | "favorite target" => "preferred_target",
                "unit type targeted" | "targets" | "healing targets" => "targets_text",
                "size" => "size",
                "special ability" => "special_ability",
                _ => "",
            };
            if !destination.is_empty() {
                put(&mut result, destination, value.clone());
                continue;
            }
            match lower.as_str() {
                "attack type" | "damage type" | "effect type" => {
                    put(&mut result, "attack_type", value.clone());
                    if let Some(value) = splash_radius(&low) {
                        put(&mut result, "splash_radius", num(value));
                    }
                    let hits = if low.contains("ground only") {
                        "ground"
                    } else if low.contains("air only") {
                        "air"
                    } else if low.contains("ground & air") || low.contains("ground and air") {
                        "both"
                    } else {
                        ""
                    };
                    if !hits.is_empty() {
                        put(&mut result, "hits", string(hits));
                    }
                }
                "range" => {
                    let values = numbers(source);
                    if values.len() >= 2 && source.contains('-') {
                        put(&mut result, "min_range", num(values[0]));
                        put(&mut result, "range", num(values[1]));
                    } else if let Some(value) = values.first() {
                        put(&mut result, "range", num(*value));
                    }
                }
                "movement speed" | "attack speed" | "heal speed" | "healing speed" => {
                    if !number.is_null() {
                        put(
                            &mut result,
                            if lower == "movement speed" {
                                "speed_display"
                            } else {
                                "attack_interval"
                            },
                            number,
                        );
                    }
                }
                _ => {
                    let destination = match lower.as_str() {
                        "housing space" => "housing",
                        "trigger radius" | "activation radius" => "trigger_radius",
                        "damage radius" | "radius" | "effect radius" | "spell radius" => "radius",
                        "death damage radius" => "death_radius",
                        "number of targets" => "targets",
                        "chain distance" => "chain_distance",
                        "chain damage decay" => "chain_decay",
                        "search radius" => "search_radius",
                        "spell duration" | "duration" | "lifetime" => "duration",
                        "hp decay per second" | "hitpoint decay per second" => "hp_decay",
                        _ => "",
                    };
                    if !destination.is_empty()
                        && (!(destination == "radius" || destination == "duration")
                            || result.get(destination).is_none())
                    {
                        put(&mut result, destination, number);
                    }
                }
            }
        }
    }
    result
}

pub(super) fn level_rows(tables: &[Json]) -> Json {
    let mut result = empty();
    for table in tables {
        if text(field(table, "kind")) != "stats"
            || text(field(table, "heading")) == "As Temporary Troop"
        {
            continue;
        }
        let columns = items(field(table, "columns"));
        let Some(first) = columns.first() else {
            continue;
        };
        let first = text(first).to_lowercase();
        if !["level", "charge", "charge level"].contains(&first.as_str()) {
            continue;
        }
        for row in items(field(table, "rows")) {
            let values = items(row);
            let Some(level) = values.first().and_then(numeric) else {
                continue;
            };
            let key = format!(
                "{}{}",
                if first.starts_with("charge") {
                    "charge:"
                } else {
                    ""
                },
                level as i64
            );
            if result.get(&key).is_none() {
                put(&mut result, &key, empty());
            }
            let entry = super::get_mut(&mut result, &key);
            for (column, value) in columns.iter().skip(1).zip(values.iter().skip(1)) {
                let column = text(column);
                if !column.is_empty() && entry.get(column).is_none() {
                    put(entry, column, value.clone());
                }
            }
        }
    }
    result
}

fn sentences(source: &str) -> Json {
    let mut result = Vec::new();
    let keywords = [
        "target", "splash", "chain", "radius", "range", "tiles", "second", "wall", "jump",
        "ignore", "immune", "stun", "freeze", "slow", "heal", "invisib", "retarget", "trigger",
        "death", "spawn", "summon", "aura", "push", "pierce", "priorit", "nearest", "closest",
        "percent", "%",
    ];
    for line in source.lines() {
        let lower = line.to_lowercase();
        if line.starts_with("## ") {
            if [
                "history",
                "gallery",
                "trivia",
                "skins",
                "audio",
                "video",
                "appearance",
            ]
            .iter()
            .any(|word| lower.contains(word))
            {
                break;
            }
            continue;
        }
        if line.chars().count() > 25
            && line.chars().count() < 700
            && keywords.iter().any(|word| lower.contains(word))
            && !result.contains(&string(line))
        {
            result.push(string(line));
        }
        if result.len() == 40 {
            break;
        }
    }
    arr(result)
}

fn add(
    records: &mut Json,
    wiki: &Path,
    name: &str,
    kind: &str,
    ck: &Json,
    title: &str,
) -> Result<(), String> {
    let (page, notes) = page(wiki, title)?;
    let tables = items(field(&page, "tables"));
    let mut attributes = attrs(tables);
    for (source, dest, scale) in [
        ("movement_speed", "speed", 0.01),
        ("attack_range", "range_ck", 0.01),
        ("attack_speed", "attack_interval_ck", 0.001),
        ("housing_space", "housing_ck", 1.0),
        ("width", "width", 1.0),
        ("hitbox_width", "hitbox", 1.0),
        ("trigger_radius", "trigger_ck", 0.01),
        ("damage_radius", "damage_radius_ck", 0.01),
    ] {
        if let Some(value) = numeric(field(ck, source)) {
            put(&mut attributes, dest, num(value * scale));
        }
    }
    for flag in [
        "is_flying",
        "is_air_targeting",
        "is_ground_targeting",
        "air_trigger",
        "ground_trigger",
    ] {
        if let Some(value) = ck.get(flag) {
            put(&mut attributes, flag, Json::Bool(truth(value)));
        }
    }
    let wiki_levels = level_rows(tables);
    let mut levels = Vec::new();
    let mut conflicts = Vec::new();
    let mut seen = Vec::new();
    let ck_levels = items(field(ck, "levels"));
    for level in ck_levels {
        let key = field(level, "level").i64().to_string();
        let mut row = obj([
            ("level", field(level, "level").clone()),
            (
                "required_townhall",
                field(level, "required_townhall").clone(),
            ),
        ]);
        for key in ["hitpoints", "dps", "damage", "duration", "radius"] {
            if !field(level, key).is_null() {
                put(&mut row, key, field(level, key).clone());
            }
        }
        let wiki = object(&wiki_levels, &key);
        if let (Some(wiki_hp), Some(hp)) = (
            numeric(field(wiki, "Hitpoints")),
            numeric(field(level, "hitpoints")),
        ) {
            if hp != 0.0 && (wiki_hp - hp).abs() > 0.5 {
                conflicts.push(string(format!(
                    "L{key} HP: game {} vs wiki {}",
                    hp,
                    clash_data::float::py_float_repr(wiki_hp)
                )));
            }
        }
        put(&mut row, "wiki", wiki.clone());
        levels.push(row);
        seen.push(key);
    }
    for (key, wiki) in entries(&wiki_levels) {
        if seen.contains(key) {
            continue;
        }
        let level = if key.starts_with("charge") {
            string(key)
        } else {
            num(key.parse::<f64>().unwrap())
        };
        levels.push(obj([
            ("level", level),
            ("wiki", wiki.clone()),
            ("wiki_only", Json::Bool(true)),
        ]));
    }
    if levels.is_empty() {
        let mut flat = empty();
        for table in tables {
            if text(field(table, "kind")) == "infobox" {
                merge(&mut flat, field(table, "fields"));
            }
        }
        if ["Hitpoints", "Damage per Second", "Damage per Attack"]
            .iter()
            .any(|key| flat.get(key).is_some())
        {
            levels.push(obj([
                ("level", num(1)),
                ("wiki", flat),
                ("wiki_only", Json::Bool(true)),
            ]));
        }
    }
    let mut max_level = empty();
    if !ck_levels.is_empty() {
        for th in 14..=18 {
            let maximum = ck_levels
                .iter()
                .filter(|row| {
                    numeric(field(row, "required_townhall")).unwrap_or(0.0) <= f64::from(th)
                })
                .filter_map(|row| numeric(field(row, "level")))
                .reduce(f64::max)
                .map_or(Json::Null, num);
            put(&mut max_level, &th.to_string(), maximum);
        }
    }
    put(
        records,
        name,
        obj([
            ("name", string(name)),
            ("kind", string(kind)),
            ("seasonal", Json::Bool(truth(field(ck, "is_seasonal")))),
            ("super", Json::Bool(truth(field(ck, "super_troop")))),
            (
                "source",
                obj([
                    ("clashking", Json::Bool(truth(ck))),
                    ("wiki", field(&page, "source").clone()),
                    ("wiki_rev", field(&page, "revid").clone()),
                ]),
            ),
            ("attrs", attributes),
            ("levels", arr(levels)),
            ("conflicts", arr(conflicts)),
            ("notes", sentences(&notes)),
            ("max_level", max_level),
        ]),
    );
    Ok(())
}

pub(super) fn build(raw: &Json, wiki: &Path) -> Result<Json, String> {
    // Freeze discovery membership as well as requiring every selected table/text.
    // Missing cached pages must never silently remove crafted defenses/equipment.
    for (_, name) in wiki_inputs() {
        if !wiki.join(name).is_file() {
            return Err(format!(
                "missing required wiki input {}",
                wiki.join(name).display()
            ));
        }
    }
    let mut records = empty();
    for (section, kind) in [
        ("troops", "troop"),
        ("spells", "spell"),
        ("heroes", "hero"),
        ("pets", "pet"),
        ("equipment", "equipment"),
        ("traps", "trap"),
        ("guardians", "guardian"),
        ("buildings", "building"),
    ] {
        for entry in items(field(raw, section)) {
            let village = entry.get("village").map(text).unwrap_or("home");
            if village != "home" || (section == "buildings" && entry.get("village").is_none()) {
                continue;
            }
            let kind = if kind == "troop" && text(field(entry, "production_building")) == "Workshop"
            {
                "siege"
            } else if kind == "troop" && truth(field(entry, "super_troop")) {
                "super_troop"
            } else {
                kind
            };
            let name = text(field(entry, "name"));
            add(&mut records, wiki, name, kind, entry, name)?;
        }
    }
    for (name, title) in SUMMONS {
        add(&mut records, wiki, name, "summon", &Json::Null, title)?;
    }
    for filename in wiki_inputs().filter_map(|(_, name)| name.strip_prefix("tables/")) {
        let page = read(&wiki.join("tables").join(filename))?;
        let title = text(field(&page, "title"));
        if records.get(title).is_some() || title.contains('/') {
            continue;
        }
        let metadata = read(&wiki.join("pages").join(filename))?;
        let categories = items(field(&metadata, "categories"));
        let has = |key: &str| categories.iter().any(|category| text(category) == key);
        let kind = if ["Crafted_Defenses", "Crafted_Defense", "Crafted_Buildings"]
            .iter()
            .any(|key| has(key))
            && has("Defenses")
        {
            "crafted_defense"
        } else if [
            "Hero_Equipment",
            "Epic_Hero_Equipment",
            "Common_Hero_Equipment",
        ]
        .iter()
        .any(|key| has(key))
        {
            "equipment"
        } else {
            continue;
        };
        add(&mut records, wiki, title, kind, &Json::Null, title)?;
    }
    Ok(records)
}

/// Exact pinned mirror membership and byte hashes; no mirrored text is embedded.
pub(super) fn wiki_inputs() -> impl Iterator<Item = (&'static str, &'static str)> {
    include_str!("wiki-inputs.sha256")
        .lines()
        .map(|line| line.split_once("  ").expect("wiki input manifest"))
}

/// Restore the documented historical registry repair (ENGINE_V2.md, Oct 18).
/// The mirror repeats L11; characters.csv carries the actual L12 beam stages.
/// This is source-derived correction data, never an inferred extra level.
pub(super) fn repair_inferno(registry: &mut Json, csv: &super::csv::Tables) -> Result<(), String> {
    let record = super::get_mut(registry, "Inferno Dragon");
    let Json::Arr(levels) = super::get_mut(record, "levels") else {
        return Err("Inferno Dragon levels missing".to_owned());
    };
    let entry = levels
        .iter_mut()
        .find(|entry| field(entry, "level") == &num(12))
        .ok_or("Inferno Dragon L12 missing")?;
    let first = csv.unit("Inferno Dragon", 1);
    let offset =
        numeric(field(first, "VisualLevel")).ok_or("Inferno Dragon VisualLevel missing")? as i64;
    let row = csv.unit("Inferno Dragon", 12 - offset + 1);
    if numeric(field(row, "VisualLevel")) != Some(12.0) {
        return Err("Inferno Dragon L12 CSV row missing".to_owned());
    }
    let wiki = super::get_mut(entry, "wiki");
    for (column, key) in [
        ("Damage per Second / Initial", "DPS"),
        ("Damage per Second / After 1.7s", "DPSLv2"),
        ("Damage per Second / After 3.2s", "DPSLv3"),
    ] {
        let value = numeric(field(row, key))
            .ok_or_else(|| format!("Inferno Dragon L12 {key} missing"))? as i64;
        let digits = value.to_string();
        let mut grouped = String::new();
        for (index, ch) in digits.chars().enumerate() {
            if index > 0 && (digits.len() - index).is_multiple_of(3) {
                grouped.push(',');
            }
            grouped.push(ch);
        }
        put(wiki, column, string(grouped));
    }
    Ok(())
}
