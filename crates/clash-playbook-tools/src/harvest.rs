use crate::{io, transcripts};
use clash_data::json::Json;
use clash_data::wire::{self, list, obj, put, string, text};
use std::fs;
use std::path::Path;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

pub fn age_days(value: &str) -> Option<f64> {
    let bytes = value.as_bytes();
    for start in 0..bytes.len() {
        if !bytes[start].is_ascii_digit() {
            continue;
        }
        let digits = bytes[start..]
            .iter()
            .take_while(|c| c.is_ascii_digit())
            .count();
        let end = start + digits;
        let after = &value[end..];
        let unit = after.trim_start();
        if after.len() == unit.len() {
            continue;
        }
        for (name, factor) in [
            ("second", 1.0 / 86400.0),
            ("minute", 1.0 / 1440.0),
            ("hour", 1.0 / 24.0),
            ("day", 1.0),
            ("week", 7.0),
            ("month", 30.4),
            ("year", 365.0),
        ] {
            if unit.starts_with(name) {
                return value[start..end].parse::<f64>().ok().map(|n| n * factor);
            }
        }
    }
    None
}

pub fn queries(family: &str) -> Result<&'static [&'static str], String> {
    match family {
        "root-rider" => Ok(&[
            "th16 root rider attack strategy",
            "th17 root rider attack strategy",
            "root rider valkyrie attack guide",
            "rc charge root rider attack",
            "th18 root rider attack strategy",
        ]),
        "thrower" => Ok(&[
            "th16 thrower attack strategy",
            "th17 thrower attack strategy",
            "thrower healer attack guide",
            "th18 thrower attack",
        ]),
        "dragon" => Ok(&[
            "th16 dragon attack strategy",
            "th17 hydra attack strategy",
            "dragon rider dragon attack guide",
            "rc walk dragons",
        ]),
        "electro-dragon" => Ok(&[
            "electro dragon attack th17",
            "edrag spam attack th16",
            "electro dragon th18 attack strategy",
        ]),
        "super-bowler" => Ok(&[
            "super bowler smash attack th17",
            "super bowler attack strategy th16",
        ]),
        "yeti" => Ok(&["super yeti attack th17", "yeti smash attack strategy th16"]),
        "lavaloon" => Ok(&["lavaloon attack th16", "lalo attack strategy th17"]),
        "meteor-golem" => Ok(&[
            "meteor golem attack strategy",
            "th16 meteor golem attack",
            "meteor golem warden walk",
            "th16 warden walk attack",
            "meteor golem eternal tome warden attack th16",
        ]),
        "warden-walk" => Ok(&[
            "th16 fireball warden walk",
            "fireball warden walk attack",
            "grand warden fireball attack th16",
            "warden walk fireball rage gem",
            "th16 warden walk attack strategy",
            "fireball walk clash of clans",
        ]),
        "th16-new" => Ok(&[
            "th16 best attack strategy",
            "th16 legend league attack",
            "th16 ranked attack strategy",
            "best th16 army after update",
            "th16 attack strategy 2026",
        ]),
        "druid-ruin-witch" => Ok(&["ruin witch attack strategy", "druid attack strategy th16"]),
        "super-minion-air" => Ok(&[
            "super minion rocket balloon attack",
            "rocket balloon attack strategy th16",
        ]),
        _ => Err(format!(
            "no default queries for family {family}; supply --query"
        )),
    }
}

pub fn read_rows(path: &Path) -> Result<Vec<Json>, String> {
    let source = fs::read_to_string(path).map_err(|e| e.to_string())?;
    if let Ok(value) = io::parse(&source) {
        return Ok(discover(&value));
    }
    source
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| io::parse(line).map(|v| discover(&v)))
        .collect::<Result<Vec<_>, _>>()
        .map(|rows| rows.into_iter().flatten().collect())
}

pub fn discover(value: &Json) -> Vec<Json> {
    let mut rows = Vec::new();
    match value {
        Json::Obj(fields) => {
            if let Some(video) = value.get("videoRenderer") {
                let title = list(video.get("title").unwrap_or(&Json::Null), "runs")
                    .iter()
                    .map(|run| text(run, "text", ""))
                    .collect::<String>();
                let channel = list(video.get("ownerText").unwrap_or(&Json::Null), "runs")
                    .first()
                    .map(|run| string(text(run, "text", "")))
                    .unwrap_or(Json::Null);
                rows.push(obj([
                    ("id", string(text(video, "videoId", ""))),
                    ("title", string(title)),
                    ("channel", channel),
                    (
                        "age",
                        video
                            .get("publishedTimeText")
                            .and_then(|v| v.get("simpleText"))
                            .cloned()
                            .unwrap_or(Json::Null),
                    ),
                    (
                        "length",
                        video
                            .get("lengthText")
                            .and_then(|v| v.get("simpleText"))
                            .cloned()
                            .unwrap_or(Json::Null),
                    ),
                ]));
            } else if value.get("id").is_some() && value.get("entries").is_none() {
                rows.push(value.clone());
                return rows;
            }
            for (_, child) in fields {
                rows.extend(discover(child));
            }
        }
        Json::Arr(values) => {
            for child in values {
                rows.extend(discover(child));
            }
        }
        _ => {}
    }
    rows
}

