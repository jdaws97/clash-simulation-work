//! Defense distribution calibration with the frozen Python objective and format.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::sync::Arc;

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_plans::compile::Compiler;
use clash_scoring::scoring::{Scenario, Strength};

use super::history::Observation;
use super::io::*;
use super::metrics::{self, Distribution};
use super::provenance;
use super::replay::{self, Settings};

#[derive(Clone)]
pub struct FitOptions {
    pub min_family: usize,
    pub grid: usize,
    pub max_correction: f64,
    pub prior_sd: f64,
    pub quick: bool,
    pub monotonic: bool,
}

impl Default for FitOptions {
    fn default() -> Self {
        Self {
            min_family: 8,
            grid: 9,
            max_correction: 1.5,
            prior_sd: 0.2,
            quick: false,
            monotonic: false,
        }
    }
}

pub fn grouped(rows: &[Observation], minimum: usize) -> BTreeMap<(i64, String), Vec<Observation>> {
    let mut counts = BTreeMap::new();
    for row in rows {
        *counts.entry((row.th, row.family.clone())).or_insert(0) += 1;
    }
    let mut groups = BTreeMap::new();
    for row in rows {
        let family =
            if row.family == "unclassified" || counts[&(row.th, row.family.clone())] < minimum {
                "pooled"
            } else {
                &row.family
            };
        groups
            .entry((row.th, family.to_owned()))
            .or_insert_with(Vec::new)
            .push(row.clone());
    }
    groups
}

fn quantile(values: &[f64], weights: &[f64], q: f64) -> f64 {
    let total: f64 = weights.iter().sum();
    let mut cumulative = 0.0;
    for (value, weight) in values.iter().zip(weights) {
        cumulative += weight;
        if cumulative >= q * total {
            return *value;
        }
    }
    *values.last().expect("nonempty grid")
}

