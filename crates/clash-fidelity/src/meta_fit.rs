//! Public aggregate-target calibration, independent of defense observations.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_plans::armies::{Build, META_FILE};
use clash_plans::compile::Compiler;
use clash_scoring::scoring::Scenario;
use clash_scoring::scouting::ScoutPolicy;

use super::io::*;
use super::replay::{self, Settings};
use super::Arguments;

const ATTACKER_DESCRIPTION: &str = "playbook; explicit generic fallback if no cited family book";
const PLAN_SEED_DESCRIPTION: &str =
    "5*(1000*base_index + replicate*angles + side) + quantile; sorted base paths";
const SCOUT_SEED_DESCRIPTION: &str = concat!(
    "shared scouting namespaces 1/2/3; army=meta-fit:BUILD:BASE_INDEX; ",
    "group=5*replicate+quantile; independent of strength",
);

struct Base {
    path: PathBuf,
    layout: Json,
}

#[derive(Clone, Copy)]
struct Point {
    strength: f64,
    rate: f64,
}

/// Equal-budget isotonic least squares (pool adjacent violators). Common
/// randomness reduces noise but cannot make targeting/scouting mechanically
/// monotone. Preserve the raw rates and explicitly project the response used
/// for root finding, rather than silently assuming every stronger army wins.
fn monotone_rates(points: &[Point]) -> Vec<f64> {
    let mut blocks: Vec<(f64, usize)> = Vec::new();
    for point in points {
        blocks.push((point.rate, 1));
        while blocks.len() >= 2 {
            let right = blocks[blocks.len() - 1];
            let left = blocks[blocks.len() - 2];
            if left.0 / left.1 as f64 <= right.0 / right.1 as f64 {
                break;
            }
            blocks.pop();
            blocks.pop();
            blocks.push((left.0 + right.0, left.1 + right.1));
        }
    }
    blocks
        .into_iter()
        .flat_map(|(sum, count)| std::iter::repeat_n(sum / count as f64, count))
        .collect()
}

fn bracket(points: &[Point], target: f64) -> (f64, bool) {
    let rates = monotone_rates(points);
    if target < rates[0] {
        return (points[0].strength, true);
    }
    if target > rates[rates.len() - 1] {
        return (points[points.len() - 1].strength, true);
    }
    let upper = rates.partition_point(|rate| *rate < target);
    if upper == 0 {
        return (points[0].strength, false);
    }
    (
        (points[upper - 1].strength * points[upper].strength).sqrt(),
        false,
    )
}

fn closest_point(points: &[Point], target: f64, root: f64, clamped: bool) -> usize {
    if clamped {
        return points
            .iter()
            .position(|point| point.strength == root)
            .expect("bound point");
    }
    points
        .iter()
        .enumerate()
        .min_by(|(_, left), (_, right)| {
            (left.rate - target)
                .abs()
                .total_cmp(&(right.rate - target).abs())
                .then_with(|| {
                    (left.strength / root)
                        .ln()
                        .abs()
                        .total_cmp(&(right.strength / root).ln().abs())
                })
                .then_with(|| left.strength.total_cmp(&right.strength))
        })
        .map(|(index, _)| index)
        .expect("nonempty curve")
}

