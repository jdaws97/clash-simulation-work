//! CLI-only program proofs. Synthetic fixtures are not game calibration.

use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use crate::armies::put;
use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;
use crate::runner::{Job, PreparedInputs, Runner};
use crate::state::Plan;

use super::mutate::{self, Mutation, MUTATIONS};
use super::{army_identity, canonical, enable, step, time, AttackProgram};
use crate::armysearch::account::AccountRules;
use crate::armysearch::genome::{ArmyGenome, PlanGenes, UnitCount};
use crate::armysearch::util::{encode, number, object, string, text, Random};

fn require(condition: bool, message: &str) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(format!("armysearch-proof program: {message}"))
    }
}

fn reverse_keys(value: &Json) -> Json {
    match value {
        Json::Obj(fields) => Json::Obj(
            fields
                .iter()
                .rev()
                .map(|(key, value)| (key.clone(), reverse_keys(value)))
                .collect(),
        ),
        Json::Arr(values) => Json::Arr(values.iter().map(reverse_keys).collect()),
        _ => value.clone(),
    }
}

fn identity_proof(
    genome: &ArmyGenome,
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
) -> Result<(), String> {
    let program = genome
        .plan
        .program
        .as_ref()
        .ok_or("missing proof program")?;
    let mut reordered = genome.clone();
    reordered.plan.program.as_mut().unwrap().steps =
        program.steps.iter().map(reverse_keys).collect();
    require(
        reordered.identity() == genome.identity(),
        "identity depends on JSON key order",
    )?;
    let first = account.compile(compiler, catalog, genome, 0.0, 7)?;
    let second = account.compile(compiler, catalog, &reordered, 0.0, 7)?;
    require(
        encode(&first) == encode(&second),
        "canonical programs compile differently",
    )?;
    let roundtrip = ArmyGenome::from_json(&genome.to_json())?;
    require(
        roundtrip.identity() == genome.identity(),
        "checkpoint changed program identity",
    )?;
    reordered.plan.program.as_mut().unwrap().seed_family = "other provenance".to_owned();
    require(
        reordered.identity() == genome.identity(),
        "cache identity includes seed provenance",
    )?;
    let mut changed = genome.clone();
    put(
        &mut changed.plan.program.as_mut().unwrap().steps[0],
        "when",
        time(37.123456),
    );
    require(
        changed.identity() != genome.identity(),
        "program timing missing from genome identity",
    )?;
    require(
        encode(&canonical(&Json::Num(-0.0))) == encode(&canonical(&Json::Num(0.0))),
        "signed zero identity differs",
    )?;
    Ok(())
}

fn invalid_proof(genome: &ArmyGenome) -> Result<(), String> {
    let original = genome
        .plan
        .program
        .as_ref()
        .ok_or("missing invalid proof program")?;
    let mut invalids = Vec::new();
    for (key, value) in [
        ("action", string("invented")),
        ("at", string("unit:Missing Troop")),
        ("at", string("building:missing")),
        ("count", Json::Num(-1.0)),
        ("count", Json::Num(0.5)),
        ("count", number(10000)),
        ("when", object([("after", string("missing-step"))])),
        (
            "when",
            object([
                ("hp_below", string("Missing Hero")),
                ("frac", Json::Num(0.5)),
            ]),
        ),
        ("when", object([("t", Json::Num(f64::NAN))])),
        (
            "when",
            object([("t", Json::Num(0.0)), ("inside", string("Missing Hero"))]),
        ),
        ("when", object([("all", Json::Arr(Vec::new()))])),
        ("when", object([("all", Json::Bool(true))])),
        ("when", object([("nonsense", Json::Num(1.0))])),
        ("when", object([("t", Json::Num(-0.1))])),
        ("group", Json::Num(1.0)),
        ("every", Json::Num(0.0)),
        ("equipment", Json::Bool(true)),
    ] {
        let mut invalid = original.clone();
        put(&mut invalid.steps[0], key, value);
        invalids.push(invalid);
    }
    let mut absent_spell = original.clone();
    absent_spell.steps.push(step(
        "unowned-spell",
        "spell",
        "Invented Spell",
        1,
        "edge:main",
        "main",
        time(0.0),
    ));
    invalids.push(absent_spell);
    let mut cycle = original.clone();
    let id = text(&cycle.steps[0], "id", "").to_owned();
    put(&mut cycle.steps[0], "when", object([("after", string(id))]));
    invalids.push(cycle);
    let mut duplicate = original.clone();
    duplicate.steps.push(duplicate.steps[0].clone());
    invalids.push(duplicate);
    let mut malformed = original.clone();
    malformed.steps[0] = Json::Null;
    invalids.push(malformed);
    for invalid in invalids {
        require(
            invalid.validate(genome).is_err(),
            "malformed/overspent program admitted",
        )?;
    }
    Ok(())
}

