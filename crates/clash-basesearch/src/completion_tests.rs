use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock};

use clash_armysearch::account::AccountRules;
use clash_plans::compile::Compiler;
use clash_scoring::scoring::{self, Scorer};
use clash_scoring::scouting::{hidden_sample, ScoutPolicy};

use crate::archive::{Archive, DescriptorDefinition, Elite};
use crate::completion_proof::synthetic_row;
use crate::eval::{self, Budget, Evaluator, Group, Manifest};
use crate::generate::{Style, TownHallZone};
use crate::json::Json;
use crate::layout::{admit, model::AdmissionPolicy, BaseRules, Layout};
use crate::oracle::{AttackArchive, OracleContext};
use crate::search::{self, Settings, State};
use crate::util::{fingerprint, object, string};
use crate::Context;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn context() -> &'static Context {
    static CONTEXT: OnceLock<Context> = OnceLock::new();
    CONTEXT.get_or_init(|| Context {
        rules: Arc::new(BaseRules::load(&root().join("rust/data/base_rules.json")).unwrap()),
        catalog: Arc::new(
            crate::catalog::Catalog::load(&root().join("rust/data/catalog.json")).unwrap(),
        ),
    })
}

fn evaluator(threads: usize) -> Evaluator<'static> {
    Evaluator {
        context: context(),
        identity: "declared-synthetic-acceptance-v1".to_owned(),
        threads,
        budget: Budget {
            limit: 20_000,
            ..Budget::default()
        },
        cache: BTreeMap::new(),
    }
}

fn empty_group(index: usize, modifier: Option<String>) -> Group {
    let mut scenarios = Vec::new();
    let plan = crate::json::parse(r#"{"$type":"Stage","drops":[],"ticks":[],"town_hall":16,"strength":1,"loadouts":{},"revives_left":0}"#).unwrap();
    for side in 0..2 {
        let mut scenario = synthetic_row(index, "declared-empty-stage", 1.0, 0, 0.0).scenario;
        scenario.angle = side as f64 * std::f64::consts::PI;
        scenario.weight = 0.5;
        scenario.full_scout = true;
        scenario.modifier = modifier.clone();
        scenarios.push(scenario);
    }
    Group {
        id: format!("empty/{index}"),
        stratum: "declared-empty-stage".to_owned(),
        population_weight: 1.0,
        scenarios,
        plans: vec![plan.clone(), plan],
    }
}

fn settings() -> Settings {
    Settings {
        town_hall: 16,
        mode: "ranked".to_owned(),
        modifier: None,
        hole_penalty: Some(0.0),
        seed: 83,
        batch: 2,
        oracle_budget: 0,
        oracle_every: 1,
        archive_groups: 2,
        polish_attempts: 0,
        alpha: 0.05,
        descriptors: DescriptorDefinition::default(),
        racing: true,
        operator_weights: crate::cli::default_operators(),
        immigrant_every: 5,
        crossover_every: 7,
    }
}

fn compiler() -> Compiler<'static> {
    let mut compiler = Compiler::load(&root(), &context().catalog.stats).unwrap();
    compiler.library.user = crate::cli::synthetic_account(&context().catalog, 16);
    compiler.pace = 1.0;
    compiler.gaps = Some((0.0, 0.0));
    compiler
}

#[test]
fn enumerable_racing_and_restricted_games() {
    crate::completion_proof::run().unwrap();
}