fn validate_curve_source(
    saved: &Json,
    inputs: &Json,
    fitter: &Fitter<'_, '_>,
    town_hall: i64,
    commit: &str,
) -> Result<(), String> {
    let provenance = saved
        .get("_provenance")
        .filter(|value| matches!(value, Json::Obj(_)))
        .ok_or("curve source lacks provenance")?;
    let source = provenance
        .get("source_hashes")
        .filter(|value| matches!(value, Json::Obj(_)))
        .ok_or("curve source lacks input hashes")?;
    if text(provenance, "fit_status", "") != "not defense-fitted"
        || text(provenance, "engine_commit", "") != commit
        || text(provenance, "public_inputs_sha256", "") != sha256(encode(source).as_bytes())
        || source.obj().len() != inputs.obj().len()
    {
        return Err("curve source has unbound public provenance".to_owned());
    }
    for (path, digest) in inputs.obj() {
        let previous = text(source, path, "");
        if previous.len() != 64 || !previous.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(format!("curve source lacks public input {path}"));
        }
        // Only the fitter and its argument dispatch may change when reselecting
        // recorded measurements. Every executable engine/compiler/scouting and
        // public-data byte must still match. Original hashes remain in ancestry.
        if !matches!(
            path.as_str(),
            "crates/clash-fidelity/src/meta_fit.rs" | "crates/clash-fidelity/src/lib.rs"
        ) && previous != digest.str()
        {
            return Err(format!("curve source input changed: {path}"));
        }
    }
    let settings = provenance
        .get("settings")
        .filter(|value| matches!(value, Json::Obj(_)))
        .ok_or("curve source lacks settings")?;
    for (key, expected) in [
        ("town_hall", town_hall as f64),
        ("angles", fitter.settings.angles as f64),
        ("scout", fitter.settings.angles as f64),
        ("hidden_samples", 3.0),
        ("angle_offset_radians", 0.21),
        ("replicates", fitter.replicates as f64),
        ("iterations", fitter.iterations as f64),
        ("initial_log_grid_points", 5.0),
        ("lower", fitter.lower),
        ("upper", fitter.upper),
        ("pace", fitter.compiler.pace),
    ] {
        if settings.get(key).and_then(Json::opt_f64) != Some(expected) {
            return Err(format!("curve source setting differs: {key}"));
        }
    }
    let quantiles = arr((0..5).map(|q| num(clash_scoring::scoring::skill(q))));
    if text(settings, "scout_policy", "") != "visible"
        || text(settings, "attacker", "") != ATTACKER_DESCRIPTION
        || settings.get("modifier") != Some(&Json::Null)
        || settings.get("gaps_enabled") != Some(&Json::Bool(fitter.compiler.gaps.is_some()))
        || settings.get("skill_quantiles") != Some(&quantiles)
        || text(settings, "plan_seed", "") != PLAN_SEED_DESCRIPTION
        || text(settings, "scout_seed", "") != SCOUT_SEED_DESCRIPTION
    {
        return Err("curve source attacker, hidden-state or seed settings differ".to_owned());
    }
    Ok(())
}

