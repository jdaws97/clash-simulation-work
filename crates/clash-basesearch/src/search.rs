//! Deterministic waves: proposals -> screen/race -> independent confirmation ->
//! frozen-version QD -> bounded attack discovery -> elite reevaluation.
use std::collections::{BTreeMap, BTreeSet};

use clash_armysearch::genome::ArmyGenome;

use crate::archive::{self, Archive, DescriptorDefinition, Elite};
use crate::eval::{self, Evaluator, Manifest, Row};
use crate::generate::{Style, TownHallZone};
use crate::json::Json;
use crate::layout::AdmittedLayout;
use crate::operators::{propose, Operator};
use crate::oracle::{self, ArmyProgramOracle, AttackArchive, OracleContext, PlaybookOracle};
use crate::race;
use crate::repair::RepairLimits;
use crate::util::{num, object, string};
use crate::{Context, ProposalRng};

#[derive(Clone, Debug)]
pub struct Settings {
    pub town_hall: i64,
    pub mode: String,
    pub modifier: Option<String>,
    pub hole_penalty: Option<f64>,
    pub seed: u64,
    pub batch: usize,
    pub oracle_budget: usize,
    pub oracle_every: usize,
    pub archive_groups: usize,
    pub polish_attempts: usize,
    pub alpha: f64,
    pub descriptors: DescriptorDefinition,
    pub racing: bool,
    pub operator_weights: Vec<(Operator, usize)>,
    pub immigrant_every: usize,
    pub crossover_every: usize,
}

impl Settings {
    pub fn to_json(&self) -> Json {
        object([
            ("town_hall", Json::Num(self.town_hall as f64)),
            ("mode", string(&self.mode)),
            ("modifier", self.modifier.clone().map_or(Json::Null, string)),
            (
                "hole_penalty",
                self.hole_penalty.map_or(Json::Null, Json::Num),
            ),
            ("seed", string(self.seed.to_string())),
            ("batch", num(self.batch)),
            ("oracle_budget", num(self.oracle_budget)),
            ("oracle_every", num(self.oracle_every)),
            ("archive_groups", num(self.archive_groups)),
            ("polish_attempts", num(self.polish_attempts)),
            ("alpha", Json::Num(self.alpha)),
            ("descriptors", self.descriptors.to_json()),
            ("racing", Json::Bool(self.racing)),
            ("immigrant_every", num(self.immigrant_every)),
            ("crossover_every", num(self.crossover_every)),
            (
                "operator_weights",
                Json::Arr(
                    self.operator_weights
                        .iter()
                        .map(|(operator, weight)| {
                            object([
                                ("operator", string(operator.name())),
                                ("weight", num(*weight)),
                            ])
                        })
                        .collect(),
                ),
            ),
        ])
    }

