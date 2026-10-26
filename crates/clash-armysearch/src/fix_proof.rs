//! Round-nine and round-eleven CLI fixtures. Layouts/citations are synthetic.

use std::sync::{Arc, Mutex};

use crate::armies::{put, remove};
use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;
use crate::runner::{Job, PreparedInputs, Runner};
use crate::state::Plan;

use super::mutate::{self, Mutation};
use super::{army_identity, enable, generic_steps, step, time, AttackProgram};
use crate::account::AccountRules;
use crate::genome::{ArmyGenome, PlanGenes, UnitCount};
use crate::operators;
use crate::score::{BattleMetrics, CandidateEstimate, Stage};
use crate::search::{Elite, Objective, SearchState};
use crate::util::{array, encode, number, object, string, text, Random};

fn require(condition: bool, message: &str) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(format!("armysearch-proof round9: {message}"))
    }
}

fn fixture(template: &ArmyGenome) -> ArmyGenome {
    let mut genome = template.clone();
    genome.plan = PlanGenes::default();
    genome.plan.snipe_mode = "off".to_owned();
    genome.troops = vec![
        UnitCount {
            name: "Barbarian".to_owned(),
            count: 1,
        },
        UnitCount {
            name: "Healer".to_owned(),
            count: 1,
        },
    ];
    genome.spells.clear();
    genome.cc_troops.clear();
    genome.cc_spells.clear();
    genome.siege = None;
    genome.normalize();
    genome
}

fn set_steps(genome: &mut ArmyGenome, steps: Vec<Json>) {
    genome.plan.program = Some(AttackProgram {
        steps: steps.clone(),
        seed_steps: steps,
        seed_family: "synthetic-round9".to_owned(),
        seed_army: army_identity(genome),
    });
}

fn delayed_heroes(genome: &ArmyGenome) -> Vec<Json> {
    generic_steps(genome)
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
        })
        .collect()
}

#[derive(Clone)]
struct Opening {
    log: Vec<String>,
    deployed: Vec<String>,
    dragon_positions: Vec<(f64, f64)>,
}

/// playbook.py:1007-1138 supplies the real scheduling and log order. Nine
/// undefended storages keep the short opening alive without adding damage.
fn native_openings(
    catalog: Arc<Catalog>,
    plans: Vec<Json>,
    max_time: f64,
) -> Result<Vec<Opening>, String> {
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
        ("name", string("SYNTHETIC round9 opening fixture")),
        ("buildings", Json::Arr(buildings)),
        ("walls", Json::Arr(Vec::new())),
        ("traps", Json::Arr(Vec::new())),
        ("heroes", Json::Arr(Vec::new())),
        ("cc_troops", Json::Arr(Vec::new())),
    ]);
    let jobs: Vec<_> = (0..plans.len())
        .map(|index| {
            Job::from_json(&object([
                ("layout", number(0)),
                ("plan", number(index)),
                ("seed", number(123)),
                ("town_hall", number(16)),
                ("max_time", Json::Num(max_time)),
            ]))
        })
        .collect();
    let rows = Mutex::new(vec![None; plans.len()]);
    let hook =
        |index: usize, _: &Job, battle: &crate::state::Battle, _: &crate::state::BattleResult| {
            let Plan::Playbook(plan) = &battle.plan else {
                panic!("round9 fixture bypassed PlaybookPlan");
            };
            let log = plan.log_steps.iter().map(|(_, id)| id.clone()).collect();
            let deployed = plan.deployed.iter().cloned().collect();
            let dragon_positions = battle
                .attackers_pool()
                .filter(|unit| unit.name == "Dragon")
                .map(|unit| (unit.x, unit.y))
                .chain(
                    battle.deployments[battle.next_deploy..]
                        .iter()
                        .filter(|drop| drop.name == "Dragon")
                        .map(|drop| (drop.x, drop.y)),
                )
                .collect();
            rows.lock().unwrap()[index] = Some(Opening {
                log,
                deployed,
                dragon_positions,
            });
        };
    Runner::new(catalog, PreparedInputs::new(vec![layout], plans))
        .run_with_summary(&jobs, 1, Some(&hook))
        .map_err(|error| error.to_string())?;
    rows.into_inner()
        .map_err(|_| "round9 fixture mutex poisoned".to_owned())?
        .into_iter()
        .map(|row| row.ok_or_else(|| "missing round9 native row".to_owned()))
        .collect()
}