fn base_pool(root: &Path, town_hall: i64) -> Result<Vec<Base>, String> {
    let directory = root.join(match town_hall {
        16 => "data/source/reference-bases/ranked-2026-10-24",
        18 => "data/source/reference-bases/ranked-th18-2026-10-25",
        _ => return Err("meta-fit town hall must be 16 or 18 (18 is sensitivity only)".to_owned()),
    });
    let mut paths = std::fs::read_dir(directory)
        .map_err(|error| error.to_string())?
        .map(|entry| {
            entry
                .map(|entry| entry.path())
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    paths.retain(|path| {
        path.extension()
            .is_some_and(|extension| extension == "json")
    });
    paths.sort();
    let mut bases = Vec::new();
    for path in paths {
        let layout = read(&path)?;
        if number(&layout, "town_hall", 0.0) != town_hall as f64 {
            return Err(format!("wrong town hall in {}", path.display()));
        }
        bases.push(Base { path, layout });
    }
    if bases.is_empty() {
        return Err("empty public base pool".to_owned());
    }
    Ok(bases)
}

/// Deliberately do not call the defense fitter's fingerprint: that includes
/// account/live inputs when enabled. This manifest has a public allowlist.
fn public_inputs(root: &Path, bases: &[Base], catalog: &Path) -> Result<Json, String> {
    fn visit(path: &Path, paths: &mut Vec<PathBuf>) -> Result<(), String> {
        for entry in std::fs::read_dir(path).map_err(|error| error.to_string())? {
            let path = entry.map_err(|error| error.to_string())?.path();
            if path.is_dir() {
                visit(&path, paths)?;
            } else if path.extension().is_some_and(|extension| {
                extension == "rs" || extension == "json" || extension == "toml"
            }) {
                paths.push(path);
            }
        }
        Ok(())
    }
    let mut paths = Vec::new();
    for directory in [
        "crates/clash-engine",
        "crates/clash-data",
        "crates/clash-layout",
        "crates/clash-plans",
        "crates/clash-scoring",
        "data/generated",
        "data/source/playbooks",
    ] {
        visit(&root.join(directory), &mut paths)?;
    }
    for path in [
        "Cargo.toml",
        "Cargo.lock",
        "crates/clash-fidelity/src/meta_fit.rs",
        "crates/clash-fidelity/src/replay.rs",
        "crates/clash-fidelity/src/lib.rs",
        "data/source/meta-armies-2026-10-15.json",
        "data/source/observed-armies.json",
        "data/source/custom-armies.json",
        "data/source/attacker-policy.json",
        "data/source/playbook-gaps.json",
        "data/source/accounts/public-th16.json",
    ] {
        paths.push(root.join(path));
    }
    paths.push(catalog.to_owned());
    paths.extend(bases.iter().map(|base| base.path.clone()));
    paths.sort();
    paths.dedup();
    Ok(obj(paths
        .into_iter()
        .map(|path| {
            let key = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            file_hash(&path).map(|digest| (key, string(digest)))
        })
        .collect::<Result<Vec<_>, _>>()?))
}

struct Fitter<'a, 'b> {
    compiler: &'a Compiler<'b>,
    catalog: Arc<Catalog>,
    bases: &'a [Base],
    settings: Settings,
    replicates: usize,
    iterations: usize,
    lower: f64,
    upper: f64,
}

impl Fitter<'_, '_> {
    fn rate(&self, build: &Build, strength: f64) -> Result<f64, String> {
        let workers = self.settings.threads.min(self.bases.len());
        let threads_per_base = self.settings.threads / workers;
        let results = Mutex::new(vec![None; self.bases.len()]);
        std::thread::scope(|scope| {
            for worker in 0..workers {
                let results = &results;
                scope.spawn(move || {
                    for index in (worker..self.bases.len()).step_by(workers) {
                        let result = self.base_rate(build, strength, index, threads_per_base);
                        results.lock().expect("meta-fit base results")[index] = Some(result);
                    }
                });
            }
        });
        // Preserve sorted-base reduction order regardless of worker scheduling.
        let rates = results.into_inner().expect("meta-fit base results");
        let mut rate = 0.0;
        for result in rates {
            rate += result.expect("base result")? / self.bases.len() as f64;
        }
        eprintln!("{} strength {strength:.6}: 3-star {rate:.4}", build.id);
        Ok(rate)
    }

    fn base_rate(
        &self,
        build: &Build,
        strength: f64,
        index: usize,
        threads: usize,
    ) -> Result<f64, String> {
        let base = &self.bases[index];
        let mut settings = self.settings.clone();
        settings.threads = threads;
        let family = clash_plans::armies::family_of(&build.value).unwrap_or("unclassified");
        let (attacker, _) = replay::attacker(self.compiler, family, "playbook");
        let mut scenarios = Vec::new();
        let mut plans = Vec::new();
        for repeat in 0..self.replicates {
            for quantile in 0..5 {
                for side in 0..self.settings.angles {
                    // Fixed across strengths; every side in a group shares
                    // a skill quantile. Scouting's hidden/planning/execution
                    // seed namespaces also exclude strength.
                    let seed = (5 * (1000 * index + repeat * self.settings.angles + side)
                        + quantile) as i64;
                    let angle = 0.21
                        + 2.0 * std::f64::consts::PI * side as f64 / self.settings.angles as f64;
                    scenarios.push(Scenario {
                        army: format!("meta-fit:{}:{index}", build.id),
                        town_hall: number(&build.value, "th", 16.0) as i64,
                        angle,
                        seed,
                        weight: 1.0 / (self.replicates * 5 * self.settings.angles) as f64,
                        modifier: None,
                        group: (5 * repeat + quantile) as i64,
                        tactic: Json::Null,
                        charge: None,
                        full_scout: true,
                    });
                    plans.push(replay::plan(
                        self.compiler,
                        &build.value,
                        angle,
                        seed,
                        strength,
                        &attacker,
                    )?);
                }
            }
        }
        let (samples, ..) = replay::run_prepared(
            Arc::clone(&self.catalog),
            &base.layout,
            &scenarios,
            plans,
            &settings,
        )?;
        Ok(samples
            .iter()
            .filter(|sample| sample.stars == 3)
            .map(|sample| sample.weight)
            .sum::<f64>())
    }

    fn fit(&self, build: &Build, cached: Option<&Json>) -> Result<Json, String> {
        let target = number(&build.value, "three_star", -1.0);
        if cached.is_some_and(|row| row.get("real").and_then(Json::opt_f64) != Some(target)) {
            return Err(format!("curve source target differs: {}", build.id));
        }
        let rate = |strength| {
            let Some(cached) = cached else {
                return self.rate(build, strength);
            };
            let point = list(cached, "curve")
                .iter()
                .find(|point| point.get("strength").and_then(Json::opt_f64) == Some(strength))
                .ok_or_else(|| format!("curve source lacks {} strength {strength}", build.id))?;
            let value = point.get("sim").and_then(Json::opt_f64).unwrap_or(f64::NAN);
            if !value.is_finite() || !(0.0..=1.0 + 1e-12).contains(&value) {
                return Err("invalid cached simulated rate".to_owned());
            }
            Ok(value)
        };
        let mut points = Vec::new();
        // A coarse log grid exposes reversals before adaptive root refinement.
        for index in 0..5 {
            let strength = self.lower * (self.upper / self.lower).powf(index as f64 / 4.0);
            points.push(Point {
                strength,
                rate: rate(strength)?,
            });
        }
        for _ in 0..self.iterations {
            let (strength, clamped) = bracket(&points, target);
            if clamped || points.iter().any(|point| point.strength == strength) {
                break;
            }
            points.push(Point {
                strength,
                rate: rate(strength)?,
            });
            points.sort_by(|left, right| left.strength.total_cmp(&right.strength));
        }
        let (root_strength, clamped) = bracket(&points, target);
        if !points.iter().any(|point| point.strength == root_strength) {
            points.push(Point {
                strength: root_strength,
                rate: rate(root_strength)?,
            });
            points.sort_by(|left, right| left.strength.total_cmp(&right.strength));
        }
        let monotone = monotone_rates(&points);
        let index = closest_point(&points, target, root_strength, clamped);
        let strength = points[index].strength;
        let sim = points[index].rate;
        let reversals = points
            .windows(2)
            .filter(|pair| pair[0].rate > pair[1].rate + 1e-12)
            .count();
        let family = clash_plans::armies::family_of(&build.value).unwrap_or("unclassified");
        let (attacker, fallback) = replay::attacker(self.compiler, family, "playbook");
        Ok(obj([
            ("strength", num(strength)),
            ("root_strength", num(root_strength)),
            ("real", num(target)),
            ("sim", num(sim)),
            ("sim_monotone", num(monotone[index])),
            ("target_error", num(sim - target)),
            ("clamped", Json::Bool(clamped)),
            (
                "clamp_bound",
                if clamped {
                    string(if strength == points[0].strength {
                        "lower"
                    } else {
                        "upper"
                    })
                } else {
                    Json::Null
                },
            ),
            ("raw_curve_reversals", num(reversals as f64)),
            ("attacker", string(attacker)),
            ("attacker_fallback", fallback.map_or(Json::Null, string)),
            ("fit_status", string("not defense-fitted")),
            (
                "curve",
                arr(points.iter().zip(monotone).map(|(point, fitted)| {
                    obj([
                        ("strength", num(point.strength)),
                        ("sim", num(point.rate)),
                        ("monotone", num(fitted)),
                    ])
                })),
            ),
        ]))
    }
}

fn borrow(build: &Build, fitted: &BTreeMap<String, Vec<f64>>) -> Json {
    let values = fitted.get(text(&build.value, "archetype", ""));
    let strength = values.map_or(1.0, |values| {
        values.iter().sum::<f64>() / values.len() as f64
    });
    obj([
        ("strength", num(strength)),
        ("real", num(number(&build.value, "three_star", 0.0))),
        ("uncalibrated", Json::Bool(true)),
        (
            "borrowed_from",
            string(if values.is_some() {
                "arithmetic mean of same-archetype TH16 builds"
            } else {
                "neutral 1.0; no TH16 archetype"
            }),
        ),
        ("fit_status", string("not defense-fitted")),
    ])
}

pub fn command(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    catalog_path: &Path,
) -> Result<Json, String> {
    if std::env::var_os("BASELAB_PARAMS_FILE").is_some()
        || std::env::var("BASELAB_FLYER_RANGE").is_ok_and(|value| value != "gamedata")
    {
        return Err(
            "meta-fit requires default engine parameters and gamedata flyer range".to_owned(),
        );
    }
    let town_hall = args.integer("--town-hall", 16)? as i64;
    let bases = base_pool(&args.root, town_hall)?;
    let replicates = args.integer("--replicates", 2)?;
    let iterations = args.integer("--iterations", 6)?;
    let lower = args.float("--lower", 0.4)?;
    let upper = args.float("--upper", 2.5)?;
    let mut settings = args.settings(false)?;
    settings.attacker = "playbook".to_owned();
    settings.seeds = replicates * 5;
    if replicates == 0 || iterations > 20 || lower <= 0.0 || upper <= lower {
        return Err("require replicates >0, iterations <=20, 0 < lower < upper".to_owned());
    }
    if settings.policy != ScoutPolicy::Visible
        || settings.scout != settings.angles
        || settings.legacy
        || settings.raw
        || settings.techniques
        || args.values.contains_key("--seeds")
        || args.value("--attacker", "playbook") != "playbook"
    {
        return Err("meta-fit requires playbook, full visible scouting and five quantiles; use --replicates, not --seeds".to_owned());
    }
    let inputs = public_inputs(&args.root, &bases, catalog_path)?;
    let revision = std::process::Command::new("git")
        .current_dir(&args.root)
        .args(["rev-parse", "HEAD"])
        .output()
        .map_err(|error| format!("git revision: {error}"))?;
    if !revision.status.success() {
        return Err(
            "cannot identify engine commit; set GIT_DIR for a relocated worktree".to_owned(),
        );
    }
    let revision = String::from_utf8(revision.stdout).map_err(|error| error.to_string())?;
    let fitter = Fitter {
        compiler,
        catalog,
        bases: &bases,
        settings,
        replicates,
        iterations,
        lower,
        upper,
    };
    let curve_path = args.optional_path("--curve-source");
    if let (Some(source), Some(out)) = (&curve_path, args.optional_path("--out")) {
        super::distinct_paths(&[source, &out])?;
    }
    let curve_hash = curve_path.as_deref().map(file_hash).transpose()?;
    let curves = curve_path.as_deref().map(read).transpose()?;
    if let Some(saved) = &curves {
        validate_curve_source(saved, &inputs, &fitter, town_hall, revision.trim())?;
    }
    let builds: Vec<_> = compiler
        .library
        .builds
        .iter()
        .filter(|build| build.library == META_FILE && build.value.get("three_star").is_some())
        .collect();
    if builds
        .iter()
        .any(|build| !(0.0..=1.0).contains(&number(&build.value, "three_star", -1.0)))
    {
        return Err("invalid public three-star target".to_owned());
    }
    let mut result = obj([] as [(&str, Json); 0]);
    let mut fitted = BTreeMap::<String, Vec<f64>>::new();
    for build in builds
        .iter()
        .filter(|build| number(&build.value, "th", 0.0) == town_hall as f64)
    {
        let cached = curves
            .as_ref()
            .map(|saved| {
                saved
                    .get(&build.id)
                    .ok_or_else(|| format!("curve source lacks {}", build.id))
            })
            .transpose()?;
        let row = fitter.fit(build, cached)?;
        fitted
            .entry(text(&build.value, "archetype", "").to_owned())
            .or_default()
            .push(number(&row, "strength", 1.0));
        put(&mut result, &build.id, row);
    }
    if town_hall == 16 {
        for build in builds
            .iter()
            .filter(|build| number(&build.value, "th", 0.0) != 16.0)
        {
            put(&mut result, &build.id, borrow(build, &fitted));
        }
    }
    let final_inputs = public_inputs(&args.root, &bases, catalog_path)?;
    if inputs != final_inputs {
        return Err("public inputs changed during meta-fit; refusing to write a prior".to_owned());
    }
    if curve_path.as_deref().map(file_hash).transpose()? != curve_hash {
        return Err("curve source changed during selection".to_owned());
    }
    let pool_paths = bases.iter().map(|base| {
        string(
            base.path
                .strip_prefix(&args.root)
                .unwrap_or(&base.path)
                .to_string_lossy(),
        )
    });
    let settings = obj([
        ("town_hall", num(town_hall as f64)),
        ("attacker", string(ATTACKER_DESCRIPTION)),
        ("scout_policy", string("visible")),
        ("scout", num(fitter.settings.angles as f64)),
        ("angles", num(fitter.settings.angles as f64)),
        ("hidden_samples", num(3.0)),
        ("angle_offset_radians", num(0.21)),
        ("replicates", num(replicates as f64)),
        (
            "skill_quantiles",
            arr((0..5).map(|q| num(clash_scoring::scoring::skill(q)))),
        ),
        ("plan_seed", string(PLAN_SEED_DESCRIPTION)),
        ("scout_seed", string(SCOUT_SEED_DESCRIPTION)),
        ("modifier", Json::Null),
        ("lower", num(lower)),
        ("upper", num(upper)),
        ("initial_log_grid_points", num(5.0)),
        ("iterations", num(iterations as f64)),
        (
            "selection",
            string(concat!(
                "closest measured target rate; ties nearest bisection root, ",
                "then lower strength; clamped fits retain the bound",
            )),
        ),
        (
            "root_method",
            string(concat!(
                "log bisection of equal-weight isotonic response; ",
                "raw and projected rates retained; final strength re-evaluated",
            )),
        ),
        ("threads", num(fitter.settings.threads as f64)),
        ("pace", num(compiler.pace)),
        ("gaps_enabled", Json::Bool(compiler.gaps.is_some())),
        ("engine_params_file", Json::Null),
        ("flyer_range", string("gamedata")),
    ]);
    let curve_source = curves.as_ref().map_or(Json::Null, |saved| {
        let original = saved.at("_provenance");
        obj([
            ("sha256", string(curve_hash.as_deref().expect("curve hash"))),
            (
                "public_inputs_sha256",
                original.at("public_inputs_sha256").clone(),
            ),
            ("source_hashes", original.at("source_hashes").clone()),
            (
                "interpretation",
                string(concat!(
                    "recorded public simulations reused; original simulation-source hashes ",
                    "preserved; current fitter replays root queries and selects a measured ",
                    "point without new simulations",
                )),
            ),
        ])
    });
    let provenance = obj([
        ("fit_status", string("not defense-fitted")),
        (
            "scope",
            string(if town_hall == 16 {
                "public TH16 fit; TH17/18 borrowed, uncalibrated"
            } else {
                "TH18 sensitivity only; never the CV prior"
            }),
        ),
        ("engine", string("rust")),
        ("engine_commit", string(revision.trim())),
        (
            "public_inputs_sha256",
            string(sha256(encode(&inputs).as_bytes())),
        ),
        ("source_hashes", inputs),
        ("base_pool", arr(pool_paths)),
        (
            "base_levels",
            string(concat!(
                "pinned layout levels, walls, heroes and hidden hypotheses as supplied; ",
                "no account overlay",
            )),
        ),
        (
            "excluded_pool",
            string("old own-layout pool excluded to prevent held-out defense layout leakage"),
        ),
        (
            "target_source",
            string(concat!(
                "data/source/meta-armies-2026-10-15.json; pinned TrophyCoach same-TH ranked ",
                "last-30-day per-build three_star; no private observations",
            )),
        ),
        ("settings", settings),
        ("curve_source", curve_source),
    ]);
    put(&mut result, "_provenance", provenance);
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn measured_match_beats_a_poor_final_midpoint_and_clamps_keep_the_bound() {
        let points = [
            Point {
                strength: 0.4,
                rate: 0.0,
            },
            Point {
                strength: 1.1,
                rate: 0.35,
            },
            Point {
                strength: 1.11,
                rate: 0.2,
            },
            Point {
                strength: 2.5,
                rate: 1.0,
            },
        ];
        assert_eq!(closest_point(&points, 0.35, 1.11, false), 1);
        assert_eq!(closest_point(&points, 0.35, 2.5, true), 3);
    }

    #[test]
    fn changed_catalog_cannot_reuse_recorded_curves() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let catalog = Arc::new(Catalog::load(&root.join("data/generated/catalog.json")).unwrap());
        let compiler = Compiler::load(&root, &catalog.stats).unwrap();
        let fitter = Fitter {
            compiler: &compiler,
            catalog: Arc::clone(&catalog),
            bases: &[],
            settings: Settings::default(),
            replicates: 2,
            iterations: 6,
            lower: 0.4,
            upper: 2.5,
        };
        let path = "data/generated/catalog.json";
        let source = obj([(path, string("a".repeat(64)))]);
        let saved = obj([(
            "_provenance",
            obj([
                ("fit_status", string("not defense-fitted")),
                ("engine_commit", string("synthetic-test")),
                (
                    "public_inputs_sha256",
                    string(sha256(encode(&source).as_bytes())),
                ),
                ("source_hashes", source),
            ]),
        )]);
        let inputs = obj([(path, string("b".repeat(64)))]);
        let error =
            validate_curve_source(&saved, &inputs, &fitter, 16, "synthetic-test").unwrap_err();
        assert!(error.contains("curve source input changed"));
    }

    #[test]
    fn public_base_rates_are_identical_across_worker_counts() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let catalog = Arc::new(Catalog::load(&root.join("data/generated/catalog.json")).unwrap());
        let compiler = Compiler::load(&root, &catalog.stats).unwrap();
        let mut bases = base_pool(&root, 16).unwrap();
        bases.truncate(2);
        let build = compiler
            .library
            .builds
            .iter()
            .find(|build| build.id == "mass-dragons-16-1")
            .unwrap();
        let mut fitter = Fitter {
            compiler: &compiler,
            catalog: Arc::clone(&catalog),
            bases: &bases,
            settings: Settings {
                angles: 2,
                scout: 2,
                ..Settings::default()
            },
            replicates: 1,
            iterations: 0,
            lower: 0.4,
            upper: 2.5,
        };
        let serial = fitter.rate(build, 1.0).unwrap();
        fitter.settings.threads = 4;
        assert_eq!(serial.to_bits(), fitter.rate(build, 1.0).unwrap().to_bits());
    }

    #[test]
    fn reversals_are_projected_and_out_of_range_targets_are_clamped() {
        let points = [
            Point {
                strength: 0.4,
                rate: 0.1,
            },
            Point {
                strength: 0.8,
                rate: 0.6,
            },
            Point {
                strength: 1.2,
                rate: 0.4,
            },
            Point {
                strength: 2.5,
                rate: 0.9,
            },
        ];
        assert_eq!(monotone_rates(&points), vec![0.1, 0.5, 0.5, 0.9]);
        assert_eq!(bracket(&points, 0.0), (0.4, true));
        assert_eq!(bracket(&points, 1.0), (2.5, true));
        assert_eq!(bracket(&points, 0.5), ((0.4_f64 * 0.8).sqrt(), false));
    }

    #[test]
    fn borrowing_is_arithmetic_with_a_neutral_fallback() {
        let build = Build {
            id: "mass-dragons-18-1".to_owned(),
            library: META_FILE.to_owned(),
            value: obj([
                ("archetype", string("mass-dragons")),
                ("three_star", num(0.55)),
            ]),
        };
        let mut fitted = BTreeMap::new();
        assert_eq!(borrow(&build, &fitted).at("strength"), &num(1.0));
        fitted.insert("mass-dragons".to_owned(), vec![0.8, 1.2]);
        assert_eq!(borrow(&build, &fitted).at("strength"), &num(1.0));
        assert!(borrow(&build, &fitted).at("uncalibrated").bool());
    }
}
