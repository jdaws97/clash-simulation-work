//! Frozen historical setups. Bounds are UTC and half open; hashes retain numeric tokens.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use clash_data::json::{self, Json};
use clash_data::wire::*;

use super::archive::{atomic_write, WriteLock};
use super::{object, required_text, timestamp};

const FIELDS: &[&str] = &[
    "layout",
    "levels",
    "wall_level",
    "wall_levels",
    "trap_levels",
    "defense_modes",
    "trap_modes",
    "cc_troops",
    "hero_levels",
    "hero_banners",
    "town_hall",
    "guardian",
];
const SOURCES: &[&str] = &["user-entered", "API", "screenshot"];
const CONFIDENCES: &[&str] = &["unknown", "low", "medium", "high"];

/// ISO UTC formatting without a time crate; inverse of the shared civil-date reader.
pub fn utc(micros: i64) -> Result<String, String> {
    let seconds = micros.div_euclid(1_000_000);
    let days = seconds.div_euclid(86400);
    let shifted = days + 719468;
    let era = shifted.div_euclid(146097);
    let day_of_era = shifted - era * 146097;
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36524 - day_of_era / 146096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month = month_index + if month_index < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    if !(1..=9999).contains(&year) {
        return Err("timestamp year outside 1..9999".to_owned());
    }
    let clock = seconds.rem_euclid(86400);
    let fraction = micros.rem_euclid(1_000_000);
    let fraction = if fraction == 0 {
        String::new()
    } else {
        format!(".{fraction:06}")
    };
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}{fraction}Z",
        clock / 3600,
        clock / 60 % 60,
        clock % 60
    ))
}

fn parse(raw: &str) -> Result<Json, String> {
    json::parse(raw).map_err(|error| error.to_string())
}

fn array<'a>(value: &'a Json, key: &str) -> Result<&'a [Json], String> {
    match value.get(key) {
        Some(Json::Arr(values)) => Ok(values),
        _ => Err(format!("{key} must be an array")),
    }
}

/// Extract already-validated JSON tokens without changing 1 into 1.0. The runtime
/// Json type stores f64 only, so reserializing it would change historical hashes.
fn raw_fields(raw: &str) -> Result<BTreeMap<String, String>, String> {
    object(&parse(raw)?)?;
    let mut fields = BTreeMap::new();
    for field in raw_members(raw)? {
        let parsed = parse(&format!("{{{field}}}"))?;
        let name = &object(&parsed)?[0].0;
        let key_length = ascii_string(name).len();
        if fields
            .insert(name.clone(), field[key_length + 1..].to_owned())
            .is_some()
        {
            return Err(format!("duplicate JSON field {name}"));
        }
    }
    Ok(fields)
}

/// Split immediate members of a validated object or array, without parsing tokens again.
fn raw_members(raw: &str) -> Result<Vec<String>, String> {
    let parsed = parse(raw)?;
    if !matches!(parsed, Json::Obj(_) | Json::Arr(_)) {
        return Err("expected object or array".to_owned());
    }
    let raw = canonical(raw)?;
    let bytes = raw.as_bytes();
    let mut members = Vec::new();
    let mut start = 1;
    let mut index = 1;
    let mut depth = 0;
    let mut quoted = false;
    while index < bytes.len() {
        let byte = bytes[index];
        if quoted {
            if byte == b'\\' {
                index += 1;
            } else if byte == b'"' {
                quoted = false;
            }
        } else {
            match byte {
                b'"' => quoted = true,
                b'{' | b'[' => depth += 1,
                b'}' | b']' if depth > 0 => depth -= 1,
                b',' | b'}' | b']' if depth == 0 => {
                    if index > start {
                        members.push(raw[start..index].to_owned());
                    }
                    start = index + 1;
                }
                _ => {}
            }
        }
        index += 1;
    }
    Ok(members)
}

