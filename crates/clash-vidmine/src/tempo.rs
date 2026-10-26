//! Read-only reduction of mined HUD observations to the shared tempo contract.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::Path;

use crate::json::Value;
use crate::tempo_metrics::{self as metrics, Measurement, Row};

fn object(fields: impl IntoIterator<Item = (impl Into<String>, Value)>) -> Value {
    Value::Object(fields.into_iter().map(|(k, v)| (k.into(), v)).collect())
}

fn optional(value: Option<f64>) -> Value {
    value.map_or(Value::Null, Value::Number)
}

fn bounded(value: &Value, max: f64) -> Option<f64> {
    value.number().filter(|v| (0.0..=max).contains(v))
}

fn summary(rows: &[Row]) -> Value {
    object([
        (
            "coverage",
            object(
                metrics::coverage(rows)
                    .into_iter()
                    .map(|(k, v)| (k, optional(v))),
            ),
        ),
        ("rows", Value::from(rows.len() as f64)),
        (
            "trustworthy_final_rows",
            Value::from(rows.iter().filter(|r| r.trustworthy_final).count() as f64),
        ),
        (
            "metrics",
            object(metrics::summarize(rows).into_iter().map(|(field, s)| {
                (
                    field,
                    object([
                        ("n", Value::from(s.n as f64)),
                        ("missing", Value::from(s.missing as f64)),
                        ("q1", optional(s.q1)),
                        ("median", optional(s.median)),
                        ("q3", optional(s.q3)),
                        ("estimate", optional(s.estimate)),
                    ]),
                )
            })),
        ),
    ])
}

fn army(attack: &Value) -> Value {
    let mut cards: BTreeMap<String, Value> = BTreeMap::new();
    for card in attack
        .get("slots")
        .array()
        .iter()
        .chain(attack.get("army_cards").array())
    {
        let Some(name) = card
            .get("name")
            .string()
            .filter(|_| card.get("name_confidence").number().unwrap_or(0.0) >= 0.8)
        else {
            continue;
        };
        let level = card.get("level").get("value").clone();
        let donated = card.get("donated").clone();
        let key = format!("{name}|{}|{}", level.encode(), donated.encode());
        let entry = cards.entry(key).or_insert_with(|| {
            object([
                ("name", Value::from(name)),
                ("level", level),
                ("donated", donated),
                ("count", Value::Null),
                ("name_confidence", card.get("name_confidence").clone()),
            ])
        });
        // Army-card and initial-slot indices are different coordinate systems.
        if let Some(count) = bounded(card.get("initial_count"), 400.0) {
            if entry.get("count").number().is_none_or(|old| count > old) {
                entry.set("count", Value::from(count));
            }
        }
    }
    Value::Array(cards.into_values().collect())
}

