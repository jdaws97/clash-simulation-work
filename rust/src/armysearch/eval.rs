//! In-process plans and battles; rust_bridge.py:108-149's subprocess is removed.

use std::collections::BTreeMap;
use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::Path;
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;
use crate::runner::{Job, PreparedInputs, Runner};
use crate::scoring::{Outcome, PlanProvider, Scenario};

use super::account::{AccountRules, NativePlanProvider};
use super::genome::ArmyGenome;
use super::score::{self, CandidateEstimate, ScenarioKey, Stage, TargetManifest};
use super::util::{encode, number, object, string};

pub trait Evaluator {
    fn evaluate(
        &mut self,
        genome: &ArmyGenome,
        stage: Stage,
        budget: usize,
    ) -> Result<CandidateEstimate, String>;
}

pub struct NativeEvaluator<'a, 'b> {
    account: &'a AccountRules,
    compiler: &'a Compiler<'b>,
    catalog: Arc<Catalog>,
    manifest: &'a TargetManifest,
    seed: u64,
    pub threads: usize,
    /// Cache lifetime binds account/catalog/layouts/options. The rest of the
    /// key is the *full* compiled plan and job JSON, not a collision-prone ID.
    cache: BTreeMap<String, Outcome>,
    cache_bytes: usize,
    raw: Option<BufWriter<File>>,
    pub executed: usize,
    pub cache_hits: usize,
}

impl<'a, 'b> NativeEvaluator<'a, 'b> {
    pub fn raw_len(&mut self) -> Result<u64, String> {
        if let Some(raw) = &mut self.raw {
            raw.flush().map_err(|error| error.to_string())?;
            raw.get_ref().sync_all().map_err(|error| error.to_string())?;
            raw.get_ref().metadata().map(|metadata| metadata.len())
                .map_err(|error| error.to_string())
        } else {
            Ok(0)
        }
    }

    pub fn new(
        account: &'a AccountRules,
        compiler: &'a Compiler<'b>,
        catalog: Arc<Catalog>,
        manifest: &'a TargetManifest,
        seed: u64,
        threads: usize,
        raw_path: Option<&Path>,
    ) -> Result<Self, String> {
        if threads == 0 {
            return Err("threads must be positive".to_owned());
        }
        let raw = raw_path.map(|path| OpenOptions::new().create(true).append(true).open(path)
            .map(BufWriter::new).map_err(|error| error.to_string())).transpose()?;
        Ok(Self {
            account,
            compiler,
            catalog,
            manifest,
            seed,
            threads,
            cache: BTreeMap::new(),
            cache_bytes: 0,
            raw,
            executed: 0,
            cache_hits: 0
        })
    }

    pub fn evaluate_rows(
        &mut self,
        genome: &ArmyGenome,
        stage: Stage,
        budget: usize,
    ) -> Result<(Vec<ScenarioKey>, Vec<Outcome>), String> {
        let keys = score::allocate(self.manifest, stage, budget, self.seed)?;
        let identity = genome.identity();
        let mut provider = NativePlanProvider {
            account: self.account,
            compiler: self.compiler,
            catalog: &self.catalog,
            genome,
        };
        let mut plans = Vec::new();
        let mut jobs = Vec::new();
        let mut pending = Vec::new();
        let mut outcomes = vec![None; keys.len()];
        for (index, key) in keys.iter().enumerate() {
            let target = &self.manifest.targets[key.target];
            let angle = (key.angle + genome.plan.angle_offset).rem_euclid(2.0 * std::f64::consts::PI);
            let scenario = Scenario {
                army: identity.clone(),
                town_hall: target.town_hall,
                angle,
                seed: key.seed,
                weight: 1.0,
                modifier: None,
                group: key.replicate as i64,
                tactic: Json::Null,
                charge: None,
                full_scout: false,
            };
            let plan = provider.prepare(&scenario, 1.0)?;
            if plan.at("strength").f64().to_bits() != 1.0_f64.to_bits() {
                return Err("compiled plan changed strength".to_owned());
            }
            let job = Job::new(key.target, plans.len(), key.seed, target.town_hall, None);
            let cache_key = format!("{}|{}|{}|{}", key.target, key.seed, target.town_hall, encode(&plan));
            if let Some(outcome) = self.cache.get(&cache_key) {
                outcomes[index] = Some(*outcome);
                self.cache_hits += 1;
            } else {
                plans.push(plan);
                jobs.push(job);
                pending.push((index, cache_key));
            }
        }
        let layouts = self.manifest.targets.iter().map(|target| target.layout.clone()).collect();
        let runner = Runner::new(Arc::clone(&self.catalog), PreparedInputs::new(layouts, plans));
        let results = runner.run(&jobs, self.threads)
            .map_err(|error| format!("armysearch battle failure: {error:?}"))?;
        self.executed += results.len();
        for ((index, key), result) in pending.into_iter().zip(results) {
            let outcome = Outcome::from(result);
            self.cache_bytes += key.len();
            self.cache.insert(key, outcome);
            // Deterministic bounded storage; cache eviction affects work only.
            while self.cache_bytes > 64 * 1024 * 1024 {
                let Some((key, _)) = self.cache.pop_first() else {
                    break;
                };
                self.cache_bytes -= key.len();
            }
            outcomes[index] = Some(outcome);
        }
        let outcomes: Vec<Outcome> = outcomes.into_iter().map(|outcome| outcome
            .expect("ordered Runner result")).collect();
        if let Some(raw) = &mut self.raw {
            for (key, outcome) in keys.iter().zip(&outcomes) {
                let row = object([
                    ("genome", string(&identity)),
                    ("stage", string(stage.name())),
                    ("base", string(&self.manifest.targets[key.target].id)),
                    ("replicate", number(key.replicate)),
                    ("side", number(key.side)),
                    ("sides", number(key.sides)),
                    ("seed", Json::Num(key.seed as f64)),
                    ("grid_angle", Json::Num(key.angle)),
                    ("angle", Json::Num((key.angle + genome.plan.angle_offset)
                        .rem_euclid(2.0 * std::f64::consts::PI))),
                    ("strength", Json::Num(1.0)),
                    ("outcome", outcome.to_json()),
                ]);
                writeln!(raw, "{}", encode(&row)).map_err(|error| error.to_string())?;
            }
            raw.flush().map_err(|error| error.to_string())?;
        }
        Ok((keys, outcomes))
    }

