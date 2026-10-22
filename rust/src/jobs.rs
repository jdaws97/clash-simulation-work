//! Task 5 CLI: shared prepared inputs, thread-local battles, ordered results.

use std::any::Any;
use std::fmt::Debug;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Instant;

use crate::catalog::Catalog;
use crate::json::{self, Json};
use crate::load::{self, Node};
use crate::setup;
use crate::state::Battle;
use crate::trace;

fn read(path: &Path) -> Result<Json, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    json::parse(&text).map_err(|error| format!("{}: {error}", path.display()))
}

fn build_job(input: &Json, index: usize, catalog: Arc<Catalog>) -> Battle {
    Node::new(input, "jobs").keys(&["layouts", "plans", "jobs"]);
    let jobs = input.at("jobs").arr();
    let job = jobs
        .get(index)
        .unwrap_or_else(|| panic!("job index {index} outside {} jobs", jobs.len()));
    let layout_index = Node::new(job.at("layout"), "job.layout").usize();
    let plan_index = Node::new(job.at("plan"), "job.plan").usize();
    let layout = input.at("layouts").arr().get(layout_index)
        .expect("job layout index out of range");
    let plan = input.at("plans").arr().get(plan_index)
        .expect("job plan index out of range");
    setup::build(layout, plan, job, catalog)
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
                build_job(&input, 0, catalog)
            } else {
                // Also accept a self-contained {layout, plan, ...options} job.
                setup::build(input.at("layout"), input.at("plan"), &input, catalog)
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
            let mut battle = build_job(&input, index, catalog);
            let file = File::create(&paths[2])
                .map_err(|error| format!("{}: {error}", paths[2].display()))?;
            let mut out = BufWriter::new(file);
            trace::write_trace(&mut battle, &mut out).map_err(|error| error.to_string())?;
            out.flush().map_err(|error| error.to_string())
        }
        "jobs" if paths.len() == 2 || paths.len() == 4 => {
            let threads = if paths.len() == 4 {
                if paths[2].as_os_str() != "--threads" {
                    return Err("expected --threads N".to_owned());
                }
                paths[3]
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
            run(&read(&paths[0])?, &paths[1], threads, catalog)
        }
        _ => Err("usage: setup-check <battle.json> <job.json> | trace-job <jobs.json> <k> <trace.txt> | jobs <jobs.json> <results.jsonl> [--threads N]".to_owned()),
    }
}

struct Metrics {
    stars: usize,
    destruction: usize,
    th_destroyed: bool,
    time: f64,
    units_left: usize,
}

fn panic_message(error: Box<dyn Any + Send>) -> String {
    if let Some(message) = error.downcast_ref::<String>() {
        message.clone()
    } else if let Some(message) = error.downcast_ref::<&str>() {
        (*message).to_owned()
    } else {
        "battle panicked".to_owned()
    }
}

fn run(input: &Json, output: &Path, threads: usize, catalog: Arc<Catalog>) -> Result<(), String> {
    Node::new(input, "jobs").keys(&["layouts", "plans", "jobs"]);
    let count = input.at("jobs").arr().len();
    let counter = AtomicUsize::new(0);
    let started = Instant::now();
    // Json inputs and the catalog are shared read-only. Rc plan vectors and all
    // mutable simulation state are created and dropped within their worker.
    let batches = std::thread::scope(|scope| {
        let mut handles = Vec::new();
        for _ in 0..threads.min(count) {
            let catalog = &catalog;
            let counter = &counter;
            handles.push(scope.spawn(move || {
                let mut results = Vec::new();
                loop {
                    let index = counter.fetch_add(1, Ordering::Relaxed);
                    if index >= count {
                        break;
                    }
                    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        let mut battle = build_job(input, index, Arc::clone(catalog));
                        let result = battle.run();
                        Metrics {
                            stars: result.stars,
                            destruction: result.destruction,
                            th_destroyed: result.th_destroyed,
                            time: result.time,
                            units_left: result.units_left,
                        }
                    }))
                    .map_err(panic_message);
                    results.push((index, result));
                }
                results
            }));
        }
        handles
            .into_iter()
            .map(|handle| handle.join().map_err(panic_message))
            .collect::<Result<Vec<_>, _>>()
    })?;
    let elapsed = started.elapsed().as_secs_f64();
    let mut results: Vec<Option<Metrics>> = (0..count).map(|_| None).collect();
    let mut failures = Vec::new();
    for batch in batches {
        for (index, result) in batch {
            match result {
                Ok(result) => results[index] = Some(result),
                Err(error) => failures.push((index, error)),
            }
        }
    }
    failures.sort_by_key(|(index, _)| *index);
    if !failures.is_empty() {
        for (index, error) in &failures {
            eprintln!("job {index}: {error}");
        }
        return Err(format!("{} jobs failed", failures.len()));
    }
    let file = File::create(output)
        .map_err(|error| format!("{}: {error}", output.display()))?;
    let mut out = BufWriter::new(file);
    for (index, result) in results.into_iter().enumerate() {
        let result = result.expect("worker omitted a job");
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
    for index in 0..expected.len().max(actual.len()) {
        let left = expected.get(index).copied().unwrap_or("<missing>");
        let right = actual.get(index).copied().unwrap_or("<missing>");
        if left != right {
            println!("  line {} Python: {left}\n           Rust: {right}", index + 1);
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
    pools!(buildings, walls, traps, attackers, defenders, fields, pending, builders, deployments);
    fields!(rng, dt, pace, pace_tap, pace_switch, pace_ability, windup, fast_end,
        modifier, def_mult, def_hero_mult, guardian_mult, atk_hero_mult, portal_stash,
        first_destroy_t, first_deploy_t, defense_ammo, allow_synthetic_cc, battle_mode,
        upgrading, crafting_phase, crafting_date, builder_starts, portal_ready_at, t,
        scouting, scout_time, ended, town_hall, record, max_time, log, frames,
        deployed_housing, monolith_housing, uid, cc_building, cc_queue, cc_released,
        th, th_on_at, defense_levels, hero_levels, wall_level, cc_level,
        damage_by_source, kills_by_source, src, src_obj, effect, poison, clones,
        total_counted, destroyed_counted, nd_version, dt_version, dt_cache,
        onboard_cargo, next_deploy, next_cc_exit, field_serial, field_identity,
        plan, guardian, unknown_scalars, attacker_order, wall_tiles_standard,
        building_indices, unit_indices);
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
