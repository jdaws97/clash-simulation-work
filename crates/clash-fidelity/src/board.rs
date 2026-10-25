//! Check A, honest CV, frozen-reference comparisons and determinism proofs.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_plans::compile::Compiler;
use clash_scoring::scoring::{self, MetaOptions, ScoringData};

use super::history::{self, Observation};
use super::io::*;
use super::metrics::{self, Distribution};
use super::replay::{self, ReplayRow};
use super::{fit, observed, provenance, read_observations, Arguments};

fn training_baseline(
    args: &Arguments,
    rows: &[Observation],
    ids: &Option<BTreeSet<String>>,
) -> Result<Option<Distribution>, String> {
    let training = if let Some(path) = args.optional_path("--train-log") {
        history::observations(
            &args.root,
            &path,
            &args.path("--history", "data/live/base-history.json"),
            true,
            None,
        )?
        .0
    } else if let Some(ids) = ids {
        rows.iter()
            .filter(|row| ids.contains(&row.id))
            .cloned()
            .collect()
    } else {
        Vec::new()
    };
    if training.is_empty() {
        return Ok(None);
    }
    Ok(Some(Distribution::observations(&training)))
}

pub fn check_a(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let settings = args.settings(false)?;
    let (observations, skipped) = read_observations(args, false)?;
    let selected = args.calibration();
    let binding = provenance::binding(
        &args.root,
        &selected,
        args.optional_path("--calibration-report").as_deref(),
    )?;
    let strength = replay::strengths(&args.root, &selected)?;
    let baseline = training_baseline(args, &observations, &binding.ids)?;
    let rows = replay::run(compiler, catalog, &observations, &strength, &settings)?;
    let (inside, outside): (Vec<_>, Vec<_>) = rows.iter().cloned().partition(|row| {
        binding
            .ids
            .as_ref()
            .is_none_or(|ids| ids.contains(&row.observation.id))
    });
    if args.flag("--exclude-fitted") && binding.ids.is_none() {
        return Err(
            "cannot establish held-out defenses: calibration report hash or ancestry is unbound"
                .to_owned(),
        );
    }
    let scored = if args.flag("--exclude-fitted") {
        &outside
    } else {
        &rows
    };
    let mut out = metrics::defense_metrics(scored, baseline.as_ref());
    for (key, value) in binding.info.obj() {
        put(&mut out, key, value.clone());
    }
    for (key, value) in [
        ("engine", string("rust")),
        ("attacker", string(&settings.attacker)),
        (
            "scout_policy",
            string(if settings.legacy {
                "legacy oracle"
            } else {
                settings.policy.name()
            }),
        ),
        ("skipped", count_map(&skipped)),
        (
            "excluded_unknown",
            num(skipped
                .iter()
                .filter(|(key, _)| key.contains("army") || key.contains("share"))
                .map(|(_, value)| value)
                .sum::<usize>() as f64),
        ),
        (
            "fitted_defenses",
            num(if args.flag("--exclude-fitted") {
                0
            } else {
                inside.len()
            } as f64),
        ),
        (
            "excluded_fitted",
            num(if args.flag("--exclude-fitted") {
                inside.len()
            } else {
                0
            } as f64),
        ),
        (
            "in_sample",
            metrics::defense_metrics(
                if args.flag("--exclude-fitted") {
                    &[]
                } else {
                    &inside
                },
                baseline.as_ref(),
            ),
        ),
        (
            "out_of_sample",
            metrics::defense_metrics(&outside, baseline.as_ref()),
        ),
        (
            "baseline_status",
            string(if baseline.is_some() {
                "estimated from training observations only; score on held-out rows for a fair comparison"
            } else {
                "unavailable: supply --train-log or use cv; held-out outcomes are never used to fit a baseline"
            }),
        ),
        ("rows", arr(scored.iter().map(ReplayRow::to_json))),
    ] {
        put(&mut out, key, value);
    }
    Ok(out)
}

