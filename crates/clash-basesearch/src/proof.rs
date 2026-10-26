//! Executable synthetic M2 proofs. No Python, golden recording, or real-game
//! calibration. The CLI writes a receipt tied to executable/catalog/rules.
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::json::Json;
use crate::layout::json::{encode, identity, number, object, string};
use crate::layout::model::{AdmissionPolicy, HeroBinding, Layout, Mode};
use crate::layout::{admit, AdmittedLayout, BaseRules};
use crate::stats::Level;

use super::anneal::{anneal, AnnealConfig};
use super::generate::{generate, preset, Style, TownHallZone};
use super::operators::guided::{Guidance, Guide};
use super::operators::{propose, Operator};
use super::repair::{conserved, finish, RepairLimits};
use super::{Context, Proposal, Rejection};

fn require(condition: bool, message: &str) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(message.to_owned())
    }
}

fn explain(error: Rejection) -> String {
    format!("{error:?}")
}

fn build(context: &Context, candidate: &AdmittedLayout) -> Result<(), String> {
    let plan = object([
        ("$type", string("Stage")),
        ("drops", Json::Arr(Vec::new())),
        ("ticks", Json::Arr(Vec::new())),
        ("revives_left", number(0)),
        ("strength", number(1)),
        ("loadouts", Json::Obj(Vec::new())),
        ("town_hall", number(candidate.layout().town_hall as i32)),
    ]);
    let options = object([("town_hall", number(candidate.layout().town_hall as i32))]);
    crate::setup::build(
        &candidate.engine_json(),
        &plan,
        &options,
        context.catalog.clone(),
    )
    .map_err(|e| format!("accepted candidate failed engine setup: {e}"))?;
    Ok(())
}

fn fixture(context: &Context, th: i64) -> Result<AdmittedLayout, String> {
    let parent =
        preset(context, th, Style::Grid, TownHallZone::Edge, th as u64).map_err(explain)?;
    let mut layout = parent.layout().clone();
    // Reverse same-size non-TH slots so diagnostics and inward/spread macros
    // exercise exposed strong defenses as well as the generator's role order.
    let mut groups = BTreeMap::<i32, Vec<usize>>::new();
    for (i, building) in layout.buildings.iter().enumerate() {
        if building.key != "th" {
            groups
                .entry(super::spatial::size(context, &building.key, false).map_err(explain)?)
                .or_default()
                .push(i);
        }
    }
    for group in groups.values() {
        let positions: Vec<_> = group
            .iter()
            .rev()
            .map(|&i| layout.buildings[i].position)
            .collect();
        for (&i, position) in group.iter().zip(positions) {
            layout.buildings[i].position = position;
        }
    }
    // Mixed walls exercise per-instance level ownership in every proposal.
    for (i, wall) in layout.walls.iter_mut().enumerate() {
        if i % 3 == 0 {
            if let Some(Level::Int(level)) = &mut wall.level {
                *level -= 1;
            }
        }
    }
    let banners: Vec<_> = layout
        .buildings
        .iter()
        .filter(|b| b.key == "banner")
        .map(|b| b.id.clone())
        .collect();
    layout.setup.heroes = [
        "Archer Queen",
        "Barbarian King",
        "Grand Warden",
        "Royal Champion",
    ]
    .iter()
    .zip(banners)
    .map(|(&hero, banner)| HeroBinding {
        hero: hero.to_owned(),
        banner: Some(banner),
    })
    .collect();
    if th == 18 {
        layout.setup.guardian = Some("Longshot".to_owned());
    }
    admit(
        layout,
        &context.rules,
        context.catalog.clone(),
        parent.policy(),
    )
    .map_err(|r| encode(&r.to_json()))
}

fn guidance(parent: &AdmittedLayout) -> Guidance {
    let ground: BTreeMap<_, _> = (0..44)
        .flat_map(|y| (0..44).map(move |x| ((x, y), ((x * 11 + y * 7) % 67 + 1) as u64)))
        .collect();
    Guidance {
        layout_identity: parent.physical_identity().to_owned(),
        account_identity: parent.account_identity().to_owned(),
        policy_identity: "synthetic-policy-v1".to_owned(),
        air: BTreeMap::from([((13, 17), 1000), ((25, 28), 999)]),
        heroes: BTreeMap::from([((18, 18), 1000)]),
        breaches: BTreeMap::from([((6, 20), 1000), ((36, 24), 30)]),
        early_loss: parent
            .layout()
            .buildings
            .iter()
            .enumerate()
            .map(|(i, b)| {
                (
                    b.id.clone(),
                    if super::spatial::role(&b.key) <= 55 {
                        100 + i as u64
                    } else {
                        1
                    },
                )
            })
            .collect(),
        ground,
    }
}