fn admission_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    templates: &[ArmyGenome],
) -> Result<(), String> {
    let mut source = None;
    for template in templates {
        let mut genome = template.clone();
        enable(account, compiler, catalog, &mut genome)?;
        operators::admit(account, compiler, catalog, &mut genome)?;
        let plan = account.compile(compiler, catalog, &genome, 0.0, 0)?;
        if let Some(id) = operators::timing_steps(&plan).first() {
            if operators::applicability(&plan)[4] {
                source = Some((genome, plan, id.clone()));
                break;
            }
        }
    }
    let (parent, baseline, id) = source.ok_or("round9 proof needs a cited delayed deployment")?;
    let mut timing = parent.clone();
    timing.plan.step_timing.insert(id.clone(), 1.0);
    operators::admit(account, compiler, catalog, &mut timing)?;
    let plan = account.compile(compiler, catalog, &timing, 0.0, 0)?;
    let when = |plan: &Json| {
        array(plan, "steps")
            .iter()
            .find(|step| text(step, "id", "") == id)
            .unwrap()
            .at("when")
            .clone()
    };
    require(
        timing.identity() != parent.identity() && when(&plan) != when(&baseline),
        "admission discarded timing or its identity",
    )?;
    let mut spread = parent.clone();
    spread.plan.tactics[4] = 1.25;
    operators::admit(account, compiler, catalog, &mut spread)?;
    let plan = account.compile(compiler, catalog, &spread, 0.0, 0)?;
    require(
        spread.identity() != parent.identity() && plan.at("steps") != baseline.at("steps"),
        "admission discarded executable spread or its identity",
    )?;
    let identity = spread.identity();
    operators::admit(account, compiler, catalog, &mut spread)?;
    require(
        spread.identity() == identity,
        "repeated admission compounded a tactic",
    )?;
    let repeated = account.compile(compiler, catalog, &spread, 0.0, 0)?;
    require(
        encode(&plan) == encode(&repeated),
        "repeated admission changed executable spread",
    )
}

fn generic_controls_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut parent = fixture(template);
    account.repair(&mut parent)?;
    enable(account, compiler, catalog, &mut parent)?;
    operators::admit(account, compiler, catalog, &mut parent)?;
    let mut changed = [false; 3];
    for seed in 0..4096 {
        if Random(seed).index(14) != 11 {
            continue;
        }
        let child = operators::mutate(
            &parent,
            &[parent.clone()],
            account,
            compiler,
            catalog,
            &mut Random(seed),
        )?;
        let plan = account.compile(compiler, catalog, &child, 0.0, 0)?;
        changed[0] |= child.plan.charge_side != parent.plan.charge_side;
        changed[1] |= child.plan.flank_offset != parent.plan.flank_offset;
        changed[2] |= child.plan.snipe_mode != parent.plan.snipe_mode;
        require(
            text(&plan, "charge_side", "") == child.plan.charge_side
                && text(&plan, "snipe_mode", "") == child.plan.snipe_mode
                && plan.at("flank_offset").f64() == child.plan.flank_offset,
            "generic opening controls did not reach the executable plan",
        )?;
        if changed.iter().all(|changed| *changed) {
            break;
        }
    }
    require(
        changed.iter().all(|changed| *changed),
        "generic opening controls never mutate",
    )
}

fn hero_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut child = fixture(template);
    enable(account, compiler, &catalog, &mut child)?;
    let replacement = account
        .roster
        .heroes
        .iter()
        .find(|hero| !child.heroes.iter().any(|choice| &choice.hero == *hero))
        .ok_or("round9 proof needs an alternate hero")?
        .clone();
    child.heroes[0].hero = replacement.clone();
    account.repair(&mut child)?;
    // Keep the opening small after account repair fills residual camp space.
    child.troops = fixture(template).troops;
    child.normalize();
    operators::admit(account, compiler, &catalog, &mut child)?;
    let program = child.plan.program.as_ref().unwrap();
    for action in ["deploy", "ability"] {
        require(
            program.steps.iter().any(|step| {
                text(step, "action", "") == action && text(step, "what", "") == replacement
            }),
            "replacement hero lost its default role",
        )?;
    }
    let mut missing = program.clone();
    missing.steps.retain(|step| {
        !(text(step, "action", "") == "deploy" && text(step, "what", "") == replacement)
    });
    require(
        missing.validate(&child).is_err(),
        "program without a selected hero deployment admitted",
    )?;
    let plan = account.compile(compiler, &catalog, &child, 0.0, 123)?;
    let rows = native_openings(catalog, vec![plan], 25.0)?;
    require(
        rows[0].deployed.contains(&replacement),
        "replacement hero did not deploy with sniping off",
    )
}

