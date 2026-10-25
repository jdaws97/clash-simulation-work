//! Native diagnostic replays use exactly Battle::run's stopping conditions.
//! Traffic and damage are descriptive; independently paired interventions are
//! estimates of a specific edit, not universal causal design claims.
use std::collections::BTreeMap;

use crate::eval::{self, Evaluator, Manifest, Row};
use crate::json::Json;
use crate::layout::{model::Tile, AdmittedLayout};
use crate::operators::guided::Guidance;
use crate::runner::{Job, PreparedInputs, Runner};
use crate::util::{num, object, string};
use crate::{Context, ProposalRng};

#[derive(Clone, Debug)]
pub struct Diagnosis {
    pub guidance: Guidance,
    pub traffic: BTreeMap<String, BTreeMap<Tile, f64>>,
    pub early: BTreeMap<String, f64>,
    pub contributions: BTreeMap<String, f64>,
    pub trap_triggers: BTreeMap<String, usize>,
    pub traces: Vec<Json>,
}

fn tile_json<T: Copy + Into<f64>>(map: &BTreeMap<Tile, T>) -> Json {
    Json::Arr(
        map.iter()
            .map(|(&(x, y), value)| {
                Json::Arr(vec![
                    Json::Num(x as f64),
                    Json::Num(y as f64),
                    Json::Num((*value).into()),
                ])
            })
            .collect(),
    )
}

impl Diagnosis {
    pub fn to_json(&self) -> Json {
        object([
            ("layout_identity", string(&self.guidance.layout_identity)),
            ("policy_identity", string(&self.guidance.policy_identity)),
            (
                "traffic",
                Json::Obj(
                    self.traffic
                        .iter()
                        .map(|(class, tiles)| (class.clone(), tile_json(tiles)))
                        .collect(),
                ),
            ),
            (
                "early_loss",
                Json::Obj(
                    self.early
                        .iter()
                        .map(|(id, value)| (id.clone(), Json::Num(*value)))
                        .collect(),
                ),
            ),
            (
                "damage_by_source",
                Json::Obj(
                    self.contributions
                        .iter()
                        .map(|(source, value)| (source.clone(), Json::Num(*value)))
                        .collect(),
                ),
            ),
            (
                "trap_triggers",
                Json::Obj(
                    self.trap_triggers
                        .iter()
                        .map(|(id, count)| (id.clone(), num(*count)))
                        .collect(),
                ),
            ),
            ("traces", Json::Arr(self.traces.clone())),
            (
                "interpretation",
                string("descriptive attribution; not a universal causal rule"),
            ),
        ])
    }

    pub fn trap_heat(&self, key: &str, air: bool) -> BTreeMap<Tile, f64> {
        let classes: Vec<(&str, f64)> = match key {
            "seeking" => vec![("healer", 1.0), ("hero_air", 1.0), ("air_mass", 0.3)],
            "airbomb" => vec![("air_mass", 1.0), ("healer", 1.0)],
            "tornado" => vec![("hero_ground", 1.0), ("ground_mass", 0.5)],
            "skeleton" if air => vec![("healer", 1.0), ("hero_air", 1.0), ("air_mass", 0.3)],
            "skeleton" => vec![("hero_ground", 1.0), ("ground_mass", 0.3)],
            "giant" => vec![("ground_mass", 1.0), ("hero_ground", 0.5)],
            _ => vec![("ground_mass", 1.0)],
        };
        let mut heat = BTreeMap::new();
        for (class, weight) in classes {
            if let Some(tiles) = self.traffic.get(class) {
                let total = tiles.values().sum::<f64>().max(1.0);
                for (tile, value) in tiles {
                    *heat.entry(*tile).or_default() += weight * value / total;
                }
            }
        }
        heat
    }
}

/// Weighted median and strongest failure-tail replay, selected after winner
/// freezing. No cherry-picked typical trace from the best completed outcome.
pub fn representative(rows: &[Row]) -> Vec<usize> {
    let mut order: Vec<_> = (0..rows.len()).collect();
    order.sort_by(|&a, &b| {
        let score = |row: &Row| row.outcome.stars as f64 * 101.0 + row.outcome.destruction;
        score(&rows[a]).total_cmp(&score(&rows[b])).then(a.cmp(&b))
    });
    let mut counts = BTreeMap::<&str, usize>::new();
    for row in rows {
        *counts.entry(&row.stratum).or_default() += 1;
    }
    let total: f64 = rows
        .iter()
        .map(|row| row.population_weight / counts[row.stratum.as_str()] as f64)
        .sum();
    let mut accumulated = 0.0;
    let mut median = 0;
    for &index in &order {
        accumulated += rows[index].population_weight / counts[rows[index].stratum.as_str()] as f64;
        median = index;
        if accumulated >= total / 2.0 {
            break;
        }
    }
    let mut selected = vec![median];
    if let Some(&tail) = order.last() {
        if tail != median {
            selected.push(tail);
        }
    }
    selected
}