fn fit_group(
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    strength: &Strength,
    rows: &[Observation],
    settings: &Settings,
    options: &FitOptions,
) -> Result<Json, String> {
    let selected = if options.quick { &rows[..1] } else { rows };
    let angles = if options.quick { 2 } else { settings.angles };
    let seeds = if options.quick { 1 } else { settings.seeds };
    let grid = if options.quick { 3 } else { options.grid };
    let corrections: Vec<_> = (0..grid)
        .map(|index| {
            (-options.max_correction.ln()
                + 2.0 * options.max_correction.ln() * index as f64 / (grid - 1) as f64)
                .exp()
        })
        .collect();
    let observed = Distribution::observations(rows);
    let mut candidates = Vec::new();
    for correction in &corrections {
        let mut samples = Vec::new();
        let mut planning = 0;
        let mut evaluations = 0;
        let mut diagnostics = 0;
        for (index, row) in selected.iter().enumerate() {
            let mut scenarios = Vec::new();
            let mut plans = Vec::new();
            let quantiles: Vec<_> = if options.quick {
                vec![2]
            } else {
                (0..5).collect()
            };
            let base =
                replay::current_strength(compiler, strength, row.th, &row.family) * correction;
            for repeat in 0..seeds {
                for q in &quantiles {
                    for side in 0..angles {
                        let seed = 5 * (1000 * index + repeat * angles + side) as i64 + q;
                        let angle = 0.21 + 2.0 * std::f64::consts::PI * side as f64 / angles as f64;
                        scenarios.push(Scenario {
                            army: format!("observed:{index}"),
                            town_hall: row.th,
                            angle,
                            seed,
                            group: 5 * repeat as i64 + q,
                            modifier: row.modifier.clone(),
                            weight: 1.0 / (seeds * quantiles.len() * angles) as f64,
                            tactic: Json::Null,
                            charge: None,
                            full_scout: false,
                        });
                        plans.push(replay::plan(
                            compiler,
                            &row.build,
                            angle,
                            seed,
                            base,
                            &settings.attacker,
                        )?);
                    }
                }
            }
            let (mut result, _, p, e, d, _) = replay::run_prepared(
                Arc::clone(&catalog),
                &row.layout,
                &scenarios,
                plans,
                settings,
            )?;
            for sample in &mut result {
                sample.weight /= selected.len() as f64;
            }
            samples.extend(result);
            planning += p;
            evaluations += e;
            diagnostics += d;
        }
        let simulated = Distribution::samples(&samples);
        let loss = metrics::loss(
            &observed,
            &simulated,
            selected.len(),
            *correction,
            options.prior_sd,
        );
        eprintln!(
            "  correction {correction:.4}: loss {:.4}",
            number(&loss, "total", 0.0)
        );
        candidates.push(obj([
            ("correction", num(*correction)),
            ("loss", loss),
            ("simulated", simulated.to_json()),
            ("planning_battles", num(planning as f64)),
            ("evaluation_battles", num(evaluations as f64)),
            ("diagnostic_replays", num(diagnostics as f64)),
        ]));
    }
    let best = candidates
        .iter()
        .enumerate()
        .min_by(|(_, left), (_, right)| {
            number(left.at("loss"), "total", 0.0)
                .total_cmp(&number(right.at("loss"), "total", 0.0))
                .then_with(|| {
                    number(left, "correction", 1.0)
                        .ln()
                        .abs()
                        .total_cmp(&number(right, "correction", 1.0).ln().abs())
                })
        })
        .map(|(index, _)| index)
        .expect("nonempty fit grid");
    let weights: Vec<_> = candidates
        .iter()
        .map(|candidate| {
            (number(candidates[best].at("loss"), "total", 0.0)
                - number(candidate.at("loss"), "total", 0.0))
            .exp()
        })
        .collect();
    let interval = arr([
        num(quantile(&corrections, &weights, 0.025)),
        num(quantile(&corrections, &weights, 0.975)),
    ]);
    let mut family_counts = BTreeMap::new();
    for row in rows {
        *family_counts.entry(row.family.clone()).or_default() += 1;
    }
    let paths: BTreeSet<_> = rows.iter().map(|row| row.layout_path.clone()).collect();
    let layouts = arr(paths.into_iter().map(|path| {
        let matching: Vec<_> = rows.iter().filter(|row| row.layout_path == path).collect();
        obj([
            ("path", string(&path)),
            ("sha256", string(&matching[0].layout_hash)),
            ("n", num(matching.len() as f64)),
            (
                "confidence",
                arr(matching.iter().map(|row| string(&row.setup_source))),
            ),
        ])
    }));
    Ok(obj([
        ("n", num(rows.len() as f64)),
        ("simulated_armies", num(selected.len() as f64)),
        ("fit_effective_n", num(selected.len() as f64)),
        ("family_counts", count_map(&family_counts)),
        ("observed", observed.to_json()),
        ("baseline", candidates[grid / 2].at("simulated").clone()),
        ("fitted", candidates[best].at("simulated").clone()),
        ("correction", candidates[best].at("correction").clone()),
        ("correction_interval_95", interval),
        ("grid_boundary", Json::Bool(best == 0 || best + 1 == grid)),
        ("uncertainty", string("approximate discrete generalized posterior on tested log grid; conditional on engine, layouts and prior")),
        ("star_probability_se_upper_bound", num(0.5 / (rows.len() as f64).sqrt())),
        ("destruction_cdf_dkw_95_half_width", num((40_f64.ln() / (2 * rows.len()) as f64).sqrt().min(1.0))),
        ("constraint", string(if rows.len() < 40 {
            "weak: fewer than 40 real defenses"
        } else {
            "conditional on model and historical layout accuracy"
        })),
        ("grid", arr(candidates)),
        ("layouts", layouts),
    ]))
}

