mod battle;
mod defense;
pub mod geom;
pub mod grid;
pub mod input;
mod units;

use std::env;
use std::fmt::Write;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use battle::{Battle, ResultRow};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("spike-engine: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args_os().skip(1);
    let usage = "usage: spike-engine <input path> <output path>";
    let input_path = PathBuf::from(args.next().ok_or(usage)?);
    let output_path = PathBuf::from(args.next().ok_or(usage)?);
    if args.next().is_some() {
        return Err(usage.to_owned());
    }
    let input = input::load(&input_path)?;
    if input.world != 50 {
        return Err("this spike requires world 50 (a 100 by 100 grid)".to_owned());
    }
    if input.dt != 0.1 {
        return Err("this spike requires dt 0.1".to_owned());
    }
    if input.scenarios.is_empty() {
        return Err("missing scenarios".to_owned());
    }
    for unit in &input.units {
        if unit.name != "Valkyrie" && unit.name != "Dragon" {
            return Err(format!("unsupported troop {:?}", unit.name));
        }
    }
    for building in &input.buildings {
        if building.key == "th" && building.weapon.is_some() {
            return Err("this spike requires a weaponless Town Hall".to_owned());
        }
    }
    for wall in &input.walls {
        if !(0..50).contains(&wall.tx) || !(0..50).contains(&wall.ty) {
            return Err("wall coordinates must be inside the world".to_owned());
        }
    }
    for scenario in &input.scenarios {
        for drop in &scenario.drops {
            if !input.units.iter().any(|unit| unit.name == drop.name) {
                return Err(format!("missing unit record for {:?}", drop.name));
            }
            if !(0.0..50.0).contains(&drop.x) || !(0.0..50.0).contains(&drop.y) {
                return Err("deployment coordinates must be inside the world".to_owned());
            }
        }
    }

    if let Ok(k) = std::env::var("SPIKE_TRACE") {
        // SPIKE_TRACE=<scenario index>: write that battle's per-tick trace instead.
        let k: usize = k.parse().map_err(|_| "SPIKE_TRACE must be a scenario index")?;
        let lines = Battle::new(&input, &input.scenarios[k]).trace();
        fs::write(&output_path, lines.join("\n") + "\n").map_err(|error| error.to_string())?;
        return Ok(());
    }
    let mut rows = Vec::with_capacity(input.scenarios.len());
    let started = Instant::now();
    for scenario in &input.scenarios {
        rows.push(Battle::new(&input, scenario).run());
    }
    let seconds_per_battle = started.elapsed().as_secs_f64() / rows.len() as f64;
    let output = output_json(seconds_per_battle, &rows);
    fs::write(&output_path, output)
        .map_err(|error| format!("cannot write {}: {error}", output_path.display()))?;
    let mean_destruction = rows.iter().map(|row| row.destruction).sum::<f64>() / rows.len() as f64;
    let mean_stars = rows.iter().map(|row| row.stars as f64).sum::<f64>() / rows.len() as f64;
    println!(
        "battles={} ms_per_battle={:.3} mean_destruction={:.3} mean_stars={:.3}",
        rows.len(),
        seconds_per_battle * 1000.0,
        mean_destruction,
        mean_stars,
    );
    Ok(())
}

fn output_json(seconds_per_battle: f64, rows: &[ResultRow]) -> String {
    let mut output = String::new();
    write!(
        output,
        "{{\"engine\": \"rust\", \"seconds_per_battle\": {seconds_per_battle:?}, \"rows\": ["
    )
    .expect("writing to a String");
    for (index, row) in rows.iter().enumerate() {
        if index != 0 {
            output.push_str(", ");
        }
        write!(
            output,
            "{{\"angle\": {:?}, \"seed\": {}, \"stars\": {}, \"destruction\": {:?}, \"time\": {:?}, \"fell\": {{",
            row.angle, row.seed, row.stars, row.destruction, row.time,
        )
        .expect("writing to a String");
        for (index, (building, time)) in row.fell.iter().enumerate() {
            if index != 0 {
                output.push_str(", ");
            }
            write!(output, "\"{building}\": {time:?}").expect("writing to a String");
        }
        write!(output, "}}, \"units_left\": {}}}", row.units_left).expect("writing to a String");
    }
    output.push_str("]}\n");
    output
}