fn priority_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut parent = fixture(template);
    let mut steps = vec![
        step(
            "first",
            "deploy",
            "Healer",
            1,
            "edge:main",
            "main",
            time(0.0),
        ),
        step(
            "second",
            "deploy",
            "Barbarian",
            1,
            "edge:main",
            "main",
            time(0.0),
        ),
    ];
    for step in &mut steps {
        remove(step, "uncited");
    }
    steps.extend(delayed_heroes(&parent));
    set_steps(&mut parent, steps);
    let mut rng = Random(0x5052494f);
    let mut learned = None;
    for _ in 0..512 {
        if let Ok(child) = mutate::apply(&parent, Mutation::Anchor, &mut rng) {
            let steps = &child.plan.program.as_ref().unwrap().steps;
            if steps[0].get("learned") == Some(&Json::Bool(true))
                && text(&steps[0], "at", "") != "edge:main"
                && text(&steps[0], "at", "").starts_with("edge:")
            {
                require(
                    !steps[0].get("uncited").is_some_and(Json::bool),
                    "anchor provenance changed scheduler priority",
                )?;
                learned = Some(child);
                break;
            }
        }
    }
    let learned = learned.ok_or("round9 anchor mutation did not touch the first action")?;
    require(
        super::report(&learned, compiler).at("label").str() == "learned (not from a real player)",
        "learned report label disappeared",
    )?;
    let plans = [&parent, &learned]
        .iter()
        .map(|genome| account.compile(compiler, &catalog, genome, 0.0, 123))
        .collect::<Result<Vec<_>, _>>()?;
    let rows = native_openings(catalog, plans, 0.1)?;
    require(
        rows.iter()
            .all(|row| row.log.first().is_some_and(|id| id == "first")),
        "a local anchor mutation demoted the first ready action",
    )
}

fn spell_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut genome = fixture(template);
    genome.spells = vec![UnitCount {
        name: "Rage Spell".to_owned(),
        count: 1,
    }];
    genome.cc_spells = genome.spells.clone();
    let mut steps = generic_steps(&genome);
    steps.retain(|step| {
        text(step, "action", "") == "deploy" && !crate::plans::is_hero(text(step, "what", ""))
    });
    steps.extend(delayed_heroes(&genome));
    let mut brewed = step(
        "late",
        "spell",
        "Rage Spell",
        1,
        "edge:main",
        "main",
        time(20.0),
    );
    put(&mut brewed, "origin", string("brewed"));
    steps.push(brewed);
    steps.push(step(
        "early",
        "spell",
        "Rage Spell",
        1,
        "edge:main",
        "main",
        time(0.0),
    ));
    set_steps(&mut genome, steps);
    let mut program = genome.plan.program.as_ref().unwrap().clone();
    require(
        program.validate(&genome).is_err(),
        "trigger-order origin panic admitted",
    )?;
    program.steps.reverse();
    require(
        program.validate(&genome).is_err(),
        "spell validity depends on step order",
    )?;
    program.steps.reverse();
    let late = program
        .steps
        .iter()
        .position(|step| text(step, "id", "") == "late")
        .unwrap();
    for origin in ["", "unknown"] {
        put(&mut program.steps[late], "origin", string(origin));
        require(
            program.validate(&genome).is_err(),
            "unknown or empty spell origin admitted",
        )?;
    }
    put(&mut program.steps[late], "origin", string("donated"));
    program.validate(&genome)?;
    program.steps.reverse();
    program.validate(&genome)?;
    program.steps.reverse();
    let early = program
        .steps
        .iter()
        .position(|step| text(step, "id", "") == "early")
        .unwrap();
    let mut overspent = program.clone();
    put(&mut overspent.steps[early], "origin", string("donated"));
    require(
        overspent.validate(&genome).is_err(),
        "donated origin overspend passed total-stock validation",
    )?;
    let mut home_only = genome.clone();
    home_only.cc_spells.clear();
    home_only.spells[0].count = 2;
    let mut safe_home = program.clone();
    put(&mut safe_home.steps[late], "origin", string("brewed"));
    safe_home.validate(&home_only)?;
    safe_home.steps.reverse();
    safe_home.validate(&home_only)?;
    let mut repeated = program.clone();
    put(&mut repeated.steps[late], "every", Json::Num(1.0));
    require(
        repeated.validate(&genome).is_err(),
        "restricted repeat can exhaust its origin",
    )?;
    genome.plan.program = Some(program);
    let plan = account.compile(compiler, &catalog, &genome, 0.0, 123)?;
    let rows = native_openings(catalog, vec![plan], 30.0)?;
    require(
        ["early", "late"]
            .iter()
            .all(|id| rows[0].log.iter().any(|entry| entry.as_str() == *id)),
        "safe mixed-origin program did not cast both copies",
    )
}

