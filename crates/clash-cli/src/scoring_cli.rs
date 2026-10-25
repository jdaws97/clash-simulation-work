//! score BUNDLE [--threads N] [--replay] [--root REPO] [--catalog CATALOG]
//! score-check REFERENCE [--battles] [--threads N] [--root REPO]
//! score-check BUNDLE REFERENCE [--battles] [--threads N] [--root REPO]
//!
//! BUNDLE: layouts, scenarios, plans, optional plan_indices (default 0..N).
//! mode defaults to ranked; scout defaults to SCOUT; scout_policy defaults to
//! visible (independent hidden ensemble). random and oracle are explicit options.
//! hole_penalty overrides
//! BASELAB_HOLE_PENALTY; an explicit null freezes the mode's default penalty.
//! Plans are rust_bridge.py:129-149 scenario_plan JSON, including strength.
//! Optional scenario_options regenerates meta scenarios from data snapshots
//! (or --root files); optional results is a layout-major array of Python
//! (stars, destruction, th_destroyed, time) rows, used only with --replay.
//! Replaying completed results requires scout_policy: oracle. score-check is a
//! legacy comparison adapter; the reference regression gate is Rust golden.
//! Embedded data freezes calibration, builds, observations and available
//! playbooks. Without data, these are loaded from --root and the environment.

use std::fmt::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::json::Json;
use crate::scoring::{self, MetaOptions, Outcome, Scenario, Scorer, ScoringData};
use crate::scouting::{ScoutPolicy, ScoutRun, HIDDEN_SAMPLES};

struct Options {
    root: PathBuf,
    catalog: Option<PathBuf>,
    threads: usize,
    replay: bool,
    battles: bool,
    files: Vec<PathBuf>,
}

/// args includes the subcommand as its first element. Kept independent of
/// process arguments so the reviewer can dispatch from the existing CLI.
pub fn main(args: &[PathBuf]) -> Result<(), String> {
    let command = args
        .first()
        .and_then(|value| value.to_str())
        .ok_or("missing score command")?;
    if !matches!(command, "score" | "score-check") {
        return Err("expected score or score-check".to_owned());
    }
    let root = std::env::var_os("BASELAB_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .to_owned()
        });
    let mut options = Options {
        root,
        catalog: std::env::var_os("BASELAB_CATALOG").map(PathBuf::from),
        threads: std::thread::available_parallelism().map_or(1, usize::from),
        replay: false,
        battles: false,
        files: Vec::new(),
    };
    let mut index = 1;
    while index < args.len() {
        match args[index].to_str() {
            Some("--replay") => options.replay = true,
            Some("--battles") => options.battles = true,
            Some(flag @ ("--threads" | "--root" | "--catalog")) => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| format!("{flag} needs a value"))?;
                match flag {
                    "--threads" => {
                        options.threads = value
                            .to_str()
                            .ok_or("invalid thread count")?
                            .parse()
                            .map_err(|_| "invalid thread count")?;
                    }
                    "--root" => options.root = value.clone(),
                    _ => options.catalog = Some(value.clone()),
                }
            }
            Some(flag) if flag.starts_with("--") => {
                return Err(format!("unknown score option {flag}"));
            }
            _ => options.files.push(args[index].clone()),
        }
        index += 1;
    }
    if options.threads == 0 {
        return Err("thread count must be positive".to_owned());
    }
    if command == "score" {
        if options.files.len() != 1 {
            return Err("usage: score BUNDLE [--threads N] [--replay] [--root REPO]".to_owned());
        }
        let bundle = scoring::read(&options.files[0])?;
        let result = score_bundle(&bundle, &options, options.replay)?;
        println!("{}", stringify(&result));
        return Ok(());
    }
    check(&options)
}

