//! Proof helper compiled against a historical baselab-engine crate in /tmp.
//! It is deliberately not a production binary target: the current CLI retains
//! current content checks, Warden handling and playbook behavior.

#[path = "decode.rs"]
mod decode;
#[path = "history.rs"]
mod history;
#[path = "io.rs"]
mod io;

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use baselab_engine::catalog::Catalog;
use baselab_engine::compile::{CompileOptions, Compiler};
use baselab_engine::json::Json;

use io::*;

fn run() -> Result<(), String> {
    let arguments: Vec<_> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    if arguments.len() != 5 {
        return Err("archive-export ROOT CATALOG PREPARED OUTPUT generic|playbook | --run PREPARED OUTPUT CATALOG THREADS".to_owned());
    }
    if arguments[0] == Path::new("--run") {
        return run_jobs(&arguments);
    }
    let root = &arguments[0];
    let catalog = Catalog::load(&arguments[1])?;
    let compiler = Compiler::load(root, &catalog.stats)?;
    let attacker = arguments[4].to_str().ok_or("invalid attacker")?;
    if !matches!(attacker, "generic" | "playbook") {
        return Err("invalid attacker".to_owned());
    }
    let mut prepared = read(&arguments[2])?;
    let (rows, _) = history::observations(
        root,
        &root.join("data/live/battles.jsonl"),
        &root.join("data/live/base-history.json"),
        false,
        None,
    )?;
    if list(&prepared, "layouts").len() != rows.len() {
        return Err("prepared input and observations differ".to_owned());
    }
    let mut plans = Vec::new();
    for job in list(&prepared, "jobs") {
        let layout = number(job, "layout", -1.0) as usize;
        let row = rows.get(layout).ok_or("invalid layout index")?;
        let plan_index = number(job, "plan", -1.0) as usize;
        let original = list(&prepared, "plans")
            .get(plan_index)
            .ok_or("invalid plan index")?;
        let seed = number(job, "seed", 0.0) as i64;
        let mut build = row.build.clone();
        // CV2 predates the to_build Warden-mode preservation fix (F12).
        remove(&mut build, "warden_mode");
        if row.th == 15 {
            put(&mut build, "th", num(16.0));
        }
        let options = CompileOptions {
            playbooks: attacker == "playbook",
            ..CompileOptions::default()
        };
        let mut plan =
            compiler.plan_for_build(&build, number(original, "angle", 0.0), seed, &options)?;
        put(&mut plan, "town_hall", num(row.th as f64));
        put(&mut plan, "observed", Json::Bool(true));
        compiler.require_legal(&mut plan)?;
        put(&mut plan, "strength", original.at("strength").clone());
        plans.push(plan);
    }
    put(&mut prepared, "plans", arr(plans));
    write(Path::new(&arguments[3]), &prepared)
}

fn run_jobs(arguments: &[PathBuf]) -> Result<(), String> {
    use baselab_engine::labels::{Name, Tag};
    use baselab_engine::{Job, PreparedInputs, Runner};

    let catalog = Arc::new(Catalog::load(&arguments[3])?);
    let inputs = PreparedInputs::load(&arguments[1])?;
    let threads: usize = arguments[4]
        .to_str()
        .ok_or("invalid threads")?
        .parse()
        .map_err(|_| "invalid threads")?;
    let runner = Runner::new(catalog, inputs);
    let jobs = &runner.inputs().jobs;
    let reasons = Mutex::new(vec![String::new(); jobs.len()]);
    let hook = |index: usize,
                _: &Job,
                battle: &baselab_engine::state::Battle,
                _: &baselab_engine::state::BattleResult| {
        let reason = if battle.destroyed_counted >= battle.total_counted {
            "all_buildings_destroyed"
        } else if battle.t >= battle.max_time {
            if battle.attackers_pool().any(|unit| {
                unit.alive
                    && !matches!(unit.name_id, Name::Healer | Name::Unicorn | Name::Totem)
                    && unit.kind != Tag::SiegeIdle
            }) {
                "timer_live_fighting_units"
            } else {
                "timer_inventory_only"
            }
        } else {
            "exhausted_offense"
        };
        reasons.lock().expect("archive diagnostics")[index] = reason.to_owned();
    };
    let results = runner
        .run_with_summary(jobs, threads, Some(&hook))
        .map_err(|error| format!("archived kernel: {error:?}"))?;
    let reasons = reasons.into_inner().expect("archive diagnostics");
    let rows = arr(results.iter().enumerate().map(|(index, result)| {
        obj([
            ("job", num(index as f64)),
            ("stars", num(result.stars as f64)),
            ("destruction", num(result.destruction as f64)),
            ("time", num(result.time)),
            ("th_destroyed", Json::Bool(result.th_destroyed)),
            ("end_reason", string(&reasons[index])),
        ])
    }));
    write(&arguments[2], &rows)
}

fn main() {
    if let Err(error) = run() {
        eprintln!("archive-export: {error}");
        std::process::exit(1);
    }
}