    pub fn validate(&self) -> Result<(), String> {
        if !(16..=18).contains(&self.town_hall)
            || !matches!(self.mode.as_str(), "ranked" | "war")
            || self.batch == 0
            || self.archive_groups == 0
            || self.oracle_every == 0
            || self.immigrant_every == 0
            || self.crossover_every == 0
            || self.operator_weights.is_empty()
            || self.operator_weights.iter().any(|(_, weight)| *weight == 0)
            || !(0.0..1.0).contains(&self.alpha)
            || self.alpha == 0.0
            || self
                .hole_penalty
                .is_some_and(|value| !value.is_finite() || value < 0.0)
            || self
                .descriptors
                .edges
                .iter()
                .any(|edges| !edges[0].is_finite() || !edges[1].is_finite() || edges[0] >= edges[1])
        {
            return Err("invalid base search settings".to_owned());
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct State {
    pub rng: ProposalRng,
    pub completed_waves: usize,
    pub candidate_cursor: usize,
    pub archive: Archive,
    pub attacks: AttackArchive,
    pub seen: BTreeSet<String>,
    pub rejected: BTreeMap<String, usize>,
    pub race_looks: usize,
    pub race_eliminated: usize,
    pub polished: bool,
    pub polish_log: Vec<Json>,
    pub annealing_temperature: f64,
    pub used_screen_seeds: BTreeSet<String>,
}

impl State {
    pub fn new(seed: u64) -> Self {
        Self {
            rng: ProposalRng::new(seed),
            completed_waves: 0,
            candidate_cursor: 0,
            archive: Archive::default(),
            attacks: AttackArchive::default(),
            seen: BTreeSet::new(),
            rejected: BTreeMap::new(),
            race_looks: 0,
            race_eliminated: 0,
            polished: false,
            polish_log: Vec::new(),
            annealing_temperature: 1.0,
            used_screen_seeds: BTreeSet::new(),
        }
    }

    pub fn to_json(&self) -> Json {
        object([
            (
                "used_screen_seeds",
                Json::Arr(self.used_screen_seeds.iter().map(string).collect()),
            ),
            ("rng", string(self.rng.0.to_string())),
            ("completed_waves", num(self.completed_waves)),
            ("candidate_cursor", num(self.candidate_cursor)),
            ("archive", self.archive.to_json()),
            ("attacks", self.attacks.to_json()),
            ("seen", Json::Arr(self.seen.iter().map(string).collect())),
            (
                "rejected",
                Json::Obj(
                    self.rejected
                        .iter()
                        .map(|(reason, count)| (reason.clone(), num(*count)))
                        .collect(),
                ),
            ),
            ("race_looks", num(self.race_looks)),
            ("race_eliminated", num(self.race_eliminated)),
            ("polished", Json::Bool(self.polished)),
            ("polish_log", Json::Arr(self.polish_log.clone())),
            (
                "annealing_temperature",
                Json::Num(self.annealing_temperature),
            ),
        ])
    }
}

struct Candidate {
    base: AdmittedLayout,
    lineage: Json,
    screen: Vec<Row>,
    eliminated: bool,
}

fn proposals(
    context: &Context,
    settings: &Settings,
    state: &mut State,
) -> Result<Vec<Candidate>, String> {
    let mut candidates = Vec::new();
    // Bounded attempts make an exhausted or constrained space explicit.
    for _ in 0..settings.batch * 64 {
        if candidates.len() == settings.batch {
            break;
        }
        let seed = state.rng.next_u64();
        let cursor = state.candidate_cursor;
        state.candidate_cursor += 1;
        let fresh =
            state.archive.cells.is_empty() || cursor.is_multiple_of(settings.immigrant_every);
        let (base, lineage) = if fresh {
            let style = Style::ALL[state.rng.index(Style::ALL.len())];
            let zone = TownHallZone::ALL[state.rng.index(3)];
            match crate::generate::preset(context, settings.town_hall, style, zone, seed) {
                Ok(base) => (
                    base,
                    object([
                        ("emitter", string(format!("immigrant:{style:?}:{zone:?}"))),
                        ("seed", string(seed.to_string())),
                    ]),
                ),
                Err(error) => {
                    *state.rejected.entry(format!("{error:?}")).or_default() += 1;
                    continue;
                }
            }
        } else {
            let ranked = if cursor % 4 == 1 {
                let mut parents: Vec<_> = state.archive.pareto.iter().collect();
                parents.sort_by(|a, b| {
                    b.robustness
                        .total_cmp(&a.robustness)
                        .then(b.objective.total_cmp(&a.objective))
                        .then(a.base.physical_identity().cmp(b.base.physical_identity()))
                });
                parents
            } else {
                state.archive.ranked()
            };
            // Half of parent draws are uniform over occupied cells; the other
            // half favor quality. Fresh immigrants retain an explicit quota.
            let index = if cursor.is_multiple_of(2) {
                state.rng.index(ranked.len())
            } else {
                state
                    .rng
                    .index(ranked.len())
                    .min(state.rng.index(ranked.len()))
            };
            let parent = &ranked[index].base;
            let total_weight: usize = settings
                .operator_weights
                .iter()
                .map(|(_, weight)| weight)
                .sum();
            let mut draw = state.rng.index(total_weight);
            let mut operator = settings.operator_weights[0].0;
            for (choice, weight) in &settings.operator_weights {
                if draw < *weight {
                    operator = *choice;
                    break;
                }
                draw -= weight;
            }
            let proposal = if cursor.is_multiple_of(settings.crossover_every) && ranked.len() > 1 {
                crate::crossover::crossover(
                    context,
                    parent,
                    &ranked[state.rng.index(ranked.len())].base,
                    seed,
                    RepairLimits::default(),
                )
            } else {
                propose(
                    context,
                    parent,
                    operator,
                    seed,
                    None,
                    RepairLimits::default(),
                )
            };
            match proposal {
                Ok(proposal) => {
                    let lineage = object([
                        ("emitter", string(proposal.operator)),
                        ("seed", string(seed.to_string())),
                        (
                            "parents",
                            Json::Arr(proposal.parents.iter().map(string).collect()),
                        ),
                        (
                            "changed_instances",
                            Json::Arr(proposal.changed_instances.iter().map(string).collect()),
                        ),
                        (
                            "repair_actions",
                            Json::Arr(
                                proposal
                                    .repair_actions
                                    .iter()
                                    .map(|action| {
                                        object([
                                            ("instance", string(&action.instance)),
                                            ("description", string(&action.description)),
                                        ])
                                    })
                                    .collect(),
                            ),
                        ),
                    ]);
                    (proposal.candidate, lineage)
                }
                Err(error) => {
                    *state.rejected.entry(format!("{error:?}")).or_default() += 1;
                    continue;
                }
            }
        };
        if state.seen.insert(base.physical_identity().to_owned()) {
            candidates.push(Candidate {
                base,
                lineage,
                screen: Vec::new(),
                eliminated: false,
            });
        }
    }
    if candidates.is_empty() {
        return Err("proposal space exhausted; inspect rejection receipts".to_owned());
    }
    Ok(candidates)
}

pub fn wave(
    context: &Context,
    settings: &Settings,
    state: &mut State,
    evaluator: &mut Evaluator<'_>,
    screen: &Manifest,
    confirmation: &Manifest,
    oracle_context: &OracleContext<'_, '_>,
    seeds: &[ArmyGenome],
) -> Result<(), String> {
    settings.validate()?;
    screen.validate()?;
    confirmation.validate()?;
    Manifest::ensure_disjoint(&[screen, confirmation])?;
    let screen_seeds = screen.seed_keys();
    if !state.used_screen_seeds.is_disjoint(&screen_seeds) {
        return Err("racing requires fresh, disjoint screen samples for every wave".to_owned());
    }
    let mut candidates = proposals(context, settings, state)?;
    // Freeze the proposals and incumbents before observing this wave's data.
    // Previous screen rows selected the parents and cannot be used to race.
    let mut incumbent_rows = BTreeMap::<usize, Vec<Row>>::new();
    if settings.racing {
        for candidate in &candidates {
            let cell = settings
                .descriptors
                .describe(context, &candidate.base)?
                .cell;
            if let Some(incumbent) = state.archive.cells.get(&cell) {
                if let std::collections::btree_map::Entry::Vacant(entry) =
                    incumbent_rows.entry(cell)
                {
                    entry.insert(evaluator.assess(
                        &incumbent.base,
                        screen,
                        state.attacks.version,
                    )?);
                }
            }
        }
    }
    let strata = screen.strata();
    let comparisons = (state.completed_waves + 1) as f64 * (state.completed_waves + 2) as f64;
    let alpha = settings.alpha / comparisons / candidates.len() as f64;
    for (group_index, group) in screen.groups.iter().enumerate() {
        for candidate in &mut candidates {
            if candidate.eliminated {
                continue;
            }
            candidate.screen.push(evaluator.evaluate(
                &candidate.base,
                group,
                state.attacks.version,
            )?);
            let descriptor = settings.descriptors.describe(context, &candidate.base)?;
            if let Some(incumbent) = state
                .archive
                .cells
                .get(&descriptor.cell)
                .filter(|_| settings.racing)
            {
                if incumbent.archive_version != state.attacks.version {
                    return Err("stale incumbent attack version".to_owned());
                }
                state.race_looks += 1;
                let per_tile = settings
                    .hole_penalty
                    .unwrap_or(if settings.mode == "ranked" { 0.25 } else { 0.8 });
                let delta = (incumbent.base.hole_tiles() as f64
                    - candidate.base.hole_tiles() as f64)
                    * per_tile;
                if race::paired(
                    &candidate.screen,
                    &incumbent_rows[&descriptor.cell],
                    &strata,
                    &settings.mode,
                    delta,
                    alpha,
                    group_index + 1,
                )?
                .is_some_and(|interval| interval.upper < 0.0)
                {
                    candidate.eliminated = true;
                    state.race_eliminated += 1;
                }
            }
        }
    }
    let survivors: Vec<_> = candidates
        .iter()
        .enumerate()
        .filter(|(_, candidate)| !candidate.eliminated)
        .map(|(index, _)| index)
        .collect();
    let scores = survivors
        .iter()
        .map(|&i| {
            eval::objective(
                &candidates[i].screen,
                &settings.mode,
                candidates[i].base.hole_tiles(),
                settings.hole_penalty,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let cells = survivors
        .iter()
        .map(|&i| {
            let cell = settings
                .descriptors
                .describe(context, &candidates[i].base)?
                .cell;
            Ok(cell)
        })
        .collect::<Result<Vec<_>, String>>()?;
    let occupied = state.archive.cells.keys().copied().collect();
    let protected = race::protect_open_cells(&scores, &cells, &occupied);
    let promotions = race::halve(&scores, &protected, 1);
    for promotion in promotions {
        let candidate = &candidates[survivors[promotion]];
        let rows = evaluator.assess(&candidate.base, confirmation, state.attacks.version)?;
        let mut elite = Elite {
            base: candidate.base.clone(),
            descriptor: settings.descriptors.describe(context, &candidate.base)?,
            lineage: candidate.lineage.clone(),
            screen: candidate.screen.clone(),
            confirmation: rows,
            objective: 0.0,
            robustness: 0.0,
            archive_version: state.attacks.version,
        };
        archive::score(&mut elite, &settings.mode, settings.hole_penalty)?;
        elite.robustness = evaluate_attacks(
            settings,
            &mut state.attacks,
            &elite.base,
            evaluator,
            oracle_context,
        )?;
        state.archive.insert(elite)?;
    }
    if (state.completed_waves + 1).is_multiple_of(settings.oracle_every)
        && settings.oracle_budget >= 28
    {
        let ranked = state.archive.ranked();
        let mut targets = Vec::new();
        if let Some(strong) = ranked.first() {
            targets.push(strong.base.clone());
            if let Some(weak) = ranked.iter().skip(1).min_by(|a, b| {
                a.robustness
                    .total_cmp(&b.robustness)
                    .then(a.base.physical_identity().cmp(b.base.physical_identity()))
            }) {
                targets.push(weak.base.clone());
            }
        }
        let old_version = state.attacks.version;
        // Strong and diverse cells are both targets. Archived historical
        // attacks are never removed when a new best response appears.
        for target in targets {
            for adapter in [
                &PlaybookOracle as &dyn oracle::AttackOracle,
                &ArmyProgramOracle,
            ] {
                if let Some(entry) = oracle::discover(
                    adapter,
                    oracle_context,
                    seeds,
                    &target,
                    evaluator,
                    &state.attacks,
                    state.rng.next_u64(),
                    settings.oracle_budget,
                    &settings.mode,
                    settings.modifier.clone(),
                )? {
                    state.attacks.compatible(&entry)?;
                    state.attacks.insert(entry);
                }
            }
        }
        if old_version != state.attacks.version {
            refresh(settings, state, evaluator, oracle_context)?;
        }
    }
    state.completed_waves += 1;
    state.used_screen_seeds.extend(screen_seeds);
    state.annealing_temperature *= 0.95;
    Ok(())
}

pub fn evaluate_attacks(
    settings: &Settings,
    attacks: &mut AttackArchive,
    base: &AdmittedLayout,
    evaluator: &mut Evaluator<'_>,
    context: &OracleContext<'_, '_>,
) -> Result<f64, String> {
    let mut worst = f64::INFINITY;
    for entry in attacks.entries.values().filter(|entry| entry.active) {
        let existing = attacks
            .payoffs
            .get(base.physical_identity())
            .and_then(|values| values.get(&entry.id));
        let rows = if let Some(rows) = existing {
            rows.clone()
        } else {
            let mut rows = Vec::new();
            for replicate in 0..settings.archive_groups {
                let seed = (3 << 44) + replicate as i64 + (settings.seed & ((1 << 40) - 1)) as i64;
                let group = oracle::group_for(
                    context,
                    &entry.genome,
                    "archive-development",
                    seed,
                    1.0,
                    settings.modifier.clone(),
                )?;
                rows.push(evaluator.evaluate(base, &group, attacks.version)?);
            }
            rows
        };
        worst = worst.min(eval::objective(&rows, &settings.mode, 0, Some(0.0))?);
        attacks
            .payoffs
            .entry(base.physical_identity().to_owned())
            .or_default()
            .insert(entry.id.clone(), rows);
    }
    // No discovered attacks is an explicitly empty dimension, represented as
    // zero rather than an infinite value in portable JSON.
    Ok(if worst.is_finite() { worst } else { 0.0 })
}

fn refresh(
    settings: &Settings,
    state: &mut State,
    evaluator: &mut Evaluator<'_>,
    context: &OracleContext<'_, '_>,
) -> Result<(), String> {
    let mut all: BTreeMap<_, _> = state
        .archive
        .cells
        .values()
        .chain(&state.archive.pareto)
        .map(|elite| (elite.base.physical_identity().to_owned(), elite.clone()))
        .collect();
    let occupied: BTreeSet<_> = state
        .archive
        .cells
        .values()
        .map(|elite| elite.base.physical_identity().to_owned())
        .collect();
    let mut archive = Archive::default();
    for elite in all.values_mut() {
        elite.robustness = evaluate_attacks(
            settings,
            &mut state.attacks,
            &elite.base,
            evaluator,
            context,
        )?;
        elite.archive_version = state.attacks.version;
        if occupied.contains(elite.base.physical_identity()) {
            archive.insert(elite.clone())?;
        }
    }
    // Pareto points are refreshed even when they are no longer cell winners.
    for elite in all.into_values() {
        if !archive
            .pareto
            .iter()
            .any(|current| current.base.physical_identity() == elite.base.physical_identity())
        {
            archive.pareto.push(elite);
        }
    }
    archive.retain_pareto();
    state.archive = archive;
    Ok(())
}