fn pool_fold_metrics(folds: &[Json]) -> Json {
    let keys = [
        "real_3star",
        "sim_3star",
        "brier",
        "destruction_mae",
        "time_to_3star_ratio",
        "joint_log_score",
        "joint_cdf_score",
        "star_rps",
        "constant_predictor_brier",
        "constant_destruction_mae",
        "constant_joint_log_score",
        "constant_joint_cdf_score",
        "constant_star_rps",
    ];
    let total: f64 = folds
        .iter()
        .map(|fold| number(fold.at("metrics"), "defenses", 0.0))
        .sum();
    let mut out = obj([("held_out_defenses", num(total))]);
    for key in keys {
        let mut weight = 0.0;
        let mut sum = 0.0;
        for fold in folds {
            let metrics = fold.at("metrics");
            if let Some(Json::Num(value)) = metrics.get(key) {
                let n = number(metrics, "defenses", 0.0);
                weight += n;
                sum += value * n;
            }
        }
        put(
            &mut out,
            key,
            if weight > 0.0 {
                num(sum / weight)
            } else {
                Json::Null
            },
        );
    }
    out
}

pub fn cv(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let (observations, skipped) = read_observations(args, true)?;
    let folds_n = args.integer("--folds", 3)?;
    if folds_n < 2 || observations.len() < folds_n {
        return Err("CV needs at least two nonempty folds".to_owned());
    }
    let settings = args.settings(false)?;
    let mut fit_settings = args.settings(true)?;
    // Fitting uses a fixed sampling budget independent of evaluation settings.
    fit_settings.angles = 4;
    fit_settings.seeds = 1;
    let options = args.fit_options()?;
    let directory = args.path("--fold-dir", "output/fidelity-rust/cv");
    std::fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    let prior = args.root.join("data/meta-calibration-r8.json");
    if file_hash(&prior)? != provenance::R8_SHA256 {
        return Err("r8 prior hash differs from frozen public prior".to_owned());
    }
    let mut folds = Vec::new();
    let mut held_out = BTreeSet::new();
    let mut pooled_rows = Vec::new();
    for fold in 0..folds_n {
        let (training, test) = {
            // Stable IDs, not outcome-stratified folds: no outcome enters assignment.
            let mut sorted = observations.clone();
            sorted.sort_by(|left, right| left.id.cmp(&right.id));
            let mut training = Vec::new();
            let mut test = Vec::new();
            for (index, row) in sorted.into_iter().enumerate() {
                if index % folds_n == fold {
                    test.push(row);
                } else {
                    training.push(row);
                }
            }
            (training, test)
        };
        if test.is_empty() || training.is_empty() {
            return Err(format!("empty CV fold {fold}"));
        }
        let path = directory.join(format!("{}-{fold}.json", settings.attacker));
        let report_path = directory.join(format!("{}-{fold}-report.json", settings.attacker));
        let binding = {
            let train_path = directory.join(format!("train-{fold}-ids.json"));
            write(
                &train_path,
                &arr(training.iter().map(|row| string(&row.id))),
            )?;
            fit::calibrate(
                &args.root,
                compiler,
                Arc::clone(&catalog),
                &training,
                &skipped,
                &fit_settings,
                &options,
                &prior,
                None,
                &args.path("--log", "data/live/battles.jsonl"),
                &args.path("--history", "data/live/base-history.json"),
                &path,
                &report_path,
            )?;
            let binding = provenance::binding(&args.root, &path, Some(&report_path))?;
            let ids = binding
                .ids
                .as_ref()
                .ok_or("new CV calibration did not bind to its report")?;
            if test.iter().any(|row| ids.contains(&row.id)) {
                return Err("CV test row occurs in calibration ancestry".to_owned());
            }
            binding.info
        };
        for row in &test {
            if !held_out.insert(row.id.clone()) {
                return Err("overlapping CV test folds".to_owned());
            }
        }
        let strength = replay::strengths(&args.root, &path)?;
        let mut rows = replay::run(compiler, Arc::clone(&catalog), &test, &strength, &settings)?;
        let metrics = metrics::defense_metrics(&rows, Some(&Distribution::observations(&training)));
        eprintln!(
            "fold {fold}: train={} test={} Brier={:.4}",
            training.len(),
            test.len(),
            number(&metrics, "brier", 0.0)
        );
        folds.push(obj([
            ("fold", num(fold as f64)),
            ("train_n", num(training.len() as f64)),
            ("train_ids", arr(training.iter().map(|row| string(&row.id)))),
            ("test_ids", arr(test.iter().map(|row| string(&row.id)))),
            ("binding", binding),
            ("metrics", metrics),
            ("rows", arr(rows.iter().map(ReplayRow::to_json))),
        ]));
        pooled_rows.append(&mut rows);
    }
    if held_out.len() != observations.len() {
        return Err("CV did not cover each observation exactly once".to_owned());
    }
    let mut out = obj([
        ("engine", string("rust")),
        ("attacker", string(&settings.attacker)),
        (
            "scout_policy",
            string(if settings.legacy {
                "legacy oracle"
            } else {
                settings.policy.name()
            }),
        ),
        (
            "validation_status",
            string("cross-validation; r8 prior; verified disjoint hash-bound ancestry"),
        ),
        ("pooled", pool_fold_metrics(&folds)),
        (
            "pooled_duration_and_end_reasons",
            metrics::defense_metrics(&pooled_rows, None),
        ),
        ("folds", arr(folds)),
        ("skipped", count_map(&skipped)),
    ]);
    if let Some(path) = args.optional_path("--reference") {
        let frozen = read(&path)?;
        let frozen = frozen.get("pooled").unwrap_or(&frozen).clone();
        let delta = compare_saved_metrics(out.at("pooled"), &frozen)?;
        put(&mut out, "saved_reference", frozen);
        put(&mut out, "difference_from_reference", delta);
        put(&mut out, "reference_sha256", string(file_hash(&path)?));
    }
    Ok(out)
}

