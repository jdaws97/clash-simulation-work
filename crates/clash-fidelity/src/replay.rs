//! Native compiler and runner integration, including explicit legacy selection.

use std::collections::BTreeMap;
use std::path::Path;
use std::sync::{Arc, Mutex};

use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_engine::labels::{Name, Tag};
use clash_engine::runner::Job;
use clash_engine::state::Battle;
use clash_plans::compile::{CompileOptions, Compiler};
use clash_scoring::scoring::{self, Outcome, Scenario, Scorer, Strength};
use clash_scoring::scouting::ScoutPolicy;

use super::decode::replay_seed;
use super::history::Observation;
use super::io::*;

#[derive(Clone)]
pub struct Settings {
    pub seeds: usize,
    pub angles: usize,
    pub threads: usize,
    pub attacker: String,
    pub policy: ScoutPolicy,
    pub legacy: bool,
    pub raw: bool,
    pub scout: usize,
    pub techniques: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            seeds: 5,
            angles: 8,
            threads: 1,
            attacker: "generic".to_owned(),
            policy: ScoutPolicy::Visible,
            legacy: false,
            raw: false,
            scout: 8,
            techniques: false,
        }
    }
}

pub fn strengths(root: &Path, calibration: &Path) -> Result<Strength, String> {
    Ok(Strength::from_sources(
        &read(&root.join("data/source/baselab-calibration.json"))?,
        &read(calibration)?,
        &read(&root.join("data/source/observed-armies.json"))?,
        &read(&root.join("data/source/custom-armies.json"))?,
    ))
}

pub fn current_strength(
    compiler: &Compiler<'_>,
    strengths: &Strength,
    th: i64,
    family: &str,
) -> f64 {
    for level in [th, 16] {
        let values: Vec<_> = compiler
            .library
            .builds
            .iter()
            .filter(|entry| {
                !entry.id.starts_with("custom:")
                    && number(&entry.value, "th", 0.0) == level as f64
                    && clash_plans::armies::family_of(&entry.value) == Some(family)
            })
            .filter_map(|entry| {
                let key = format!("meta:{}", entry.id);
                strengths
                    .0
                    .iter()
                    .find(|(name, _)| name == &key)
                    .map(|(_, strength)| (*strength, number(&entry.value, "share", 1.0)))
            })
            .collect();
        if !values.is_empty() {
            let total: f64 = values.iter().map(|(_, weight)| weight).sum();
            return (values
                .iter()
                .map(|(value, weight)| weight * value.ln())
                .sum::<f64>()
                / total)
                .exp();
        }
    }
    strengths.get(match family {
        "dragon" => "hydra",
        "thrower" => "throwers",
        "electro-dragon" => "edrag",
        "root-rider" => "rootrider",
        _ => "unclassified",
    })
}

pub fn attacker(
    compiler: &Compiler<'_>,
    family: &str,
    requested: &str,
) -> (String, Option<String>) {
    let book = if family == "super-dragon" {
        "dragon"
    } else {
        family
    };
    if requested == "playbook" && !compiler.playbooks.iter().any(|(name, _)| name == book) {
        let note = if family == "unclassified" {
            "unclassified army family".to_owned()
        } else {
            format!("no cited playbook for {family}")
        };
        ("generic".to_owned(), Some(note))
    } else {
        (requested.to_owned(), None)
    }
}

pub fn plan(
    compiler: &Compiler<'_>,
    build: &Json,
    angle: f64,
    seed: i64,
    strength: f64,
    attacker: &str,
) -> Result<Json, String> {
    let options = CompileOptions {
        playbooks: attacker == "playbook",
        ..CompileOptions::default()
    };
    let town_hall = number(build, "th", 16.0) as i64;
    let mut construction_build = build.clone();
    if town_hall == 15 && text(build, "archetype", "").starts_with("log-") {
        // The shared compiler admits search armies at TH16..18. Its generic
        // role composition is independent of TH; restore the real TH before
        // resolving stock, validating levels or constructing any battle.
        put(&mut construction_build, "th", num(16.0));
    }
    let mut plan = compiler.plan_for_build(&construction_build, angle, seed, &options)?;
    put(&mut plan, "town_hall", num(town_hall as f64));
    if town_hall == 15 {
        put(
            &mut plan,
            "build_id",
            string(format!("{}-15-1", text(build, "archetype", "log"))),
        );
    }
    // Exact logged rosters are observed; the compiler still runs its content
    // preflight and native setup still rejects unsupported content.
    put(&mut plan, "observed", Json::Bool(true));
    compiler.require_legal(&mut plan)?;
    put(&mut plan, "strength", num(strength * scoring::skill(seed)));
    Ok(plan)
}

pub fn end_reason(battle: &Battle) -> &'static str {
    if battle.destroyed_counted >= battle.total_counted {
        "all_buildings_destroyed"
    } else if battle.t >= battle.max_time {
        if battle.attackers_pool().any(|unit| {
            unit.alive
                && !matches!(unit.name_id, Name::Healer | Name::Unicorn | Name::Totem)
                && unit.kind != Tag::SiegeIdle
        }) {
            "timer_live_fighting_units"
        } else {
            "timer_inventory_only"
        }
    } else {
        "exhausted_offense"
    }
}

