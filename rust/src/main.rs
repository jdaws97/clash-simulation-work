//! CLI for prepared jobs and reference battle exports; battle.py is the reference.

use std::env;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;
use std::time::Instant;

use baselab_engine::catalog::Catalog;
use baselab_engine::{jobs, json, load, stats, trace};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("baselab-engine: {error}");
            ExitCode::FAILURE
        }
    }
}

fn catalog_path() -> Result<PathBuf, String> {
    if let Some(path) = env::var_os("BASELAB_CATALOG") {
        return Ok(PathBuf::from(path));
    }
    let executable = env::current_exe().map_err(|error| error.to_string())?;
    let directory = executable
        .parent()
        .ok_or("executable has no parent directory")?;
    Ok(directory.join("../../data/catalog.json"))
}

fn run() -> Result<(), String> {
    let mut args = env::args_os().skip(1);
    let usage = "usage: baselab-engine trace <battle.json> <trace.txt> | run <battle.json>... | stats-check <cases.json> | setup-check <battle.json> <job.json> | trace-job <jobs.json> <k> <trace.txt> | jobs <jobs.json> <results.jsonl> [--threads N] | bench-runner <jobs.json> [--threads N]";
    let command = args.next().ok_or(usage)?;
    let paths: Vec<PathBuf> = args.map(PathBuf::from).collect();
    let command = command.to_str().ok_or(usage)?;
    if command == "stats-check" && paths.len() == 1 {
        return stats_check(&paths[0]);
    }
    if matches!(
        command,
        "setup-check" | "trace-job" | "jobs" | "bench-runner"
    ) {
        let catalog = Arc::new(Catalog::load(&catalog_path()?)?);
        return jobs::command(command, &paths, catalog);
    }
    if !matches!(command, "trace" | "run")
        || paths.is_empty()
        || command == "trace" && paths.len() != 2
    {
        return Err(usage.to_owned());
    }
    let catalog = Arc::new(Catalog::load(&catalog_path()?)?);
    if command == "trace" {
        let mut battle = load::load(&paths[0], catalog)?;
        let file = File::create(&paths[1])
            .map_err(|error| format!("{}: {error}", paths[1].display()))?;
        let mut out = BufWriter::new(file);
        trace::write_trace(&mut battle, &mut out)
            .map_err(|error| format!("{}: {error}", paths[1].display()))?;
        out.flush()
            .map_err(|error| format!("{}: {error}", paths[1].display()))?;
        return Ok(());
    }
    let mut total_ms = 0.0;
    for path in &paths {
        let mut battle = load::load(path, Arc::clone(&catalog))?;
        let started = Instant::now();
        let result = battle.run();
        let milliseconds = started.elapsed().as_secs_f64() * 1000.0;
        total_ms += milliseconds;
        println!(
            "{} stars={} destruction={} time={} ms_per_battle={:.3}",
            path.display(),
            result.stars,
            result.destruction,
            trace::py_float_repr(result.time),
            milliseconds,
        );
    }
    println!(
        "battles={} ms_per_battle={:.3}",
        paths.len(),
        total_ms / paths.len() as f64,
    );
    Ok(())
}

/// stats.get over [name, level, [keys...], default] cases (written by
/// rust_export.py stats-check): one line per case, the result's bits or None.
fn stats_check(path: &PathBuf) -> Result<(), String> {
    let catalog = Catalog::load(&catalog_path()?)?;
    let text = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    let cases = json::parse(&text).map_err(|error| error.to_string())?;
    let mut out = String::new();
    for case in cases.arr() {
        let case = case.arr();
        let level = stats::Level::from_json(&case[1]);
        let keys: Vec<&str> = case[2].arr().iter().map(|k| k.str()).collect();
        let value = catalog
            .stats
            .get(case[0].str(), &level, &keys, case[3].opt_f64());
        match value {
            Some(v) => out.push_str(&format!("{:016x}\n", v.to_bits())),
            None => out.push_str("None\n"),
        }
    }
    print!("{out}");
    Ok(())
}