fn compare_saved_metrics(current: &Json, saved: &Json) -> Result<Json, String> {
    let mut differences = Vec::new();
    for key in [
        "sim_3star",
        "brier",
        "destruction_mae",
        "time_to_3star_ratio",
    ] {
        let difference = match (current.get(key), saved.get(key)) {
            (Some(Json::Num(current)), Some(Json::Num(saved)))
                if current.is_finite() && saved.is_finite() =>
            {
                num(current - saved)
            }
            (Some(Json::Null), Some(Json::Num(_) | Json::Null))
            | (Some(Json::Num(_)), Some(Json::Null)) => Json::Null,
            _ => return Err(format!("missing or invalid saved comparison metric {key}")),
        };
        differences.push((key, difference));
    }
    Ok(obj(differences))
}

pub fn proof(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let (observations, _) = read_observations(args, false)?;
    let strength = replay::strengths(&args.root, &args.calibration())?;
    let mut settings = args.settings(false)?;
    settings.threads = 1;
    let reference = replay::run(
        compiler,
        Arc::clone(&catalog),
        &observations,
        &strength,
        &settings,
    )?;
    let bytes = encode(&arr(reference.iter().map(ReplayRow::to_json)));
    let mut runs = vec![obj([
        ("threads", num(1.0)),
        ("rows_sha256", string(sha256(bytes.as_bytes()))),
        ("identical", Json::Bool(true)),
    ])];
    for threads in [4, 16] {
        settings.threads = threads;
        let rows = replay::run(
            compiler,
            Arc::clone(&catalog),
            &observations,
            &strength,
            &settings,
        )?;
        let actual = encode(&arr(rows.iter().map(ReplayRow::to_json)));
        let equal = bytes == actual;
        runs.push(obj([
            ("threads", num(threads as f64)),
            ("rows_sha256", string(sha256(actual.as_bytes()))),
            ("identical", Json::Bool(equal)),
        ]));
        if !equal {
            return Err(format!("thread determinism failed at {threads} workers"));
        }
    }
    Ok(obj([
        ("engine", string("rust")),
        ("defenses", num(observations.len() as f64)),
        ("seeds", num(settings.seeds as f64)),
        ("angles", num(settings.angles as f64)),
        (
            "scout_policy",
            string(if settings.legacy {
                "legacy oracle"
            } else {
                settings.policy.name()
            }),
        ),
        ("runs", arr(runs)),
        ("metrics", metrics::defense_metrics(&reference, None)),
        (
            "inputs",
            provenance::fingerprint(&args.root, &[&args.calibration()])?,
        ),
    ]))
}