#[test]
fn native_scorer_equivalence_hidden_isolation_workers_cache_and_budget() {
    let context = context();
    let base = crate::generate::preset(context, 16, Style::Grid, TownHallZone::Edge, 73).unwrap();
    let compiler = compiler();
    let account = AccountRules::load(&context.catalog, &compiler).unwrap();
    let (seeds, _) =
        clash_armysearch::operators::seeds(&root(), &account, &compiler, &context.catalog).unwrap();
    let genome = seeds
        .iter()
        .find(|genome| genome.plan.family == "root-rider")
        .unwrap();
    let oracle_context = OracleContext {
        account: &account,
        compiler: &compiler,
        catalog: &context.catalog,
    };
    let group = crate::oracle::group_for(
        &oracle_context,
        genome,
        "known-visible",
        128,
        1.0,
        Some("legend1".to_owned()),
    )
    .unwrap();
    let direct = Scorer::new(
        context.catalog.clone(),
        vec![base.engine_json()],
        group.scenarios.clone(),
        group.plans.clone(),
        vec![0, 1],
    )
    .unwrap()
    .scout(context.catalog.clone(), 0, 1, ScoutPolicy::Visible, Some(2))
    .unwrap();
    let mut first = None;
    for threads in [1, 4, 16] {
        let mut evaluator = evaluator(threads);
        let row = evaluator.evaluate(&base, &group, 0).unwrap();
        assert_eq!(row.outcome.to_json(), direct.outcomes[0].to_json());
        assert_eq!(row.scenario.to_json(), direct.scenarios[0].to_json());
        assert_eq!(row.source_index, direct.source_indices[0]);
        assert_eq!(evaluator.budget.planning, 6);
        assert_eq!(evaluator.budget.execution, 1);
        let warm = evaluator.evaluate(&base, &group, 0).unwrap();
        assert_eq!(row.to_json(), warm.to_json());
        assert_eq!(evaluator.budget.used(), 7);
        assert_eq!(evaluator.budget.cache_hits, 1);
        if let Some(expected) = &first {
            assert_eq!(&row.to_json(), expected);
        } else {
            first = Some(row.to_json());
        }
        let diagnosis = crate::diagnostics::collect(
            context,
            &base,
            std::slice::from_ref(&row),
            "visible-test",
            &mut evaluator,
        )
        .unwrap();
        assert_eq!(diagnosis.traces[0].at("outcome"), &row.outcome.to_json());
        assert!(!diagnosis.traffic.is_empty());
        let expected = scoring::objective(
            &scoring::summarise(&direct.scenarios, &direct.outcomes, Some(1)).unwrap(),
            "ranked",
            base.hole_tiles(),
            Some(0.25),
        );
        assert_eq!(
            eval::objective(&[row], "ranked", base.hole_tiles(), Some(0.25)).unwrap(),
            expected
        );
    }
    let mut changed = base.layout().clone();
    changed.buildings.retain(|building| building.key != "tesla");
    changed.traps.clear();
    changed.setup.cc_troops.clear();
    let changed = admit(
        changed,
        &context.rules,
        context.catalog.clone(),
        &AdmissionPolicy {
            require_full: false,
            ..AdmissionPolicy::default()
        },
    )
    .unwrap();
    for seed in [1, 42, 8191] {
        assert_eq!(
            hidden_sample(&base.engine_json(), &context.catalog, seed).unwrap(),
            hidden_sample(&changed.engine_json(), &context.catalog, seed).unwrap()
        );
    }
    let row = evaluator(4).evaluate(&changed, &group, 0).unwrap();
    assert_eq!(row.source_index, direct.source_indices[0]);
    let mut short = evaluator(4);
    short.budget.limit = 6;
    assert!(short.evaluate(&base, &group, 0).is_err());
    assert_eq!(short.budget.used(), 0);
    let known = crate::json::parse(include_str!("../fixtures/known-visible.json")).unwrap();
    assert_eq!(direct.outcomes[0].to_json(), *known.at("outcome"));
    assert_eq!(direct.source_indices[0], known.at("source").usize());
    assert_eq!(
        direct.planning_battles,
        known.at("planning_battles").usize()
    );
    assert_eq!(
        direct.evaluation_battles,
        known.at("execution_battles").usize()
    );
}