pub fn collect(
    context: &Context,
    base: &AdmittedLayout,
    rows: &[Row],
    policy: &str,
    evaluator: &mut Evaluator<'_>,
) -> Result<Diagnosis, String> {
    if rows.is_empty() {
        return Err("diagnostics require committed outcomes".to_owned());
    }
    evaluator.budget.reserve(rows.len())?;
    let mut diagnosis = Diagnosis {
        guidance: Guidance {
            layout_identity: base.physical_identity().to_owned(),
            account_identity: base.account_identity().to_owned(),
            policy_identity: policy.to_owned(),
            ground: BTreeMap::new(),
            air: BTreeMap::new(),
            heroes: BTreeMap::new(),
            breaches: BTreeMap::new(),
            early_loss: BTreeMap::new(),
        },
        traffic: BTreeMap::new(),
        early: BTreeMap::new(),
        contributions: BTreeMap::new(),
        trap_triggers: BTreeMap::new(),
        traces: Vec::new(),
    };
    let mut total_weight = 0.0;
    let mut allocations = BTreeMap::<&str, usize>::new();
    for row in rows {
        *allocations.entry(&row.stratum).or_default() += 1;
    }
    for row in rows {
        evaluator.budget.diagnostics += 1;
        let job = Job::new(
            0,
            0,
            row.scenario.seed,
            base.layout().town_hall,
            row.scenario.modifier.clone(),
        );
        let runner = Runner::new(
            context.catalog.clone(),
            PreparedInputs::new(vec![base.engine_json()], vec![row.plan.clone()]),
        );
        let mut battle = runner.build(&job).map_err(|error| error.to_string())?;
        battle.record = true;
        let weight = row.population_weight / allocations[row.stratum.as_str()] as f64
            * (row.outcome.stars as f64 + row.outcome.destruction / 100.0).powi(2);
        total_weight += weight;
        let mut fell = BTreeMap::new();
        let mut ticks = Vec::new();
        let mut step = 0;
        while !battle.ended && (battle.scouting || battle.t < battle.max_time) {
            battle.step();
            step += 1;
            for (index, building) in battle.buildings.iter().enumerate() {
                if !building.alive {
                    fell.entry(index).or_insert(battle.t);
                }
            }
            if step % 5 == 0 {
                let mut units = Vec::new();
                for unit in battle.attackers_pool().filter(|unit| unit.alive) {
                    let tile = ((unit.x - 3.0) as i32, (unit.y - 3.0) as i32);
                    if !(0..44).contains(&tile.0) || !(0..44).contains(&tile.1) {
                        continue;
                    }
                    let target = if unit.flying {
                        &mut diagnosis.guidance.air
                    } else {
                        &mut diagnosis.guidance.ground
                    };
                    *target.entry(tile).or_default() += (weight * 1000.0).round() as u64;
                    if unit.is_hero {
                        *diagnosis.guidance.heroes.entry(tile).or_default() +=
                            (weight * 1000.0).round() as u64;
                    }
                    let class = if unit.is_hero {
                        if unit.flying {
                            "hero_air"
                        } else {
                            "hero_ground"
                        }
                    } else if unit.name == "Healer" {
                        "healer"
                    } else if unit.flying {
                        "air_mass"
                    } else {
                        "ground_mass"
                    };
                    if !matches!(unit.kind.as_str(), "pet" | "siege_idle") && unit.name != "Totem" {
                        *diagnosis
                            .traffic
                            .entry(class.to_owned())
                            .or_default()
                            .entry(tile)
                            .or_default() += weight * unit.housing.max(1) as f64;
                    }
                    units.push(object([
                        ("id", num(unit.id.0)),
                        ("name", string(&unit.name)),
                        ("x", Json::Num(unit.x)),
                        ("y", Json::Num(unit.y)),
                        ("hp", Json::Num(unit.hp)),
                    ]));
                }
                ticks.push(object([
                    ("time", Json::Num(battle.t)),
                    ("units", Json::Arr(units)),
                ]));
            }
            if battle.scouting {
                continue;
            }
            if battle.destroyed_counted >= battle.total_counted || battle.offense_finished() {
                break;
            }
        }
        battle.ended = true;
        let result = battle.result();
        let replay = crate::scoring_outcome(&result);
        if replay.to_json() != row.outcome.to_json() {
            return Err(format!("diagnostic replay differs for {}", row.group_id));
        }
        for (index, time) in fell {
            if let Some(building) = base.layout().buildings.get(index) {
                *diagnosis.early.entry(building.id.clone()).or_default() +=
                    weight * (1.0 - time / result.time.max(1.0));
            }
        }
        for wall in battle.walls.iter().filter(|wall| !wall.alive) {
            *diagnosis
                .guidance
                .breaches
                .entry((wall.tx - 3, wall.ty - 3))
                .or_default() += (weight * 1000.0).round() as u64;
        }
        for (index, trap) in battle.traps.iter().enumerate() {
            if !trap.armed {
                if let Some(placement) = base.layout().traps.get(index) {
                    *diagnosis
                        .trap_triggers
                        .entry(placement.id.clone())
                        .or_default() += 1;
                }
            }
        }
        for (source, damage) in &battle.damage_by_source {
            *diagnosis
                .contributions
                .entry(source.to_string())
                .or_default() += weight * damage;
        }
        diagnosis.traces.push(object([
            ("group_id", string(&row.group_id)),
            ("outcome", replay.to_json()),
            ("reproduces_bulk", Json::Bool(true)),
            ("ticks", Json::Arr(ticks)),
            (
                "events",
                Json::Arr(
                    battle
                        .log
                        .iter()
                        .map(|event| string(crate::trace::event_json(event)))
                        .collect(),
                ),
            ),
        ]));
    }
    for (id, value) in &mut diagnosis.early {
        *value /= total_weight.max(1.0);
        diagnosis
            .guidance
            .early_loss
            .insert(id.clone(), (*value * 1_000_000.0).round() as u64);
    }
    Ok(diagnosis)
}

