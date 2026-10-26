//! JSON-independent tempo contract shared with the fidelity adapter by path.
//! Keeping this source shared avoids subtly different censoring or quantiles.

use std::collections::BTreeMap;

pub const SCHEMA: &str = "clash-tempo-v1";
pub const TIMES: [u32; 7] = [15, 30, 45, 60, 90, 120, 150];

#[derive(Clone, Debug, Default)]
pub struct Row {
    pub cluster: String,
    pub attacker_th: Option<u32>,
    pub defender_th: Option<u32>,
    pub trustworthy_final: bool,
    pub values: BTreeMap<String, Option<f64>>,
}

pub fn quantile(values: &[f64], probability: f64) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let index = probability * (sorted.len() - 1) as f64;
    let lower = index.floor() as usize;
    let upper = index.ceil() as usize;
    Some(sorted[lower] + (sorted[upper] - sorted[lower]) * index.fract())
}

pub fn interpolate(points: &[(f64, f64)], time: f64) -> Option<f64> {
    if points.first()?.0 > time || points.last()?.0 < time {
        return None;
    }
    let upper = points.partition_point(|point| point.0 < time);
    let right = *points.get(upper)?;
    if right.0 == time || upper == 0 {
        return Some(right.1);
    }
    let left = points[upper - 1];
    Some(left.1 + (right.1 - left.1) * (time - left.0) / (right.0 - left.0))
}

pub fn crossing(points: &[(f64, f64)], target: f64) -> Option<f64> {
    let upper = points.iter().position(|point| point.1 >= target)?;
    if upper == 0 {
        // Already reached at the first observation: left-censored.
        return None;
    }
    let left = points[upper - 1];
    let right = points[upper];
    Some(left.0 + (right.0 - left.0) * (target - left.1) / (right.1 - left.1))
}

pub struct Measurement<'a> {
    pub damage: &'a [(f64, f64)],
    pub max_interpolation_gap_s: Option<f64>,
    pub deployments: &'a [f64],
    pub stars: [Option<f64>; 3],
    pub final_damage: Option<f64>,
    pub final_stars: Option<f64>,
    pub end: Option<f64>,
    pub trustworthy_final: bool,
}

pub fn measure(input: Measurement<'_>) -> BTreeMap<String, Option<f64>> {
    let mut values = BTreeMap::new();
    let first = input.deployments.iter().copied().min_by(f64::total_cmp);
    let last = input.deployments.iter().copied().max_by(f64::total_cmp);
    values.insert("first_deployment_s".to_owned(), first);
    values.insert("last_deployment_s".to_owned(), last);
    for time in TIMES {
        values.insert(
            format!("destruction_{time}s"),
            interpolate(input.damage, time as f64)
                .filter(|_| gap_allowed(input.damage, time as f64, input.max_interpolation_gap_s))
                .filter(|_| input.end.is_none_or(|end| time as f64 <= end)),
        );
    }
    for (index, time) in input.stars.iter().enumerate() {
        values.insert(format!("star_{}_s", index + 1), *time);
    }
    for target in [50, 90] {
        values.insert(
            format!("time_to_{target}_s"),
            crossing(input.damage, target as f64)
                .filter(|time| gap_allowed(input.damage, *time, input.max_interpolation_gap_s)),
        );
    }
    values.insert("final_destruction".to_owned(), input.final_damage);
    values.insert("final_stars".to_owned(), input.final_stars);
    values.insert("battle_end_s".to_owned(), input.end);
    values.insert(
        "three_star_share".to_owned(),
        input
            .final_stars
            .filter(|_| input.trustworthy_final)
            .map(|stars| if stars == 3.0 { 1.0 } else { 0.0 }),
    );
    for time in [60, 90] {
        values.insert(
            format!("deploying_after_{time}s_share"),
            last.map(|last| if last > time as f64 { 1.0 } else { 0.0 }),
        );
    }
    values
}

fn gap_allowed(points: &[(f64, f64)], time: f64, limit: Option<f64>) -> bool {
    let Some(limit) = limit else { return true };
    let upper = points.partition_point(|point| point.0 < time);
    match (
        upper.checked_sub(1).and_then(|i| points.get(i)),
        points.get(upper),
    ) {
        (_, Some(right)) if right.0 == time => true,
        (Some(left), Some(right)) => right.0 - left.0 <= limit,
        _ => false,
    }
}

#[derive(Debug)]
pub struct Summary {
    pub n: usize,
    pub missing: usize,
    pub q1: Option<f64>,
    pub median: Option<f64>,
    pub q3: Option<f64>,
    pub estimate: Option<f64>,
}

fn observed(row: &Row, field: &str) -> Option<f64> {
    if matches!(field, "final_destruction" | "final_stars") && !row.trustworthy_final {
        return None;
    }
    row.values
        .get(field)
        .copied()
        .flatten()
        .filter(|v| v.is_finite())
}