/// The Healer is an alive nonattacking reserve at t=0, preventing the standard
/// stalled-army rescue from advancing the t=30 Barbarian. Nine undefended
/// storages give a reproducible engagement without incoming damage or heroes.
/// A t=0 edge Rage expires before combat. A group_inside Rage follows the
/// Barbarian and increases measured native damage. All stats are unmodified.
fn timing_fixture(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    template: &ArmyGenome,
) -> Result<Json, String> {
    let mut early = template.clone();
    early.plan = PlanGenes::default();
    early.plan.snipe_mode = "off".to_owned();
    early.troops = vec![
        UnitCount {
            name: "Barbarian".to_owned(),
            count: 1,
        },
        UnitCount {
            name: "Healer".to_owned(),
            count: 1,
        },
    ];
    early.spells = vec![UnitCount {
        name: "Rage Spell".to_owned(),
        count: 1,
    }];
    early.cc_troops.clear();
    early.cc_spells.clear();
    early.siege = None;
    early.normalize();
    account.check(&early)?;
    let mut steps = vec![
        step(
            "reserve",
            "deploy",
            "Healer",
            1,
            "edge:right",
            "support",
            time(0.0),
        ),
        step(
            "main",
            "deploy",
            "Barbarian",
            1,
            "edge:main",
            "main",
            time(30.0),
        ),
        step(
            "rage",
            "spell",
            "Rage Spell",
            1,
            "edge:main",
            "main",
            time(0.0),
        ),
    ];
    // Selected heroes must have deployment roles, even in this troop-only
    // engagement. Their t=180 roles stay beyond the fixture's 90-second limit.
    steps.extend(
        super::generic_steps(&early)
            .into_iter()
            .filter_map(|mut role| {
                if text(&role, "action", "") == "deploy"
                    && crate::plans::is_hero(text(&role, "what", ""))
                {
                    put(&mut role, "when", time(180.0));
                    Some(role)
                } else {
                    None
                }
            }),
    );
    early.plan.program = Some(AttackProgram {
        steps: steps.clone(),
        seed_steps: steps,
        seed_family: "synthetic-timing".to_owned(),
        seed_army: army_identity(&early),
    });
    early.plan.program.as_ref().unwrap().validate(&early)?;
    // The same mutation operator used in production must discover the known
    // useful trigger. Seeded rejection sampling does not edit the candidate.
    let mut rng = Random(0x52414745);
    let mut discovered = None;
    let mut attempts = 0;
    for attempt in 1..=8192 {
        attempts = attempt;
        if let Ok(candidate) = mutate::apply(&early, Mutation::Trigger, &mut rng) {
            let program = candidate.plan.program.as_ref().unwrap();
            if program.steps[2]
                .get("when")
                .and_then(|when| when.get("group_inside"))
                == Some(&string("main"))
            {
                discovered = Some(candidate);
                break;
            }
        }
    }
    let mut discovered =
        discovered.ok_or("program mutation did not discover group_inside in 8192 tries")?;
    // Anchor is a separate production mutation. Find its group-centre change
    // without changing the discovered trigger or composing a handcrafted step.
    let trigger_parent = discovered.clone();
    let mut anchor_found = false;
    for _ in 0..8192 {
        if let Ok(candidate) = mutate::apply(&trigger_parent, Mutation::Anchor, &mut rng) {
            if text(&candidate.plan.program.as_ref().unwrap().steps[2], "at", "") == "group:main" {
                discovered = candidate;
                anchor_found = true;
                break;
            }
        }
    }
    require(
        anchor_found,
        "anchor mutation did not discover group centre",
    )?;
    let candidates = [&early, &discovered];
    let plans = candidates
        .iter()
        .map(|genome| account.compile(compiler, &catalog, genome, 0.0, 123))
        .collect::<Result<Vec<_>, _>>()?;
    let mut buildings = Vec::new();
    for x in [12, 20, 28] {
        for y in [12, 20, 28] {
            buildings.push(object([
                ("key", string("gs")),
                ("x", number(x)),
                ("y", number(y)),
            ]));
        }
    }
    let layout = object([
        (
            "name",
            string("SYNTHETIC program timing proof; nine undefended storages"),
        ),
        ("buildings", Json::Arr(buildings)),
        ("walls", Json::Arr(Vec::new())),
        ("traps", Json::Arr(Vec::new())),
        ("heroes", Json::Arr(Vec::new())),
        ("cc_troops", Json::Arr(Vec::new())),
    ]);
    let runner = Runner::new(catalog, PreparedInputs::new(vec![layout], plans));
    // Sixteen jobs ensure the 16-thread comparison actually has sixteen jobs.
    let jobs: Vec<_> = (0..16)
        .map(|index| {
            Job::from_json(&object([
                ("layout", number(0)),
                ("plan", number(index % 2)),
                ("seed", number(123)),
                ("town_hall", number(16)),
                ("max_time", Json::Num(90.0)),
                ("record", Json::Bool(true)),
            ]))
        })
        .collect();
    let mut expected = None;
    let mut timing = None;
    for threads in [1, 4, 16] {
        let rows = Mutex::new(vec![None; jobs.len()]);
        let hook = |index: usize,
                    _: &Job,
                    battle: &crate::state::Battle,
                    _: &crate::state::BattleResult| {
            let damage = battle
                .buildings
                .iter()
                .map(|building| building.max_hp - building.hp.max(0.0))
                .sum::<f64>();
            let Plan::Playbook(plan) = &battle.plan else {
                panic!("timing proof bypassed playbook compiler");
            };
            let at = |id: &str| {
                plan.log_steps
                    .iter()
                    .find(|(_, name)| name == id)
                    .map(|(time, _)| *time)
            };
            rows.lock().unwrap()[index] = Some((
                damage.to_bits(),
                at("main").map(f64::to_bits),
                at("rage").map(f64::to_bits),
            ));
        };
        let results = runner
            .run_with_summary(&jobs, threads, Some(&hook))
            .map_err(|error| error.to_string())?;
        require(
            results[1].destruction > results[0].destruction,
            "inside Rage did not improve native destruction",
        )?;
        let early_destruction = results[0].destruction;
        let learned_destruction = results[1].destruction;
        let rows = rows
            .into_inner()
            .map_err(|_| "timing proof mutex poisoned")?;
        let current = (results, rows.clone());
        if let Some(expected) = &expected {
            require(
                &current == expected,
                "program native results differ at 1/4/16 threads",
            )?;
        } else {
            expected = Some(current);
        }
        let (early_damage, main_at, early_at) = rows[0].ok_or("missing early Rage proof row")?;
        let (inside_damage, _, inside_at) = rows[1].ok_or("missing inside Rage proof row")?;
        let main_at = main_at
            .map(f64::from_bits)
            .ok_or("main deployment did not execute")?;
        let early_at = early_at
            .map(f64::from_bits)
            .ok_or("early Rage did not execute")?;
        let inside_at = inside_at
            .map(f64::from_bits)
            .ok_or("inside Rage did not execute")?;
        require(
            main_at >= 30.0 && early_at < 1.0 && inside_at > main_at,
            "native fixture did not exercise the intended timing window",
        )?;
        require(
            f64::from_bits(inside_damage) > f64::from_bits(early_damage),
            "inside Rage did not improve native damage over the wasted t=0 Rage",
        )?;
        timing = Some(object([
            ("early_damage", Json::Num(f64::from_bits(early_damage))),
            ("learned_damage", Json::Num(f64::from_bits(inside_damage))),
            ("early_destruction", number(early_destruction)),
            ("learned_destruction", number(learned_destruction)),
            ("early_rage_at", Json::Num(early_at)),
            ("learned_rage_at", Json::Num(inside_at)),
            ("main_deploy_at", Json::Num(main_at)),
        ]));
    }
    Ok(object([
        (
            "scope",
            string("synthetic native battle; measured damage, not calibrated attack strength"),
        ),
        ("mutation_attempts", number(attempts)),
        (
            "results",
            timing.ok_or("timing fixture produced no results")?,
        ),
        (
            "program",
            discovered.plan.program.as_ref().unwrap().to_json(),
        ),
        (
            "selected_by",
            string("greater native damage and destruction on the same synthetic battle"),
        ),
        (
            "native_threads",
            Json::Arr([1, 4, 16].into_iter().map(number).collect()),
        ),
    ]))
}