fn ground_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut genome = fixture(template);
    if !genome.heroes.iter().any(|hero| hero.hero == "Grand Warden") {
        genome.heroes[0].hero = "Grand Warden".to_owned();
        account.repair(&mut genome)?;
    }
    genome.troops = vec![
        UnitCount {
            name: "Dragon".to_owned(),
            count: 6,
        },
        UnitCount {
            name: "Healer".to_owned(),
            count: 4,
        },
    ];
    genome.normalize();
    enable(account, compiler, catalog, &mut genome)?;
    // The shared walk rule (F3) grounds Healers following the Warden at his
    // edge under any group, so start from Healers on the other flank: a real
    // air baseline that only the installed Warden walk below should ground.
    if let Some(healer) = genome
        .plan
        .program
        .as_mut()
        .unwrap()
        .steps
        .iter_mut()
        .find(|step| text(step, "what", "") == "Healer")
    {
        put(healer, "at", string("edge:funnel"));
        put(healer, "group", string("funnel"));
    }
    let original = account.compile(compiler, catalog, &genome, 0.0, 0)?;
    require(
        !original.at("ground").bool(),
        "air fixture already selected ground mode",
    )?;
    for anchor in [
        "unit:Grand Warden",
        "unit_ahead:Grand Warden",
        "edge:charge",
    ] {
        let mut child = genome.clone();
        let steps = &mut child.plan.program.as_mut().unwrap().steps;
        let warden = steps
            .iter_mut()
            .find(|step| {
                text(step, "action", "") == "deploy" && text(step, "what", "") == "Grand Warden"
            })
            .unwrap();
        let id = text(warden, "id", "").to_owned();
        put(warden, "at", string("edge:charge"));
        put(warden, "group", string("charge"));
        let healer = steps
            .iter_mut()
            .find(|step| text(step, "what", "") == "Healer")
            .unwrap();
        put(healer, "at", string(anchor));
        put(healer, "group", string("charge"));
        put(
            healer,
            "when",
            object([("after", string(id)), ("delay", Json::Num(1.0))]),
        );
        let plan = account.compile(compiler, catalog, &child, 0.0, 0)?;
        require(
            plan.at("ground").bool(),
            "installed Healer-supported Warden stayed airborne",
        )?;
        if anchor == "edge:charge" {
            let healer = child
                .plan
                .program
                .as_mut()
                .unwrap()
                .steps
                .iter_mut()
                .find(|step| text(step, "what", "") == "Healer")
                .unwrap();
            put(healer, "when", time(0.0));
            let before = account.compile(compiler, catalog, &child, 0.0, 0)?;
            require(
                !before.at("ground").bool(),
                "Healers preceding the Warden forced ground mode",
            )?;
        }
    }
    Ok(())
}

fn provenance_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut parent = fixture(template);
    enable(account, compiler, catalog, &mut parent)?;
    let mut unchanged_anchor = false;
    for seed in 0..4096 {
        if let Ok(child) = mutate::apply(&parent, Mutation::Anchor, &mut Random(seed)) {
            if child.plan.program.as_ref().unwrap().steps
                != parent.plan.program.as_ref().unwrap().steps
                && child.identity() == parent.identity()
            {
                unchanged_anchor = true;
                break;
            }
        }
    }
    require(
        unchanged_anchor,
        "same-anchor mutation changed executable identity",
    )?;
    let estimate = CandidateEstimate {
        stage: Stage::Quick,
        metrics: BattleMetrics::default(),
        bases: Vec::new(),
        battles: 0,
        unused_budget: 0,
        standard_error: 0.0,
    };
    let mut archive = SearchState::new(11);
    for index in 0..3 {
        let mut genome = parent.clone();
        put(
            &mut genome.plan.program.as_mut().unwrap().steps[index],
            "learned",
            Json::Bool(true),
        );
        require(
            genome.identity() == parent.identity(),
            "learned flag changed identity",
        )?;
        let roundtrip = ArmyGenome::from_json(&genome.to_json())?;
        require(
            roundtrip.plan.program.as_ref().unwrap().steps[index]
                .at("learned")
                .bool(),
            "checkpoint discarded learned provenance",
        )?;
        archive.insert(
            Elite {
                genome,
                quick: estimate.clone(),
                confirm: estimate.clone(),
            },
            Objective::Ranked,
            account,
        );
    }
    require(
        archive.archive.values().map(Vec::len).sum::<usize>() == 1,
        "provenance-only variants occupied multiple archive slots",
    )
}