pub fn summarize(rows: &[Row]) -> BTreeMap<String, Summary> {
    let fields = measure(Measurement {
        damage: &[],
        max_interpolation_gap_s: None,
        deployments: &[],
        stars: [None; 3],
        final_damage: None,
        final_stars: None,
        end: None,
        trustworthy_final: false,
    });
    fields
        .keys()
        .map(|field| {
            let values: Vec<_> = rows.iter().filter_map(|row| observed(row, field)).collect();
            let median = quantile(&values, 0.5);
            let estimate = if field.ends_with("_share") {
                (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64)
            } else {
                median
            };
            (
                field.clone(),
                Summary {
                    n: values.len(),
                    missing: rows.len() - values.len(),
                    q1: quantile(&values, 0.25),
                    median,
                    q3: quantile(&values, 0.75),
                    estimate,
                },
            )
        })
        .collect()
}

pub fn coverage(rows: &[Row]) -> BTreeMap<&'static str, Option<f64>> {
    let triples = rows
        .iter()
        .filter(|row| observed(row, "three_star_share") == Some(1.0))
        .count();
    let unknown = rows
        .iter()
        .filter(|row| observed(row, "three_star_share").is_none())
        .count();
    let clusters: std::collections::BTreeSet<_> = rows.iter().map(|row| &row.cluster).collect();
    BTreeMap::from([
        ("clusters", Some(clusters.len() as f64)),
        (
            "unknown_attacker_th_rows",
            Some(rows.iter().filter(|row| row.attacker_th.is_none()).count() as f64),
        ),
        ("verified_three_star_rows", Some(triples as f64)),
        ("unknown_final_rows", Some(unknown as f64)),
        (
            "three_star_all_rows_lower_bound",
            (!rows.is_empty()).then(|| triples as f64 / rows.len() as f64),
        ),
        (
            "three_star_all_rows_upper_bound",
            (!rows.is_empty()).then(|| (triples + unknown) as f64 / rows.len() as f64),
        ),
    ])
}

#[derive(Debug)]
pub struct Difference {
    pub estimate: Option<f64>,
    pub low: Option<f64>,
    pub high: Option<f64>,
    pub replicates: usize,
}

fn next_index(state: &mut u64, size: usize) -> usize {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    (*state % size as u64) as usize
}

fn clusters(rows: &[Row]) -> Vec<Vec<&Row>> {
    let mut groups: BTreeMap<&str, Vec<&Row>> = BTreeMap::new();
    for row in rows {
        groups.entry(&row.cluster).or_default().push(row);
    }
    groups.into_values().collect()
}

fn resample<'a>(groups: &[Vec<&'a Row>], state: &mut u64) -> Vec<&'a Row> {
    let mut rows = Vec::new();
    for _ in 0..groups.len() {
        rows.extend_from_slice(&groups[next_index(state, groups.len())]);
    }
    rows
}

fn estimate(rows: &[&Row], field: &str) -> Option<f64> {
    let values: Vec<_> = rows.iter().filter_map(|row| observed(row, field)).collect();
    if field.ends_with("_share") {
        (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64)
    } else {
        quantile(&values, 0.5)
    }
}

pub fn differences(sim: &[Row], video: &[Row], replicates: usize) -> BTreeMap<String, Difference> {
    let sim_summary = summarize(sim);
    let video_summary = summarize(video);
    let mut draws: BTreeMap<String, Vec<f64>> = sim_summary
        .keys()
        .map(|k| (k.clone(), Vec::new()))
        .collect();
    let sim_groups = clusters(sim);
    let video_groups = clusters(video);
    let mut state = 0x5654_7465_6d70_6f31;
    for _ in 0..replicates {
        let sim_draw = resample(&sim_groups, &mut state);
        let video_draw = resample(&video_groups, &mut state);
        for (field, values) in &mut draws {
            if let (Some(sim), Some(video)) =
                (estimate(&sim_draw, field), estimate(&video_draw, field))
            {
                values.push(sim - video);
            }
        }
    }
    draws
        .into_iter()
        .map(|(field, values)| {
            let difference = Difference {
                estimate: sim_summary
                    .get(&field)
                    .and_then(|s| s.estimate)
                    .zip(video_summary.get(&field).and_then(|s| s.estimate))
                    .map(|(a, b)| a - b),
                low: quantile(&values, 0.05),
                high: quantile(&values, 0.95),
                replicates: values.len(),
            };
            (field, difference)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_linear_tempo_and_censoring() {
        let values = measure(Measurement {
            damage: &[(0.0, 0.0), (60.0, 100.0)],
            max_interpolation_gap_s: None,
            deployments: &[0.0, 45.0],
            stars: [Some(30.0), Some(40.0), Some(60.0)],
            final_damage: Some(100.0),
            final_stars: Some(3.0),
            end: Some(60.0),
            trustworthy_final: true,
        });
        assert_eq!(values["destruction_15s"], Some(25.0));
        assert_eq!(values["destruction_90s"], None);
        assert_eq!(values["time_to_90_s"], Some(54.0));
        let row = Row {
            cluster: "synthetic".to_owned(),
            trustworthy_final: true,
            values,
            ..Row::default()
        };
        assert_eq!(
            summarize(std::slice::from_ref(&row))["three_star_share"].estimate,
            Some(1.0)
        );
        let difference = differences(std::slice::from_ref(&row), std::slice::from_ref(&row), 20);
        assert_eq!(difference["battle_end_s"].low, Some(0.0));
        assert_eq!(difference["battle_end_s"].high, Some(0.0));
        assert_eq!(crossing(&[(20.0, 75.0)], 50.0), None);
    }
}