    /// Replay a weighted median of *scouted selections*, never the best side
    /// of the entire grid. Recording must reproduce the original scalar row.
    pub fn median_replay(
        &mut self,
        genome: &ArmyGenome,
        keys: &[ScenarioKey],
        outcomes: &[Outcome],
    ) -> Result<Json, String> {
        let mut selections = Vec::new();
        for (target, base) in self.manifest.targets.iter().enumerate() {
            let groups = keys.iter().filter(|key| key.target == target).map(|key| key.replicate).max();
            let Some(groups) = groups.map(|last| last + 1) else {
                continue;
            };
            for replicate in 0..groups {
                let indices: Vec<_> = keys.iter().enumerate().filter(|(_, key)| key.target == target && key.replicate == replicate).map(|(index, _)| index).collect();
                let scenarios: Vec<_> = indices.iter().map(|index| Scenario {
                    army: base.id.clone(),
                    town_hall: base.town_hall,
                    angle: keys[*index].angle,
                    seed: keys[*index].seed,
                    weight: base.weight / groups as f64 / indices.len() as f64,
                    modifier: None,
                    group: replicate as i64,
                    tactic: Json::Null,
                    charge: None,
                    full_scout: false,
                }).collect();
                let rows: Vec<_> = indices.iter().map(|index| outcomes[*index]).collect();
                for selected in crate::scoring::scouted(&scenarios, &rows, Some(crate::scoring::SCOUT)) {
                    selections.push((indices[selected.scenario], selected.weight));
                }
            }
        }
        selections.sort_by(|(a, _), (b, _)| {
            let left = crate::scoring::attacker_trophies(outcomes[*a].stars, outcomes[*a].destruction);
            let right = crate::scoring::attacker_trophies(outcomes[*b].stars, outcomes[*b].destruction);
            left.cmp(&right).then_with(|| outcomes[*a].destruction.total_cmp(&outcomes[*b].destruction)).then_with(|| a.cmp(b))
        });
        let total: f64 = selections.iter().map(|(_, weight)| weight).sum();
        let mut cumulative = 0.0;
        let selected = selections.iter().find_map(|(index, weight)| {
            cumulative += weight;
            (cumulative >= total * 0.5).then_some(*index)
        }).ok_or("median replay has no weighted rows")?;
        let key = &keys[selected];
        let target = &self.manifest.targets[key.target];
        let angle = (key.angle + genome.plan.angle_offset).rem_euclid(2.0 * std::f64::consts::PI);
        let plan = self.account.compile(self.compiler, &self.catalog, genome, angle, key.seed)?;
        let runner = Runner::new(Arc::clone(&self.catalog), PreparedInputs::new(vec![target.layout
            .clone()], vec![plan]));
        let job = Job::new(0, 0, key.seed, target.town_hall, None);
        let mut battle = runner.build(&job);
        battle.record = true;
        let result = battle.run();
        self.executed += 1;
        let original = outcomes[selected];
        if result.stars as i64 != original.stars || result.destruction as f64 != original.destruction
            || result.time.to_bits() != original.time.to_bits() || result.th_destroyed != original.th_destroyed
        {
            return Err("recorded median replay differs from original battle".to_owned());
        }
        let events = result.log.iter()
            .map(|event| crate::json::parse(&crate::trace::event_json(event)).map_err(|error| error
                .to_string())).collect::<Result<Vec<_>, _>>()?;
        let mut narrative = Vec::new();
        if let crate::state::Plan::Playbook(plan) = &battle.plan {
            for (time, id) in plan.log_steps.iter() {
                narrative.push(string(format!("{time:.1}s: execute plan step {id}")));
            }
        }
        narrative.push(string(format!("Finish: {} stars, {}% destruction, {} attacker trophies", result.stars, result.destruction, crate::scoring::attacker_trophies(original.stars, original.destruction))));
        Ok(object([
            ("selection", string("weighted median of holdout scouting selections")),
            ("base", string(&target.id)),
            ("seed", Json::Num(key.seed as f64)),
            ("angle", Json::Num(angle)),
            ("outcome", original.to_json()),
            ("verified_recording_parity", Json::Bool(true)),
            ("narrative", Json::Arr(narrative)),
            ("events", Json::Arr(events)),
        ]))
    }
}

impl Evaluator for NativeEvaluator<'_, '_> {
    fn evaluate(
        &mut self,
        genome: &ArmyGenome,
        stage: Stage,
        budget: usize,
    ) -> Result<CandidateEstimate, String> {
        let (keys, outcomes) = self.evaluate_rows(genome, stage, budget)?;
        score::summarise(self.manifest, stage, &keys, &outcomes, budget)
    }
}