fn reduce(attack: &Value) -> Result<(Row, Value), String> {
    let video_id = attack.get("video_id").string().ok_or("missing video_id")?;
    let index = attack
        .get("attack")
        .number()
        .filter(|v| *v >= 1.0 && v.fract() == 0.0)
        .ok_or("invalid attack index")?;
    let clock: Vec<_> = attack
        .get("clock_series")
        .array()
        .iter()
        .filter_map(|sample| {
            let t = sample.get("video_t").number()?;
            let c = bounded(sample.get("clock_t"), 180.0)?;
            (sample.get("confidence").number().unwrap_or(0.0) >= 0.6).then_some((t, c))
        })
        .collect();
    let offsets: Vec<_> = clock.iter().map(|(t, c)| t + c).collect();
    let anchor = metrics::quantile(&offsets, 0.5).ok_or("no confident clock observations")?;
    let inliers: Vec<_> = clock
        .iter()
        .filter(|(t, c)| (t + c - anchor).abs() <= 2.0)
        .collect();
    if inliers.len() < 6 || inliers.len() as f64 / (clock.len() as f64) < 0.7 {
        return Err("clock fails unit-speed anchor consistency".to_owned());
    }
    let elapsed = |sample: &Value| -> Option<f64> {
        let t = sample.get("video_t").number()?;
        let e = t + 180.0 - anchor;
        let first = inliers.first()?.0;
        let last = inliers.last()?.0;
        (t >= first - 1.0 && t <= last + 3.0 && (-0.6..=180.6).contains(&e))
            .then_some(e.clamp(0.0, 180.0))
    };
    let mut candidates: Vec<_> = attack
        .get("damage_series")
        .array()
        .iter()
        .filter_map(|sample| {
            (sample.get("confidence").number().unwrap_or(0.0) >= 0.7)
                .then(|| Some((elapsed(sample)?, bounded(sample.get("percent"), 100.0)?)))?
        })
        .collect();
    candidates.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut damage: Vec<(f64, f64)> = Vec::new();
    let mut rejected_damage = 0;
    for (i, point) in candidates.iter().copied().enumerate() {
        let persistent = candidates[i + 1..]
            .iter()
            .take_while(|next| next.0 <= point.0 + 1.0)
            .any(|next| next.1 == point.1 && next.0 - point.0 >= 0.15)
            || candidates[..i]
                .iter()
                .rev()
                .take_while(|prev| prev.0 >= point.0 - 1.0)
                .any(|prev| prev.1 == point.1 && point.0 - prev.0 >= 0.15);
        if persistent
            && damage
                .last()
                .is_none_or(|last| point.0 > last.0 && point.1 >= last.1)
        {
            damage.push(point);
        } else {
            rejected_damage += 1;
        }
    }
    let mut stars = [None; 3];
    let mut observed_stars: Option<f64> = None;
    for sample in attack.get("stars").array() {
        let Some(star) = bounded(sample.get("star"), 3.0).filter(|v| *v >= 1.0 && v.fract() == 0.0)
        else {
            continue;
        };
        if sample.get("confidence").number().unwrap_or(0.0) < 0.6 {
            continue;
        }
        let slot = &mut stars[star as usize - 1];
        if slot.is_none() {
            *slot = elapsed(sample);
        }
        observed_stars = Some(observed_stars.unwrap_or(0.0).max(star));
    }
    let final_damage = damage.last().map(|p| p.1);
    let hundred: Vec<_> = damage.iter().filter(|p| p.1 == 100.0).collect();
    let completed = hundred
        .first()
        .zip(hundred.last())
        .is_some_and(|(first, last)| last.0 - first.0 >= 0.4)
        && observed_stars == Some(3.0);
    let result = attack.get("result_screen");
    let result_damage = bounded(result.get("damage").get("value"), 100.0);
    let result_stars = bounded(result.get("stars"), 3.0).filter(|v| v.fract() == 0.0);
    let settled = result.get("settled") == &Value::Bool(true)
        && result
            .get("damage")
            .get("confidence")
            .number()
            .unwrap_or(0.0)
            >= 0.7
        && result_damage.zip(final_damage).is_some_and(|(r, d)| r >= d)
        && result_stars.is_some_and(|s| observed_stars.is_none_or(|old| s >= old))
        && result_damage.zip(result_stars).is_some_and(|(d, s)| {
            (d == 100.0) == (s == 3.0) && (d < 50.0 || s >= 1.0) && (s < 2.0 || d >= 50.0)
        });
    let timed_out = inliers
        .iter()
        .any(|(t, c)| *c == 0.0 && *t + 180.0 - anchor >= 179.0)
        && damage.last().is_some_and(|p| p.0 >= 179.0);
    let trustworthy = completed
        || settled
        || (timed_out && final_damage.is_some() && observed_stars.is_some_and(|s| s < 3.0));
    let end = if completed {
        hundred.first().map(|p| p.0)
    } else if timed_out {
        Some(180.0)
    } else {
        None
    };
    if completed {
        // Terminal clock zero is a display state, not 180 elapsed seconds.
        stars[2] = end;
    } else {
        stars[2] = None;
    }
    if let Some(end) = end {
        damage.retain(|p| p.0 <= end);
    }
    let deployments: Vec<_> = attack
        .get("deployments")
        .array()
        .iter()
        .filter_map(|sample| {
            (sample.get("confidence").number().unwrap_or(0.0) >= 0.6
                && sample.get("delta").number().is_some_and(|v| v > 0.0))
            .then(|| elapsed(sample))?
        })
        .collect();
    let th = match attack.get("attacker_th") {
        Value::Number(v) => Some(*v),
        value => value.get("best").number(),
    }
    .filter(|v| (1.0..=18.0).contains(v) && v.fract() == 0.0)
    .map(|v| v as u32);
    let row = Row {
        cluster: video_id.to_owned(),
        attacker_th: th,
        defender_th: None,
        trustworthy_final: trustworthy,
        values: metrics::measure(Measurement {
            damage: &damage,
            max_interpolation_gap_s: Some(3.0),
            deployments: &deployments,
            stars,
            final_damage: if settled { result_damage } else { final_damage },
            final_stars: if settled {
                result_stars
            } else {
                observed_stars
            },
            end,
            trustworthy_final: trustworthy,
        }),
    };
    let mut output = object([
        ("video_id", Value::from(video_id)),
        ("attack", Value::from(index)),
        ("attacker_th", optional(th.map(f64::from))),
        ("defender_th", Value::Null),
        (
            "attacker_th_status",
            Value::from(if th.is_some() {
                "minimum-compatible estimate; higher TH possible"
            } else {
                "unknown"
            }),
        ),
        ("attacker_th_evidence", attack.get("attacker_th").clone()),
        ("league", attack.get("league").get("label").clone()),
        ("army", army(attack)),
        (
            "end_observed",
            Value::Bool(completed || settled || timed_out),
        ),
        ("trustworthy_final", Value::Bool(trustworthy)),
        (
            "final_source",
            Value::from(if completed {
                "sustained_100_and_third_star"
            } else if settled {
                "settled_confident_result_screen"
            } else if timed_out {
                "consistent_timer_zero"
            } else {
                "last_confident_HUD_observation_end_unobserved"
            }),
        ),
        ("raw_final_percent", attack.get("final_percent").clone()),
        ("raw_final_stars", attack.get("final_stars").clone()),
        (
            "last_observed_elapsed_s",
            optional(damage.last().map(|p| p.0)),
        ),
        ("deployment_timing_is_partial", Value::Bool(true)),
        (
            "clock_outliers",
            Value::from((clock.len() - inliers.len()) as f64),
        ),
        (
            "rejected_damage_samples",
            Value::from(rejected_damage as f64),
        ),
        ("timing_status", attack.get("timing_status").clone()),
    ]);
    for (field, value) in &row.values {
        output.set(field, optional(*value));
    }
    Ok((row, output))
}