fn score_bundle(bundle: &Json, options: &Options, replay: bool) -> Result<Json, String> {
    let data = if let Some(data) = bundle.get("data") {
        ScoringData::from_json(data)
    } else {
        ScoringData::load(&options.root)?
    };
    let generated = bundle
        .get("scenario_options")
        .map(|value| {
            MetaOptions::from_json(value)
                .and_then(|options| scoring::meta_scenarios(&data, &options))
        })
        .transpose()?;
    let scenarios: Vec<Scenario> = if let Some(generated) = &generated {
        generated.scenarios.clone()
    } else {
        bundle
            .at("scenarios")
            .arr()
            .iter()
            .map(Scenario::from_json)
            .collect()
    };
    let layouts = bundle.at("layouts").arr();
    let mode = scoring::string(bundle, "mode").unwrap_or_else(|| "ranked".to_owned());
    let scout = bundle
        .get("scout")
        .filter(|value| !value.is_null())
        .map(Json::usize);
    let penalty = if let Some(per) = bundle.get("hole_penalty") {
        per.opt_f64()
    } else {
        std::env::var("BASELAB_HOLE_PENALTY")
            .ok()
            .filter(|value| !value.is_empty())
            .map(|value| value.parse::<f64>().map_err(|error| error.to_string()))
            .transpose()?
    };
    let need_catalog = !replay || bundle.get("building_sizes").is_none();
    let catalog = if need_catalog {
        let path = options
            .catalog
            .clone()
            .unwrap_or_else(|| options.root.join("rust/data/catalog.json"));
        Some(Arc::new(Catalog::load(&path)?))
    } else {
        None
    };
    let sizes: Vec<(String, usize)> = if let Some(sizes) = bundle.get("building_sizes") {
        sizes
            .obj()
            .iter()
            .map(|(key, size)| (key.clone(), size.usize()))
            .collect()
    } else {
        catalog
            .as_ref()
            .unwrap()
            .building_types
            .iter()
            .map(|(key, value)| (key.clone(), value.size))
            .collect()
    };
    let policy = ScoutPolicy::parse(
        bundle
            .get("scout_policy")
            .and_then(Json::opt_str)
            .unwrap_or("visible"),
    )?;
    let runs = if replay {
        if policy != ScoutPolicy::Oracle {
            return Err("replaying completed battles requires explicit scout_policy: oracle; visible scouting needs independent ensemble battles".to_owned());
        }
        let rows = bundle
            .get("results")
            .ok_or("replay requires bundle.results")?
            .arr();
        rows.iter()
            .map(|rows| {
                let outcomes: Vec<_> = rows.arr().iter().map(Outcome::from_json).collect();
                if outcomes.len() != scenarios.len() {
                    return Err("replay needs one outcome per scenario".to_owned());
                }
                let selections = scoring::scouted(&scenarios, &outcomes, scout);
                let mut selected = Vec::new();
                let mut selected_outcomes = Vec::new();
                let mut source_indices = Vec::new();
                for row in selections {
                    let mut scenario = scenarios[row.scenario].clone();
                    scenario.weight = row.weight;
                    selected.push(scenario);
                    selected_outcomes.push(outcomes[row.scenario]);
                    source_indices.push(row.scenario);
                }
                Ok(ScoutRun {
                    scenarios: selected,
                    outcomes: selected_outcomes,
                    source_indices,
                    planning_battles: 0,
                    evaluation_battles: 0,
                })
            })
            .collect::<Result<Vec<_>, String>>()?
    } else {
        let scorer = prepare_bundle(
            bundle,
            layouts,
            &scenarios,
            &data,
            catalog.as_ref().unwrap(),
        )?;
        (0..layouts.len())
            .map(|index| {
                scorer.scout(
                    Arc::clone(catalog.as_ref().unwrap()),
                    index,
                    options.threads,
                    policy,
                    scout,
                )
            })
            .collect::<Result<Vec<_>, _>>()?
    };
    if runs.len() != layouts.len() {
        return Err("results must have one row per layout".to_owned());
    }
    let village = scoring::number(bundle, "village", 44.0) as i64;
    let margin = scoring::number(bundle, "margin", 3.0) as i64;
    let mut output = Vec::new();
    for (layout, run) in layouts.iter().zip(runs) {
        let summary = scoring::summarise(&run.scenarios, &run.outcomes, Some(1))?;
        let holes = scoring::hole_tiles(layout, &sizes, village, margin);
        let selections = run
            .source_indices
            .iter()
            .zip(&run.scenarios)
            .map(|(index, scenario)| {
                Json::Arr(vec![Json::Num(*index as f64), Json::Num(scenario.weight)])
            })
            .collect();
        output.push(scoring::object(vec![
            (
                "name",
                Json::Str(scoring::string(layout, "name").unwrap_or_default()),
            ),
            (
                "objective",
                Json::Num(scoring::objective(&summary, &mode, holes, penalty)),
            ),
            ("summary", summary.to_json()),
            ("scouting", Json::Arr(selections)),
            (
                "results",
                Json::Arr(run.outcomes.iter().map(Outcome::to_json).collect()),
            ),
            (
                "evaluation_scenarios",
                Json::Arr(run.scenarios.iter().map(Scenario::to_json).collect()),
            ),
            ("planning_battles", Json::Num(run.planning_battles as f64)),
            (
                "evaluation_battles",
                Json::Num(run.evaluation_battles as f64),
            ),
            ("holes", Json::Num(holes as f64)),
        ]));
    }
    let th_mix = generated.as_ref().map_or(Json::Null, |generated| {
        Json::Obj(
            generated
                .th_mix
                .iter()
                .map(|(th, weight)| (th.to_string(), Json::Num(*weight)))
                .collect(),
        )
    });
    let shares = generated.as_ref().map_or(Json::Null, |generated| {
        let entries = generated
            .build_shares
            .iter()
            .map(|(th, builds)| {
                let builds = builds
                    .iter()
                    .map(|(key, weight)| (key.clone(), Json::Num(*weight)))
                    .collect();
                (th.to_string(), Json::Obj(builds))
            })
            .collect();
        Json::Obj(entries)
    });
    let mut output = scoring::object(vec![
        ("scout_policy", Json::Str(policy.name().to_owned())),
        (
            "hidden_samples",
            Json::Num(if policy == ScoutPolicy::Visible {
                HIDDEN_SAMPLES as f64
            } else {
                0.0
            }),
        ),
        (
            "scenarios",
            Json::Arr(scenarios.iter().map(Scenario::to_json).collect()),
        ),
        (
            "skills",
            Json::Arr(
                scenarios
                    .iter()
                    .map(|sc| Json::Num(scoring::skill(sc.seed)))
                    .collect(),
            ),
        ),
        ("strength", data.strength.to_json()),
        ("observations", data.observations.to_json()),
        ("th_mix", th_mix),
        (
            "mix_source",
            generated
                .as_ref()
                .map_or(Json::Null, |generated| Json::Str(generated.source.clone())),
        ),
        ("build_shares", shares),
        ("layouts", Json::Arr(output)),
    ]);
    if let Some(cases) = bundle.get("trophy_cases") {
        let values = cases
            .arr()
            .iter()
            .map(|case| {
                let values = case.arr();
                let stars = values[0].i64();
                let pct = values[1].f64();
                Json::Arr(vec![
                    Json::Num(scoring::attacker_trophies(stars, pct) as f64),
                    Json::Num(scoring::defender_trophies(stars, pct) as f64),
                ])
            })
            .collect();
        if let Json::Obj(fields) = &mut output {
            fields.push(("trophies".to_owned(), Json::Arr(values)));
        }
    }
    Ok(output)
}

