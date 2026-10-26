//! Standalone native measurement CLI; engine mechanics remain library-owned.

mod board;
mod decode;
mod fit;
mod history;
mod io;
mod metrics;
mod observed;
mod provenance;
mod th18;

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_plans::compile::Compiler;
use clash_scoring::scouting::ScoutPolicy;

mod replay;
use io::*;

const USAGE: &str = concat!(
    "fidelity decode CODE|LOG | replay [LOG] | check-a | board | calibrate | cv | ",
    "observed REPLAY | th18 | proof | export-jobs | score-jobs PREPARED OUTCOMES ",
    "[--root ROOT] [--out FILE] [--threads N] [--seeds N] [--angles N] ",
    "[--attacker generic|playbook] [--scout-policy visible|random|oracle] ",
    "[--legacy-oracle] [--calibration FILE] [--calibration-report FILE]",
);

pub struct Arguments {
    pub command: String,
    pub root: PathBuf,
    pub values: BTreeMap<String, String>,
    pub flags: BTreeSet<String>,
    pub positional: Vec<String>,
}

impl Arguments {
    fn parse(arguments: Vec<String>) -> Result<Self, String> {
        let mut args = arguments.into_iter();
        let command = args.next().ok_or(USAGE)?;
        let mut values = BTreeMap::new();
        let mut flags = BTreeSet::new();
        let mut positional = Vec::new();
        let boolean = [
            "--legacy-oracle",
            "--raw",
            "--quick",
            "--monotonic-cap",
            "--exclude-fitted",
            "--techniques",
            "--refit",
            "--full-scout",
        ];
        let valued = [
            "--root",
            "--out",
            "--threads",
            "--seeds",
            "--angles",
            "--attacker",
            "--scout-policy",
            "--scout",
            "--calibration",
            "--calibration-report",
            "--prior-report",
            "--log",
            "--history",
            "--base",
            "--since",
            "--until",
            "--train-log",
            "--report",
            "--grid",
            "--max-correction",
            "--prior-sd",
            "--min-family",
            "--folds",
            "--fold-dir",
            "--only",
            "--label",
            "--levels",
            "--strength",
            "--jitter",
            "--catalog",
            "--town-hall",
            "--variants",
            "--replicates",
            "--reference",
            "--tolerance",
        ];
        while let Some(argument) = args.next() {
            if ["--reference-cv2", "--archive-cv2", "--python"].contains(&argument.as_str()) {
                return Err(format!("{argument} is retired; use native CV and --reference FILE for an explicit saved metrics comparison"));
            }
            if boolean.contains(&argument.as_str()) {
                flags.insert(argument);
            } else if valued.contains(&argument.as_str()) {
                values.insert(
                    argument.clone(),
                    args.next()
                        .ok_or_else(|| format!("missing value for {argument}"))?,
                );
            } else if argument.starts_with('-') {
                return Err(format!("unknown option {argument}; {USAGE}"));
            } else {
                positional.push(argument);
            }
        }
        let root = values
            .get("--root")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("BASELAB_ROOT").map(PathBuf::from))
            .unwrap_or(std::env::current_dir().map_err(|error| error.to_string())?);
        let root = root
            .ancestors()
            .find(|path| path.join("crates/clash-engine/Cargo.toml").is_file())
            .ok_or("cannot find repository; pass --root")?
            .to_owned();
        Ok(Self {
            command,
            root,
            values,
            flags,
            positional,
        })
    }

    pub fn value<'a>(&'a self, key: &str, default: &'a str) -> &'a str {
        self.values.get(key).map_or(default, String::as_str)
    }
    pub fn flag(&self, key: &str) -> bool {
        self.flags.contains(key)
    }
    pub fn integer(&self, key: &str, default: usize) -> Result<usize, String> {
        self.values.get(key).map_or(Ok(default), |value| {
            value.parse().map_err(|_| format!("invalid {key}"))
        })
    }
    pub fn float(&self, key: &str, default: f64) -> Result<f64, String> {
        let value = self.values.get(key).map_or(Ok(default), |value| {
            value.parse().map_err(|_| format!("invalid {key}"))
        })?;
        if !value.is_finite() {
            return Err(format!("{key} must be finite"));
        }
        Ok(value)
    }
    pub fn path(&self, key: &str, default: &str) -> PathBuf {
        resolve(&self.root, self.value(key, default))
    }
    pub fn optional_path(&self, key: &str) -> Option<PathBuf> {
        self.values.get(key).map(|value| resolve(&self.root, value))
    }
    pub fn calibration(&self) -> PathBuf {
        self.optional_path("--calibration")
            .or_else(|| {
                std::env::var("BASELAB_CALIBRATION")
                    .ok()
                    .filter(|value| !value.is_empty())
                    .map(|value| resolve(&self.root, &value))
            })
            .unwrap_or_else(|| self.root.join("data/meta-calibration-r8.json"))
    }
    pub fn settings(&self, fit: bool) -> Result<replay::Settings, String> {
        let default_attacker = if std::env::var("BASELAB_REPLAY_PLAYBOOKS").as_deref() == Ok("1") {
            "playbook"
        } else {
            "generic"
        };
        let settings = replay::Settings {
            seeds: self.integer(
                "--seeds",
                if fit {
                    1
                } else if self.flag("--quick") {
                    2
                } else {
                    5
                },
            )?,
            angles: self.integer("--angles", if fit { 4 } else { 8 })?,
            threads: self.integer("--threads", 1)?,
            attacker: self.value("--attacker", default_attacker).to_owned(),
            policy: ScoutPolicy::parse(self.value("--scout-policy", "visible"))?,
            legacy: self.flag("--legacy-oracle"),
            raw: self.flag("--raw") || self.value("--strength", "calibrated") == "raw",
            scout: self.integer("--scout", 2)?,
            techniques: self.flag("--techniques"),
        };
        if settings.seeds == 0
            || settings.threads == 0
            || settings.angles < 2
            || settings.scout == 0
            || settings.scout > settings.angles
        {
            return Err("require seeds/threads/scout >=1 and angles >= max(2,scout)".to_owned());
        }
        if !matches!(settings.attacker.as_str(), "generic" | "playbook") {
            return Err("attacker must be generic or playbook".to_owned());
        }
        Ok(settings)
    }
    pub fn fit_options(&self) -> Result<fit::FitOptions, String> {
        let options = fit::FitOptions {
            min_family: self.integer("--min-family", 8)?,
            grid: self.integer("--grid", 9)?,
            max_correction: self.float("--max-correction", 1.5)?,
            prior_sd: self.float("--prior-sd", 0.2)?,
            quick: self.flag("--quick"),
            monotonic: self.flag("--monotonic-cap"),
        };
        if options.min_family < 2
            || options.grid < 3
            || options.grid.is_multiple_of(2)
            || options.max_correction <= 1.0
            || options.prior_sd <= 0.0
        {
            return Err(
                "need min-family >=2, odd grid >=3, max-correction >1 and prior-sd >0".to_owned(),
            );
        }
        Ok(options)
    }
}

