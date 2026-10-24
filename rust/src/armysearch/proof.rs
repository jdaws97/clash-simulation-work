//! CLI verification fixtures, deliberately not test files.

use std::collections::BTreeSet;
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;
use crate::scoring::{self, Outcome, Scenario};

use super::account::AccountRules;
use super::eval::{Evaluator, NativeEvaluator};
use super::genome::ArmyGenome;
use super::operators;
use super::report;
use super::score::{self, CandidateEstimate, Split, Stage, TargetManifest};
use super::search::{self, Objective, SearchState};
use super::util::{encode, number, object, string, Random};

fn require(condition: bool, message: &str) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(format!("armysearch-proof: {message}"))
    }
}

struct TinyEvaluator<'a> {
    manifest: &'a TargetManifest,
    threads: usize,
    calls: Vec<Split>,
}

impl Evaluator for TinyEvaluator<'_> {
    fn evaluate(
        &mut self,
        genome: &ArmyGenome,
        stage: Stage,
        budget: usize,
    ) -> Result<CandidateEstimate, String> {
        self.calls.push(stage.split());
        let keys = score::allocate(self.manifest, stage, budget, 123)?;
        let pick = (genome.plan.angle_offset * 16.0 / (2.0 * std::f64::consts::PI)).round() as usize;
        let threads = self.threads;
        let rows = std::thread::scope(|scope| {
            let mut handles = Vec::new();
            for thread in 0..threads {
                let keys = &keys;
                handles.push(scope.spawn(move || {
                    (thread..keys.len()).step_by(threads).map(|index| {
                        let outcome = if pick == 7 {
                            Outcome {
                                stars: 3,
                                destruction: 100.0,
                                th_destroyed: true,
                                time: 100.0
                            }
                        } else {
                            Outcome {
                                stars: 2,
                                destruction: 50.0 + pick as f64,
                                th_destroyed: true,
                                time: 120.0
                            }
                        };
                        (index, outcome)
                    }).collect::<Vec<_>>()
                }));
            }
            handles.into_iter().flat_map(|handle| handle.join().expect("tiny worker")).collect::<Vec<_>>()
        });
        let mut rows = rows;
        rows.sort_by_key(|(index, _)| *index);
        let outcomes: Vec<Outcome> = rows.into_iter().map(|(_, outcome)| outcome).collect();
        score::summarise(self.manifest, stage, &keys, &outcomes, budget)
    }
}

