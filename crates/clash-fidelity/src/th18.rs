//! Paired TH18 level x defending-CC sensitivity experiment (first research test).

use std::sync::Arc;

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_plans::compile::Compiler;
use clash_scoring::scoring::Scenario;
use clash_scoring::scouting::ScoutPolicy;

use super::io::*;
use super::metrics::Distribution;
use super::provenance;
use super::replay::{self, Settings};
use super::Arguments;

pub fn variant(
    original: &Json,
    catalog: &Catalog,
    level_mode: &str,
    cc_mode: &str,
) -> Result<Json, String> {
    let mut layout = original.clone();
    let mut levels = obj([] as [(&str, Json); 0]);
    let cap_th = if level_mode == "th17-max" { 17 } else { 18 };
    for building in list(original, "buildings") {
        let key = text(building, "key", "");
        if key == "banner" {
            continue;
        }
        let kind = catalog
            .building_types
            .iter()
            .find(|(name, _)| name == key)
            .ok_or_else(|| format!("unknown building {key}"))?;
        let stat_name = if key == "crafting" {
            catalog
                .setup
                .at("crafted")
                .get(text(building, "mode", "none"))
                .and_then(Json::opt_str)
                .unwrap_or(&kind.1.name)
        } else {
            &kind.1.name
        };
        let max = catalog
            .stats
            .max_level(stat_name, cap_th)
            .or_else(|| catalog.stats.max_level(stat_name, 18).map(|_| 1))
            .ok_or_else(|| format!("no max level for {stat_name}"))?;
        let level =
            if level_mode == "one-lower" && kind.1.kind == clash_engine::labels::Tag::Defense {
                (max - 1).max(1)
            } else {
                max
            };
        // The TH18 shell and its artillery remain TH18 in all conditions.
        put(
            &mut levels,
            key,
            num(if key == "th" { 18.0 } else { level as f64 }),
        );
    }
    for trap in list(original, "traps") {
        let key = text(trap, "key", "");
        let name = catalog
            .trap_names
            .iter()
            .find(|(name, _)| name == key)
            .map(|(_, name)| name.as_str())
            .ok_or_else(|| format!("unknown trap {key}"))?;
        let max = catalog.stats.max_level(name, cap_th).unwrap_or(1);
        let level = if level_mode == "one-lower" {
            (max - 1).max(1)
        } else {
            max
        };
        put(&mut levels, &format!("trap:{key}"), num(level as f64));
    }
    let guardian = text(original, "guardian", "Longshot");
    let max = catalog.stats.max_level(guardian, cap_th).unwrap_or(1);
    put(
        &mut levels,
        "guardian",
        num(if level_mode == "one-lower" {
            (max - 1).max(1) as f64
        } else {
            max as f64
        }),
    );
    let mut heroes = obj([] as [(&str, Json); 0]);
    for hero in list(original, "heroes") {
        let max = catalog
            .stats
            .max_level(hero.str(), cap_th)
            .ok_or_else(|| format!("no max for {}", hero.str()))?;
        put(
            &mut heroes,
            hero.str(),
            num(if level_mode == "one-lower" {
                (max - 1).max(1) as f64
            } else {
                max as f64
            }),
        );
    }
    put(&mut layout, "levels", levels);
    put(&mut layout, "hero_levels", heroes);
    put(
        &mut layout,
        "wall_level",
        num(catalog
            .stats
            .max_level("Wall", if level_mode == "th17-max" { 17 } else { 18 })
            .ok_or("missing wall cap")? as f64),
    );
    remove(&mut layout, "wall_levels");
    // These are explicit hypotheses, not recovered occupants.
    match cc_mode {
        "empty" => put(&mut layout, "cc_troops", arr([])),
        "default" => {}
        "strong" => {
            let cargo = (0..3)
                .map(|_| string("Ice Golem"))
                .chain((0..10).map(|_| string("Archer")));
            put(&mut layout, "cc_troops", arr(cargo));
        }
        _ => return Err("unknown CC condition".to_owned()),
    }
    Ok(layout)
}

