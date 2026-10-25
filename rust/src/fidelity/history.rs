//! Frozen defensive snapshots take precedence over legacy inclusive-day hints.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use baselab_engine::json::{self, Json};

use super::decode::{identity, Decoder};
use super::io::*;

/// UTC microseconds, supporting API/ISO dates and explicit numeric offsets.
pub fn timestamp(source: &str) -> Result<i64, String> {
    fn integer(source: &str) -> Result<i64, String> {
        source.parse().map_err(|_| "invalid_timestamp".to_owned())
    }
    let (date, clock) = source.split_once('T').unwrap_or((source, "00:00:00Z"));
    let digits: String = date.chars().filter(char::is_ascii_digit).collect();
    if digits.len() != 8 {
        return Err("invalid_timestamp".to_owned());
    }
    let year = integer(&digits[..4])?;
    let month = integer(&digits[4..6])?;
    let day = integer(&digits[6..])?;
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let lengths = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if !(1..=12).contains(&month) || day < 1 || day > lengths[(month - 1) as usize] {
        return Err("invalid_timestamp".to_owned());
    }
    let adjusted = year - i64::from(month <= 2);
    let era = adjusted.div_euclid(400);
    let yoe = adjusted - era * 400;
    let shifted = month + if month > 2 { -3 } else { 9 };
    let doy = (153 * shifted + 2) / 5 + day - 1;
    let days = era * 146097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719468;
    let zone_index = clock
        .char_indices()
        .find(|(_, ch)| *ch == '+' || *ch == '-')
        .map(|(index, _)| index);
    let mut offset = 0;
    let clock = if let Some(index) = zone_index {
        let zone = &clock[index + 1..];
        let zone = zone.replace(':', "");
        if zone.len() != 4 {
            return Err("invalid_timestamp".to_owned());
        }
        let hours = integer(&zone[..2])?;
        let minutes = integer(&zone[2..])?;
        if hours > 23 || minutes > 59 {
            return Err("invalid_timestamp".to_owned());
        }
        offset = (hours * 60 + minutes)
            * 60
            * if clock.as_bytes()[index] == b'+' {
                1
            } else {
                -1
            };
        &clock[..index]
    } else {
        clock.trim_end_matches('Z')
    };
    let (clock, fraction) = clock.split_once('.').unwrap_or((clock, ""));
    let clock = clock.replace(':', "");
    if clock.len() != 6 || fraction.len() > 6 || !fraction.bytes().all(|byte| byte.is_ascii_digit())
    {
        return Err("invalid_timestamp".to_owned());
    }
    let hour = integer(&clock[..2])?;
    let minute = integer(&clock[2..4])?;
    let second = integer(&clock[4..])?;
    if hour > 23 || minute > 59 || second > 59 {
        return Err("invalid_timestamp".to_owned());
    }
    let micros = if fraction.is_empty() {
        0
    } else {
        integer(fraction)? * 10_i64.pow((6 - fraction.len()) as u32)
    };
    Ok(((days * 24 + hour) * 3600 + minute * 60 + second - offset) * 1_000_000 + micros)
}