fn tiny_proofs(manifest: &TargetManifest, seed: &ArmyGenome) -> Result<(), String> {
    let sides: Vec<_> = (0..8).map(|side| Scenario {
        army: "scout-proof".to_owned(),
        town_hall: 16,
        angle: side as f64,
        seed: 123,
        weight: 1.0 / 8.0,
        modifier: None,
        group: 0,
        tactic: Json::Null,
        charge: None,
        full_scout: false,
    }).collect();
    let outcomes: Vec<_> = (0..8).map(|side| Outcome {
        stars: 2,
        destruction: 50.0 + side as f64 * 6.0,
        th_destroyed: true,
        time: 100.0,
    }).collect();
    let selected = scoring::scouted(&sides, &outcomes, Some(2));
    require(selected.len() == 28, "eight-side scouting did not enumerate 28 pairs")?;
    let mut pair = 0;
    for first in 0..8 {
        for second in first + 1..8 {
            require(selected[pair].scenario == second, "scouting chose a different pair winner")?;
            pair += 1;
        }
    }
    require(scoring::attacker_trophies(3, 100.0) == 40 && scoring::attacker_trophies(2, 100.0) == 32, "ranked trophy direction or boundary changed")?;
    let mut candidates = Vec::new();
    for index in 0..16 {
        let mut genome = seed.clone();
        genome.plan.angle_offset = (2.0 * std::f64::consts::PI) * index as f64 / 16.0;
        candidates.push(genome);
    }
    let mut expected = None;
    for threads in [1, 4, 16] {
        let mut evaluator = TinyEvaluator {
            manifest,
            threads,
            calls: Vec::new()
        };
        let mut state = SearchState::new(123);
        search::assess_wave(&mut state, candidates[..8]
            .to_vec(), &mut evaluator, manifest, 4, 8, Objective::Ranked);
        // A persisted checkpoint must lead to the same second-wave archive.
        let mut restored = report::roundtrip_state(&state, Objective::Ranked)?;
        search::assess_wave(&mut state, candidates[8..]
            .to_vec(), &mut evaluator, manifest, 4, 8, Objective::Ranked);
        search::assess_wave(&mut restored, candidates[8..]
            .to_vec(), &mut evaluator, manifest, 4, 8, Objective::Ranked);
        require(encode(&state.to_json()) == encode(&restored.to_json()), "resume changed archive")?;
        let best = state.elites(Objective::Ranked).remove(0);
        require(best.genome.identity() == candidates[7]
            .identity(), "tiny enumerable space missed known optimum")?;
        require(evaluator.calls.iter().all(|split| *split == Split::Search), "holdout entered search")?;
        let archive = encode(&report::archive_json(&state));
        if let Some(expected) = &expected {
            require(&archive == expected, "synthetic archive differs across thread counts")?;
        }
        expected = Some(archive);
        // Adversarial holdout changes must leave all development keys/scores
        // and the archive unchanged. Holdout is only evaluated after freezing.
        let mut changed = manifest.clone();
        for target in &mut changed.targets {
            if target.split == Split::Holdout {
                target.weight *= 999.0;
                target.layout = Json::Null;
            }
        }
        let mut isolated = SearchState::new(123);
        let mut changed_eval = TinyEvaluator {
            manifest: &changed,
            threads,
            calls: Vec::new()
        };
        search::assess_wave(&mut isolated, candidates[..8]
            .to_vec(), &mut changed_eval, &changed, 4, 8, Objective::Ranked);
        search::assess_wave(&mut isolated, candidates[8..]
            .to_vec(), &mut changed_eval, &changed, 4, 8, Objective::Ranked);
        require(encode(&report::archive_json(&state)) == encode(&report::archive_json(&isolated)), "holdout contents affected archive")?;
        let keys = score::allocate(manifest, Stage::Quick, 9, 123)?;
        require(keys.len() <= 9 && keys.iter().all(|key| manifest.targets[key.target].split == Split::Search), "budget or split allocation failure")?;
        let development: BTreeSet<i64> = score::allocate(manifest, Stage::Confirm, 16, 123)?.iter()
            .map(|key| key.seed).collect();
        let holdout: BTreeSet<i64> = score::allocate(manifest, Stage::Holdout, 16, 123)?.iter()
            .map(|key| key.seed).collect();
        require(development.is_disjoint(&holdout), "holdout reused confirmation seeds")?;
    }
    Ok(())
}