pub fn read_index(path: &Path) -> Result<Vec<Json>, String> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let source = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut rows = Vec::new();
    for line in source.lines().filter(|line| !line.trim().is_empty()) {
        let row = io::parse(line)?;
        let id = text(&row, "id", "");
        io::safe_name(id)?;
        if let Some(i) = rows.iter().position(|old| text(old, "id", "") == id) {
            rows[i] = row;
        } else {
            rows.push(row);
        }
    }
    Ok(rows)
}

pub fn merge(
    index: &mut Vec<Json>,
    rows: Vec<Json>,
    family: &str,
    query: &str,
    date: &str,
    max_age: f64,
) -> Result<usize, String> {
    let today = date_days(date)?;
    let mut added = 0;
    for mut row in rows {
        let id = text(&row, "id", "").to_owned();
        if id.is_empty() {
            continue;
        }
        io::safe_name(&id)?;
        let age = age_days(text(&row, "age", "")).or_else(|| {
            let uploaded = text(&row, "upload_date", "");
            (uploaded.len() == 8)
                .then(|| {
                    date_days(&format!(
                        "{}-{}-{}",
                        &uploaded[..4],
                        &uploaded[4..6],
                        &uploaded[6..]
                    ))
                })
                .and_then(Result::ok)
                .map(|day| (today - day) as f64)
        });
        let Some(age) = age.filter(|age| *age >= 0.0 && *age <= max_age) else {
            continue;
        };
        if let Some(existing) = index.iter_mut().find(|r| text(r, "id", "") == id) {
            let mut families = list(existing, "families").to_vec();
            if !families
                .iter()
                .any(|v| matches!(v, Json::Str(s) if s == family))
            {
                families.push(string(family));
            }
            put(existing, "families", Json::Arr(families));
            continue;
        }
        put(&mut row, "families", Json::Arr(vec![string(family)]));
        put(&mut row, "query", string(query));
        put(
            &mut row,
            "age_days",
            wire::num(
                format!("{age:.1}")
                    .parse::<f64>()
                    .map_err(|e| e.to_string())?,
            ),
        );
        put(&mut row, "harvested", string(date));
        index.push(row);
        added += 1;
    }
    Ok(added)
}

pub fn save(path: &Path, rows: &[Json]) -> Result<(), String> {
    let mut output = String::new();
    for row in rows {
        output.push_str(&wire::encode(row));
        output.push('\n');
    }
    io::atomic_write(path, output.as_bytes())
}

pub fn search(query: &str, pages: usize, executable: &str) -> Result<Vec<Json>, String> {
    let limit = pages
        .checked_mul(20)
        .filter(|n| *n > 0 && *n <= 1000)
        .ok_or("pages must be 1..50")?;
    let response = Command::new(executable)
        .args([
            "--ignore-config",
            "--flat-playlist",
            "--dump-single-json",
            "--",
            &format!("ytsearch{limit}:{query}"),
        ])
        .output()
        .map_err(|e| format!("{executable}: {e}"))?;
    if !response.status.success() {
        return Err(format!(
            "search provider exited {}: {}",
            response.status,
            String::from_utf8_lossy(&response.stderr)
        ));
    }
    Ok(discover(&io::parse(&String::from_utf8_lossy(
        &response.stdout,
    ))?))
}

pub fn today() -> Result<String, String> {
    let days = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs()
        / 86400;
    let mut year = 1970;
    let mut day = days as i64;
    loop {
        let count = if leap(year) { 366 } else { 365 };
        if day < count {
            break;
        }
        year += 1;
        day -= count;
    }
    let mut month = 1;
    for count in months(year) {
        if day < count {
            break;
        }
        month += 1;
        day -= count;
    }
    Ok(format!("{year:04}-{month:02}-{:02}", day + 1))
}

fn leap(year: i64) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}
fn months(year: i64) -> [i64; 12] {
    [
        31,
        if leap(year) { 29 } else { 28 },
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
    ]
}
fn date_days(date: &str) -> Result<i64, String> {
    let parts = date
        .split('-')
        .map(str::parse::<i64>)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "date must be YYYY-MM-DD")?;
    if parts.len() != 3 {
        return Err("date must be YYYY-MM-DD".to_owned());
    }
    let (year, month, day) = (parts[0], parts[1], parts[2]);
    if !(1970..=9999).contains(&year)
        || !(1..=12).contains(&month)
        || day < 1
        || day > months(year)[month as usize - 1]
    {
        return Err("invalid date".to_owned());
    }
    Ok((1970..year)
        .map(|y| if leap(y) { 366 } else { 365 })
        .sum::<i64>()
        + months(year)[..month as usize - 1].iter().sum::<i64>()
        + day
        - 1)
}

pub fn fetch_missing(index: &[Json], directory: &Path, executable: &str) -> Result<(), String> {
    let mut errors = Vec::new();
    for row in index {
        let id = text(row, "id", "");
        if directory.join(format!("{id}.json")).exists() {
            continue;
        }
        if let Err(error) = transcripts::fetch(id, directory, executable) {
            errors.push(format!("{id}: {error}"));
        }
    }
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors.join("\n"))
    }
}