fn encode_fields(fields: &BTreeMap<String, String>) -> String {
    format!(
        "{{{}}}",
        fields
            .iter()
            .map(|(key, value)| format!("{}:{value}", ascii_string(key)))
            .collect::<Vec<_>>()
            .join(",")
    )
}

fn positive_integer(raw: &str) -> bool {
    !raw.contains(['.', 'e', 'E']) && raw.parse::<u64>().is_ok_and(|value| value > 0)
}

pub fn freeze_layout(layout: &str, levels: &str) -> Result<String, String> {
    let mut frozen = raw_fields(layout)?;
    let levels = raw_fields(levels)?;
    for key in ["name", "buildings", "heroes", "cc_troops"] {
        if !frozen.contains_key(key) {
            return Err(format!("layout must explicitly supply {key}"));
        }
    }
    for key in ["levels", "hero_levels", "wall_level", "wall_levels"] {
        if let Some(value) = levels.get(key) {
            frozen.insert(key.to_owned(), value.clone());
        }
    }
    for key in ["levels", "hero_levels", "wall_level"] {
        if !frozen.contains_key(key) {
            return Err(format!("levels file or layout must supply {key}"));
        }
    }
    for (key, value) in [
        ("wall_levels", "[]"),
        ("walls", "[]"),
        ("traps", "[]"),
        ("town_hall", "16"),
        ("guardian", "\"Longshot\""),
    ] {
        frozen
            .entry(key.to_owned())
            .or_insert_with(|| value.to_owned());
    }
    let mut defense_levels = raw_fields(&frozen["levels"])?;
    let mut trap_levels = raw_fields(frozen.get("trap_levels").map_or("{}", String::as_str))?;
    for (key, value) in &defense_levels {
        if let Some(key) = key.strip_prefix("trap:") {
            trap_levels.insert(key.to_owned(), value.clone());
        }
    }
    if let Some(raw) = levels.get("trap_levels") {
        trap_levels.extend(raw_fields(raw)?);
    }
    for (key, value) in &trap_levels {
        defense_levels.insert(format!("trap:{key}"), value.clone());
    }
    frozen.insert("levels".to_owned(), encode_fields(&defense_levels));
    frozen.insert("trap_levels".to_owned(), encode_fields(&trap_levels));
    for key in ["levels", "hero_levels", "trap_levels"] {
        if raw_fields(&frozen[key])?
            .values()
            .any(|value| !positive_integer(value))
        {
            return Err(format!("{key} must map names to positive integer levels"));
        }
    }
    if frozen["wall_level"] != "null" && !positive_integer(&frozen["wall_level"]) {
        return Err("wall_level must be a positive integer or null".to_owned());
    }
    let value = parse(&encode_fields(&frozen))?;
    let wall_positions: BTreeSet<_> = array(&value, "walls")?
        .iter()
        .map(|wall| match wall {
            Json::Arr(position) if position.len() == 2 => Ok(encode(wall)),
            _ => Err("walls must contain coordinate pairs".to_owned()),
        })
        .collect::<Result<_, _>>()?;
    let mut seen = BTreeSet::new();
    for (wall, raw) in array(&value, "wall_levels")?
        .iter()
        .zip(raw_members(&frozen["wall_levels"])?)
    {
        let x = wall.get("x").ok_or("wall level missing x")?;
        let y = wall.get("y").ok_or("wall level missing y")?;
        let position = encode(&arr([x.clone(), y.clone()]));
        let level = raw_fields(&raw)?;
        if !wall_positions.contains(&position)
            || !seen.insert(position)
            || !positive_integer(level.get("level").map_or("", String::as_str))
        {
            return Err("invalid or repeated wall level position or level".to_owned());
        }
    }
    let heroes = array(&value, "heroes")?;
    let mut hero_names = BTreeSet::new();
    for hero in heroes {
        let Json::Str(hero) = hero else {
            return Err("heroes must contain names".to_owned());
        };
        if !hero_names.insert(hero) {
            return Err("defending heroes must be unique".to_owned());
        }
    }
    let buildings = array(&value, "buildings")?;
    let banners: Vec<_> = buildings
        .iter()
        .zip(raw_members(&frozen["buildings"])?)
        .filter(|(building, _)| text(building, "key", "") == "banner")
        .collect();
    if heroes.len() > banners.len() {
        return Err("more defending heroes than banners".to_owned());
    }
    let mut hero_banners = Vec::new();
    for (index, (_, raw)) in banners.into_iter().enumerate() {
        let fields = raw_fields(&raw)?;
        hero_banners.push(format!(
            "{{\"x\":{},\"y\":{},\"hero\":{}}}",
            fields.get("x").ok_or("banner missing x")?,
            fields.get("y").ok_or("banner missing y")?,
            encode(heroes.get(index).unwrap_or(&Json::Null))
        ));
    }
    frozen.insert(
        "hero_banners".to_owned(),
        format!("[{}]", hero_banners.join(",")),
    );
    canonical(&encode_fields(&frozen))
}