pub fn command(args: &[String]) -> io::Result<()> {
    let mut input = None;
    let mut output = None;
    let mut options = args.iter();
    while let Some(option) = options.next() {
        let destination = match option.as_str() {
            "--in" => &mut input,
            "--out" => &mut output,
            _ => return Err(io::Error::other(format!("unknown tempo option {option}"))),
        };
        *destination = Some(
            options
                .next()
                .ok_or_else(|| io::Error::other(format!("missing value for {option}")))?,
        );
    }
    let input = Path::new(input.ok_or_else(|| io::Error::other("tempo requires --in DIR"))?);
    let output = Path::new(output.ok_or_else(|| io::Error::other("tempo requires --out FILE"))?);
    let mut directories = vec![input.to_path_buf()];
    for entry in fs::read_dir(input)? {
        let path = entry?.path();
        if path.is_dir() {
            directories.push(path);
        }
    }
    directories.sort();
    let mut rows = Vec::new();
    let mut json_rows = Vec::new();
    let mut excluded = Vec::new();
    let mut reasons: BTreeMap<String, usize> = BTreeMap::new();
    let mut total = 0;
    for directory in directories {
        for path in crate::icons::attack_paths(&directory)? {
            total += 1;
            let attack = Value::parse(&fs::read_to_string(&path)?)
                .map_err(|e| io::Error::other(format!("{}: {e}", path.display())))?;
            let reason = if attack.get("sped_up") == &Value::Bool(true) {
                Some("sped_up".to_owned())
            } else if attack.get("usable_for_timing") != &Value::Bool(true) {
                Some(format!(
                    "non_usable: {}",
                    attack
                        .get("timing_status")
                        .string()
                        .unwrap_or("missing timing status")
                ))
            } else {
                match reduce(&attack) {
                    Ok((row, json)) => {
                        rows.push(row);
                        json_rows.push(json);
                        None
                    }
                    Err(reason) => Some(format!("invalid_timing: {reason}")),
                }
            };
            if let Some(reason) = reason {
                *reasons.entry(reason.clone()).or_default() += 1;
                excluded.push(object([
                    ("path", Value::from(path.to_string_lossy().as_ref())),
                    ("reason", Value::from(reason.as_str())),
                    ("timing_status", attack.get("timing_status").clone()),
                ]));
            }
        }
    }
    if total == 0 {
        return Err(io::Error::other("no attack-NN.json inputs found"));
    }
    let mut groups: BTreeMap<String, Vec<Row>> = BTreeMap::new();
    for row in &rows {
        groups
            .entry(
                row.attacker_th
                    .map_or_else(|| "unknown".to_owned(), |th| th.to_string()),
            )
            .or_default()
            .push(row.clone());
    }
    let report = object([
        ("schema", Value::from(metrics::SCHEMA)), ("source", Value::from(input.to_string_lossy().as_ref())),
        ("input_attacks", Value::from(total as f64)),
        ("excluded_counts", object(reasons.into_iter().map(|(k, n)| (k, Value::from(n as f64))))),
        ("excluded", Value::Array(excluded)),
        ("method", Value::from("elapsed=video_t+180-median(video_t+clock_t), confident clock inliers within 2s; damage confidence>=0.7 and repeated within 1s; stars/deployments confidence>=0.6; army name confidence>=0.8; final aggregates and p3 require trustworthy_final; linear destruction interpolation only across gaps<=3s and never beyond observations; deployment shares count observed card deltas including spells and are lower bounds")),
        ("aggregate", summary(&rows)),
        ("by_attacker_th", object(groups.iter().map(|(th, rows)| (th, summary(rows))))),
        ("rows", Value::Array(json_rows)),
    ]);
    if let Some(parent) = output.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    fs::write(output, report.encode() + "\n")?;
    eprintln!(
        "tempo: {total} inputs, {} included, {} excluded, {} trustworthy finals",
        rows.len(),
        total - rows.len(),
        rows.iter().filter(|r| r.trustworthy_final).count()
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_terminal_clock_zero_does_not_mean_timeout() {
        let mut attack = Value::parse(r#"{"video_id":"synthetic","attack":1,"clock_series":[],"damage_series":[],"stars":[{"star":3,"clock_t":0,"video_t":21,"confidence":1}]}"#).unwrap();
        attack.set(
            "clock_series",
            Value::Array(
                (0..=12)
                    .map(|i| {
                        object([
                            ("video_t", Value::from(10.0 + i as f64)),
                            (
                                "clock_t",
                                Value::from(if i >= 10 { 0.0 } else { 180.0 - i as f64 }),
                            ),
                            ("confidence", Value::from(1.0)),
                        ])
                    })
                    .collect(),
            ),
        );
        attack.set(
            "damage_series",
            Value::Array(
                (0..=24)
                    .map(|i| {
                        object([
                            ("video_t", Value::from(10.0 + i as f64 / 2.0)),
                            ("percent", Value::from(if i >= 20 { 100.0 } else { 0.0 })),
                            ("confidence", Value::from(1.0)),
                        ])
                    })
                    .collect(),
            ),
        );
        let (row, _) = reduce(&attack).unwrap();
        assert_eq!(row.values["battle_end_s"], Some(10.0));
        assert_eq!(row.values["star_3_s"], Some(10.0));
        assert!(row.trustworthy_final);
    }
}