pub fn read_observations(
    args: &Arguments,
    historical: bool,
) -> Result<(Vec<history::Observation>, BTreeMap<String, usize>), String> {
    let log = args
        .optional_path("--log")
        .or_else(|| {
            args.positional
                .first()
                .map(|path| resolve(&args.root, path))
        })
        .unwrap_or_else(|| args.root.join("data/live/battles.jsonl"));
    let (mut rows, skipped) = history::observations(
        &args.root,
        &log,
        &args.path("--history", "data/live/base-history.json"),
        historical,
        args.values.get("--base").map(String::as_str),
    )?;
    if let Some(value) = args.values.get("--town-hall") {
        let th: i64 = value.parse().map_err(|_| "invalid town hall")?;
        rows.retain(|row| row.th == th);
    }
    if args.values.contains_key("--since") || args.values.contains_key("--until") {
        let since = history::timestamp(args.value("--since", "19000101"))?;
        let until = history::timestamp(args.value("--until", "99991231"))? + 86_400_000_000;
        let ids: BTreeSet<_> = history::battles(&log)?
            .iter()
            .filter(|battle| {
                history::timestamp(text(battle, "battleTimestamp", ""))
                    .is_ok_and(|time| since <= time && time < until)
            })
            .filter_map(|battle| decode::identity(battle).ok())
            .collect();
        rows.retain(|row| ids.contains(&row.id));
    }
    Ok((rows, skipped))
}

pub fn distinct_paths(paths: &[&Path]) -> Result<(), String> {
    let mut seen = BTreeSet::new();
    for path in paths {
        let normalized = path.canonicalize().unwrap_or_else(|_| (*path).to_owned());
        if !seen.insert(normalized) {
            return Err("outputs and input files must have distinct paths".to_owned());
        }
    }
    Ok(())
}