fn provenance(
    frozen: &Json,
    source: &str,
    confidence: &str,
    overrides: Option<&Json>,
) -> Result<Json, String> {
    if !SOURCES.contains(&source) || !CONFIDENCES.contains(&confidence) {
        return Err("invalid snapshot source or confidence".to_owned());
    }
    let mut missing = BTreeMap::<&str, BTreeSet<String>>::new();
    for (field, rows, name) in [
        ("trap_levels", array(frozen, "traps")?, "key"),
        ("levels", array(frozen, "buildings")?, "key"),
    ] {
        for row in rows {
            let key = required_text(row, name)?;
            if field == "levels" && ["th", "banner"].contains(&key) {
                continue;
            }
            if frozen
                .get(field)
                .and_then(|levels| levels.get(key))
                .is_none()
            {
                missing.entry(field).or_default().insert(key.to_owned());
            }
        }
    }
    for hero in array(frozen, "heroes")? {
        let Json::Str(hero) = hero else {
            return Err("invalid defending hero".to_owned());
        };
        if frozen.at("hero_levels").get(hero).is_none() {
            missing
                .entry("hero_levels")
                .or_default()
                .insert(hero.clone());
        }
    }
    if frozen.get("wall_level") == Some(&Json::Null) {
        let covered: BTreeSet<_> = array(frozen, "wall_levels")?
            .iter()
            .map(|wall| encode(&arr([wall.at("x").clone(), wall.at("y").clone()])))
            .collect();
        for wall in array(frozen, "walls")? {
            if !covered.contains(&encode(wall)) {
                missing
                    .entry("wall_level")
                    .or_default()
                    .insert(encode(wall));
            }
        }
    }
    let mut fields = obj(FIELDS.iter().map(|key| {
        (
            *key,
            obj([
                ("source", string(source)),
                ("confidence", string(confidence)),
            ]),
        )
    }));
    for (key, absent) in &missing {
        put(
            &mut fields,
            key,
            obj([
                ("source", string(source)),
                ("confidence", string("unknown")),
                (
                    "notes",
                    string(format!(
                        "Missing levels; engine uses Town Hall maxima: {}",
                        absent.iter().cloned().collect::<Vec<_>>().join(", ")
                    )),
                ),
            ]),
        );
    }
    if let Some(overrides) = overrides {
        for (key, value) in object(overrides)? {
            if !FIELDS.contains(&key.as_str())
                || !SOURCES.contains(&required_text(value, "source")?)
                || !CONFIDENCES.contains(&required_text(value, "confidence")?)
                || missing.contains_key(key.as_str()) && text(value, "confidence", "") != "unknown"
            {
                return Err(format!("invalid provenance override for {key}"));
            }
            let mut field = fields.at(key).clone();
            for (name, value) in object(value)? {
                put(&mut field, name, value.clone());
            }
            put(&mut fields, key, field);
        }
    }
    Ok(fields)
}

pub struct SnapshotOptions<'a> {
    pub from: &'a str,
    pub to: Option<&'a str>,
    pub period: &'a str,
    pub source: &'a str,
    pub confidence: &'a str,
    pub notes: &'a str,
    pub provenance: Option<&'a Json>,
}