pub fn run(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    templates: &[ArmyGenome],
    iterations: usize,
) -> Result<Json, String> {
    let mut seeds = Vec::new();
    for template in templates.iter().take(12) {
        let mut genome = template.clone();
        enable(account, compiler, &catalog, &mut genome)?;
        genome.plan.program.as_ref().unwrap().validate(&genome)?;
        seeds.push(genome);
    }
    let seed = seeds.first().ok_or("program proof needs seeds")?;
    identity_proof(seed, account, compiler, &catalog)?;
    invalid_proof(seed)?;
    let fixes = super::fixes::run(account, compiler, Arc::clone(&catalog), templates)?;
    let mut crossover_seed = seed.clone();
    let mut crossover_steps = vec![step(
        "crossover-fixture",
        "deploy",
        &seed.troops[0].name,
        1,
        "edge:main",
        "main",
        time(0.0),
    )];
    crossover_steps.extend(super::generic_steps(seed).into_iter().filter(|role| {
        text(role, "action", "") == "deploy" && crate::plans::is_hero(text(role, "what", ""))
    }));
    crossover_seed.plan.program.as_mut().unwrap().steps = crossover_steps;
    let mut crossover_rng = Random(123);
    let mut crossed = false;
    for _ in 0..256 {
        if let Ok(child) = mutate::crossover(&crossover_seed, &crossover_seed, &mut crossover_rng) {
            child.plan.program.as_ref().unwrap().validate(&child)?;
            crossed = true;
            break;
        }
    }
    require(crossed, "same-army program crossover admitted no children")?;
    let mut current = seed.clone();
    let mut rng = Random(20261024);
    let mut accepted = 0;
    let mut rejected = BTreeMap::<String, usize>::new();
    for index in 0..iterations {
        if index % 64 == 0 {
            current = seeds[rng.index(seeds.len())].clone();
        }
        let proposal = if index % 11 == 0 {
            mutate::crossover(&current, &seeds[rng.index(seeds.len())], &mut rng)
        } else {
            mutate::apply(&current, MUTATIONS[index % MUTATIONS.len()], &mut rng)
        };
        match proposal {
            Ok(genome) => {
                let program = genome
                    .plan
                    .program
                    .as_ref()
                    .ok_or("program mutation lost program")?;
                program.validate(&genome)?;
                let plan =
                    account.compile(compiler, &catalog, &genome, genome.plan.angle_offset, 0)?;
                require(
                    text(&plan, "$type", "") == "PlaybookPlan"
                        && plan.at("strength").f64().to_bits() == 1.0_f64.to_bits(),
                    "program bypassed the normal compile path or changed strength",
                )?;
                require(
                    canonical(plan.at("steps")) == program.identity_json(),
                    "compiled steps differ from genome program",
                )?;
                current = genome;
                accepted += 1;
            }
            Err(reason) => {
                require(!reason.is_empty(), "mutation rejection lacks a reason")?;
                *rejected.entry(reason).or_default() += 1;
            }
        }
        if (index + 1) % 500 == 0 {
            eprintln!("armysearch-proof programs {}/{}", index + 1, iterations);
        }
    }
    require(
        accepted > 100 && !rejected.is_empty(),
        "program fuzz lacked accepted/rejected coverage",
    )?;
    let timing = timing_fixture(account, compiler, catalog, seed)?;
    Ok(object([
        ("status", string("passed")),
        ("iterations", number(iterations)),
        ("accepted", number(accepted)),
        ("rejected_with_reason", number(rejected.values().sum())),
        (
            "rejection_reasons",
            Json::Obj(
                rejected
                    .into_iter()
                    .map(|(reason, count)| (reason, number(count)))
                    .collect(),
            ),
        ),
        ("canonical_identity", Json::Bool(true)),
        ("round9_fixes", fixes),
        ("timing_discovery", timing),
    ]))
}