fn prepare_bundle(
    bundle: &Json,
    layouts: &[Json],
    scenarios: &[Scenario],
    data: &ScoringData,
    catalog: &Arc<Catalog>,
) -> Result<Scorer, String> {
    let plans = bundle.at("plans").arr().to_vec();
    let indices: Vec<usize> = bundle.get("plan_indices").map_or_else(
        || (0..scenarios.len()).collect(),
        |value| value.arr().iter().map(Json::usize).collect(),
    );
    if indices.len() != scenarios.len() {
        return Err("each scenario needs a valid prepared plan index".to_owned());
    }
    // rust_bridge.py:129-149: prepared plans include this exact product.
    // Reject stale calibration/skill rather than silently running old plans.
    for (scenario, index) in scenarios.iter().zip(&indices) {
        let plan = plans
            .get(*index)
            .ok_or("prepared plan index out of range")?;
        let expected = data.strength.get(&scenario.army) * scoring::skill(scenario.seed);
        if plan.at("strength").f64().to_bits() != expected.to_bits() {
            return Err(format!(
                "prepared plan strength differs for {} seed {}",
                scenario.army, scenario.seed,
            ));
        }
    }
    Scorer::new(
        Arc::clone(catalog),
        layouts.to_vec(),
        scenarios.to_vec(),
        plans,
        indices,
    )
}