pub fn run(
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    manifest: &TargetManifest,
    templates: &[ArmyGenome],
    iterations: usize,
) -> Result<Json, String> {
    if iterations < 2000 {
        return Err("proof fuzz count must be at least 2000".to_owned());
    }
    let mut rng = Random(20261024);
    let mut current = templates[0].clone();
    let mut accepted = 0;
    let mut rejected = 0;
    let mut reasons = std::collections::BTreeMap::<String, usize>::new();
    for index in 0..iterations {
        let candidate = if index % 17 == 0 {
            operators::immigrant(account, &mut rng).and_then(|mut genome| {
                operators::admit(account, compiler, &catalog, &mut genome)?;
                Ok(genome)
            })
        } else if index % 11 == 0 {
            let others: Vec<_> = templates.iter().filter(|other| other.plan.family == current.plan.family).collect();
            if others.is_empty() {
                operators::mutate(&current, templates, account, compiler, &catalog, &mut rng)
            } else {
                operators::crossover(&current, others[rng.index(others
                    .len())], account, compiler, &catalog, &mut rng)
            }
        } else {
            operators::mutate(&current, templates, account, compiler, &catalog, &mut rng)
        };
        match candidate {
            Ok(genome) => {
                account.check(&genome)?;
                let plan = account.compile(compiler, &catalog, &genome, genome.plan.angle_offset, 0)?;
                require(!plan.at("observed").bool(), "observed replay exemption inherited")?;
                require(plan.at("strength").f64().to_bits() == 1.0_f64.to_bits(), "strength changed")?;
                accepted += 1;
                current = genome;
            }
            Err(reason) => {
                require(!reason.is_empty(), "rejection has no reason")?;
                *reasons.entry(reason).or_default() += 1;
                rejected += 1;
            }
        }
        if (index + 1) % 500 == 0 {
            eprintln!("armysearch-proof legality {}/{}", index + 1, iterations);
        }
    }
    require(accepted > 100, "legality fuzz admitted too few genomes")?;
    let mut invalid = templates[0].clone();
    invalid.troops[0].count = 321;
    require(account.check(&invalid).is_err(), "housing overflow admitted")?;
    invalid = templates[0].clone();
    invalid.heroes[0].pet = invalid.heroes[1].pet.clone();
    require(account.check(&invalid).is_err(), "duplicate pet admitted")?;
    invalid = templates[0].clone();
    invalid.heroes[0].equipment[0] = invalid.heroes[1].equipment[0].clone();
    require(account.check(&invalid).is_err(), "wrong-owner equipment admitted")?;
    invalid = templates[0].clone();
    invalid.troops[0].name = "Meteor Golem".to_owned();
    require(account.check(&invalid).is_err(), "Barracks19 troop admitted")?;
    let mut replay = templates[0].to_build();
    crate::armies::put(&mut replay, "observed", Json::Bool(true));
    require(!ArmyGenome::from_build(&replay).to_build().at("observed")
        .bool(), "observed seed inherited exemption")?;
    let mut reordered = templates[0].clone();
    reordered.heroes.reverse();
    reordered.troops.reverse();
    for hero in &mut reordered.heroes {
        hero.equipment.reverse();
    }
    require(reordered.identity() == templates[0].identity(), "canonical identity depends on collection order")?;
    let original_plan = account.compile(compiler, &catalog, &templates[0], 0.0, 0)?;
    let reordered_plan = account.compile(compiler, &catalog, &reordered, 0.0, 0)?;
    require(encode(&original_plan) == encode(&reordered_plan), "canonical genomes compiled in different iteration orders")?;
    // One search base and one independent holdout make the native fixture
    // small while exercising the actual plan compiler, Runner and archive.
    let search_base = manifest.targets.iter().find(|target| target.split == Split::Search)
        .ok_or("proof requires search base")?.clone();
    let holdout_base = manifest.targets.iter().find(|target| target.split == Split::Holdout)
        .ok_or("proof requires holdout base")?.clone();
    let small = TargetManifest {
        targets: vec![search_base, holdout_base]
    };
    tiny_proofs(&small, &templates[0])?;
    let candidates: Vec<ArmyGenome> = templates.iter().take(2).cloned().collect();
    let mut expected = None;
    for threads in [1, 4, 16] {
        eprintln!("armysearch-proof native determinism threads={threads}");
        let mut evaluator = NativeEvaluator::new(account, compiler, Arc::clone(&catalog), &small, 999, threads, None)?;
        let mut state = SearchState::new(999);
        search::assess_wave(&mut state, candidates.clone(), &mut evaluator, &small, 4, 8, Objective::Ranked);
        require(!state.archive.is_empty(), "native battle proof produced no archive")?;
        require(state.rejected.is_empty(), "native battle proof rejected a fixture")?;
        for elite in state.archive.values().flatten() {
            let replay = evaluator.evaluate(&elite.genome, Stage::Confirm, 8)?;
            require(encode(&replay.to_json()) == encode(&elite.confirm.to_json()), "cache changed estimate")?;
        }
        require(evaluator.cache_hits > 0, "native cache proof had no cache hit")?;
        let archive = encode(&report::archive_json(&state));
        if let Some(expected) = &expected {
            require(&archive == expected, "native archive differs for 1/4/16 threads")?;
        }
        expected = Some(archive);
    }
    Ok(object([
        ("status", string("passed")),
        ("legality_iterations", number(iterations)),
        ("accepted", number(accepted)),
        ("rejected_with_reason", number(rejected)),
        ("rejection_reasons", Json::Obj(reasons.into_iter()
            .map(|(reason, count)| (reason, number(count))).collect())),
        ("native_thread_counts", Json::Arr([1, 4, 16].into_iter().map(number).collect())),
        ("gates", Json::Arr(["legality", "canonical identity", "native thread determinism", "tiny known optimum", "checkpoint roundtrip/resume", "cache equivalence", "budget ceiling", "holdout isolation and fresh seeds"].into_iter().map(string).collect())),
        ("scope", string("native proof gates only; Python plan/battle parity and catalog parity remain external reviewer gates")),
    ]))
}