fn receipt(result: &Result<Proposal, Rejection>) -> String {
    match result {
        Ok(p) => format!(
            "{}:{}:{}:{:?}:{:?}:{:?}",
            p.candidate.physical_identity(),
            p.operator,
            p.seed,
            p.parents,
            p.changed_instances,
            p.repair_actions
        ),
        Err(rejection) => format!("{rejection:?}"),
    }
}

fn proposal(
    context: &Context,
    parent: &AdmittedLayout,
    operator: Operator,
    seed: u64,
    diagnostics: &Guidance,
) -> Result<Proposal, Rejection> {
    propose(
        context,
        parent,
        operator,
        seed,
        Some(Guide {
            diagnostics,
            policy_identity: "synthetic-policy-v1",
        }),
        RepairLimits::default(),
    )
}

fn determinism(context: &Context, parents: &[AdmittedLayout]) -> Result<usize, String> {
    let diagnostics: Vec<_> = parents.iter().map(guidance).collect();
    let mates: Vec<_> = parents
        .iter()
        .map(|parent| {
            generate(context, parent, Style::Rings, TownHallZone::Mid, 37)
                .map(|p| p.candidate)
                .map_err(explain)
        })
        .collect::<Result<_, _>>()?;
    let operator_jobs = parents.len() * Operator::ALL.len() * 8;
    let generator_jobs = parents.len() * Style::ALL.len() * 3;
    let jobs = operator_jobs + generator_jobs + parents.len() * 8;
    let run = |workers: usize| {
        std::thread::scope(|scope| {
            let handles: Vec<_> = (0..workers)
                .map(|worker| {
                    let diagnostics = &diagnostics;
                    let mates = &mates;
                    scope.spawn(move || {
                        (worker..jobs)
                            .step_by(workers)
                            .map(|job| {
                                let result = if job < operator_jobs {
                                    let parent = job / (Operator::ALL.len() * 8);
                                    let operator = Operator::ALL[(job / 8) % Operator::ALL.len()];
                                    proposal(
                                        context,
                                        &parents[parent],
                                        operator,
                                        (job % 8) as u64,
                                        &diagnostics[parent],
                                    )
                                } else if job < operator_jobs + generator_jobs {
                                    let index = job - operator_jobs;
                                    generate(
                                        context,
                                        &parents[index / (Style::ALL.len() * 3)],
                                        Style::ALL[(index / 3) % Style::ALL.len()],
                                        TownHallZone::ALL[index % 3],
                                        index as u64,
                                    )
                                } else {
                                    let index = job - operator_jobs - generator_jobs;
                                    super::crossover::crossover(
                                        context,
                                        &parents[index / 8],
                                        &mates[index / 8],
                                        index as u64,
                                        RepairLimits::default(),
                                    )
                                };
                                if let Ok(proposal) = &result {
                                    build(context, &proposal.candidate)?;
                                }
                                Ok((job, receipt(&result)))
                            })
                            .collect::<Result<Vec<_>, String>>()
                    })
                })
                .collect();
            let mut rows = Vec::new();
            for handle in handles {
                rows.extend(handle.join().map_err(|_| "determinism worker panicked")??);
            }
            rows.sort_by_key(|(job, _)| *job);
            Ok::<_, String>(rows)
        })
    };
    let expected = run(1)?;
    for workers in [4, 16, 1] {
        require(
            run(workers)? == expected,
            "proposal/repair differs across threads or repeated runs",
        )?;
    }
    Ok(jobs)
}