pub fn board(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let mut out = obj([
        ("engine", string("rust")),
        (
            "label",
            string(args.value("--label", "native fidelity board")),
        ),
    ]);
    let only = args.value("--only", "ABCD");
    if only.contains('A') {
        put(
            &mut out,
            "A_real_defenses",
            check_a(args, compiler, Arc::clone(&catalog))?,
        );
    }
    if only.contains('B') {
        put(
            &mut out,
            "B_observed_replays",
            observed::all(args, compiler, Arc::clone(&catalog))?,
        );
    }
    if only.contains('C') {
        put(
            &mut out,
            "C_th_order",
            check_c(args, compiler, Arc::clone(&catalog))?,
        );
    }
    if only.contains('D') {
        put(
            &mut out,
            "D_exposed_eagle",
            check_d(args, compiler, catalog)?,
        );
    }
    Ok(out)
}

fn check_c(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let data = ScoringData::load(&args.root)?;
    let strength = replay::strengths(&args.root, &args.calibration())?;
    let layout = observed::layout(args, &args.root.join("data/reference-bases/your-base.json"))?;
    let settings = args.settings(false)?;
    let mut rates = obj([] as [(&str, Json); 0]);
    for th in [16, 17] {
        let options_json = obj([
            ("mode", string("ranked")),
            (
                "n_angles",
                num(if args.flag("--quick") { 4.0 } else { 8.0 }),
            ),
            ("seeds", arr([num(7.0)])),
            ("th_mix", obj([(th.to_string(), num(1.0))])),
            ("playbooks", Json::Bool(settings.attacker == "playbook")),
        ]);
        let options = MetaOptions::from_json(&options_json)?;
        let scenarios = scoring::meta_scenarios(&data, &options)?.scenarios;
        let mut by_family = BTreeMap::<String, Vec<scoring::Scenario>>::new();
        for scenario in scenarios {
            let build = compiler.library.build_by_id(&scenario.army)?;
            let family = clash_plans::armies::family_of(build).unwrap_or("unclassified");
            by_family
                .entry(family.to_owned())
                .or_default()
                .push(scenario);
        }
        let mut family_rates = obj([] as [(&str, Json); 0]);
        for (family, scenarios) in by_family {
            let plans = scenarios
                .iter()
                .map(|scenario| {
                    let build = compiler.library.build_by_id(&scenario.army)?;
                    replay::plan(
                        compiler,
                        build,
                        scenario.angle,
                        scenario.seed,
                        strength.get(&scenario.army),
                        &settings.attacker,
                    )
                })
                .collect::<Result<Vec<_>, String>>()?;
            let samples =
                replay::run_prepared(Arc::clone(&catalog), &layout, &scenarios, plans, &settings)?
                    .0;
            put(
                &mut family_rates,
                &family,
                num(Distribution::samples(&samples).stars[3]),
            );
        }
        put(&mut rates, &format!("th{th}"), family_rates);
    }
    let inversions = arr(rates
        .at("th16")
        .obj()
        .iter()
        .filter(|(family, rate)| {
            rates
                .at("th17")
                .get(family)
                .is_some_and(|other| other.f64() + 0.05 < rate.f64())
        })
        .map(|(family, _)| string(family)));
    put(&mut rates, "inversions", inversions);
    Ok(rates)
}

