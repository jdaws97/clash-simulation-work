//! Observed actions executed by a local controller over the engine's Stage plan.
//! No engine callbacks, targeting rules or unsupported-content checks are changed.

use std::path::Path;
use std::sync::{Arc, Mutex};

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_engine::plans::AttackPlan;
use clash_engine::pyrandom::PyRandom;
use clash_engine::runner::{Job, PreparedInputs, Runner};
use clash_engine::state::{Battle, Team, UnitRef};
use clash_plans::compile::Compiler;

use super::decode::Decoder;
use super::io::*;
use super::metrics::{mean, weighted_median};
use super::replay;
use super::Arguments;

const KEY_KINDS: [&str; 7] = ["ad", "inferno", "eagle", "scatter", "th", "mono", "xbow"];

pub fn layout(args: &Arguments, path: &Path) -> Result<Json, String> {
    let mut layout = read(path)?;
    let own = read(&clash_data::private::account(&args.root))?;
    for key in ["levels", "wall_level", "hero_levels"] {
        if let Some(value) = own.get(key) {
            put(&mut layout, key, value.clone());
        }
    }
    Ok(layout)
}

fn track(
    battle: &Battle,
    curve: &mut Vec<Json>,
    falls: &mut Json,
    stars: &mut Json,
    final_sample: bool,
) {
    if final_sample
        || curve
            .last()
            .is_none_or(|last| battle.t + 1e-9 >= last.arr()[0].f64() + 0.5)
    {
        curve.push(arr([
            num((battle.t * 10.0).round() / 10.0),
            num(battle.destruction() as f64),
        ]));
    }
    for building in &battle.buildings {
        if !building.alive && KEY_KINDS.contains(&building.key.as_str()) {
            let x = (building.x - battle.catalog.margin - building.size as f64 / 2.0).round();
            let y = (building.y - battle.catalog.margin - building.size as f64 / 2.0).round();
            let label = format!("{}({x},{y})", building.key);
            if falls.get(&label).is_none() {
                put(falls, &label, num(battle.t));
            }
        }
    }
    for star in 1..=battle.stars() {
        if stars.get(&star.to_string()).is_none() {
            put(stars, &star.to_string(), num(battle.t));
        }
    }
}

fn event_actions(replay: &Json, key: &str, jitter: f64, rng: &mut PyRandom) -> Vec<Json> {
    let mut actions = list(replay, key).to_vec();
    for action in &mut actions {
        for axis in ["x", "y"] {
            if let Some(value) = action.get(axis).cloned().filter(|_| jitter > 0.0) {
                put(
                    action,
                    axis,
                    num(value.f64() + rng.uniform(-jitter, jitter)),
                );
            }
        }
    }
    actions.sort_by(|left, right| number(left, "t", 0.0).total_cmp(&number(right, "t", 0.0)));
    actions
}