pub fn read_history(path: &Path) -> Result<Json, String> {
    match std::fs::read_to_string(path) {
        Ok(raw) => {
            let mut history = parse(&raw)?;
            object(&history)?;
            if history.get("snapshots").is_none() {
                put(&mut history, "snapshots", arr([]));
            }
            array(&history, "snapshots")?;
            Ok(history)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(obj([
            ("schema_version", num(2.0)),
            ("periods", arr([])),
            ("snapshots", arr([])),
        ])),
        Err(error) => Err(error.to_string()),
    }
}

pub fn snapshot_for_battle<'a>(history: &'a Json, when: &str) -> Result<Option<&'a Json>, String> {
    let when = timestamp(when)?;
    let mut found = None;
    for entry in array(history, "snapshots")? {
        let start = timestamp(required_text(entry, "from")?)?;
        let end = match entry.get("to") {
            Some(Json::Str(end)) => timestamp(end)?,
            Some(Json::Null) | None => i64::MAX,
            _ => return Err("invalid snapshot end".to_owned()),
        };
        if start <= when && when < end {
            if found.is_some() {
                return Err("overlapping_snapshots".to_owned());
            }
            found = Some(entry);
        }
    }
    Ok(found)
}

pub fn add_snapshot(
    root: &Path,
    history_path: &Path,
    layout: &str,
    levels: &str,
    options: &SnapshotOptions<'_>,
) -> Result<Json, String> {
    let start = timestamp(options.from)?;
    let end = options.to.map(timestamp).transpose()?;
    if end.is_some_and(|end| end <= start) {
        return Err("--to must be after --from (end is exclusive)".to_owned());
    }
    if !["tournament", "league-day"].contains(&options.period) {
        return Err("period must be tournament or league-day".to_owned());
    }
    let frozen = freeze_layout(layout, levels)?;
    let fields = provenance(
        &parse(&frozen)?,
        options.source,
        options.confidence,
        options.provenance,
    )?;
    let from = utc(start)?;
    let to = end.map(utc).transpose()?.map_or(Json::Null, string);
    let _lock = WriteLock::acquire(history_path)?;
    let mut history = read_history(history_path)?;
    let mut snapshots = array(&history, "snapshots")?.to_vec();
    for previous in &mut snapshots {
        let old_start = timestamp(required_text(previous, "from")?)?;
        let mut old_end = match previous.get("to") {
            Some(Json::Str(value)) => Some(timestamp(value)?),
            Some(Json::Null) | None => None,
            _ => return Err("invalid snapshot end".to_owned()),
        };
        if old_end.is_none() && old_start < start {
            put(previous, "to", string(&from));
            old_end = Some(start);
        }
        if end.is_none_or(|end| old_start < end) && old_end.is_none_or(|end| start < end) {
            return Err(format!(
                "period overlaps snapshot {}",
                text(previous, "id", "")
            ));
        }
    }
    let digest = sha256(frozen.as_bytes());
    let parent = history_path.parent().unwrap_or(Path::new("."));
    let archive = parent
        .join("snapshots")
        .join(format!("{}-{}.json", &from[..10], &digest[..12]));
    let absolute = if archive.is_absolute() {
        archive.clone()
    } else {
        std::env::current_dir()
            .map_err(|error| error.to_string())?
            .join(&archive)
    };
    let layout_path = absolute
        .strip_prefix(root)
        .unwrap_or(&absolute)
        .to_string_lossy()
        .replace('\\', "/");
    let entry = obj([
        ("id", string(format!("{from}-{}", &digest[..12]))),
        ("from", string(from)),
        ("to", to),
        ("period", string(options.period)),
        ("layout", string(layout_path)),
        ("sha256", string(&digest)),
        ("fields", fields),
        ("notes", string(options.notes)),
    ]);
    match std::fs::read_to_string(&archive) {
        Ok(raw) if sha256(canonical(&raw)?.as_bytes()) == digest => {}
        Ok(_) => return Err("refusing to overwrite changed snapshot".to_owned()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            atomic_write(&archive, format!("{frozen}\n").as_bytes())?
        }
        Err(error) => return Err(error.to_string()),
    }
    snapshots.push(entry.clone());
    snapshots
        .sort_by_key(|entry| timestamp(text(entry, "from", "")).expect("validated snapshot start"));
    put(&mut history, "snapshots", arr(snapshots));
    put(&mut history, "schema_version", num(2.0));
    atomic_write(history_path, format!("{}\n", encode(&history)).as_bytes())?;
    Ok(entry)
}