pub fn setup(
    root: &Path,
    history: &Json,
    when: &str,
    base: Option<&str>,
    historical_only: bool,
) -> Result<(Json, String, String), String> {
    let time = timestamp(when)?;
    let mut matches = Vec::new();
    if base.is_none() {
        for entry in list(history, "snapshots") {
            let start = timestamp(text(entry, "from", ""))?;
            let end = match entry.get("to") {
                Some(Json::Str(value)) => timestamp(value)?,
                _ => i64::MAX,
            };
            if start <= time && time < end {
                matches.push(entry);
            }
        }
    }
    if matches.len() > 1 {
        return Err("overlapping_snapshots".to_owned());
    }
    if let Some(entry) = matches.first() {
        let path = text(entry, "layout", "");
        let raw = std::fs::read_to_string(resolve(root, path))
            .map_err(|error| format!("missing_layout_file: {error}"))?;
        if sha256(canonical(&raw)?.as_bytes()) != text(entry, "sha256", "") {
            return Err("snapshot_hash_mismatch".to_owned());
        }
        return Ok((
            json::parse(&raw).map_err(|error| error.to_string())?,
            path.to_owned(),
            "frozen_snapshot".to_owned(),
        ));
    }
    // Compare UTC day boundaries rather than the timestamp's local date.
    let day = time.div_euclid(86_400_000_000) * 86_400_000_000;
    let periods: Vec<_> = list(history, "periods")
        .iter()
        .filter_map(|entry| {
            let start = timestamp(text(entry, "from", "")).ok()?;
            let end = match entry.get("to") {
                Some(Json::Str(value)) => timestamp(value).ok()?,
                _ => i64::MAX,
            };
            (start <= day && day <= end).then_some(entry)
        })
        .collect();
    if historical_only && (periods.len() != 1 || text(periods[0], "layout", "").is_empty()) {
        return Err("missing_or_ambiguous_history".to_owned());
    }
    let path = base.unwrap_or_else(|| {
        periods
            .first()
            .map_or("data/reference-bases/your-base.json", |entry| {
                text(entry, "layout", "data/reference-bases/your-base.json")
            })
    });
    let mut layout = read(&resolve(root, path))?;
    if historical_only {
        if ["levels", "hero_levels"]
            .iter()
            .any(|key| !matches!(layout.get(key), Some(Json::Obj(entries)) if !entries.is_empty()))
            || number(&layout, "wall_level", 0.0) <= 0.0
        {
            return Err("missing_historical_levels".to_owned());
        }
        return Ok((
            layout,
            path.to_owned(),
            "legacy_historical_levels".to_owned(),
        ));
    }
    let own = read(&root.join("data/your-levels.json"))?;
    for key in [
        "levels",
        "hero_levels",
        "wall_level",
        "wall_levels",
        "cc_troops",
        "heroes",
    ] {
        if let Some(value) = own.get(key) {
            put(&mut layout, key, value.clone());
        }
    }
    if let Some(Json::Obj(traps)) = own.get("trap_levels") {
        let mut levels = layout
            .get("levels")
            .cloned()
            .unwrap_or_else(|| obj([] as [(&str, Json); 0]));
        for (key, value) in traps {
            put(&mut levels, &format!("trap:{key}"), value.clone());
        }
        put(&mut layout, "levels", levels);
    }
    Ok((
        layout,
        path.to_owned(),
        "current_levels_fallback_unverified".to_owned(),
    ))
}

pub fn battles(path: &Path) -> Result<Vec<Json>, String> {
    let raw =
        std::fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    if let Ok(value) = json::parse(&raw) {
        return match value {
            Json::Arr(values) => Ok(values),
            Json::Obj(_) if value.get("items").is_some() => Ok(list(&value, "items").to_vec()),
            Json::Obj(_) => Ok(vec![value]),
            _ => Err("battle log must be an object, array or JSONL".to_owned()),
        };
    }
    raw.lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| json::parse(line).map_err(|error| error.to_string()))
        .collect()
}

#[derive(Clone)]
pub struct Observation {
    pub id: String,
    pub build: Json,
    pub family: String,
    pub th: i64,
    pub layout: Json,
    pub layout_path: String,
    pub layout_hash: String,
    pub setup_source: String,
    pub modifier: Option<String>,
    pub stars: i64,
    pub pct: f64,
    pub time: f64,
}