pub fn polish(
    context: &Context,
    initial: &AdmittedLayout,
    evaluator: &mut Evaluator<'_>,
    screen: &Manifest,
    confirmation: &Manifest,
    settings: &crate::search::Settings,
    version: usize,
) -> Result<(AdmittedLayout, Vec<Json>), String> {
    let mut base = initial.clone();
    let mut log = Vec::new();
    let mut rng = ProposalRng::new(settings.seed ^ 0x7472617073);
    for attempt in 0..settings.polish_attempts {
        let screen_rows = evaluator.assess(&base, screen, version)?;
        let diagnosis = collect(
            context,
            &base,
            &screen_rows,
            &evaluator.identity.clone(),
            evaluator,
        )?;
        if base.layout().traps.is_empty() {
            break;
        }
        let mut draft = base.layout().clone();
        let index = rng.index(draft.traps.len());
        let trap = &mut draft.traps[index];
        let heat = diagnosis.trap_heat(
            &trap.key,
            trap.mode == Some(crate::layout::model::Mode::Air),
        );
        let Some((&tile, _)) = heat
            .iter()
            .max_by(|(ta, a), (tb, b)| a.total_cmp(b).then(tb.cmp(ta)))
        else {
            continue;
        };
        trap.position = tile;
        let proposal = crate::repair::finish(
            context,
            &base,
            draft,
            "traffic-class-trap-polish",
            rng.next_u64(),
            crate::repair::RepairLimits::default(),
        );
        let Ok(proposal) = proposal else { continue };
        let candidate = proposal.candidate;
        if candidate.layout().buildings != initial.layout().buildings
            || candidate.layout().walls != initial.layout().walls
            || candidate.layout().setup != initial.layout().setup
        {
            continue;
        }
        let child_screen = evaluator.assess(&candidate, screen, version)?;
        let screen_delta = eval::objective(
            &child_screen,
            &settings.mode,
            base.hole_tiles(),
            settings.hole_penalty,
        )? - eval::objective(
            &screen_rows,
            &settings.mode,
            base.hole_tiles(),
            settings.hole_penalty,
        )?;
        let parent_confirm = evaluator.assess(&base, confirmation, version)?;
        let child_confirm = evaluator.assess(&candidate, confirmation, version)?;
        let delta = eval::objective(
            &child_confirm,
            &settings.mode,
            base.hole_tiles(),
            settings.hole_penalty,
        )? - eval::objective(
            &parent_confirm,
            &settings.mode,
            base.hole_tiles(),
            settings.hole_penalty,
        )?;
        log.push(object([
            ("attempt", num(attempt)),
            ("parent", string(base.physical_identity())),
            ("candidate", string(candidate.physical_identity())),
            ("screen_difference", Json::Num(screen_delta)),
            ("confirmation_difference", Json::Num(delta)),
            ("accepted", Json::Bool(screen_delta > 0.0 && delta > 0.0)),
            ("intervention_admission", candidate.receipt()),
            (
                "diagnostics_identity",
                string(&diagnosis.guidance.layout_identity),
            ),
            ("paired_groups", num(child_confirm.len())),
            ("structure_frozen", Json::Bool(true)),
            (
                "interpretation",
                string("independent development confirmation; selection-biased estimate"),
            ),
        ]));
        if screen_delta > 0.0 && delta > 0.0 {
            base = candidate;
        }
        // Diagnostics are regenerated after every accepted identity change.
    }
    Ok((base, log))
}