#[derive(Clone, Debug)]
pub struct Sample {
    pub stars: i64,
    pub pct: f64,
    pub time: f64,
    pub weight: f64,
    pub end_reason: String,
}

impl Sample {
    pub fn to_json(&self) -> Json {
        obj([
            ("stars", num(self.stars as f64)),
            ("destruction", num(self.pct)),
            ("time", num(self.time)),
            ("weight", num(self.weight)),
            ("end_reason", string(&self.end_reason)),
        ])
    }
}

#[derive(Clone)]
pub struct ReplayRow {
    pub observation: Observation,
    pub attacker: String,
    pub fallback: Option<String>,
    pub samples: Vec<Sample>,
    pub reasons: BTreeMap<String, usize>,
    pub planning: usize,
    pub evaluations: usize,
    pub diagnostics: usize,
    pub scenarios: Vec<Scenario>,
}

impl ReplayRow {
    pub fn to_json(&self) -> Json {
        let p3: f64 = self
            .samples
            .iter()
            .filter(|sample| sample.stars == 3)
            .map(|sample| sample.weight)
            .sum();
        let pct: f64 = self
            .samples
            .iter()
            .map(|sample| sample.pct * sample.weight)
            .sum();
        let t3: f64 = self
            .samples
            .iter()
            .filter(|sample| sample.stars == 3)
            .map(|sample| sample.time * sample.weight)
            .sum();
        obj([
            ("battle_id", string(&self.observation.id)),
            ("real_stars", num(self.observation.stars as f64)),
            ("real_pct", num(self.observation.pct)),
            ("real_time", num(self.observation.time)),
            ("attacker", string(&self.attacker)),
            (
                "attacker_fallback",
                self.fallback.as_ref().map_or(Json::Null, string),
            ),
            ("family", string(&self.observation.family)),
            ("setup_source", string(&self.observation.setup_source)),
            ("layout_path", string(&self.observation.layout_path)),
            ("layout_sha256", string(&self.observation.layout_hash)),
            ("p3", num(p3)),
            ("pct", num(pct)),
            (
                "sim_time_3star",
                if p3 > 0.0 { num(t3 / p3) } else { Json::Null },
            ),
            ("samples", arr(self.samples.iter().map(Sample::to_json))),
            ("sim_end_reason_counts", count_map(&self.reasons)),
            ("planning_battles", num(self.planning as f64)),
            ("evaluation_battles", num(self.evaluations as f64)),
            ("diagnostic_replays", num(self.diagnostics as f64)),
            (
                "evaluation_scenarios",
                arr(self.scenarios.iter().map(Scenario::to_json)),
            ),
        ])
    }
}

pub fn run_prepared(
    catalog: Arc<Catalog>,
    layout: &Json,
    scenarios: &[Scenario],
    plans: Vec<Json>,
    settings: &Settings,
) -> Result<
    (
        Vec<Sample>,
        BTreeMap<String, usize>,
        usize,
        usize,
        usize,
        Vec<Scenario>,
    ),
    String,