pub fn observations(
    root: &Path,
    log: &Path,
    history_path: &Path,
    historical: bool,
    base: Option<&str>,
) -> Result<(Vec<Observation>, BTreeMap<String, usize>), String> {
    let decoder = Decoder::load(root)?;
    let history = read(history_path)?;
    let mut rows = Vec::new();
    let mut skipped = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for battle in battles(log)? {
        if text(&battle, "battleType", "") != "ranked"
            || battle.get("attack") != Some(&Json::Bool(false))
        {
            continue;
        }
        let parsed = (|| {
            let th = number(&battle, "opponentTownHallLevel", 0.0);
            let stars = number(&battle, "stars", -1.0);
            let pct = number(&battle, "destructionPercentage", -1.0);
            if !(1.0..=18.0).contains(&th)
                || th.fract() != 0.0
                || !(0.0..=3.0).contains(&stars)
                || stars.fract() != 0.0
                || !(0.0..=100.0).contains(&pct)
                || (stars == 3.0) != (pct == 100.0)
            {
                return Err("invalid_outcome_or_timestamp".to_owned());
            }
            let when = text(&battle, "battleTimestamp", "");
            timestamp(when)?;
            let id = identity(&battle)?;
            if !seen.insert(id.clone()) {
                return Err("duplicate".to_owned());
            }
            let build = decoder.build(text(&battle, "armyShareCode", ""), th as i64, rows.len())?;
            let (layout, path, source) = setup(root, &history, when, base, historical)?;
            let league = text(&battle, "player_league", "").to_lowercase();
            let modifier = if let Some((_, suffix)) = league.split_once("legend") {
                Some(
                    match suffix.trim() {
                        "i" => "legend1",
                        "ii" => "legend2",
                        "iii" => "legend3",
                        _ => return Err("unknown_league_modifier".to_owned()),
                    }
                    .to_owned(),
                )
            } else {
                None
            };
            let family = baselab_engine::armies::family_of(&build)
                .unwrap_or("unclassified")
                .to_owned();
            Ok(Observation {
                id,
                build,
                family,
                th: th as i64,
                layout,
                layout_hash: file_hash(&resolve(root, &path))?,
                layout_path: path,
                setup_source: source,
                modifier,
                stars: stars as i64,
                pct,
                time: number(&battle, "battleTime", 0.0),
            })
        })();
        match parsed {
            Ok(row) => rows.push(row),
            Err(reason) => *skipped.entry(reason).or_default() += 1,
        }
    }
    Ok((rows, skipped))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utc_boundaries_and_invalid_dates() {
        assert_eq!(
            timestamp("20261021T183738.123Z"),
            timestamp("2026-10-21T14:37:38.123-04:00")
        );
        assert_eq!(timestamp("1970-01-01").unwrap(), 0);
        assert!(timestamp("2026-02-29").is_err());
        assert!(timestamp("20261021T250000Z").is_err());
    }

    #[test]
    fn synthetic_snapshots_are_half_open_hash_checked_and_unambiguous() {
        let directory =
            std::env::temp_dir().join(format!("rf1-snapshot-test-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let raw = "{\"name\":\"declared synthetic fixture\",\"levels\":{\"cannon\":1}}";
        std::fs::write(directory.join("frozen.json"), raw).unwrap();
        let entry = obj([
            ("from", string("2026-10-21T00:00:00Z")),
            ("to", string("2026-10-22T00:00:00Z")),
            ("layout", string("frozen.json")),
            ("sha256", string(sha256(canonical(raw).unwrap().as_bytes()))),
        ]);
        let history = obj([("snapshots", arr([entry.clone()]))]);
        assert_eq!(
            setup(&directory, &history, "20261021T000000Z", None, true)
                .unwrap()
                .2,
            "frozen_snapshot"
        );
        assert!(setup(&directory, &history, "20261022T000000Z", None, true).is_err());
        let overlap = obj([("snapshots", arr([entry.clone(), entry]))]);
        assert_eq!(
            setup(&directory, &overlap, "20261021T000000Z", None, true).unwrap_err(),
            "overlapping_snapshots"
        );
        std::fs::write(directory.join("frozen.json"), "{}").unwrap();
        assert_eq!(
            setup(&directory, &history, "20261021T000000Z", None, true).unwrap_err(),
            "snapshot_hash_mismatch"
        );
        std::fs::remove_dir_all(directory).unwrap();
    }
}