fn repair_proofs(context: &Context, parent: &AdmittedLayout) -> Result<(), String> {
    let original = parent.engine_json();
    let mut broken = parent.layout().clone();
    broken.buildings.remove(0);
    broken.traps.remove(0);
    broken.walls.remove(0);
    broken.buildings[0].position = (-1, -1);
    broken.setup.cc_troops.push(crate::layout::model::CcEntry {
        name: "Archer".to_owned(),
        source: None,
        level: None,
        count: 1,
        object_form: true,
    });
    let repaired = finish(
        context,
        parent,
        broken.clone(),
        "synthetic-repair",
        81,
        RepairLimits::default(),
    )
    .map_err(explain)?;
    require(
        conserved(parent.layout(), repaired.candidate.layout()),
        "missing piece restoration changed inventory",
    )?;
    build(context, &repaired.candidate)?;
    let repeated = finish(
        context,
        parent,
        broken.clone(),
        "synthetic-repair",
        81,
        RepairLimits::default(),
    );
    require(
        receipt(&Ok(repaired)) == receipt(&repeated),
        "repair not deterministic",
    )?;
    require(
        matches!(
            finish(
                context,
                parent,
                broken,
                "bounded",
                1,
                RepairLimits {
                    tile_checks: 0,
                    relocations: 0
                }
            ),
            Err(Rejection::RepairBudget)
        ),
        "repair ignored zero budget",
    )?;
    for kind in 0..5 {
        let mut invalid = parent.layout().clone();
        match kind {
            0 => invalid.buildings[0].key = "unknown-content".to_owned(),
            1 => {
                invalid
                    .setup
                    .levels
                    .insert("cc".to_owned(), Level::Int(10000));
            }
            2 => invalid.walls[0].level = Some(Level::Int(1)),
            3 => invalid.traps.push(invalid.traps[0].clone()),
            _ => invalid.buildings[0].mode = Some(Mode::NW),
        }
        require(
            finish(
                context,
                parent,
                invalid,
                "invalid",
                1,
                RepairLimits::default(),
            )
            .is_err(),
            "repair silently replaced unknown content or upgraded levels",
        )?;
    }
    let mut gears = parent.layout().clone();
    for b in &mut gears.buildings {
        if b.key == "mortar" {
            b.mode = Some(Mode::Geared);
        }
    }
    if let Ok(repaired) = finish(
        context,
        parent,
        gears,
        "gear-repair",
        1,
        RepairLimits::default(),
    ) {
        require(
            repaired
                .candidate
                .layout()
                .buildings
                .iter()
                .filter(|b| b.key == "mortar" && b.mode.is_some_and(Mode::geared))
                .count()
                <= 1,
            "gear repair kept duplicates",
        )?;
        build(context, &repaired.candidate)?;
    } else {
        return Err("valid duplicate gear repair failed".to_owned());
    }
    let diag = guidance(parent);
    let stale = Guide {
        diagnostics: &diag,
        policy_identity: "different-policy",
    };
    require(
        matches!(
            propose(
                context,
                parent,
                Operator::TrafficTraps,
                1,
                Some(stale),
                RepairLimits::default()
            ),
            Err(Rejection::StaleGuidance)
        ),
        "stale diagnostic policy reused",
    )?;
    let mut diag = diag;
    diag.layout_identity = "different-layout".to_owned();
    require(
        matches!(
            proposal(context, parent, Operator::TrafficTraps, 1, &diag),
            Err(Rejection::StaleGuidance)
        ),
        "stale diagnostic layout reused",
    )?;
    let mut transformed = parent.layout().clone();
    // Make defaults explicit for an exact representation round trip.
    for b in &mut transformed.buildings {
        if matches!(b.key.as_str(), "sweeper" | "firespitter") && b.mode.is_none() {
            b.mode = Some(Mode::E);
        }
    }
    let before = transformed.clone();
    super::operators::macro_ops::transpose(&mut transformed);
    super::operators::macro_ops::transpose(&mut transformed);
    require(
        before == transformed,
        "transpose round trip changed pieces, levels or facing",
    )?;
    require(
        parent.engine_json() == original,
        "failed repair mutated parent",
    )?;
    Ok(())
}

