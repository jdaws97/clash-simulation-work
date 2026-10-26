//! Tempo diagnostics through the existing compiler, visible scout and job runner.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, Mutex};

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_engine::runner::Job;
use clash_engine::state::{Battle, BattleResult};
use clash_engine::trace::LogValue;
use clash_plans::armies::META_FILE;
use clash_plans::compile::Compiler;
use clash_scoring::scoring::{Scenario, Scorer};
use clash_scoring::scouting::ScoutPolicy;

use super::io::*;
use super::{provenance, replay, Arguments};

// The same std-only measurement contract as `clash video tempo`.
use clash_vidmine::tempo_metrics as metrics;
use metrics::{Measurement, Row};

fn optional(value: Option<f64>) -> Json {
    value.map_or(Json::Null, num)
}

fn summary(rows: &[Row]) -> Json {
    obj([
        (
            "coverage",
            obj(metrics::coverage(rows)
                .into_iter()
                .map(|(k, v)| (k, optional(v)))),
        ),
        ("rows", num(rows.len() as f64)),
        (
            "trustworthy_final_rows",
            num(rows.iter().filter(|r| r.trustworthy_final).count() as f64),
        ),
        (
            "metrics",
            obj(metrics::summarize(rows).into_iter().map(|(field, s)| {
                (
                    field,
                    obj([
                        ("n", num(s.n as f64)),
                        ("missing", num(s.missing as f64)),
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

fn differences(sim: &[Row], video: &[Row]) -> Json {
    obj(metrics::differences(sim, video, 1000)
        .into_iter()
        .map(|(field, d)| {
            (
                field,
                obj([
                    ("sim_minus_video", optional(d.estimate)),
                    ("bootstrap_90_low", optional(d.low)),
                    ("bootstrap_90_high", optional(d.high)),
                    ("valid_replicates", num(d.replicates as f64)),
                ]),
            )
        }))
}

fn video_rows(input: &Json) -> Result<Vec<Row>, String> {
    if text(input, "schema", "") != metrics::SCHEMA {
        return Err(
            "--video requires clash video tempo output with schema clash-tempo-v1".to_owned(),
        );
    }
    let Json::Arr(values) = input.get("rows").ok_or("video report missing rows")? else {
        return Err("video rows must be an array".to_owned());
    };
    let fields = metrics::summarize(&[]);
    let mut rows = Vec::new();
    for value in values {
        let mut row = Row {
            cluster: text(value, "video_id", "").to_owned(),
            trustworthy_final: match value.get("trustworthy_final") {
                Some(Json::Bool(flag)) => *flag,
                _ => return Err("video row missing boolean trustworthy_final".to_owned()),
            },
            ..Row::default()
        };
        if row.cluster.is_empty() {
            return Err("video row missing video_id".to_owned());
        }
        row.attacker_th = match value.get("attacker_th") {
            Some(Json::Null) => None,
            Some(Json::Num(v)) if (1.0..=18.0).contains(v) && v.fract() == 0.0 => Some(*v as u32),
            _ => return Err("invalid video attacker_th".to_owned()),
        };
        for field in fields.keys() {
            let number = match value.get(field) {
                Some(Json::Null) => None,
                Some(Json::Num(v)) if v.is_finite() => Some(*v),
                _ => return Err(format!("video row missing or invalid {field}")),
            };
            row.values.insert(field.clone(), number);
        }
        rows.push(row);
    }
    if rows.is_empty() {
        return Err("video report has no usable rows".to_owned());
    }
    Ok(rows)
}

fn log_number(value: Option<&LogValue>) -> Option<f64> {
    match value {
        Some(LogValue::Float(v)) => Some(*v),
        Some(LogValue::Int(v)) => Some(*v as f64),
        _ => None,
    }
}

fn log_text(value: Option<&LogValue>) -> Option<&str> {
    match value {
        Some(LogValue::String(v)) => Some(v),
        _ => None,
    }
}

fn army_cards(build: &Json) -> Json {
    let mut cards = Vec::new();
    for source in ["troops", "spells", "cc"] {
        if let Some(Json::Obj(entries)) = build.get(source) {
            for (name, count) in entries {
                cards.push(obj([
                    ("name", string(name)),
                    ("count", count.clone()),
                    ("level", Json::Null),
                    ("donated", Json::Bool(source == "cc")),
                    ("name_confidence", num(1.0)),
                ]));
            }
        }
    }
    for hero in list(build, "heroes") {
        cards.push(obj([
            ("name", hero.clone()),
            ("count", num(1.0)),
            ("level", Json::Null),
            ("donated", Json::Bool(false)),
            ("name_confidence", num(1.0)),
        ]));
    }
    arr(cards)
}

fn battle_row(
    battle: &Battle,
    result: &BattleResult,
    base: &str,
    scenario: &Scenario,
    build: &Json,
    defender_th: u32,
) -> Result<(Row, Json), String> {
    let mut damage = vec![(0.0, 0.0)];
    let mut deployments = Vec::new();
    let mut stars = [None; 3];
    let mut th_destroyed = false;
    let mut current_damage = 0.0;
    for event in &battle.log {
        let time = log_number(event.first()).ok_or("invalid event time")?;
        match log_text(event.get(1)) {
            Some("deploy" | "spell") => deployments.push(time),
            Some("destroyed") => {
                current_damage = log_number(event.get(3)).ok_or("invalid destroyed event")?;
                th_destroyed |= log_text(event.get(2)) == Some("th");
                if damage.last().is_some_and(|p| p.0 == time) {
                    if let Some(last) = damage.last_mut() {
                        last.1 = current_damage;
                    }
                } else {
                    damage.push((time, current_damage));
                }
                let earned = usize::from(th_destroyed)
                    + usize::from(current_damage >= 50.0)
                    + usize::from(current_damage >= 100.0);
                for star in stars.iter_mut().take(earned) {
                    if star.is_none() {
                        *star = Some(time);
                    }
                }
            }
            _ => {}
        }
    }
    if current_damage != result.destruction as f64 || stars.iter().flatten().count() != result.stars
    {
        return Err("recorded battle events disagree with native result".to_owned());
    }
    if damage.last().is_some_and(|p| p.0 < result.time) {
        damage.push((result.time, current_damage));
    }
    // Recover the HUD's 5 Hz observation stream from the complete event log.
    // Holding each destruction value until the next event avoids inventing
    // gradual damage during long intervals with no destroyed buildings.
    let events = damage;
    let mut damage = Vec::new();
    let mut cursor = 0;
    for tick in 0..=(result.time * 5.0).ceil() as usize {
        let time = (tick as f64 / 5.0).min(result.time);
        while cursor + 1 < events.len() && events[cursor + 1].0 <= time {
            cursor += 1;
        }
        damage.push((time, events[cursor].1));
    }
    let row = Row {
        cluster: base.to_owned(),
        attacker_th: Some(scenario.town_hall as u32),
        defender_th: Some(defender_th),
        trustworthy_final: true,
        values: metrics::measure(Measurement {
            damage: &damage,
            max_interpolation_gap_s: Some(3.0),
            deployments: &deployments,
            stars,
            final_damage: Some(result.destruction as f64),
            final_stars: Some(result.stars as f64),
            end: Some(result.time),
            trustworthy_final: true,
        }),
    };
    let mut json = obj([
        ("video_id", Json::Null),
        ("attack", num(scenario.group as f64)),
        ("base", string(base)),
        ("attacker_th", num(scenario.town_hall as f64)),
        ("defender_th", num(defender_th as f64)),
        ("league", Json::Null),
        ("army_id", string(&scenario.army)),
        ("army", army_cards(build)),
        ("army_build", build.clone()),
        ("seed", num(scenario.seed as f64)),
        ("angle", num(scenario.angle)),
        ("skill_quantile", num((scenario.group as usize % 5) as f64)),
        ("scenario_weight", num(scenario.weight)),
        ("trustworthy_final", Json::Bool(true)),
        ("end_observed", Json::Bool(true)),
        (
            "final_source",
            string("native_battle_result_checked_against_events"),
        ),
        ("end_reason", string(replay::end_reason(battle))),
        ("deployment_timing_is_partial", Json::Bool(false)),
        ("last_observed_elapsed_s", num(result.time)),
    ]);
    for (field, value) in &row.values {
        put(&mut json, field, optional(*value));
    }
    Ok((row, json))
}

pub fn command(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let video_path = args
        .optional_path("--video")
        .ok_or("tempo requires --video FILE")?;
    let output = args
        .optional_path("--out")
        .ok_or("tempo requires --out FILE")?;
    super::distinct_paths(&[&video_path, &output])?;
    let video = read(&video_path)?;
    let videos = video_rows(&video)?;
    let angles = args.integer("--angles", 3)?;
    let repeats = args.integer("--replicates", args.integer("--seeds", 2)?)?;
    let scout = args.integer("--scout", 2)?;
    let threads = args.integer("--threads", 4)?;
    if !(2..=16).contains(&angles)
        || repeats == 0
        || repeats > 10
        || scout < 2
        || scout > angles
        || threads == 0
    {
        return Err(
            "tempo requires angles 2..16, replicates 1..10, threads>=1 and 2<=scout<=angles"
                .to_owned(),
        );
    }
    if args.value("--attacker", "playbook") != "playbook"
        || args.value("--scout-policy", "visible") != "visible"
    {
        return Err(
            "tempo benchmark requires --attacker playbook --scout-policy visible".to_owned(),
        );
    }
    let calibration = args.calibration();
    let strengths = replay::strengths(&args.root, &calibration)?;
    let catalog_path = args
        .optional_path("--catalog")
        .unwrap_or_else(|| clash_data::catalog::path(&args.root));
    let mut sources = vec![video_path.clone(), calibration.clone(), catalog_path];
    let mut bases: BTreeMap<u32, Vec<(String, Json)>> = BTreeMap::new();
    for directory in ["ranked-2026-10-24", "ranked-th18-2026-10-25"] {
        let directory = args
            .root
            .join("data/source/reference-bases")
            .join(directory);
        let mut paths = std::fs::read_dir(&directory)
            .map_err(|e| format!("{}: {e}", directory.display()))?
            .map(|e| e.map(|e| e.path()))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| e.to_string())?;
        paths.retain(|p| p.extension().is_some_and(|ext| ext == "json"));
        paths.sort();
        for path in paths {
            let layout = read(&path)?;
            let th = number(&layout, "town_hall", 0.0) as u32;
            if !matches!(th, 16..=18) {
                return Err(format!("invalid reference TH in {}", path.display()));
            }
            let name = path
                .file_stem()
                .ok_or("base path has no stem")?
                .to_string_lossy()
                .into_owned();
            bases.entry(th).or_default().push((name, layout));
            sources.push(path);
        }
    }
    let supported: BTreeSet<_> = videos
        .iter()
        .filter_map(|r| r.attacker_th)
        .filter(|th| (16..=18).contains(th))
        .collect();
    let selected_th = args
        .values
        .get("--town-hall")
        .map(|s| s.parse::<u32>().map_err(|_| "invalid --town-hall"))
        .transpose()?;
    if selected_th.is_some_and(|th| !(16..=18).contains(&th)) {
        return Err("meta tempo supports attacker TH16..18".to_owned());
    }
    let mut armies: BTreeMap<u32, Vec<_>> = BTreeMap::new();
    for entry in &compiler.library.builds {
        let th = number(&entry.value, "th", 0.0) as u32;
        if entry.library == META_FILE
            && selected_th.map_or_else(|| supported.contains(&th), |selected| th == selected)
        {
            armies.entry(th).or_default().push(entry);
        }
    }
    if armies.is_empty() || bases.is_empty() {
        return Err("no supported meta armies or reference bases".to_owned());
    }
    // A balanced incomplete crossing covers every army and every base in each
    // TH cell without turning a diagnostic into tens of thousands of battles.
    let pairs: usize = armies
        .iter()
        .map(|(attacker_th, a)| {
            bases
                .iter()
                .filter(|(defender_th, _)| *defender_th >= attacker_th)
                .map(|(_, b)| a.len().max(b.len()))
                .sum::<usize>()
        })
        .sum();
    let budget = pairs * repeats * 5 * (angles * 3 + 2);
    if budget > 6000 {
        return Err(format!("tempo would run up to {budget} battles; reduce replicates/angles/scout or select --town-hall (limit 6000)"));
    }
    let inputs = provenance::fingerprint(
        &args.root,
        &sources.iter().map(|p| p.as_path()).collect::<Vec<_>>(),
    )?;
    let mut rows = Vec::new();
    let mut json_rows = Vec::new();
    let mut design = Vec::new();
    let mut planning = 0;
    let mut evaluations = 0;
    let mut diagnostics = 0;
    for (attacker_th, builds) in &armies {
        for (defender_th, layouts) in &bases {
            if defender_th < attacker_th {
                continue;
            }
            for pair in 0..builds.len().max(layouts.len()) {
                let entry = builds[pair % builds.len()];
                let (base, layout) = &layouts[pair % layouts.len()];
                let family = clash_plans::armies::family_of(&entry.value)
                    .ok_or_else(|| format!("unknown meta army family {}", entry.id))?;
                let (attacker, fallback) = replay::attacker(compiler, family, "playbook");
                if let Some(reason) = fallback {
                    return Err(format!("{}: playbook unavailable: {reason}", entry.id));
                }
                let army_id = format!("meta:{}", entry.id);
                let strength = strengths.get(&army_id);
                let mut scenarios = Vec::new();
                let mut plans = Vec::new();
                for repeat in 0..repeats {
                    for q in 0..5 {
                        for side in 0..angles {
                            let seed = (5 * (angles * repeat + side) + q) as i64;
                            let angle = std::f64::consts::TAU * side as f64 / angles as f64;
                            scenarios.push(Scenario {
                                army: army_id.clone(),
                                town_hall: *attacker_th as i64,
                                angle,
                                seed,
                                weight: 1.0 / (repeats * 5 * angles) as f64,
                                modifier: None,
                                group: (5 * repeat + q) as i64,
                                tactic: Json::Null,
                                charge: None,
                                full_scout: true,
                            });
                            let plan = replay::plan(
                                compiler,
                                &entry.value,
                                angle,
                                seed,
                                strength,
                                &attacker,
                            )?;
                            if number(&plan, "town_hall", 0.0) != *attacker_th as f64 {
                                return Err("compiled army TH mismatch".to_owned());
                            }
                            plans.push(plan);
                        }
                    }
                }
                let scorer = Scorer::new(
                    Arc::clone(&catalog),
                    vec![layout.clone()],
                    scenarios.clone(),
                    plans,
                    (0..scenarios.len()).collect(),
                )?;
                let selected = scorer.scout(
                    Arc::clone(&catalog),
                    0,
                    threads,
                    ScoutPolicy::Visible,
                    Some(scout),
                )?;
                planning += selected.planning_battles;
                evaluations += selected.evaluation_battles;
                let jobs: Vec<_> = selected
                    .scenarios
                    .iter()
                    .zip(&selected.source_indices)
                    .map(|(scenario, index)| {
                        let mut options =
                            Job::new(0, *index, scenario.seed, *defender_th as i64, None)
                                .options()
                                .clone();
                        put(&mut options, "layout", num(0.0));
                        put(&mut options, "plan", num(*index as f64));
                        put(&mut options, "record", Json::Bool(true));
                        Job::from_json(&options)
                    })
                    .collect();
                let captured = Mutex::new(vec![None; jobs.len()]);
                let hook = |index: usize, _: &Job, battle: &Battle, result: &BattleResult| {
                    let scenario = &selected.scenarios[index];
                    let value =
                        battle_row(battle, result, base, scenario, &entry.value, *defender_th);
                    if let Ok(mut slots) = captured.lock() {
                        slots[index] = Some(value);
                    }
                };
                let actual = scorer
                    .runner
                    .run_with_summary(&jobs, threads, Some(&hook))
                    .map_err(|e| format!("tempo diagnostic replay: {e:?}"))?;
                diagnostics += actual.len();
                let captured = captured
                    .into_inner()
                    .map_err(|_| "tempo summary mutex poisoned")?;
                for ((value, actual), expected) in
                    captured.into_iter().zip(actual).zip(&selected.outcomes)
                {
                    if actual.stars as i64 != expected.stars
                        || actual.destruction as f64 != expected.destruction
                        || actual.time.to_bits() != expected.time.to_bits()
                    {
                        return Err("recording changed native scout outcome".to_owned());
                    }
                    let (row, mut json) = value.ok_or("missing tempo diagnostic")??;
                    put(&mut json, "attack", num((rows.len() + 1) as f64));
                    rows.push(row);
                    json_rows.push(json);
                }
                design.push(obj([
                    ("attacker_th", num(*attacker_th as f64)),
                    ("defender_th", num(*defender_th as f64)),
                    ("army_id", string(&army_id)),
                    ("base", string(base)),
                    ("strength", num(strength)),
                    (
                        "selected_scenarios",
                        arr(selected.scenarios.iter().map(Scenario::to_json)),
                    ),
                ]));
                eprintln!("tempo TH{attacker_th}->TH{defender_th} {base} {}: {} selected; total battles {}", entry.id, selected.scenarios.len(), planning + evaluations + diagnostics);
            }
        }
    }
    let mut comparisons = Vec::new();
    for attacker_th in armies.keys() {
        let video_group: Vec<_> = videos
            .iter()
            .filter(|r| r.attacker_th == Some(*attacker_th))
            .cloned()
            .collect();
        for defender_th in bases.keys() {
            if defender_th < attacker_th {
                continue;
            }
            let sim: Vec<_> = rows
                .iter()
                .filter(|r| {
                    r.attacker_th == Some(*attacker_th) && r.defender_th == Some(*defender_th)
                })
                .cloned()
                .collect();
            comparisons.push(obj([
                ("attacker_th", num(*attacker_th as f64)),
                ("defender_th", num(*defender_th as f64)),
                ("sim", summary(&sim)),
                ("video_same_attacker_estimate", summary(&video_group)),
                ("video_all", summary(&videos)),
                (
                    "differences_vs_same_attacker_estimate",
                    differences(&sim, &video_group),
                ),
                ("differences_vs_all_video", differences(&sim, &videos)),
            ]));
        }
    }
    let changed = inputs
        != provenance::fingerprint(
            &args.root,
            &sources.iter().map(|p| p.as_path()).collect::<Vec<_>>(),
        )?;
    if changed {
        return Err("tempo inputs changed during run".to_owned());
    }
    Ok(obj([
        ("schema", string(metrics::SCHEMA)), ("engine", string("rust-v29")),
        ("video", video), ("video_sha256", string(file_hash(&video_path)?)),
        ("inputs", inputs), ("inputs_changed_during_run", Json::Bool(false)),
        ("calibration_sha256", string(file_hash(&calibration)?)),
        ("attacker", string("playbook")), ("scout_policy", string("visible")),
        ("angles", num(angles as f64)), ("replicates", num(repeats as f64)),
        ("skill_quantiles", num(5.0)), ("scout", num(scout as f64)),
        ("full_scout", Json::Bool(true)),
        ("planning_battles", num(planning as f64)), ("evaluation_battles", num(evaluations as f64)),
        ("diagnostic_replays", num(diagnostics as f64)), ("total_battles", num((planning + evaluations + diagnostics) as f64)),
        ("design", string("balanced cyclic incomplete crossing within each attacker/defender TH cell with defender TH >= attacker TH: max(armies,bases) pairs; every meta build and base appears; equal selected-row weights, not measured video army prevalence; every replicate contains all five skill quantiles; visible hidden ensemble chooses among all candidate sides, followed by native recorded replay")),
        ("uncertainty", string("unpaired cluster percentile bootstrap, 1000 replicates, deterministic seed; resample whole video IDs and whole reference base IDs; sim minus video; median differences for continuous fields, mean differences for shares; conditional on observed fields and trustworthy finals, not correction for censoring or selection bias; TH best is a minimum-compatible estimate, video defender TH unknown; no matched real/sim attacks")),
        ("unmatched_video_attacker_rows", num(videos.iter().filter(|r| r.attacker_th.is_none_or(|th| !armies.contains_key(&th))).count() as f64)),
        ("sim_aggregate", summary(&rows)), ("comparisons", arr(comparisons)),
        ("pairings", arr(design)), ("sim_rows", arr(json_rows)),
    ]))
}