> {
    let scorer = Scorer::new(
        Arc::clone(&catalog),
        vec![layout.clone()],
        scenarios.to_vec(),
        plans,
        (0..scenarios.len()).collect(),
    )?;
    let th = number(layout, "town_hall", 16.0) as i64;
    let mut expected = Vec::new();
    let (eval_scenarios, indices, weights, planning, evaluations, diagnostics) = if settings.legacy
    {
        (
            scenarios.to_vec(),
            (0..scenarios.len()).collect::<Vec<_>>(),
            Vec::new(),
            0,
            scenarios.len(),
            0,
        )
    } else {
        let selected = scorer.scout(
            Arc::clone(&catalog),
            0,
            settings.threads,
            settings.policy,
            Some(settings.scout),
        )?;
        expected = selected
            .source_indices
            .iter()
            .copied()
            .zip(selected.outcomes.iter().copied())
            .collect();
        let (eval_scenarios, indices, weights) = if settings.policy == ScoutPolicy::Oracle {
            let mut evaluations = scenarios.to_vec();
            for scenario in &mut evaluations {
                // Same documented execution namespace as scouting.rs. All
                // sides in a group receive paired execution randomness.
                let identity = format!(
                    "{}|{}|{:?}|{}|0",
                    scenario.army, scenario.town_hall, scenario.modifier, scenario.group
                );
                let hash = identity.bytes().fold(0xcbf29ce484222325_u64, |hash, byte| {
                    (hash ^ byte as u64).wrapping_mul(0x100000001b3)
                });
                scenario.seed = ((3_u64 << 48) | (hash & ((1 << 48) - 1))) as i64;
            }
            let mut weights = vec![0.0; scenarios.len()];
            for (index, scenario) in selected.source_indices.iter().zip(&selected.scenarios) {
                weights[*index] = scenario.weight;
            }
            (evaluations, (0..scenarios.len()).collect(), weights)
        } else {
            let weights = selected
                .scenarios
                .iter()
                .map(|scenario| scenario.weight)
                .collect();
            (selected.scenarios, selected.source_indices, weights)
        };
        let count = indices.len();
        (
            eval_scenarios,
            indices,
            weights,
            selected.planning_battles,
            selected.evaluation_battles,
            count,
        )
    };
    let jobs: Vec<_> = eval_scenarios
        .iter()
        .zip(&indices)
        .map(|(scenario, index)| Job::new(0, *index, scenario.seed, th, scenario.modifier.clone()))
        .collect();
    let reasons = Mutex::new(vec![String::new(); jobs.len()]);
    let hook = |index: usize, _: &Job, battle: &Battle, _: &clash_engine::state::BattleResult| {
        reasons.lock().expect("diagnostic mutex")[index] = end_reason(battle).to_owned();
    };
    let results = scorer
        .runner
        .run_with_summary(&jobs, settings.threads, Some(&hook))
        .map_err(|error| format!("replay: {error:?}"))?;
    let reasons = reasons.into_inner().expect("diagnostic mutex");
    let mut counts = BTreeMap::new();
    for reason in &reasons {
        *counts.entry(reason.clone()).or_default() += 1;
    }
    let outcomes: Vec<_> = results.iter().copied().map(Outcome::from).collect();
    for (index, expected) in expected {
        let position = indices
            .iter()
            .position(|candidate| *candidate == index)
            .ok_or("missing diagnostic replay")?;
        let actual = outcomes[position];
        if actual.stars != expected.stars
            || actual.destruction != expected.destruction
            || actual.time.to_bits() != expected.time.to_bits()
        {
            return Err("diagnostic replay differs from native scout execution".to_owned());
        }
    }
    let selection = if settings.legacy {
        scoring::scouted(scenarios, &outcomes, Some(settings.scout))
    } else {
        weights
            .iter()
            .enumerate()
            .filter(|(_, weight)| **weight > 0.0)
            .map(|(index, weight)| scoring::Selection {
                scenario: index,
                weight: *weight,
            })
            .collect()
    };
    let total: f64 = selection.iter().map(|selected| selected.weight).sum();
    let samples = selection
        .iter()
        .map(|selected| {
            let row = outcomes[selected.scenario];
            Sample {
                stars: row.stars,
                pct: row.destruction,
                time: row.time,
                weight: selected.weight / total,
                end_reason: reasons[selected.scenario].clone(),
            }
        })
        .collect();
    Ok((
        samples,
        counts,
        planning,
        evaluations,
        diagnostics,
        eval_scenarios,
    ))
}

pub fn run(
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    observations: &[Observation],
    strength: &Strength,
    settings: &Settings,
) -> Result<Vec<ReplayRow>, String> {
    let mut rows = Vec::new();
    for observation in observations {
        let (kind, fallback) = attacker(compiler, &observation.family, &settings.attacker);
        let value = if settings.raw {
            1.0
        } else {
            current_strength(compiler, strength, observation.th, &observation.family)
        };
        let mut scenarios = Vec::new();
        let mut plans = Vec::new();
        let mut techniques = vec![None];
        if settings.techniques && kind == "generic" {
            for (hero, cap) in [("Archer Queen", 5.0), ("Grand Warden", 4.0)] {
                if list(&observation.build, "heroes")
                    .iter()
                    .any(|name| name.str() == hero)
                {
                    let healers = number(observation.build.at("troops"), "Healer", 0.0).min(cap);
                    techniques.push(Some((hero, healers)));
                }
            }
        }
        for seed_index in 0..settings.seeds {
            for side in 0..settings.angles {
                let seed = replay_seed(
                    &observation.id,
                    seed_index as i64,
                    side as i64,
                    settings.angles as i64,
                );
                let angle =
                    2.0 * std::f64::consts::PI * side as f64 / settings.angles as f64 + 0.21;
                for technique in &techniques {
                    let mut prepared =
                        plan(compiler, &observation.build, angle, seed, value, &kind)?;
                    if let Some((hero, healers)) = technique {
                        put(&mut prepared, "charge_hero", string(*hero));
                        put(&mut prepared, "charge_n", num(*healers));
                    }
                    plans.push(prepared);
                    scenarios.push(Scenario {
                        army: format!("observed:{}", observation.id),
                        town_hall: observation.th,
                        angle,
                        seed,
                        weight: 1.0 / (settings.seeds * settings.angles * techniques.len()) as f64,
                        modifier: if settings.legacy {
                            None
                        } else {
                            observation.modifier.clone()
                        },
                        group: seed_index as i64,
                        tactic: Json::Null,
                        charge: None,
                        full_scout: false,
                    });
                }
            }
        }
        let (samples, reasons, planning, evaluations, diagnostics, scenarios) = run_prepared(
            Arc::clone(&catalog),
            &observation.layout,
            &scenarios,
            plans,
            settings,
        )?;
        rows.push(ReplayRow {
            observation: observation.clone(),
            attacker: kind,
            fallback,
            samples,
            reasons,
            planning,
            evaluations,
            diagnostics,
            scenarios,
        });
    }
    Ok(rows)
}