#[test]
fn exact_checkpoint_waves_and_thread_counts() {
    let compiler = compiler();
    let account = AccountRules::load(&context().catalog, &compiler).unwrap();
    let oracle_context = OracleContext {
        account: &account,
        compiler: &compiler,
        catalog: &context().catalog,
    };
    let settings = settings();
    let screen = Manifest {
        id: "screen".to_owned(),
        groups: (0..2).map(|i| empty_group(i, None)).collect(),
    };
    let confirm = Manifest {
        id: "confirm".to_owned(),
        groups: (10..12).map(|i| empty_group(i, None)).collect(),
    };
    let mut expected = None;
    for workers in [1, 4, 16] {
        let mut state = State::new(settings.seed);
        let mut evaluator = evaluator(workers);
        search::wave(
            context(),
            &settings,
            &mut state,
            &mut evaluator,
            &screen,
            &confirm,
            &oracle_context,
            &[],
        )
        .unwrap();
        let temp =
            std::env::temp_dir().join(format!("clash-lA-resume-{}-{workers}", std::process::id()));
        std::fs::create_dir_all(&temp).unwrap();
        let path = temp.join("checkpoint.json");
        crate::checkpoint::save(&path, "test-inputs", &state, &evaluator).unwrap();
        let policy = AdmissionPolicy {
            require_all_walls: true,
            ..AdmissionPolicy::default()
        };
        let (mut resumed, budget, cache) =
            crate::checkpoint::resume(&path, "test-inputs", context(), &settings, &policy).unwrap();
        let mut resumed_evaluator = Evaluator {
            context: context(),
            identity: evaluator.identity.clone(),
            threads: workers,
            budget,
            cache,
        };
        search::wave(
            context(),
            &settings,
            &mut state,
            &mut evaluator,
            &screen,
            &confirm,
            &oracle_context,
            &[],
        )
        .unwrap();
        search::wave(
            context(),
            &settings,
            &mut resumed,
            &mut resumed_evaluator,
            &screen,
            &confirm,
            &oracle_context,
            &[],
        )
        .unwrap();
        assert_eq!(state.to_json(), resumed.to_json());
        if workers == 1 {
            let mut full_settings = settings.clone();
            full_settings.racing = false;
            let mut full_state = State::new(settings.seed);
            let mut full_evaluator = Evaluator {
                context: context(),
                identity: evaluator.identity.clone(),
                threads: 1,
                budget: Budget {
                    limit: 20_000,
                    ..Budget::default()
                },
                cache: BTreeMap::new(),
            };
            for _ in 0..2 {
                search::wave(
                    context(),
                    &full_settings,
                    &mut full_state,
                    &mut full_evaluator,
                    &screen,
                    &confirm,
                    &oracle_context,
                    &[],
                )
                .unwrap();
            }
            assert_eq!(state.archive.to_json(), full_state.archive.to_json());
            assert_eq!(state.seen, full_state.seen);
            assert_eq!(state.rng.0, full_state.rng.0);
        }
        assert_eq!(evaluator.budget, resumed_evaluator.budget);
        assert_eq!(
            evaluator.cache.keys().collect::<Vec<_>>(),
            resumed_evaluator.cache.keys().collect::<Vec<_>>()
        );
        let artifact = state.to_json();
        if let Some(expected) = &expected {
            assert_eq!(&artifact, expected);
        } else {
            expected = Some(artifact);
        }
        assert!(
            crate::checkpoint::resume(&path, "changed-engine", context(), &settings, &policy)
                .is_err()
        );
        // The previous complete backup remains a valid recovery point if an
        // interrupted replacement leaves the primary path absent.
        crate::checkpoint::save(&path, "test-inputs", &state, &evaluator).unwrap();
        std::fs::remove_file(&path).unwrap();
        crate::checkpoint::resume(&path, "test-inputs", context(), &settings, &policy).unwrap();
        if workers == 16 {
            let frozen_state = state.to_json();
            let reference = state.archive.ranked()[0].base.clone();
            let final_a = Manifest {
                id: "final-a".to_owned(),
                groups: (100..102).map(|i| empty_group(i, None)).collect(),
            };
            let final_b = Manifest {
                id: "changed-final-seeds".to_owned(),
                groups: (200..202).map(|i| empty_group(i, None)).collect(),
            };
            let mut frozen_files = Vec::new();
            for (name, manifest) in [("a", &final_a), ("b", &final_b)] {
                let out = temp.join(name);
                std::fs::create_dir_all(&out).unwrap();
                crate::report::finish(
                    &out,
                    context(),
                    &settings,
                    &state,
                    &mut evaluator,
                    &confirm,
                    manifest,
                    &reference,
                    &oracle_context,
                )
                .unwrap();
                frozen_files.push(std::fs::read(out.join("frozen-finalists.json")).unwrap());
            }
            assert_eq!(frozen_files[0], frozen_files[1]);
            assert_eq!(state.to_json(), frozen_state);
        }
        std::fs::remove_dir_all(temp).unwrap();
    }
}