fn tiny(context: &Context) -> Result<AdmittedLayout, String> {
    let raw = object([
        (
            "name",
            string("declared synthetic four-state annealing space"),
        ),
        ("town_hall", number(16)),
        (
            "buildings",
            Json::Arr(vec![object([
                ("key", string("th")),
                ("x", number(0)),
                ("y", number(0)),
            ])]),
        ),
        ("heroes", Json::Arr(Vec::new())),
        ("cc_troops", Json::Arr(Vec::new())),
        ("guardian", Json::Null),
    ]);
    let layout = Layout::from_json(&raw).map_err(|r| encode(&r.to_json()))?;
    admit(
        layout,
        &context.rules,
        context.catalog.clone(),
        &AdmissionPolicy {
            require_full: false,
            ..AdmissionPolicy::default()
        },
    )
    .map_err(|r| encode(&r.to_json()))
}

fn annealing_proof(context: &Context) -> Result<Json, String> {
    let start = tiny(context)?;
    let values: [f64; 4] = [1.0, 0.0, 5.0, 2.0];
    let mut enumerable = Vec::new();
    for x in 0..4 {
        let mut layout = start.layout().clone();
        layout.buildings[0].position.0 = x;
        let candidate = admit(
            layout,
            &context.rules,
            context.catalog.clone(),
            start.policy(),
        )
        .map_err(|r| encode(&r.to_json()))?;
        build(context, &candidate)?;
        enumerable.push((candidate.physical_identity().to_owned(), values[x as usize]));
    }
    let best = enumerable
        .iter()
        .max_by(|a, b| a.1.total_cmp(&b.1))
        .unwrap();
    let run = |temperature| {
        anneal(
            start.clone(),
            AnnealConfig {
                steps: 128,
                temperature,
                seed: 73,
            },
            |parent, _, seed| {
                let mut draft = parent.layout().clone();
                draft.buildings[0].position.0 = (draft.buildings[0].position.0 + 1) % 4;
                finish(
                    context,
                    parent,
                    draft,
                    "tiny-next-state",
                    seed,
                    RepairLimits::default(),
                )
            },
            |layout| Ok(values[layout.layout().buildings[0].position.0 as usize]),
        )
    };
    let result = run(3.0)?;
    require(
        result.best_score == best.1 && result.best.physical_identity() == best.0,
        "annealing missed known enumerated optimum",
    )?;
    let repeated = run(3.0)?;
    require(
        result.trajectory == repeated.trajectory
            && result.best.physical_identity() == repeated.best.physical_identity(),
        "annealing differs across runs",
    )?;
    require(
        run(0.0)?.best_score == 1.0,
        "zero-temperature annealing accepted downhill move",
    )?;
    require(
        anneal(
            start,
            AnnealConfig {
                steps: 1,
                temperature: f64::NAN,
                seed: 0,
            },
            |_, _, _| unreachable!(),
            |_| unreachable!(),
        )
        .is_err(),
        "nonfinite temperature accepted",
    )?;
    Ok(object([
        ("states", number(4)),
        ("optimum", Json::Num(result.best_score)),
        ("accepted", number(result.accepted as i32)),
        ("winner", string(result.best.physical_identity())),
    ]))
}