pub fn command(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let real_path = args
        .root
        .join("local/digitize/ranked-bases-2026-10-25-th18/results.json");
    let real = read(&real_path)?;
    let army = "custom:user-rr-oct25";
    let build = compiler.library.build_by_id(army)?;
    let strength = replay::strengths(&args.root, &args.calibration())?.get(army);
    let replicates = args.integer("--replicates", if args.flag("--quick") { 1 } else { 5 })?;
    let angles = args.integer("--angles", 8)?;
    let threads = args.integer("--threads", 4)?;
    if replicates == 0 || angles < 2 || threads == 0 {
        return Err("replicates/threads must be positive; angles >=2".to_owned());
    }
    let levels: Vec<_> = match args.value("--variants", "all") {
        "all" => vec!["th18-max", "one-lower", "th17-max"],
        "current" => vec!["th18-max"],
        _ => return Err("variants must be all or current".to_owned()),
    };
    let mut scenarios = Vec::new();
    let mut plans = Vec::new();
    for repeat in 0..replicates {
        for q in 0..5 {
            for side in 0..angles {
                let seed = (5 * (angles * repeat + side) + q) as i64;
                let angle = 2.0 * std::f64::consts::PI * side as f64 / angles as f64;
                scenarios.push(Scenario {
                    army: army.to_owned(),
                    town_hall: 16,
                    angle,
                    seed,
                    weight: 1.0 / (replicates * 5 * angles) as f64,
                    modifier: None,
                    group: (5 * repeat + q) as i64,
                    tactic: Json::Null,
                    charge: None,
                    full_scout: true,
                });
                // account inventory and exact custom levels are encoded in build.
                plans.push(replay::plan(
                    compiler,
                    build,
                    angle,
                    seed,
                    strength,
                    args.value("--attacker", "playbook"),
                )?);
            }
        }
    }
    let mut results = Vec::new();
    let inputs = provenance::fingerprint(&args.root, &[&real_path, &args.calibration()])?;
    for base in ["r18a", "r18b", "r18c", "r18d"] {
        let source = args.root.join(format!(
            "data/source/reference-bases/ranked-th18-2026-10-25/{base}.json"
        ));
        let original = read(&source)?;
        let observed = list(&real, "attacks")
            .iter()
            .find(|row| text(row, "id", "").ends_with(&base[3..]))
            .cloned()
            .unwrap_or(Json::Null);
        for level in &levels {
            for cc in ["empty", "default", "strong"] {
                let layout = variant(&original, &catalog, level, cc)?;
                let mut policies = obj([] as [(&str, Json); 0]);
                for policy in [
                    ScoutPolicy::Random,
                    ScoutPolicy::Visible,
                    ScoutPolicy::Oracle,
                ] {
                    let settings = Settings {
                        seeds: replicates * 5,
                        angles,
                        threads,
                        attacker: args.value("--attacker", "playbook").to_owned(),
                        policy,
                        scout: angles,
                        ..Settings::default()
                    };
                    let (samples, reasons, planning, evaluations, diagnostics, selected) =
                        replay::run_prepared(
                            Arc::clone(&catalog),
                            &layout,
                            &scenarios,
                            plans.clone(),
                            &settings,
                        )?;
                    let dist = Distribution::samples(&samples);
                    let mean_stars: f64 = dist
                        .stars
                        .iter()
                        .enumerate()
                        .map(|(stars, p)| stars as f64 * p)
                        .sum();
                    let triples = samples.iter().filter(|sample| sample.stars == 3).count();
                    let groups = replicates * 5;
                    let zero_bound = if triples == 0 {
                        1.0 - 0.05_f64.powf(1.0 / groups as f64)
                    } else {
                        1.0
                    };
                    let result = obj([
                        ("distribution", dist.to_json()),
                        ("mean_stars", num(mean_stars)),
                        ("p3", num(dist.stars[3])),
                        ("independent_skill_groups", num(groups as f64)),
                        (
                            "zero_three_star_95_upper_bound",
                            if triples == 0 {
                                num(zero_bound)
                            } else {
                                Json::Null
                            },
                        ),
                        ("planning_battles", num(planning as f64)),
                        ("evaluation_battles", num(evaluations as f64)),
                        ("diagnostic_replays", num(diagnostics as f64)),
                        ("end_reasons", count_map(&reasons)),
                        (
                            "selected_sides",
                            arr(selected.iter().map(Scenario::to_json)),
                        ),
                        ("samples", arr(samples.iter().map(replay::Sample::to_json))),
                    ]);
                    let key = match policy {
                        ScoutPolicy::Random => "random",
                        ScoutPolicy::Visible => "visible",
                        ScoutPolicy::Oracle => "oracle",
                    };
                    put(&mut policies, key, result);
                }
                eprintln!(
                    "{base} {level}/{cc}: mean stars random={:.2} visible={:.2} oracle={:.2}",
                    number(policies.at("random"), "mean_stars", 0.0),
                    number(policies.at("visible"), "mean_stars", 0.0),
                    number(policies.at("oracle"), "mean_stars", 0.0)
                );
                results.push(obj([
                    ("base", string(base)),
                    ("layout_source_sha256", string(file_hash(&source)?)),
                    ("levels", string(*level)),
                    ("cc", string(cc)),
                    ("defense_levels", layout.at("levels").clone()),
                    ("hero_levels", layout.at("hero_levels").clone()),
                    ("wall_level", layout.at("wall_level").clone()),
                    ("cc_troops", layout.at("cc_troops").clone()),
                    (
                        "real_stars",
                        observed.get("stars").cloned().unwrap_or(Json::Null),
                    ),
                    (
                        "real_destruction",
                        observed.get("destruction").cloned().unwrap_or(Json::Null),
                    ),
                    ("policies", policies),
                ]));
            }
        }
    }
    Ok(obj([
        ("engine", string("rust")),
        ("army", string(army)),
        ("attacker", string(args.value("--attacker", "playbook"))),
        ("strength", num(strength)),
        (
            "calibration_sha256",
            string(file_hash(&args.calibration())?),
        ),
        (
            "experiment",
            string(concat!(
                "paired 3 level conditions x 3 CC hypotheses x random/visible/oracle; ",
                "full side choice; all five skill quantiles per replicate; no league modifier",
            )),
        ),
        (
            "level_interpretation",
            string(concat!(
                "one-lower reduces defense buildings, traps, guardian and defending heroes, ",
                "floor 1; economy and walls remain TH18-max. ",
                "TH17-max caps defenses/heroes/traps/walls; TH18-only content stays at level 1. ",
                "TH18 shell/artillery and topology retained in every condition",
            )),
        ),
        (
            "cc_interpretation",
            string(concat!(
                "default is the saved layout package; strong is a declared 55-housing ",
                "candidate: 3 Ice Golems + 10 Archers; it is not an empirically strongest CC",
            )),
        ),
        (
            "uncertainty",
            string(concat!(
                "development comparator; four single real outcomes; ",
                "reference transcriptions include uncertain positions/traps. ",
                "Zero triples do not imply impossible; binomial bound is illustrative ",
                "because skill quantiles are paired",
            )),
        ),
        (
            "inputs_changed_during_run",
            Json::Bool(
                inputs != provenance::fingerprint(&args.root, &[&real_path, &args.calibration()])?,
            ),
        ),
        ("inputs", inputs),
        ("results", arr(results)),
    ]))
}