pub fn run(arguments: Vec<String>) -> Result<(), String> {
    if arguments
        .iter()
        .any(|argument| argument == "--help" || argument == "-h")
    {
        println!("{USAGE}");
        return Ok(());
    }
    let args = Arguments::parse(arguments)?;
    if args.command == "decode" {
        let decoder = decode::Decoder::load(&args.root)?;
        let input = args.positional.first().ok_or(USAGE)?;
        let path = resolve(&args.root, input);
        let output = if path.is_file() {
            arr(history::battles(&path)?
                .iter()
                .filter(|battle| text(battle, "battleType", "") == "ranked")
                .map(|battle| {
                    decoder
                        .decode(text(battle, "armyShareCode", ""))
                        .map(|army| {
                            obj([
                                (
                                    "battle_id",
                                    string(decode::identity(battle).unwrap_or_default()),
                                ),
                                ("army", army),
                            ])
                        })
                })
                .collect::<Result<Vec<_>, _>>()?)
        } else {
            decoder.decode(input)?
        };
        return emit(&args, &output);
    }
    let catalog = Arc::new(Catalog::load(
        &args.path("--catalog", "rust/data/catalog.json"),
    )?);
    let compiler = Compiler::load(&args.root, &catalog.stats)?;
    let output = match args.command.as_str() {
        "replay" | "check-a" => board::check_a(&args, &compiler, Arc::clone(&catalog))?,
        "export-jobs" => export_jobs(&args, &compiler)?,
        "score-jobs" => board::score_jobs(&args)?,
        "board" => board::board(&args, &compiler, Arc::clone(&catalog))?,
        "calibrate" => {
            let settings = args.settings(true)?;
            let options = args.fit_options()?;
            let (rows, skipped) = read_observations(&args, true)?;
            let out = args.path("--out", "output/fidelity-rust/calibration.json");
            let report = args.optional_path("--report").unwrap_or_else(|| {
                out.with_file_name(format!(
                    "report-{}",
                    out.file_name().unwrap_or_default().to_string_lossy()
                ))
            });
            let prior = args.calibration();
            let log = args.path("--log", "data/live/battles.jsonl");
            let history = args.path("--history", "data/live/base-history.json");
            distinct_paths(&[&out, &report, &prior, &log, &history])?;
            let result = fit::calibrate(
                &args.root,
                &compiler,
                Arc::clone(&catalog),
                &rows,
                &skipped,
                &settings,
                &options,
                &prior,
                args.optional_path("--prior-report").as_deref(),
                &log,
                &history,
                &out,
                &report,
            )?;
            println!("saved {}; report {}", out.display(), report.display());
            // calibrate already wrote both artifacts; never overwrite the flat mapping.
            return if result.at("inputs_changed_during_run").bool() {
                Err("calibration inputs changed during run; result marked uncalibrated".to_owned())
            } else {
                Ok(())
            };
        }
        "cv" => board::cv(&args, &compiler, Arc::clone(&catalog))?,
        "observed" => observed::command(&args, &compiler, Arc::clone(&catalog))?,
        "th18" => th18::command(&args, &compiler, Arc::clone(&catalog))?,
        "proof" => board::proof(&args, &compiler, Arc::clone(&catalog))?,
        _ => return Err(USAGE.to_owned()),
    };
    emit(&args, &output)
}

fn export_jobs(args: &Arguments, compiler: &Compiler<'_>) -> Result<Json, String> {
    let settings = args.settings(false)?;
    let observations = read_observations(args, false)?.0;
    let strength = replay::strengths(&args.root, &args.calibration())?;
    let mut layouts = Vec::new();
    let mut plans = Vec::new();
    let mut jobs = Vec::new();
    for row in observations {
        let layout_index = layouts.len();
        layouts.push(row.layout.clone());
        let value = if settings.raw {
            1.0
        } else {
            replay::current_strength(compiler, &strength, row.th, &row.family)
        };
        for repeat in 0..settings.seeds {
            for side in 0..settings.angles {
                let seed = decode::replay_seed(
                    &row.id,
                    repeat as i64,
                    side as i64,
                    settings.angles as i64,
                );
                let angle =
                    2.0 * std::f64::consts::PI * side as f64 / settings.angles as f64 + 0.21;
                let prepared =
                    replay::plan(compiler, &row.build, angle, seed, value, &settings.attacker)?;
                plans.push(prepared);
                jobs.push(obj([
                    ("layout", num(layout_index as f64)),
                    ("plan", num((plans.len() - 1) as f64)),
                    ("seed", num(seed as f64)),
                    ("town_hall", num(number(&row.layout, "town_hall", 16.0))),
                    ("modifier", Json::Null),
                ]));
            }
        }
    }
    Ok(obj([
        ("layouts", arr(layouts)),
        ("plans", arr(plans)),
        ("jobs", arr(jobs)),
    ]))
}

fn emit(args: &Arguments, output: &Json) -> Result<(), String> {
    if let Some(path) = args.optional_path("--out") {
        write(&path, output)?;
    } else {
        println!("{}", encode(output));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retired_reference_modes_fail_before_loading_inputs() {
        for flag in ["--reference-cv2", "--archive-cv2", "--python"] {
            let error = Arguments::parse(vec!["cv".to_owned(), flag.to_owned()])
                .err()
                .unwrap();
            assert!(error.contains("retired"));
            assert!(error.contains("--reference FILE"));
        }
    }
}
