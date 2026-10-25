//! CLI adapters for prepared jobs, setup comparison and battle traces.

use std::fmt::Debug;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

use crate::catalog::Catalog;
use crate::json::{self, Json};
use crate::load::{self, Node};
use crate::runner::{Job, PreparedInputs, RunError, Runner};
use crate::setup;
use crate::state::Battle;
use crate::trace;

fn read(path: &Path) -> Result<Json, String> {
    let text =
        std::fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    json::parse(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn build_job(input: &Json, index: usize, catalog: Arc<Catalog>) -> Result<Battle, String> {
    Node::new(input, "jobs").keys(&["layouts", "plans", "jobs"]);
    let jobs = input.at("jobs").arr();
    let job = jobs
        .get(index)
        .unwrap_or_else(|| panic!("job index {index} outside {} jobs", jobs.len()));
    let inputs = PreparedInputs::new(
        input.at("layouts").arr().to_vec(),
        input.at("plans").arr().to_vec(),
    );
    Runner::new(catalog, inputs)
        .build(&Job::from_json(job))
        .map_err(|error| error.to_string())
}

pub fn command(command: &str, paths: &[PathBuf], catalog: Arc<Catalog>) -> Result<(), String> {
    match command {
        "setup-check" if paths.len() == 2 => {
            let expected = load::load(&paths[0], Arc::clone(&catalog))?;
            let input = read(&paths[1])?;
            let actual = if input.get("jobs").is_some() {
                if input.at("jobs").arr().len() != 1 {
                    return Err("setup-check requires exactly one job".to_owned());
                }
                build_job(&input, 0, catalog)?
            } else {
                // Also accept a self-contained {layout, plan, ...options} job.
                setup::build(input.at("layout"), input.at("plan"), &input, catalog).map_err(|error| error.to_string())?
            };
            let differences = compare(&expected, &actual);
            if differences == 0 {
                println!("setup identical");
                Ok(())
            } else {
                Err(format!("setup differs in {differences} fields/entities"))
            }
        }
        "trace-job" if paths.len() == 3 => {
            let input = read(&paths[0])?;
            let index = paths[1]
                .to_str()
                .ok_or("invalid job index")?
                .parse::<usize>()
                .map_err(|_| "invalid job index")?;
            let mut battle = build_job(&input, index, catalog)?;
            let file = File::create(&paths[2])
                .map_err(|error| format!("{}: {error}", paths[2].display()))?;
            let mut out = BufWriter::new(file);
            trace::write_trace(&mut battle, &mut out).map_err(|error| error.to_string())?;
            out.flush().map_err(|error| error.to_string())
        }
        "jobs" if paths.len() == 2 || paths.len() == 4 => {
            let threads = thread_count(paths, 2)?;
            run(&read(&paths[0])?, &paths[1], threads, catalog)
        }
        "bench-runner" if paths.len() == 1 || paths.len() == 3 => {
            let threads = thread_count(paths, 1)?;
            let inputs = PreparedInputs::load(&paths[0])?;
            bench(&Runner::new(catalog, inputs), threads)
        }
        _ => Err("usage: setup-check <battle.json> <job.json> | trace-job <jobs.json> <k> <trace.txt> | jobs <jobs.json> <results.jsonl> [--threads N] | bench-runner <jobs.json> [--threads N]".to_owned()),
    }
}

fn thread_count(paths: &[PathBuf], required: usize) -> Result<usize, String> {
    let threads = if paths.len() == required + 2 {
        if paths[required].as_os_str() != "--threads" {
            return Err("expected --threads N".to_owned());
        }
        paths[required + 1]
            .to_str()
            .ok_or("invalid thread count")?
            .parse::<usize>()
            .map_err(|_| "invalid thread count")?
    } else {
        std::thread::available_parallelism().map_or(1, |value| value.get())
    };
    if threads == 0 {
        return Err("thread count must be positive".to_owned());
    }
    Ok(threads)
}

fn report_error(error: RunError) -> String {
    if let RunError::Jobs(failures) = &error {
        for failure in failures {
            eprintln!("job {}: {}", failure.index, failure.message);
        }
    }
    error.to_string()
}

fn run(input: &Json, output: &Path, threads: usize, catalog: Arc<Catalog>) -> Result<(), String> {
    let runner = Runner::new(catalog, PreparedInputs::from_json(input));
    let jobs = &runner.inputs().jobs;
    let count = jobs.len();
    let started = Instant::now();
    let results = runner.run(jobs, threads).map_err(report_error)?;
    let elapsed = started.elapsed().as_secs_f64();
    let file = File::create(output).map_err(|error| format!("{}: {error}", output.display()))?;
    let mut out = BufWriter::new(file);
    for (index, result) in results.into_iter().enumerate() {
        writeln!(
            out,
            "{{\"job\":{index},\"stars\":{},\"destruction\":{},\"th_destroyed\":{},\"time\":{},\"units_left\":{}}}",
            result.stars,
            result.destruction,
            result.th_destroyed,
            trace::py_float_repr(result.time),
            result.units_left,
        )
        .map_err(|error| error.to_string())?;
    }
    out.flush().map_err(|error| error.to_string())?;
    println!(
        "battles={count} wall_seconds={elapsed:.6} battles_per_second={:.3}",
        count as f64 / elapsed,
    );
    Ok(())
}

fn bench(runner: &Runner, threads: usize) -> Result<(), String> {
    let jobs = &runner.inputs().jobs;
    let started = Instant::now();
    let first = runner.run(jobs, threads).map_err(report_error)?;
    let first_elapsed = started.elapsed().as_secs_f64();
    let started = Instant::now();
    let second = runner.run(jobs, threads).map_err(report_error)?;
    let second_elapsed = started.elapsed().as_secs_f64();
    println!(
        "run=1 battles={} wall_seconds={first_elapsed:.6}",
        jobs.len()
    );
    println!(
        "run=2 battles={} wall_seconds={second_elapsed:.6}",
        jobs.len()
    );
    println!("identical={}", first == second);
    Ok(())
}

fn difference<T: Debug>(path: &str, expected: &T, actual: &T) -> usize {
    // Rust's shortest round-trip Debug floats distinguish every finite bit
    // pattern (and signed zero). Pretty output includes all nested extra/kit data.
    let expected = format!("{expected:#?}");
    let actual = format!("{actual:#?}");
    if expected == actual {
        return 0;
    }
    println!("{path}:");
    let expected: Vec<_> = expected.lines().collect();
    let actual: Vec<_> = actual.lines().collect();
    // context: the enclosing field names above the first difference
    if let Some(first) = (0..expected.len().min(actual.len())).find(|&i| expected[i] != actual[i]) {
        for line in &expected[first.saturating_sub(12)..first] {
            println!("  context: {line}");
        }
    }
    for index in 0..expected.len().max(actual.len()) {
        let left = expected.get(index).copied().unwrap_or("<missing>");
        let right = actual.get(index).copied().unwrap_or("<missing>");
        if left != right {
            println!(
                "  line {} Python: {left}\n           Rust: {right}",
                index + 1
            );
        }
    }
    1
}

fn entities<T: Debug>(name: &str, expected: &[T], actual: &[T]) -> usize {
    let mut differences = difference(&format!("{name}.len"), &expected.len(), &actual.len());
    for index in 0..expected.len().max(actual.len()) {
        differences += difference(
            &format!("{name}[{index}]"),
            &expected.get(index),
            &actual.get(index),
        );
    }
    differences
}

fn compare(expected: &Battle, actual: &Battle) -> usize {
    let mut differences = 0;
    macro_rules! fields {
        ($($field:ident),* $(,)?) => {
            $(differences += difference(stringify!($field), &expected.$field, &actual.$field);)*
        };
    }
    macro_rules! pools {
        ($($field:ident),* $(,)?) => {
            $(differences += entities(stringify!($field), &expected.$field, &actual.$field);)*
        };
    }
    pools!(
        buildings,
        walls,
        traps,
        attackers,
        defenders,
        fields,
        pending,
        builders,
        deployments
    );
    fields!(
        rng,
        dt,
        pace,
        pace_tap,
        pace_switch,
        pace_ability,
        windup,
        fast_end,
        flyer_range,
        modifier,
        def_mult,
        def_hero_mult,
        guardian_mult,
        atk_hero_mult,
        portal_stash,
        first_destroy_t,
        first_deploy_t,
        defense_ammo,
        allow_synthetic_cc,
        battle_mode,
        upgrading,
        crafting_phase,
        crafting_date,
        builder_starts,
        portal_ready_at,
        t,
        scouting,
        scout_time,
        ended,
        town_hall,
        record,
        max_time,
        log,
        frames,
        deployed_housing,
        monolith_housing,
        uid,
        cc_building,
        cc_queue,
        cc_released,
        th,
        th_on_at,
        defense_levels,
        hero_levels,
        wall_level,
        cc_level,
        damage_by_source,
        kills_by_source,
        src,
        src_obj,
        effect,
        poison,
        clones,
        total_counted,
        destroyed_counted,
        nd_version,
        dt_version,
        dt_cache,
        onboard_cargo,
        next_deploy,
        next_cc_exit,
        field_serial,
        field_identity,
        plan,
        guardian,
        unknown_scalars,
        attacker_order,
        wall_tiles_standard,
        building_indices,
        unit_indices
    );
    for (name, left, right) in [
        ("banner_tiles", &expected.banner_tiles, &actual.banner_tiles),
        ("no_deploy", &expected.no_deploy, &actual.no_deploy),
        ("nd_cache", &expected.nd_cache, &actual.nd_cache),
    ] {
        let mut left: Vec<_> = left.iter().copied().collect();
        let mut right: Vec<_> = right.iter().copied().collect();
        left.sort();
        right.sort();
        differences += difference(name, &left, &right);
    }
    differences += difference("grid.version", &expected.grid.version, &actual.grid.version);
    differences
}