#[test]
fn enumerable_archive_optimum_and_per_cell_winners() {
    let context = context();
    let mut archive = Archive::default();
    let definition = DescriptorDefinition::default();
    let mut truth = BTreeMap::<usize, f64>::new();
    let mut candidates = Vec::new();
    for (index, x) in [2, 8, 14, 20, 28, 36].iter().enumerate() {
        let layout = Layout::from_json(&object([
            (
                "name",
                string("declared enumerable synthetic TH-only layout"),
            ),
            ("town_hall", Json::Num(16.0)),
            (
                "buildings",
                Json::Arr(vec![object([
                    ("key", string("th")),
                    ("x", Json::Num(*x as f64)),
                    ("y", Json::Num(20.0)),
                ])]),
            ),
            ("walls", Json::Arr(Vec::new())),
            ("traps", Json::Arr(Vec::new())),
            ("heroes", Json::Arr(Vec::new())),
            ("cc_troops", Json::Arr(Vec::new())),
        ]))
        .unwrap();
        let base = admit(
            layout,
            &context.rules,
            context.catalog.clone(),
            &AdmissionPolicy {
                require_full: false,
                ..AdmissionPolicy::default()
            },
        )
        .unwrap();
        let descriptor = definition.describe(context, &base).unwrap();
        let row = synthetic_row(0, "known-payoff", 1.0, 2, 50.0 + index as f64 * 6.0);
        let objective =
            eval::objective(std::slice::from_ref(&row), "ranked", 0, Some(0.0)).unwrap();
        truth
            .entry(descriptor.cell)
            .and_modify(|value| *value = value.max(objective))
            .or_insert(objective);
        let elite = Elite {
            base,
            descriptor,
            lineage: Json::Null,
            screen: vec![row.clone()],
            confirmation: vec![row],
            objective,
            robustness: 0.0,
            archive_version: 0,
        };
        candidates.push(elite.clone());
        archive.insert(elite).unwrap();
    }
    // Reverse arrival order to ensure the opening quota protects quality,
    // rather than whichever layout happened to arrive first in the cell.
    candidates.reverse();
    let scores: Vec<_> = candidates.iter().map(|elite| elite.objective).collect();
    let cells: Vec<_> = candidates
        .iter()
        .map(|elite| elite.descriptor.cell)
        .collect();
    let protected = crate::race::protect_open_cells(&scores, &cells, &Default::default());
    let promotions = crate::race::halve(&scores, &protected, 1);
    let mut raced = Archive::default();
    for index in promotions {
        raced.insert(candidates[index].clone()).unwrap();
    }
    assert_eq!(archive.cells.len(), raced.cells.len());
    for (cell, elite) in &archive.cells {
        assert_eq!(elite.objective, raced.cells[cell].objective);
    }
    assert_eq!(archive.ranked()[0].objective, 24.0 - 0.0025);
    for (cell, expected) in truth {
        assert_eq!(archive.cells[&cell].objective, expected);
    }
    let mut stale = archive.ranked()[0].clone();
    stale.archive_version = 1;
    assert!(archive.insert(stale).is_err());
}

#[test]
fn attack_duplicates_historical_retention_and_oracle_accounting() {
    let compiler = compiler();
    let account = AccountRules::load(&context().catalog, &compiler).unwrap();
    let (seeds, _) =
        clash_armysearch::operators::seeds(&root(), &account, &compiler, &context().catalog)
            .unwrap();
    let oracle_context = OracleContext {
        account: &account,
        compiler: &compiler,
        catalog: &context().catalog,
    };
    let base =
        crate::generate::preset(context(), 16, Style::Grid, TownHallZone::Central, 52).unwrap();
    let mut archive = AttackArchive::default();
    let mut evaluator = evaluator(4);
    for adapter in [
        &crate::oracle::PlaybookOracle as &dyn crate::oracle::AttackOracle,
        &crate::oracle::ArmyProgramOracle,
    ] {
        let before = evaluator.budget.used();
        let entry = crate::oracle::discover(
            adapter,
            &oracle_context,
            &seeds,
            &base,
            &mut evaluator,
            &archive,
            81,
            28,
            "ranked",
            None,
        )
        .unwrap()
        .unwrap();
        assert!(evaluator.budget.used() - before <= 28);
        assert_eq!(entry.validation.len(), 2);
        account.check(&entry.genome).unwrap();
        if adapter.name().contains("program") {
            assert!(entry.genome.plan.program.is_some());
        }
        assert!(archive.insert(entry.clone()));
        archive.compatible(&entry).unwrap();
        let mut incompatible = entry.clone();
        clash_plans::armies::put(&mut incompatible.metadata, "mode", string("war"));
        assert!(archive.compatible(&incompatible).is_err());
        let version = archive.version;
        assert!(!archive.insert(entry));
        assert_eq!(archive.version, version);
    }
    let id = archive.entries.keys().next().unwrap().clone();
    archive.entries.get_mut(&id).unwrap().active = false;
    let decoded = AttackArchive::from_json(&archive.to_json()).unwrap();
    assert!(decoded.entries.contains_key(&id));
    assert!(!decoded.entries[&id].active);
    assert_eq!(evaluator.budget.oracle_training, 28);
    assert_eq!(evaluator.budget.oracle_validation, 28);
}