fn cap_monotonic(calibration: &mut Json) {
    let mut families = BTreeMap::<String, BTreeMap<i64, Vec<String>>>::new();
    for (key, value) in calibration.obj() {
        if value.get("strength").is_none() {
            continue;
        }
        let parts: Vec<_> = key.rsplitn(3, '-').collect();
        if parts.len() == 3 {
            if let Ok(th) = parts[1].parse::<i64>() {
                families
                    .entry(parts[2].to_owned())
                    .or_default()
                    .entry(th)
                    .or_default()
                    .push(key.clone());
            }
        }
    }
    for levels in families.values() {
        let Some(th17) = levels.get(&17) else {
            continue;
        };
        let lo = th17
            .iter()
            .map(|key| number(calibration.at(key), "strength", 1.0))
            .fold(f64::INFINITY, f64::min);
        let hi = th17
            .iter()
            .map(|key| number(calibration.at(key), "strength", 1.0))
            .fold(f64::NEG_INFINITY, f64::max);
        for (th, cap) in [(16, lo), (18, hi)] {
            for key in levels.get(&th).into_iter().flatten() {
                let old = number(calibration.at(key), "strength", 1.0);
                if th == 16 && old > cap || th == 18 && old < cap {
                    let mut entry = calibration.at(key).clone();
                    put(&mut entry, "capped_from", num(old));
                    put(&mut entry, "strength", num(cap));
                    put(calibration, key, entry);
                }
            }
        }
    }
}