fn spread_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    template: &ArmyGenome,
) -> Result<(), String> {
    let mut genome = fixture(template);
    genome.troops = vec![UnitCount {
        name: "Dragon".to_owned(),
        count: 9,
    }];
    let mut steps = vec![step(
        "dragons",
        "deploy",
        "Dragon",
        9,
        "edge:main",
        "main",
        time(0.0),
    )];
    steps.extend(delayed_heroes(&genome));
    set_steps(&mut genome, steps);
    let mut plans = Vec::new();
    for scale in [1.0 - 0.000001, 1.0, 1.0 + 0.000001, 1.6] {
        genome.plan.tactics[4] = scale;
        plans.push(account.compile(compiler, &catalog, &genome, 0.0, 0)?);
    }
    let rows = native_openings(catalog, plans, 0.1)?;
    let mut spans = Vec::new();
    for row in rows {
        require(
            row.dragon_positions.len() == 9,
            "spread fixture lost scheduled Dragons",
        )?;
        let low = row
            .dragon_positions
            .iter()
            .map(|point| point.1)
            .fold(f64::INFINITY, f64::min);
        let high = row
            .dragon_positions
            .iter()
            .map(|point| point.1)
            .fold(f64::NEG_INFINITY, f64::max);
        spans.push(high - low);
    }
    require(
        spans[1] > 6.0
            && (spans[0] - spans[1]).abs() < 0.001
            && (spans[2] - spans[1]).abs() < 0.001
            && spans[3] > spans[1],
        "spread scaling collapsed a deployment line into a stack",
    )
}

fn installed_coverage_proof(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    templates: &[ArmyGenome],
) -> Result<(), String> {
    let mut checked = false;
    if let Some(template) = templates
        .iter()
        .find(|genome| genome.plan.family != "generic")
    {
        let mut genome = template.clone();
        enable(account, compiler, catalog, &mut genome)?;
        account.compile(compiler, catalog, &genome, 0.0, 0)?;
        genome.plan.program.as_mut().unwrap().steps.retain(|step| {
            text(step, "action", "") == "deploy" && crate::plans::is_hero(text(step, "what", ""))
        });
        for step in &mut genome.plan.program.as_mut().unwrap().steps {
            put(step, "when", time(0.0));
            put(step, "at", string("edge:main"));
            put(step, "group", string("main"));
        }
        genome.plan.program.as_ref().unwrap().validate(&genome)?;
        match account.compile(compiler, catalog, &genome, 0.0, 0) {
            Err(reason) if reason.contains("fewer than 35% cited troop deployments") => {}
            _ => {
                return Err(
                    "armysearch-proof round11: source coverage admitted hero-only program"
                        .to_owned(),
                );
            }
        }
        checked = true;
    }
    require(checked, "coverage proof requires a cited template")
}

pub(super) fn run(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    templates: &[ArmyGenome],
) -> Result<Json, String> {
    let template = templates.first().ok_or("round9 proof requires a seed")?;
    admission_proof(account, compiler, &catalog, templates)?;
    generic_controls_proof(account, compiler, &catalog, template)?;
    hero_proof(account, compiler, Arc::clone(&catalog), template)?;
    priority_proof(account, compiler, Arc::clone(&catalog), template)?;
    spell_proof(account, compiler, Arc::clone(&catalog), template)?;
    ground_proof(account, compiler, &catalog, template)?;
    provenance_proof(account, compiler, &catalog, template)?;
    spread_proof(account, compiler, Arc::clone(&catalog), template)?;
    installed_coverage_proof(account, compiler, &catalog, templates)?;
    Ok(object([
        ("admission_preserves_timing_and_tactics", Json::Bool(true)),
        ("generic_opening_controls_mutate", Json::Bool(true)),
        ("replacement_hero_deploys", Json::Bool(true)),
        ("learned_provenance_preserves_priority", Json::Bool(true)),
        ("spell_origins_are_order_independent", Json::Bool(true)),
        ("installed_warden_walk_is_ground", Json::Bool(true)),
        ("provenance_deduplicates_archive", Json::Bool(true)),
        ("spread_preserves_lines", Json::Bool(true)),
        (
            "installed_program_requires_cited_coverage",
            Json::Bool(true),
        ),
    ]))
}
