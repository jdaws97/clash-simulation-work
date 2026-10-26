//! Recorded step_gaps.py timing estimator; fallback provenance stays explicit.
use crate::citations::Transcripts;
use crate::io;
use clash_data::json::Json;
use clash_data::wire::{self, list, obj, string, text};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

fn rounded(value: f64) -> f64 {
    format!("{value:.1}").parse().unwrap_or(value)
}
fn median(values: &mut [f64]) -> f64 {
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    if values.len().is_multiple_of(2) {
        (values[mid - 1] + values[mid]) / 2.0
    } else {
        values[mid]
    }
}

fn summary(mut values: Vec<f64>) -> Result<Json, String> {
    if values.len() < 2 {
        return Err("timing summary requires at least two pairs in each group".to_owned());
    }
    let value = median(&mut values);
    let n = values.len();
    let quartiles = (1..4)
        .map(|i| {
            // statistics.quantiles(n=4, method='exclusive'), including extrapolation.
            let position = i * (n + 1);
            let j = (position / 4).clamp(1, n - 1);
            let delta = position as f64 - (j * 4) as f64;
            Json::Num(rounded(
                (values[j - 1] * (4.0 - delta) + values[j] * delta) / 4.0,
            ))
        })
        .collect();
    Ok(obj([
        ("median", wire::num(rounded(value))),
        ("n", wire::num(n as f64)),
        ("quartiles", Json::Arr(quartiles)),
    ]))
}

fn cite_times(
    step: &Json,
    transcripts: &mut Transcripts,
    tally: &mut BTreeMap<String, usize>,
    seen: &mut BTreeSet<String>,
) -> Result<BTreeMap<String, Option<f64>>, String> {
    let mut times = BTreeMap::new();
    for cite in list(step, "cite") {
        // Recorded battle events have a different clock from narration.
        if cite.get("replay").is_some() {
            continue;
        }
        let located = transcripts.verify(cite)?;
        let stored = io::optional_number(cite.get("verified_t"))?;
        let stated = io::optional_number(cite.get("t"))?;
        let how = if located.is_some() {
            "located in transcript"
        } else if stored.is_some() {
            "stored verified_t"
        } else {
            "stated t only"
        };
        let key = wire::encode(&Json::Arr(
            ["video", "quote", "t"]
                .iter()
                .map(|k| cite.get(k).cloned().unwrap_or(Json::Null))
                .collect(),
        ));
        if seen.insert(key) {
            *tally.entry(how.to_owned()).or_default() += 1;
        }
        times.insert(
            text(cite, "video", "").to_owned(),
            located.or(stored).or(stated),
        );
    }
    Ok(times)
}

pub fn measure(directory: &Path, transcripts: &mut Transcripts) -> Result<(Json, Json), String> {
    let (mut same, mut change) = (Vec::new(), Vec::new());
    let (mut tally, mut seen) = (BTreeMap::new(), BTreeSet::new());
    for path in io::files(directory, "json")? {
        if path
            .file_name()
            .is_some_and(|n| n.to_string_lossy().starts_with("test-"))
        {
            continue;
        }
        let playbook = io::read(&path)?;
        let steps: BTreeMap<_, _> = list(&playbook, "steps")
            .iter()
            .map(|s| (text(s, "id", ""), s))
            .collect();
        for step in list(&playbook, "steps") {
            let when = step.get("when").unwrap_or(&Json::Null);
            let Some(previous) = steps.get(text(when, "after", "")) else {
                continue;
            };
            if wire::number(when, "delay", 0.0) != 0.0 {
                continue;
            }
            let a = cite_times(previous, transcripts, &mut tally, &mut seen)?;
            let b = cite_times(step, transcripts, &mut tally, &mut seen)?;
            let mut gaps = Vec::new();
            for (video, time) in a {
                if let (Some(a), Some(Some(b))) = (time, b.get(&video)) {
                    let gap = b - a;
                    if gap > 0.0 && gap <= 90.0 {
                        gaps.push(gap);
                    }
                }
            }
            if !gaps.is_empty() {
                let gap = median(&mut gaps);
                if text(step, "group", "main") == text(previous, "group", "main") {
                    same.push(gap);
                } else {
                    change.push(gap);
                }
            }
        }
    }
    let output = obj([
        ("note", string("Median wait (s) between a step and the step it follows, from same-video cite times (tools/baselab/step_gaps.py).")),
        ("same_group", summary(same)?), ("group_change", summary(change)?),
    ]);
    Ok((output, wire::count_map(&tally)))
}