pub fn calibrate(
    root: &Path,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    rows: &[Observation],
    skipped: &BTreeMap<String, usize>,
    settings: &Settings,
    options: &FitOptions,
    prior: &Path,
    prior_report: Option<&Path>,
    log: &Path,
    history: &Path,
    out: &Path,
    report_path: &Path,
) -> Result<Json, String> {
    if rows.is_empty() {
        return Err("no usable ranked defenses".to_owned());
    }
    let strength = replay::strengths(root, prior)?;
    let ancestry = arr([provenance::prior_snapshot(root, prior, prior_report)?]);
    let extras = [prior, log, history];
    let inputs = provenance::fingerprint(root, &extras)?;
    let ids: BTreeSet<_> = rows.iter().map(|row| row.id.clone()).collect();
    let python_ids = format!(
        "[{}]",
        ids.iter()
            .map(|id| ascii_string(id))
            .collect::<Vec<_>>()
            .join(", ")
    );
    let provenance = obj([
        ("engine", string("rust")),
        ("calibration_report", string(report_path.to_string_lossy())),
        ("battle_ids_sha256", string(sha256(python_ids.as_bytes()))),
        ("prior_calibration_sha256", string(file_hash(prior)?)),
        ("source_hashes", inputs.clone()),
    ]);
    let groups = grouped(rows, options.min_family);
    let mut fits = BTreeMap::new();
    for ((th, family), group) in &groups {
        eprintln!(
            "TH{th} {family}: n={}{}",
            group.len(),
            if options.quick { " QUICK DRY RUN" } else { "" }
        );
        fits.insert(
            (*th, family.clone()),
            fit_group(
                compiler,
                Arc::clone(&catalog),
                &strength,
                group,
                settings,
                options,
            )?,
        );
    }
    let mut calibration = obj([] as [(&str, Json); 0]);
    for build in compiler
        .library
        .builds
        .iter()
        .filter(|build| !build.id.starts_with("custom:"))
    {
        let family = clash_plans::armies::family_of(&build.value).unwrap_or("unclassified");
        let th = number(&build.value, "th", 16.0) as i64;
        let key = if fits.contains_key(&(th, family.to_owned())) {
            (th, family.to_owned())
        } else {
            (th, "pooled".to_owned())
        };
        let fitted = fits.get(&key);
        let correction = fitted.map_or(1.0, |fit| number(fit, "correction", 1.0));
        let n = fitted.map_or(0.0, |fit| number(fit, "n", 0.0));
        let family_n = fitted.map_or(0.0, |fit| number(fit.at("family_counts"), family, 0.0));
        let prior_strength = strength.get(&format!("meta:{}", build.id));
        put(
            &mut calibration,
            &build.id,
            obj([
                ("strength", num(prior_strength * correction)),
                ("real", num(number(&build.value, "three_star", 0.0))),
                (
                    "real_source",
                    string("TrophyCoach same-TH rate; not the defense fit target"),
                ),
                ("prior_strength", num(prior_strength)),
                ("correction", num(correction)),
                (
                    "defense_group",
                    fitted.map_or(Json::Null, |_| string(format!("TH{}:{}", key.0, key.1))),
                ),
                ("n", num(n)),
                ("family_n", num(family_n)),
                (
                    "uncalibrated",
                    Json::Bool(options.quick || fitted.is_none() || family_n == 0.0),
                ),
                ("weakly_constrained", Json::Bool(n < 40.0)),
                ("dry_run", Json::Bool(options.quick)),
                ("provenance", provenance.clone()),
            ]),
        );
    }
    for ((th, family), fit) in &fits {
        put(
            &mut calibration,
            &format!("defense-th{th}-{family}"),
            obj([
                ("strength", fit.at("correction").clone()),
                (
                    "strength_kind",
                    string("correction to each family's current strength"),
                ),
                ("n", fit.at("n").clone()),
                (
                    "correction_interval_95",
                    fit.at("correction_interval_95").clone(),
                ),
                ("uncalibrated", Json::Bool(options.quick)),
                ("dry_run", Json::Bool(options.quick)),
                ("provenance", provenance.clone()),
            ]),
        );
    }
    if options.monotonic {
        cap_monotonic(&mut calibration);
    }
    let final_inputs = provenance::fingerprint(root, &extras)?;
    let changed = inputs != final_inputs
        || rows.iter().any(|row| {
            file_hash(&resolve(root, &row.layout_path)).ok().as_deref() != Some(&row.layout_hash)
        });
    let Json::Obj(entries) = &mut calibration else {
        unreachable!()
    };
    for (_, entry) in entries {
        put(entry, "inputs_changed_during_run", Json::Bool(changed));
        if changed {
            put(entry, "uncalibrated", Json::Bool(true));
        }
    }
    write(out, &calibration)?;
    let report = obj([
        ("dry_run", Json::Bool(options.quick)),
        (
            "validation_status",
            string("training fit only; requires fresh held-out defenses"),
        ),
        (
            "loss",
            string(concat!(
                "multinomial star NLL (98% simulated + 2% uniform) + ",
                "n * mean squared destruction CDF difference on 0..99% + ",
                "0.5*(log(correction)/prior_sd)^2",
            )),
        ),
        ("prior_sd", num(options.prior_sd)),
        ("min_family", num(options.min_family as f64)),
        ("attacker", string(&settings.attacker)),
        (
            "scouting",
            string(if settings.legacy {
                "legacy oracle completed battles; same seeds as frozen Python fitter"
            } else {
                settings.policy.name()
            }),
        ),
        ("monotonic_cap", Json::Bool(options.monotonic)),
        (
            "attacker_levels",
            string("Town Hall maximum; share codes do not encode researched levels"),
        ),
        ("n", num(rows.len() as f64)),
        ("battle_ids", arr(rows.iter().map(|row| string(&row.id)))),
        ("ancestry", ancestry),
        ("skipped", count_map(skipped)),
        ("inputs", inputs),
        ("provenance", provenance),
        ("final_source_hashes", final_inputs),
        ("inputs_changed_during_run", Json::Bool(changed)),
        ("calibration_sha256", string(file_hash(out)?)),
        ("engine_fallbacks", obj([] as [(&str, Json); 0])),
        (
            "groups",
            obj(fits
                .into_iter()
                .map(|((th, family), fit)| (format!("TH{th}:{family}"), fit))),
        ),
    ]);
    write(report_path, &report)?;
    Ok(report)
}
