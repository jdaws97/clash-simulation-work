//! Shared frozen snapshot/history readers and UTC boundaries.
use crate::json::{self, Json};
use crate::wire::*;
use std::path::Path;

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
            .map_or("data/source/reference-bases/your-base.json", |entry| {
                text(
                    entry,
                    "layout",
                    "data/source/reference-bases/your-base.json",
                )
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
    let own = read(&crate::private::account(root))?;
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