fn check(options: &Options) -> Result<(), String> {
    if options.files.is_empty() || options.files.len() > 2 {
        return Err("usage: score-check [BUNDLE] REFERENCE [--battles] [--threads N]".to_owned());
    }
    let reference = scoring::read(options.files.last().unwrap())?;
    let mut cases = Vec::new();
    let external;
    if options.files.len() == 2 {
        external = scoring::read(&options.files[0])?;
        cases.push((
            "bundle".to_owned(),
            &external,
            reference.get("expected").unwrap_or(&reference),
        ));
    } else if let Some(entries) = reference.get("cases") {
        for (index, case) in entries.arr().iter().enumerate() {
            cases.push((
                scoring::string(case, "name").unwrap_or_else(|| index.to_string()),
                case.at("bundle"),
                case.at("expected"),
            ));
        }
    } else {
        cases.push((
            "bundle".to_owned(),
            reference.at("bundle"),
            reference.at("expected"),
        ));
    }
    let mut compared = 0;
    for (name, bundle, expected) in &cases {
        let actual = match score_bundle(bundle, options, !options.battles) {
            Ok(result) => result,
            Err(error) => scoring::object(vec![("error", Json::Str(error))]),
        };
        compare(&actual, expected, name, &mut compared)?;
    }
    println!(
        "{{\"ok\":true,\"cases\":{},\"numeric_values\":{},\"battles\":{}}}",
        cases.len(),
        compared,
        options.battles,
    );
    Ok(())
}

// Float equality alone accepts -0.0 == 0.0. Compare IEEE bits recursively,
// including weights, rounded summaries and objectives; never use tolerances.
fn compare(actual: &Json, expected: &Json, path: &str, compared: &mut usize) -> Result<(), String> {
    match (actual, expected) {
        (Json::Num(actual), Json::Num(expected)) => {
            *compared += 1;
            if actual.to_bits() != expected.to_bits() {
                return Err(format!(
                    "{path}: {actual:?} ({:016x}) != Python {expected:?} ({:016x})",
                    actual.to_bits(),
                    expected.to_bits(),
                ));
            }
        }
        (Json::Arr(actual), Json::Arr(expected)) => {
            if actual.len() != expected.len() {
                return Err(format!(
                    "{path}: {} rows != Python {}",
                    actual.len(),
                    expected.len(),
                ));
            }
            for (index, (actual, expected)) in actual.iter().zip(expected).enumerate() {
                compare(actual, expected, &format!("{path}[{index}]"), compared)?;
            }
        }
        (Json::Obj(actual), Json::Obj(expected)) => {
            if actual.len() != expected.len() {
                return Err(format!(
                    "{path}: {} keys != Python {}",
                    actual.len(),
                    expected.len(),
                ));
            }
            for ((key, actual), (expected_key, expected)) in actual.iter().zip(expected) {
                if key != expected_key {
                    return Err(format!(
                        "{path}: key order {key:?} != Python {expected_key:?}"
                    ));
                }
                compare(actual, expected, &format!("{path}.{key}"), compared)?;
            }
        }
        _ if actual == expected => {}
        _ => return Err(format!("{path}: {actual:?} != Python {expected:?}")),
    }
    Ok(())
}

/// Json preserves object order but has no writer. Emit round-trip decimal
/// numbers with Rust's shortest representation, preserving negative zero.
fn stringify(value: &Json) -> String {
    let mut output = String::new();
    write_json(value, &mut output);
    output
}

fn write_json(value: &Json, output: &mut String) {
    match value {
        Json::Null => output.push_str("null"),
        Json::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        Json::Num(value) => {
            if value.is_nan() {
                output.push_str("NaN");
            } else if *value == f64::INFINITY {
                output.push_str("Infinity");
            } else if *value == f64::NEG_INFINITY {
                output.push_str("-Infinity");
            } else {
                write!(output, "{value:?}").unwrap();
            }
        }
        Json::Str(value) => {
            output.push('"');
            for character in value.chars() {
                match character {
                    '"' => output.push_str("\\\""),
                    '\\' => output.push_str("\\\\"),
                    '\n' => output.push_str("\\n"),
                    '\r' => output.push_str("\\r"),
                    '\t' => output.push_str("\\t"),
                    character if character < '\u{20}' => {
                        write!(output, "\\u{:04x}", character as u32).unwrap();
                    }
                    character => output.push(character),
                }
            }
            output.push('"');
        }
        Json::Arr(values) => {
            output.push('[');
            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                write_json(value, output);
            }
            output.push(']');
        }
        Json::Obj(values) => {
            output.push('{');
            for (index, (key, value)) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                write_json(&Json::Str(key.clone()), output);
                output.push(':');
                write_json(value, output);
            }
            output.push('}');
        }
    }
}