fn check_d(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let path = args
        .optional_path("--base")
        .ok_or("exposed-eagle check needs an explicit --base FILE")?;
    let layout = read(&path)?;
    let strength = replay::strengths(&args.root, &args.calibration())?;
    let mut opened = 0;
    let mut down = 0;
    let mut total = 0;
    for army in [
        "meta:e-drag-spam-17-5",
        "meta:mass-dragons-17-1",
        "meta:root-rider-17-1",
        "meta:mass-thrower-17-1",
        "meta:root-rider-16-1",
        "meta:mass-dragons-16-1",
    ] {
        let build = compiler.library.build_by_id(army)?;
        for side in 0..if args.flag("--quick") { 2 } else { 4 } {
            let plan = replay::plan(
                compiler,
                build,
                0.3 + side as f64 * std::f64::consts::PI / 2.0,
                11 + side,
                strength.get(army),
                "playbook",
            )?;
            let runner = clash_engine::Runner::new(
                Arc::clone(&catalog),
                clash_engine::PreparedInputs::new(vec![layout.clone()], vec![plan]),
            );
            let mut battle = runner
                .build(&clash_engine::Job::new(0, 0, 11 + side, 16, None))
                .map_err(|error| error.to_string())?;
            let eagle = battle
                .buildings
                .iter()
                .find(|building| building.key == "eagle")
                .ok_or("no exposed eagle")?
                .id;
            if let Some(plan) = battle.plan.attack() {
                opened += usize::from(plan.snipe_log.iter().any(|event| {
                    event
                        .arr()
                        .get(2)
                        .is_some_and(|value| value.f64() == eagle.0 as f64)
                }));
            }
            while battle.t < 30.0 && !battle.ended {
                battle.step();
            }
            down += usize::from(!battle.building(eagle).alive);
            total += 1;
        }
    }
    Ok(obj([
        ("battles", num(total as f64)),
        ("opening_on_eagle", num(opened as f64 / total as f64)),
        ("eagle_down_by_30s", num(down as f64 / total as f64)),
    ]))
}