fn defender_trophies(stars: f64, pct: f64) -> f64 {
    if stars == 0.0 {
        40.0
    } else if stars >= 3.0 {
        0.0
    } else if stars == 2.0 {
        40.0 - (16.0 + ((pct - 50.0) / 3.0).floor().max(0.0))
    } else {
        40.0 - (5.0 + ((pct - 1.0).max(0.0) / 9.0).floor()).min(15.0)
    }
}

pub fn report(history: &Json, battles: &[Json]) -> Result<Json, String> {
    let entries = array(history, "snapshots")?;
    let mut grouped = BTreeMap::<String, Vec<f64>>::new();
    let mut seen = BTreeSet::new();
    let mut uncovered = 0;
    for battle in battles {
        if text(battle, "battleType", "") != "ranked"
            || battle.get("attack") != Some(&Json::Bool(false))
        {
            continue;
        }
        let when = required_text(battle, "battleTimestamp")?;
        let opponent = required_text(battle, "opponentPlayerTag")?;
        if !seen.insert((timestamp(when)?, opponent)) {
            continue;
        }
        let stars = number(battle, "stars", -1.0);
        let pct = number(battle, "destructionPercentage", -1.0);
        if !(0.0..=3.0).contains(&stars) || stars.fract() != 0.0 || !(0.0..=100.0).contains(&pct) {
            return Err("invalid ranked defense outcome".to_owned());
        }
        if let Some(entry) = snapshot_for_battle(history, when)? {
            grouped
                .entry(required_text(entry, "id")?.to_owned())
                .or_default()
                .push(defender_trophies(stars, pct));
        } else {
            uncovered += 1;
        }
    }
    let mut entries: Vec<_> = entries.iter().collect();
    for entry in &entries {
        timestamp(required_text(entry, "from")?)?;
    }
    entries.sort_by_key(|entry| timestamp(text(entry, "from", "")).expect("validated start"));
    let mut rows = Vec::new();
    for entry in entries {
        let values = grouped
            .get(required_text(entry, "id")?)
            .map_or(&[][..], Vec::as_slice);
        let mean = if values.is_empty() {
            None
        } else {
            Some(values.iter().sum::<f64>() / values.len() as f64)
        };
        let interval = if values.len() >= 2 {
            let mean = mean.expect("nonempty values");
            let variance = values
                .iter()
                .map(|value| (value - mean).powi(2))
                .sum::<f64>()
                / (values.len() - 1) as f64;
            let margin = 1.96 * (variance / values.len() as f64).sqrt();
            arr([
                num((mean - margin).max(0.0)),
                num((mean + margin).min(40.0)),
            ])
        } else {
            Json::Null
        };
        rows.push(obj([
            ("id", entry.at("id").clone()),
            ("from", entry.at("from").clone()),
            ("to", entry.get("to").cloned().unwrap_or(Json::Null)),
            ("layout", entry.get("layout").cloned().unwrap_or(Json::Null)),
            ("ranked_defenses", num(values.len() as f64)),
            ("mean_defender_trophies", mean.map_or(Json::Null, num)),
            ("interval_95", interval),
        ]));
    }
    Ok(obj([
        ("snapshots", arr(rows)),
        ("uncovered_defenses", num(uncovered as f64)),
    ]))
}