fn one(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    replay: &Json,
    seed: i64,
    strength: f64,
    level_mode: &str,
    jitter: f64,
) -> Result<Json, String> {
    let b = replay.at("battle");
    let decoder = Decoder::load(&args.root)?;
    let build = decoder.build(
        text(b, "armyShareCode", ""),
        number(b, "attacker_th", 16.0) as i64,
        0,
    )?;
    let mut base = replay::plan(compiler, &build, 0.0, seed, 1.0, "generic")?;
    put(&mut base, "strength", num(strength));
    let source = text(replay.at("source"), "layout", "");
    let layout = layout(args, &resolve(&args.root, source))?;
    let mut rng = PyRandom::new(seed);
    let drops = event_actions(replay, "deployments", jitter, &mut rng);
    let casts = event_actions(replay, "spells", jitter, &mut rng);
    let abilities = event_actions(replay, "hero_abilities", 0.0, &mut rng);
    let levels = if level_mode == "observed" {
        replay
            .get("observed_levels")
            .cloned()
            .unwrap_or_else(|| obj([] as [(&str, Json); 0]))
    } else {
        obj([] as [(&str, Json); 0])
    };
    for key in [
        "troop_levels",
        "hero_levels",
        "spell_levels",
        "cc_spell_levels",
        "pet_levels",
    ] {
        let entries = obj(levels
            .obj()
            .iter()
            .filter(|(_, value)| matches!(value, Json::Num(number) if number.fract() == 0.0))
            .cloned());
        put(&mut base, key, entries);
    }
    let mut stock = list(&base, "_spell_stock").to_vec();
    for spell in &mut stock {
        if let Some(level) = levels.get(text(spell, "name", "")) {
            if matches!(level, Json::Num(_)) {
                put(spell, "level", level.clone());
            }
        }
    }
    put(&mut base, "_spell_stock", arr(stock));
    compiler.require_legal(&mut base)?;
    let mut controller = AttackPlan::load(&base);
    let mut stage = obj([
        ("$type", string("Stage")),
        ("town_hall", build.at("th").clone()),
        ("strength", num(strength)),
        ("ticks", arr([])),
        ("revives_left", num(0.0)),
        (
            "drops",
            arr(drops.iter().flat_map(|drop| {
                let name = text(drop, "unit", "");
                let level = levels
                    .get(name)
                    .filter(|value| matches!(value, Json::Num(_)))
                    .cloned()
                    .unwrap_or(Json::Null);
                (0..number(drop, "count", 1.0) as usize).map(move |_| {
                    arr([
                        num(number(drop, "t", 0.0)),
                        string(name),
                        num(number(drop, "x", 0.0)),
                        num(number(drop, "y", 0.0)),
                        level.clone(),
                    ])
                })
            })),
        ),
        ("auto_ability_on_ko", Json::Bool(false)),
        ("observed", Json::Bool(true)),
    ]);
    for key in [
        "loadouts",
        "cc_troops",
        "cc_levels",
        "troop_levels",
        "hero_levels",
        "equipment_levels",
        "account_equipment",
        "pet_levels",
        "clan_castle_level",
    ] {
        if let Some(value) = base.get(key) {
            put(&mut stage, key, value.clone());
        }
    }
    let runner = Runner::new(
        Arc::clone(&catalog),
        PreparedInputs::new(vec![layout.clone()], vec![stage]),
    );
    let job = Job::new(0, 0, seed, number(&layout, "town_hall", 16.0) as i64, None);
    let mut battle = runner.build(&job).map_err(|error| error.to_string())?;
    for deployment in &mut battle.deployments {
        if drops.iter().any(|drop| {
            text(drop, "unit", "") == deployment.name
                && number(drop, "t", 0.0) == deployment.time
                && text(drop, "source", "").contains("clan castle")
        }) || base.get("siege").and_then(Json::opt_str) == Some(deployment.name.as_str())
        {
            deployment.source = "cc".to_owned();
        }
    }
    let mut cast_index = 0;
    let mut ability_index = 0;
    let mut curve = Vec::new();
    let mut falls = obj([] as [(&str, Json); 0]);
    let mut stars = falls.clone();
    let mut missed = Vec::new();
    while !battle.ended && battle.t < battle.max_time {
        // Match ObservedPlan.on_tick: deployments first, then scheduled actions,
        // then track, then the engine's normal combat tick.
        while battle.next_deploy < battle.deployments.len()
            && battle.deployments[battle.next_deploy].time <= battle.t
        {
            battle.deploy(battle.deployments[battle.next_deploy].clone());
            battle.next_deploy += 1;
        }
        battle.rebuild_buckets();
        while cast_index < casts.len() && number(&casts[cast_index], "t", 0.0) <= battle.t + 1e-9 {
            let cast = &casts[cast_index];
            let name = text(cast, "spell", "");
            let origin = if text(cast, "origin", "").contains("clan") {
                "donated"
            } else {
                "brewed"
            };
            if controller
                .stock
                .iter()
                .any(|stock| stock.name == name && stock.remaining > 0 && stock.origin == origin)
            {
                controller.cast_spell(
                    &mut battle,
                    name,
                    number(cast, "x", 0.0) + catalog.margin,
                    number(cast, "y", 0.0) + catalog.margin,
                    None,
                    Some(origin),
                );
            } else {
                missed.push(string(format!(
                    "{name} at {}: no matching inventory",
                    number(cast, "t", 0.0)
                )));
            }
            cast_index += 1;
        }
        while ability_index < abilities.len()
            && number(&abilities[ability_index], "t", 0.0) <= battle.t + 1e-9
        {
            let ability = &abilities[ability_index];
            let name = text(ability, "hero", "");
            let hero = battle
                .attackers_pool()
                .find(|unit| unit.name == name && unit.is_hero)
                .map(|unit| UnitRef {
                    team: Team::Atk,
                    id: unit.id,
                });
            if let Some(hero) =
                hero.filter(|hero| battle.unit(*hero).alive && !battle.unit(*hero).ability_used)
            {
                clash_engine::heroes::activate(&mut battle, hero, false);
            } else {
                missed.push(string(format!(
                    "{name} ability at {}: dead/used/absent",
                    number(ability, "t", 0.0)
                )));
            }
            ability_index += 1;
        }
        track(&battle, &mut curve, &mut falls, &mut stars, false);
        battle.step();
        if battle.destroyed_counted >= battle.total_counted
            || battle.offense_finished()
                && cast_index == casts.len()
                && ability_index == abilities.len()
        {
            break;
        }
    }
    track(&battle, &mut curve, &mut falls, &mut stars, true);
    let reason = replay::end_reason(&battle);
    let result = battle.result();
    Ok(obj([
        ("seed", num(seed as f64)),
        ("strength", num(strength)),
        ("levels", string(level_mode)),
        ("jitter_tiles", num(jitter)),
        ("stars", num(result.stars as f64)),
        ("pct", num(result.destruction as f64)),
        ("time", num(result.time)),
        ("end_reason", string(reason)),
        ("curve", arr(curve)),
        ("falls", falls),
        ("stars_t", stars),
        ("missed", arr(missed)),
        ("units_left", num(result.units_left as f64)),
    ]))
}