fn owned_proof(context: &Context) -> Result<usize, String> {
    use crate::layout::model::InventoryPolicy;
    let raw = crate::json::parse(
        r#"{
        "name":"declared synthetic lower-level owned inventory",
        "town_hall":16,
        "buildings":[{"key":"th","x":0,"y":0},{"key":"cannon","x":10,"y":10}],
        "traps":[{"key":"bomb","x":20,"y":20}],
        "walls":[[30,30],[31,30],[32,30]],
        "wall_level":16,
        "wall_levels":[{"x":31,"y":30,"level":15},{"x":32,"y":30,"level":14}],
        "levels":{"cannon":5,"trap:bomb":2},
        "heroes":[],"cc_troops":[],"guardian":null
    }"#,
    )
    .map_err(|e| e.to_string())?;
    let layout = Layout::from_json(&raw).map_err(|r| encode(&r.to_json()))?;
    let policy = AdmissionPolicy {
        require_all_walls: true,
        inventory: InventoryPolicy::Owned {
            snapshot_id: "declared-synthetic-M2-owned".to_owned(),
            buildings: BTreeMap::from([("th".to_owned(), 1), ("cannon".to_owned(), 1)]),
            traps: BTreeMap::from([("bomb".to_owned(), 1)]),
            walls: 3,
            levels: layout.setup.levels.clone(),
            hero_levels: BTreeMap::new(),
            wall_level: Level::Int(16),
            wall_levels: vec![Level::Int(16), Level::Int(15), Level::Int(14)],
            geared: Default::default(),
        },
        ..AdmissionPolicy::default()
    };
    let parent = admit(layout, &context.rules, context.catalog.clone(), &policy)
        .map_err(|r| encode(&r.to_json()))?;
    let mut accepted = 0;
    let diagnostics = guidance(&parent);
    for operator in Operator::ALL {
        for seed in 0..8 {
            if let Ok(p) = proposal(context, &parent, operator, seed, &diagnostics) {
                require(
                    conserved(parent.layout(), p.candidate.layout())
                        && parent.account_identity() == p.candidate.account_identity(),
                    "owned account upgraded or lost pieces",
                )?;
                build(context, &p.candidate)?;
                accepted += 1;
            }
        }
    }
    for style in Style::ALL {
        let p = generate(context, &parent, style, TownHallZone::Mid, 19).map_err(explain)?;
        require(
            conserved(parent.layout(), p.candidate.layout()),
            "owned generator changed inventory/levels",
        )?;
        build(context, &p.candidate)?;
        let child = super::crossover::crossover(
            context,
            &parent,
            &p.candidate,
            71,
            RepairLimits::default(),
        );
        if let Ok(child) = child {
            build(context, &child.candidate)?;
            accepted += 1;
        }
        accepted += 1;
    }
    require(accepted > 0, "owned proof accepted nothing")?;
    Ok(accepted)
}

fn rejection_code(rejection: &Rejection) -> &'static str {
    match rejection {
        Rejection::NotApplicable(_) => "not_applicable",
        Rejection::ContextMismatch => "context",
        Rejection::Conservation(_) => "conservation",
        Rejection::RepairBudget => "repair_budget",
        Rejection::Admission(_) => "admission",
        Rejection::StaleGuidance => "stale_guidance",
        Rejection::InvalidConfig(_) => "invalid_config",
    }
}