/// Score an ordered prepared-job export with an explicitly selected historical
/// kernel's output. This keeps the archival proof's aggregation in Rust too.
pub fn score_jobs(args: &Arguments) -> Result<Json, String> {
    if args.positional.len() != 2 {
        return Err("score-jobs PREPARED.json OUTCOMES.jsonl [--train-log FILE]".to_owned());
    }
    let prepared_path = resolve(&args.root, &args.positional[0]);
    let settings = args.settings(false)?;
    let outcomes_path = resolve(&args.root, &args.positional[1]);
    let prepared = read(&prepared_path)?;
    let outcomes = history::battles(&outcomes_path)?;
    let jobs = list(&prepared, "jobs");
    if jobs.len() != outcomes.len() {
        return Err("historical kernel output is incomplete".to_owned());
    }
    let (observations, skipped) = history::observations(
        &args.root,
        &args.path("--log", "data/live/battles.jsonl"),
        &args.path("--history", "data/live/base-history.json"),
        false,
        None,
    )?;
    if observations.len() != list(&prepared, "layouts").len() {
        return Err("prepared layouts do not match the observation set".to_owned());
    }
    let mut rows = Vec::new();
    for (index, observation) in observations.iter().enumerate() {
        if prepared.at("layouts").arr()[index] != observation.layout {
            return Err(format!(
                "prepared layout {index} differs from reconstructed defense"
            ));
        }
        let mut scenarios = Vec::new();
        let mut results = Vec::new();
        let mut raw_reasons = Vec::new();
        let mut reasons = BTreeMap::new();
        let mut actual_attacker = None;
        for (job_index, (job, result)) in jobs.iter().zip(&outcomes).enumerate() {
            if number(result, "job", -1.0) != job_index as f64 {
                return Err("historical kernel results must be indexed in job order".to_owned());
            }
            if number(job, "layout", -1.0) != index as f64 {
                continue;
            }
            let plan = list(&prepared, "plans")
                .get(number(job, "plan", -1.0) as usize)
                .ok_or("historical job has invalid plan index")?;
            let kind = match text(plan, "$type", "") {
                "PlaybookPlan" => "playbook",
                "AttackPlan" => "generic",
                _ => return Err("historical fidelity plan must be generic or playbook".to_owned()),
            };
            if actual_attacker
                .as_ref()
                .is_some_and(|actual| actual != kind)
            {
                return Err("historical observation mixes attacker policies".to_owned());
            }
            actual_attacker = Some(kind.to_owned());
            let seed = number(job, "seed", 0.0) as i64;
            let per_repeat = settings.angles;
            let group = scenarios.len() / per_repeat;
            scenarios.push(scoring::Scenario {
                army: observation.id.clone(),
                town_hall: observation.th,
                angle: number(plan, "angle", 0.0),
                seed,
                weight: 1.0,
                modifier: None,
                group: group as i64,
                tactic: Json::Null,
                charge: None,
                full_scout: false,
            });
            results.push(scoring::Outcome {
                stars: number(result, "stars", -1.0) as i64,
                destruction: number(result, "destruction", -1.0),
                time: number(result, "time", 0.0),
                th_destroyed: result.get("th_destroyed") == Some(&Json::Bool(true)),
            });
            let reason = text(result, "end_reason", "unrecorded").to_owned();
            if reason != "unrecorded" {
                *reasons.entry(reason.clone()).or_default() += 1;
            }
            raw_reasons.push(reason);
        }
        if scenarios.is_empty() {
            return Err("no historical jobs for observation".to_owned());
        }
        let selections = scoring::scouted(&scenarios, &results, Some(settings.scout));
        let total: f64 = selections.iter().map(|selection| selection.weight).sum();
        let samples = selections
            .into_iter()
            .map(|selection| {
                let outcome = results[selection.scenario];
                replay::Sample {
                    stars: outcome.stars,
                    pct: outcome.destruction,
                    time: outcome.time,
                    weight: selection.weight / total,
                    end_reason: raw_reasons[selection.scenario].clone(),
                }
            })
            .collect();
        let actual_attacker = actual_attacker.ok_or("missing historical attacker")?;
        let fallback = if settings.attacker == "playbook" && actual_attacker == "generic" {
            Some(format!("no cited playbook for {}", observation.family))
        } else {
            None
        };
        rows.push(ReplayRow {
            observation: observation.clone(),
            attacker: actual_attacker,
            fallback,
            samples,
            reasons,
            planning: 0,
            evaluations: results.len(),
            diagnostics: 0,
            scenarios,
        });
    }
    let training = if let Some(path) = args.optional_path("--train-log") {
        history::observations(
            &args.root,
            &path,
            &args.path("--history", "data/live/base-history.json"),
            true,
            None,
        )?
        .0
    } else {
        Vec::new()
    };
    let train_ids: BTreeSet<_> = training.iter().map(|row| row.id.clone()).collect();
    if !train_ids.is_empty() {
        rows.retain(|row| !train_ids.contains(&row.observation.id));
    }
    let baseline = (!training.is_empty()).then(|| Distribution::observations(&training));
    let mut report = metrics::defense_metrics(&rows, baseline.as_ref());
    put(&mut report, "validation_status", string("archival kernel comparison; supplied training partition is not a hash-bound calibration ancestry claim"));
    put(
        &mut report,
        "label",
        string(args.value("--label", "explicit historical kernel")),
    );
    put(
        &mut report,
        "prepared_sha256",
        string(file_hash(&prepared_path)?),
    );
    put(
        &mut report,
        "outcomes_sha256",
        string(file_hash(&outcomes_path)?),
    );
    put(&mut report, "skipped", count_map(&skipped));
    put(
        &mut report,
        "rows",
        arr(rows.iter().map(ReplayRow::to_json)),
    );
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saved_metrics_compare_numbers_and_preserve_missing_measurements() {
        let saved = obj([
            ("sim_3star", num(0.25)),
            ("brier", num(0.5)),
            ("destruction_mae", num(10.0)),
            ("time_to_3star_ratio", Json::Null),
        ]);
        let current = obj([
            ("sim_3star", num(0.5)),
            ("brier", num(0.25)),
            ("destruction_mae", num(12.0)),
            ("time_to_3star_ratio", num(1.0)),
        ]);
        assert_eq!(
            compare_saved_metrics(&current, &saved).unwrap(),
            obj([
                ("sim_3star", num(0.25)),
                ("brier", num(-0.25)),
                ("destruction_mae", num(2.0)),
                ("time_to_3star_ratio", Json::Null),
            ])
        );
        let mut incomplete = saved;
        remove(&mut incomplete, "brier");
        assert!(compare_saved_metrics(&current, &incomplete).is_err());
    }
}