fn at(curve: &[Json], time: f64) -> f64 {
    let mut last = None;
    // Inspect every point in input order, including malformed earlier rows.
    for point in curve {
        if point.arr()[0].f64() <= time + 1e-9 {
            last = Some(point);
        }
    }
    last.map_or(0.0, |point| point.arr()[1].f64())
}

pub fn event_metric(real: f64, tolerance: f64, times: &[Option<f64>]) -> Json {
    let observed: Vec<_> = times.iter().flatten().copied().collect();
    let fraction = observed.len() as f64 / times.len().max(1) as f64;
    obj([
        ("real", num(real)),
        (
            "sim_median_conditional",
            weighted_median(&observed.iter().map(|time| (*time, 1.0)).collect::<Vec<_>>()),
        ),
        (
            "conditional_time_mae_s",
            mean(
                &observed
                    .iter()
                    .map(|time| (time - real).abs())
                    .collect::<Vec<_>>(),
            ),
        ),
        ("observed", num(observed.len() as f64)),
        ("missed", num((times.len() - observed.len()) as f64)),
        ("occurrence_brier", num((fraction - 1.0).powi(2))),
        (
            "within_annotation_tolerance_share",
            num(observed
                .iter()
                .filter(|time| (**time - real).abs() <= tolerance)
                .count() as f64
                / times.len().max(1) as f64),
        ),
    ])
}

fn summarize(replay: &Json, rows: &[Json]) -> Json {
    let real_curve: Vec<_> = list(replay, "destruction_every_2s")
        .iter()
        .map(|point| arr([num(number(point, "t", 0.0)), num(number(point, "pct", 0.0))]))
        .collect();
    let end = real_curve.last().map_or(0.0, |point| point.arr()[0].f64());
    let errors: Vec<_> = (4..=end as usize)
        .step_by(4)
        .map(|time| {
            rows.iter()
                .map(|row| at(list(row, "curve"), time as f64))
                .sum::<f64>()
                / rows.len().max(1) as f64
                - at(&real_curve, time as f64)
        })
        .collect();
    let mut events = obj([] as [(&str, Json); 0]);
    for event in list(replay, "key_defense_falls") {
        let label = format!(
            "{}({},{})",
            text(event, "key", ""),
            number(event, "x", 0.0),
            number(event, "y", 0.0)
        );
        let times: Vec<_> = rows
            .iter()
            .map(|row| row.at("falls").get(&label).map(Json::f64))
            .collect();
        put(
            &mut events,
            &label,
            event_metric(
                number(event, "t", 0.0),
                number(event, "plus_minus_s", 0.0),
                &times,
            ),
        );
    }
    let mut stars = obj([] as [(&str, Json); 0]);
    for event in list(replay, "stars") {
        let star = number(event, "star", 0.0) as usize;
        let times: Vec<_> = rows
            .iter()
            .map(|row| row.at("stars_t").get(&star.to_string()).map(Json::f64))
            .collect();
        put(
            &mut stars,
            &format!("star{star}"),
            event_metric(
                number(event, "t", 0.0),
                number(event, "plus_minus_s", 0.0),
                &times,
            ),
        );
    }
    obj([
        ("curve_bias_pts", mean(&errors)),
        (
            "curve_mae_pts",
            mean(&errors.iter().map(|error| error.abs()).collect::<Vec<_>>()),
        ),
        ("stars", stars),
        ("key_defense_falls", events),
    ])
}