pub fn run(context: &Context, seeds: usize) -> Result<Json, String> {
    require(seeds > 0, "proof seeds must be positive")?;
    let parents: Vec<_> = (16..=18)
        .map(|th| fixture(context, th))
        .collect::<Result<_, _>>()?;
    let mut accepted_total = 0;
    let mut rows = Vec::new();
    for parent in &parents {
        build(context, parent)?;
        repair_proofs(context, parent)?;
        let diagnostics = guidance(parent);
        let original = parent.engine_json();
        for operator in Operator::ALL {
            let (accepted, rejects) = std::thread::scope(|scope| {
                let workers = seeds.min(8);
                let handles: Vec<_> = (0..workers)
                    .map(|worker| {
                        let diagnostics = &diagnostics;
                        scope.spawn(move || {
                            let mut accepted = 0;
                            let mut rejects = BTreeMap::<&str, usize>::new();
                            for seed in (worker..seeds).step_by(workers) {
                                let result =
                                    proposal(context, parent, operator, seed as u64, diagnostics);
                                match result {
                                    Ok(p) => {
                                        require(
                                            conserved(parent.layout(), p.candidate.layout()),
                                            "operator failed ordered inventory/level conservation",
                                        )?;
                                        require(
                                            parent.account_identity()
                                                == p.candidate.account_identity(),
                                            "operator changed account identity",
                                        )?;
                                        require(
                                            !p.changed_instances.is_empty(),
                                            "accepted no-op lacks changed instances",
                                        )?;
                                        let readmitted = admit(
                                            p.candidate.layout().clone(),
                                            &context.rules,
                                            context.catalog.clone(),
                                            parent.policy(),
                                        )
                                        .map_err(|r| encode(&r.to_json()))?;
                                        require(
                                            readmitted.physical_identity()
                                                == p.candidate.physical_identity(),
                                            "accepted proposal does not re-admit",
                                        )?;
                                        build(context, &p.candidate)?;
                                        accepted += 1;
                                    }
                                    Err(rejection) => {
                                        require(
                                            !matches!(
                                                rejection,
                                                Rejection::Conservation(_)
                                                    | Rejection::ContextMismatch
                                                    | Rejection::StaleGuidance
                                                    | Rejection::InvalidConfig(_)
                                            ),
                                            &format!(
                                "operator {operator:?} violated internal invariant: {rejection:?}"
                            ),
                                        )?;
                                        *rejects.entry(rejection_code(&rejection)).or_default() +=
                                            1;
                                    }
                                }
                            }
                            Ok::<_, String>((accepted, rejects))
                        })
                    })
                    .collect();
                let mut accepted = 0;
                let mut rejects = BTreeMap::<&str, usize>::new();
                for handle in handles {
                    let (count, reasons) = handle
                        .join()
                        .map_err(|_| "operator proof worker panicked")??;
                    accepted += count;
                    for (reason, count) in reasons {
                        *rejects.entry(reason).or_default() += count;
                    }
                }
                Ok::<_, String>((accepted, rejects))
            })?;
            accepted_total += accepted;
            require(parent.engine_json() == original, "proposal mutated parent")?;
            if seeds >= 64 {
                eprintln!(
                    "M2 TH{} {operator:?}: attempts={seeds} accepted={accepted}",
                    parent.layout().town_hall
                );
            }
            rows.push(object([
                ("town_hall", number(parent.layout().town_hall as i32)),
                ("operator", string(operator.name())),
                ("attempts", number(seeds as i32)),
                ("accepted", number(accepted)),
                (
                    "rejections",
                    Json::Obj(
                        rejects
                            .into_iter()
                            .map(|(k, v)| (k.to_owned(), number(v as i32)))
                            .collect(),
                    ),
                ),
            ]));
        }
        eprintln!(
            "M2 operators TH{}: {} seeds/operator complete",
            parent.layout().town_hall,
            seeds
        );
    }
    // Require each operator to produce a physical change somewhere it applies.
    // Low smoke-test seed counts need not hit every randomized applicability.
    if seeds >= 64 {
        for operator in Operator::ALL {
            let accepted: i64 = rows
                .iter()
                .filter(|r| r.at("operator").str() == operator.name())
                .map(|r| r.at("accepted").i64())
                .sum();
            require(
                accepted > 0,
                &format!("operator coverage empty: {operator:?}"),
            )?;
        }
    }
    let mut generator_rows = Vec::new();
    for parent in &parents {
        for style in Style::ALL {
            for zone in TownHallZone::ALL {
                let mut accepted = 0;
                for seed in 0..4 {
                    match generate(context, parent, style, zone, seed) {
                        Ok(p) => {
                            build(context, &p.candidate)?;
                            let th = super::spatial::th(p.candidate.layout());
                            let expected_offset = match zone {
                                TownHallZone::Central => 0,
                                TownHallZone::Mid => 100,
                                TownHallZone::Edge => 324,
                            };
                            require(
                                super::spatial::distance((th.0 + 2, th.1 + 2), (22, 22))
                                    == expected_offset,
                                "generator missed explicit TH zone",
                            )?;
                            require(
                                conserved(parent.layout(), p.candidate.layout()),
                                "generator lost inventory",
                            )?;
                            let repeated = generate(context, parent, style, zone, seed);
                            require(
                                receipt(&Ok(p)) == receipt(&repeated),
                                "generator nondeterminism",
                            )?;
                            accepted += 1;
                        }
                        Err(Rejection::RepairBudget) => {}
                        Err(error) => {
                            return Err(format!("generator {style:?}/{zone:?}: {error:?}"))
                        }
                    }
                }
                require(
                    accepted > 0,
                    &format!(
                        "generator never packed {style:?}/{zone:?}/TH{}",
                        parent.layout().town_hall
                    ),
                )?;
                generator_rows.push(object([
                    ("town_hall", number(parent.layout().town_hall as i32)),
                    ("style", string(format!("{style:?}"))),
                    ("zone", string(format!("{zone:?}"))),
                    ("attempts", number(4)),
                    ("accepted", number(accepted)),
                ]));
            }
        }
    }
    let mut crossovers = 0;
    for parent in &parents {
        let b = generate(context, parent, Style::Rings, TownHallZone::Mid, 37)
            .map_err(explain)?
            .candidate;
        for seed in 0..seeds {
            let result = super::crossover::crossover(
                context,
                parent,
                &b,
                seed as u64,
                RepairLimits::default(),
            );
            let repeated = super::crossover::crossover(
                context,
                parent,
                &b,
                seed as u64,
                RepairLimits::default(),
            );
            require(
                receipt(&result) == receipt(&repeated),
                "crossover nondeterminism",
            )?;
            if let Ok(p) = result {
                build(context, &p.candidate)?;
                require(
                    conserved(parent.layout(), p.candidate.layout()),
                    "crossover changed inventory",
                )?;
                crossovers += 1;
            }
        }
        let mut incompatible = b.layout().clone();
        incompatible.walls[0].level = Some(Level::Int(1));
        let incompatible = admit(
            incompatible,
            &context.rules,
            context.catalog.clone(),
            b.policy(),
        )
        .map_err(|r| encode(&r.to_json()))?;
        require(
            matches!(
                super::crossover::crossover(
                    context,
                    parent,
                    &incompatible,
                    0,
                    RepairLimits::default()
                ),
                Err(Rejection::Conservation(_))
            ),
            "crossover mixed accounts/levels",
        )?;
    }
    require(crossovers > 0, "no crossover accepted")?;
    let deterministic_jobs = determinism(context, &parents)?;
    let owned_builds = owned_proof(context)?;
    Ok(object([
        ("schema_version", number(1)),
        ("status", string("passed")),
        (
            "evidence",
            string("declared synthetic model/search correctness; not real-game calibration"),
        ),
        ("seeds_per_th_operator", number(seeds as i32)),
        (
            "operator_attempts",
            number((seeds * parents.len() * Operator::ALL.len()) as i32),
        ),
        ("operator_accepted_engine_builds", number(accepted_total)),
        ("operator_coverage", Json::Arr(rows)),
        ("generator_coverage", Json::Arr(generator_rows)),
        ("accepted_crossovers", number(crossovers)),
        ("owned_account_engine_builds", number(owned_builds as i32)),
        (
            "determinism_jobs_per_run",
            number(deterministic_jobs as i32),
        ),
        (
            "workers",
            Json::Arr(vec![number(1), number(4), number(16), number(1)]),
        ),
        ("annealing", annealing_proof(context)?),
    ]))
}