#[test]
fn th17_th18_descriptors_no_eagle_required_and_frozen_corpus() {
    let mut corpus = Vec::new();
    for th in [17, 18] {
        let base =
            crate::generate::preset(context(), th, Style::Scatter, TownHallZone::Central, 84)
                .unwrap();
        assert!(!base
            .layout()
            .buildings
            .iter()
            .any(|building| building.key == "eagle"));
        let descriptor = DescriptorDefinition::default()
            .describe(context(), &base)
            .unwrap();
        assert!(descriptor.cell < 81);
        assert!(descriptor.values.iter().all(|value| value.is_finite()));
        corpus.push(base);
    }
    corpus.push(
        crate::generate::preset(context(), 16, Style::Wide, TownHallZone::Edge, 600).unwrap(),
    );
    let (definition, receipt) = DescriptorDefinition::from_corpus(context(), &corpus).unwrap();
    assert_eq!(definition.corpus_identity, fingerprint(&receipt));
    let (repeated, repeated_receipt) =
        DescriptorDefinition::from_corpus(context(), &corpus).unwrap();
    assert_eq!(definition, repeated);
    assert_eq!(receipt, repeated_receipt);
}

#[test]
fn paired_reports_holdout_isolation_and_replayable_jobs() {
    let base =
        crate::generate::preset(context(), 16, Style::Grid, TownHallZone::Central, 99).unwrap();
    let mut evaluator = evaluator(4);
    let rows = (0..2)
        .map(|i| evaluator.evaluate(&base, &empty_group(i, None), 0).unwrap())
        .collect::<Vec<_>>();
    let interval = crate::report::paired_bootstrap(&rows, &rows, "ranked", 27).unwrap();
    assert_eq!(interval.at("mean").f64(), 0.0);
    assert_eq!(
        interval.at("interval"),
        &Json::Arr(vec![Json::Num(0.0), Json::Num(0.0)])
    );
    let prepared = crate::report::prepared_jobs(&[&base], std::slice::from_ref(&rows));
    let inputs = crate::runner::PreparedInputs::from_json(&prepared);
    let jobs = inputs.jobs.clone();
    let replay = crate::runner::Runner::new(context().catalog.clone(), inputs)
        .run(&jobs, 4)
        .unwrap();
    for (result, row) in replay.iter().zip(&rows) {
        assert_eq!(result.stars as i64, row.outcome.stars);
        assert_eq!(result.destruction as f64, row.outcome.destruction);
    }
    let before = fingerprint(&object([(
        "rows",
        Json::Arr(rows.iter().map(|row| row.to_json()).collect()),
    )]));
    let changed_final = (100..102)
        .map(|i| evaluator.evaluate(&base, &empty_group(i, None), 0).unwrap())
        .collect::<Vec<_>>();
    crate::report::paired_bootstrap(&changed_final, &changed_final, "war", 492).unwrap();
    assert_eq!(
        before,
        fingerprint(&object([(
            "rows",
            Json::Arr(rows.iter().map(|row| row.to_json()).collect())
        )]))
    );
    let mut wrong = rows.clone();
    wrong[0].group_id = "changed-lineage".to_owned();
    assert!(crate::report::paired_bootstrap(&rows, &wrong, "ranked", 27).is_err());
}