pub fn run_file(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    path: &Path,
) -> Result<Json, String> {
    let replay = read(path)?;
    let build = Decoder::load(&args.root)?.build(
        text(replay.at("battle"), "armyShareCode", ""),
        number(replay.at("battle"), "attacker_th", 16.0) as i64,
        0,
    )?;
    let family = clash_plans::armies::family_of(&build).unwrap_or("unclassified");
    let cal = replay::current_strength(
        compiler,
        &replay::strengths(&args.root, &args.calibration())?,
        number(&build, "th", 16.0) as i64,
        family,
    );
    let strength_modes = match args.value("--strength", "both") {
        "both" => vec![cal, 1.0],
        "raw" => vec![1.0],
        "calibrated" => vec![cal],
        _ => return Err("strength must be raw, calibrated or both".to_owned()),
    };
    let level_modes = match args.value("--levels", "both") {
        "both" => vec!["engine", "observed"],
        "engine" => vec!["engine"],
        "observed" => vec!["observed"],
        _ => return Err("levels must be engine, observed or both".to_owned()),
    };
    let seeds = args.integer("--seeds", if args.flag("--quick") { 4 } else { 6 })?;
    let threads = args.integer("--threads", 1)?;
    let jitter = args.float("--jitter", 1.5)?;
    if seeds == 0 || threads == 0 || jitter < 0.0 {
        return Err("seeds/threads must be positive and jitter nonnegative".to_owned());
    }
    let mut configs = Vec::new();
    for level in level_modes {
        for strength in &strength_modes {
            let slots = Mutex::new(vec![None; seeds]);
            let next = std::sync::atomic::AtomicUsize::new(0);
            std::thread::scope(|scope| {
                for _ in 0..threads.min(seeds) {
                    let slots = &slots;
                    let next = &next;
                    let replay = &replay;
                    let catalog = Arc::clone(&catalog);
                    scope.spawn(move || loop {
                        let index = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        if index >= seeds {
                            break;
                        }
                        let result = one(
                            args,
                            compiler,
                            Arc::clone(&catalog),
                            replay,
                            1000 + index as i64,
                            *strength,
                            level,
                            if index == 0 { 0.0 } else { jitter },
                        );
                        slots.lock().expect("observed results")[index] = Some(result);
                    });
                }
            });
            let rows = slots
                .into_inner()
                .expect("observed results")
                .into_iter()
                .map(|slot| slot.expect("worker result"))
                .collect::<Result<Vec<_>, _>>()?;
            configs.push(obj([
                ("levels", string(level)),
                ("strength", num(*strength)),
                ("metrics", summarize(&replay, &rows)),
                ("rows", arr(rows)),
            ]));
        }
    }
    Ok(obj([
        ("engine", string("rust")),
        ("replay_sha256", string(file_hash(path)?)),
        ("calibration_sha256", string(file_hash(&args.calibration())?)),
        ("controller", string("observed Stage deployments, stock-checked spells and scheduled abilities; automatic abilities disabled")),
        ("configs", arr(configs)),
    ]))
}

pub fn command(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let path = args
        .positional
        .first()
        .ok_or("observed requires a replay JSON path")?;
    run_file(args, compiler, catalog, &resolve(&args.root, path))
}

pub fn all(
    args: &Arguments,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let mut paths: Vec<_> = std::fs::read_dir(args.root.join("data/source/replays"))
        .map_err(|error| error.to_string())?
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect();
    paths.sort();
    let mut results = Vec::new();
    for path in paths {
        let real = read(&path)?;
        if list(&real, "deployments").is_empty() || list(&real, "destruction_every_2s").is_empty() {
            continue;
        }
        let result = run_file(args, compiler, Arc::clone(&catalog), &path)?;
        results.push((
            path.file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned(),
            result,
        ));
    }
    Ok(obj(results))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_events_are_not_fake_999_second_observations() {
        let result = event_metric(40.0, 2.0, &[Some(41.0), None]);
        assert_eq!(result.at("sim_median_conditional"), &num(41.0));
        assert_eq!(result.at("occurrence_brier"), &num(0.25));
        assert_eq!(result.at("missed"), &num(1.0));
    }
}