pub fn command(args: &[PathBuf], catalog: Arc<Catalog>, catalog_path: &Path) -> Result<(), String> {
    let usage = "basesearch-proof <repo-root> <receipt.json> [seeds-per-TH-operator=1000]";
    if !(2..=3).contains(&args.len()) {
        return Err(usage.to_owned());
    }
    let seeds = if args.len() == 3 {
        args[2]
            .to_str()
            .ok_or(usage)?
            .parse::<usize>()
            .map_err(|_| usage)?
    } else {
        1000
    };
    let rules = Arc::new(BaseRules::load(
        &args[0].join("data/generated/base_rules.json"),
    )?);
    let catalog_bytes = std::fs::read(catalog_path).map_err(|e| e.to_string())?;
    require(
        identity(&catalog_bytes) == rules.catalog_identity,
        "catalog fingerprint differs from rules",
    )?;
    let context = Context { rules, catalog };
    let mut report = run(&context, seeds)?;
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    let Json::Obj(fields) = &mut report else {
        unreachable!()
    };
    fields.push((
        "executable_identity".to_owned(),
        string(identity(
            &std::fs::read(executable).map_err(|e| e.to_string())?,
        )),
    ));
    fields.push(("rules_identity".to_owned(), string(&context.rules.identity)));
    fields.push((
        "catalog_identity".to_owned(),
        string(&context.rules.catalog_identity),
    ));
    std::fs::write(&args[1], crate::layout::rules::pretty(&report)).map_err(|e| e.to_string())?;
    println!("M2 proposal proof: status=passed attempts={} accepted={} crossover={} workers=1/4/16/1 receipt={}", report.at("operator_attempts").i64(), report.at("operator_accepted_engine_builds").i64(), report.at("accepted_crossovers").i64(), args[1].display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_m2_proof_smoke() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let context = Context {
            rules: Arc::new(BaseRules::load(&root.join("data/generated/base_rules.json")).unwrap()),
            catalog: Arc::new(Catalog::load(&root.join("data/generated/catalog.json")).unwrap()),
        };
        run(&context, 8).unwrap();
    }
}
