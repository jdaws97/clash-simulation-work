//! Visible-state side commitment (R5), with explicit random/oracle comparators.
//! docs/RUST_REVIEW_2026-10-25.md and SIMULATION_METHODS_RESEARCH.md recommend
//! hidden ensembles; the priors here are assumptions, not measured game rules.

use std::collections::BTreeSet;
use std::sync::Arc;

use crate::armies::{list, put, string};
use crate::catalog::Catalog;
use crate::json::Json;
use crate::pyrandom::PyRandom;
use crate::runner::{Job, PreparedInputs, Runner};
use crate::scoring::{self, Outcome, Scenario, Scorer, Selection};
use crate::stats::Level;

pub const HIDDEN_SAMPLES: usize = 3;

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum ScoutPolicy {
    #[default]
    Visible,
    Random,
    Oracle,
}

impl ScoutPolicy {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "visible" => Ok(Self::Visible),
            "random" => Ok(Self::Random),
            "oracle" => Ok(Self::Oracle),
            _ => Err("scout_policy must be visible, random, or oracle".to_owned()),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Visible => "visible",
            Self::Random => "random",
            Self::Oracle => "oracle (completed-battle upper bound)",
        }
    }
}

pub struct ScoutRun {
    pub scenarios: Vec<Scenario>,
    pub outcomes: Vec<Outcome>,
    pub source_indices: Vec<usize>,
    pub planning_battles: usize,
    pub evaluation_battles: usize,
}

fn groups(scenarios: &[Scenario]) -> Vec<Vec<usize>> {
    let mut groups: Vec<Vec<usize>> = Vec::new();
    for (index, scenario) in scenarios.iter().enumerate() {
        let group = groups.iter_mut().find(|group| {
            let first = &scenarios[group[0]];
            first.army == scenario.army
                && first.town_hall == scenario.town_hall
                && first.modifier == scenario.modifier
                && first.group == scenario.group
                && first.full_scout == scenario.full_scout
        });
        if let Some(group) = group {
            group.push(index);
        } else {
            groups.push(vec![index]);
        }
    }
    groups
}

/// Stable FNV mixing, with disjoint 48-bit seed namespaces. Seeds stay exactly
/// representable in JSON. Neither hidden content nor candidate order is hashed.
fn seed(scenario: &Scenario, domain: u64, sample: usize) -> i64 {
    let mut hash = 0xcbf29ce484222325_u64;
    let identity = format!(
        "{}|{}|{:?}|{}|{}",
        scenario.army, scenario.town_hall, scenario.modifier, scenario.group, sample
    );
    for byte in identity.bytes() {
        hash = (hash ^ byte as u64).wrapping_mul(0x100000001b3);
    }
    ((domain << 48) | (hash & ((1 << 48) - 1))) as i64
}

fn square(x: i64, y: i64, size: usize) -> impl Iterator<Item = (i64, i64)> {
    (0..size as i64).flat_map(move |dx| (0..size as i64).map(move |dy| (x + dx, y + dy)))
}

fn place(
    occupied: &mut BTreeSet<(i64, i64)>,
    size: usize,
    village: i64,
    rng: &mut PyRandom,
) -> Result<(i64, i64), String> {
    let mut free = Vec::new();
    for x in 0..=village - size as i64 {
        for y in 0..=village - size as i64 {
            if square(x, y, size).all(|tile| !occupied.contains(&tile)) {
                free.push((x, y));
            }
        }
    }
    if free.is_empty() {
        return Err(format!(
            "visible layout has no legal {size}x{size} hidden placement"
        ));
    }
    let (x, y) = free[rng.below(free.len())];
    occupied.extend(square(x, y, size));
    Ok((x, y))
}

/// A strict visible-field projection: original traps, Tesla count/positions/
/// levels, CC contents/levels, notes and arbitrary metadata are never consulted.
/// output/research/usage/hidden-tesla.md and clan-castle-lure-and-kill.md:
/// https://clashofclans.fandom.com/wiki/Hidden_Tesla/Home_Village
/// https://clashofclans.fandom.com/wiki/Clan_Castle
pub fn hidden_sample(layout: &Json, catalog: &Catalog, sample_seed: i64) -> Result<Json, String> {
    let town_hall = scoring::number(layout, "town_hall", 16.0) as i64;
    if !(16..=18).contains(&town_hall) {
        return Err("visible scout priors cover defender TH16..18".to_owned());
    }
    let village = (catalog.world as f64 - 2.0 * catalog.margin) as i64;
    let mut visible = Json::Obj(Vec::new());
    for key in ["town_hall", "walls", "wall_levels", "heroes", "guardian"] {
        if let Some(value) = layout.get(key) {
            put(&mut visible, key, value.clone());
        }
    }
    let mut buildings: Vec<_> = list(layout, "buildings")
        .iter()
        .filter(|building| building.get("key").and_then(Json::opt_str) != Some("tesla"))
        .cloned()
        .collect();
    if let Some(Json::Obj(levels)) = layout.get("levels") {
        let levels: Vec<_> = levels
            .iter()
            .filter(|(key, _)| {
                key == "guardian"
                    || key != "tesla" && catalog.building_types.iter().any(|(name, _)| name == key)
            })
            .cloned()
            .collect();
        if !levels.is_empty() {
            put(&mut visible, "levels", Json::Obj(levels));
        }
    }
    let mut occupied = BTreeSet::new();
    for wall in list(&visible, "walls") {
        occupied.insert((wall.arr()[0].i64(), wall.arr()[1].i64()));
    }
    for building in &buildings {
        let key = building.at("key").str();
        let kind = catalog
            .building_types
            .iter()
            .find(|(name, _)| name == key)
            .ok_or_else(|| format!("unknown visible building {key}"))?;
        occupied.extend(square(
            building.at("x").i64(),
            building.at("y").i64(),
            kind.1.size,
        ));
    }
    let mut rng = PyRandom::new(sample_seed);
    let tesla = catalog
        .building_types
        .iter()
        .find(|(key, _)| key == "tesla")
        .ok_or("catalog has no Hidden Tesla")?;
    for _ in 0..tesla.1.count {
        let (x, y) = place(&mut occupied, tesla.1.size, village, &mut rng)?;
        buildings.push(scoring::object(vec![
            ("key", string("tesla")),
            ("x", Json::Num(x as f64)),
            ("y", Json::Num(y as f64)),
        ]));
    }
    // Inventory matches mechanics.py:146-150's existing TH16..18 model.
    // Positions are uniform over unoccupied legal tiles; this is an assumed
    // prior, deliberately independent of the actual hidden layout.
    let counts = if town_hall == 16 {
        [8, 9, 7, 7, 8, 4, 1, 0]
    } else if town_hall == 17 {
        [8, 9, 8, 7, 9, 4, 1, 1]
    } else {
        [8, 9, 8, 8, 9, 4, 1, 1]
    };
    let mut traps = Vec::new();
    for (key, count) in [
        "bomb", "spring", "giant", "airbomb", "seeking", "skeleton", "tornado", "giga",
    ]
    .into_iter()
    .zip(counts)
    {
        let size = if matches!(key, "giant" | "giga") {
            2
        } else {
            1
        };
        for _ in 0..count {
            let (x, y) = place(&mut occupied, size, village, &mut rng)?;
            let mut trap = scoring::object(vec![
                ("key", string(key)),
                ("x", Json::Num(x as f64)),
                ("y", Json::Num(y as f64)),
            ]);
            if key == "skeleton" {
                put(
                    &mut trap,
                    "mode",
                    string(if rng.below(2) == 0 { "air" } else { "ground" }),
                );
            }
            traps.push(trap);
        }
    }
    // Visible CC building level bounds housing; three equally likely assumed
    // defensive roles. Catalog housing and normal receiving caps still apply.
    let castle = buildings
        .iter()
        .find(|building| building.at("key").str() == "cc");
    let mut cargo = Vec::new();
    if let Some(castle) = castle {
        let level = castle
            .get("level")
            .or_else(|| visible.get("levels").and_then(|levels| levels.get("cc")))
            .map(Json::i64)
            .or_else(|| catalog.stats.max_level("Clan Castle", town_hall))
            .ok_or("missing visible Clan Castle level")?;
        let mut housing = catalog
            .stats
            .get("Clan Castle", &Level::Int(level), &["Troop Capacity"], None)
            .ok_or("missing Clan Castle capacity")? as i64;
        let names: &[&str] = match rng.below(3) {
            0 => &["Ice Golem", "Ice Golem", "Ice Golem"],
            1 => &["Lava Hound", "Headhunter", "Headhunter"],
            _ => &["Dragon", "Dragon", "Headhunter"],
        };
        for name in names
            .iter()
            .copied()
            .chain(std::iter::repeat("Archer").take(55))
        {
            let space = scoring::number(
                catalog.stats.attrs(name),
                "housing_ck",
                scoring::number(catalog.stats.attrs(name), "housing", 1.0),
            ) as i64;
            if housing >= space && space > 0 {
                cargo.push(string(name));
                housing -= space;
            }
        }
    }
    put(&mut visible, "buildings", Json::Arr(buildings));
    put(&mut visible, "traps", Json::Arr(traps));
    put(&mut visible, "cc_troops", Json::Arr(cargo));
    Ok(visible)
}

impl Scorer {
    /// Selection uses hidden-state predictions only. Real-state battles start
    /// after all selections have been committed; repeat winners share one run.
    pub fn scout(
        &self,
        catalog: Arc<Catalog>,
        layout_index: usize,
        threads: usize,
        policy: ScoutPolicy,
        scout: Option<usize>,
    ) -> Result<ScoutRun, String> {
        let inputs = self.runner.inputs();
        let layout = inputs
            .layouts
            .get(layout_index)
            .ok_or("layout index out of range")?;
        let town_hall = scoring::number(layout, "town_hall", 16.0) as i64;
        let groups = groups(&self.scenarios);
        let mut group_of = vec![0; self.scenarios.len()];
        for (index, group) in groups.iter().enumerate() {
            for member in group {
                group_of[*member] = index;
            }
        }
        let mut planning_battles = 0;
        let selections = match policy {
            ScoutPolicy::Visible => {
                let mut hidden = Vec::new();
                for group in &groups {
                    for sample in 0..HIDDEN_SAMPLES {
                        hidden.push(hidden_sample(
                            layout,
                            &catalog,
                            seed(&self.scenarios[group[0]], 1, sample),
                        )?);
                    }
                }
                let mut jobs = Vec::new();
                for (index, scenario) in self.scenarios.iter().enumerate() {
                    for sample in 0..HIDDEN_SAMPLES {
                        jobs.push(Job::new(
                            group_of[index] * HIDDEN_SAMPLES + sample,
                            self.plan_indices[index],
                            seed(scenario, 2, sample),
                            town_hall,
                            scenario.modifier.clone(),
                        ));
                    }
                }
                let runner = Runner::new(
                    Arc::clone(&catalog),
                    PreparedInputs::new(hidden, inputs.plans.clone()),
                );
                let rows = runner
                    .run(&jobs, threads)
                    .map_err(|error| format!("scout ensemble: {error:?}"))?;
                planning_battles = rows.len();
                let utility: Vec<_> = rows
                    .chunks(HIDDEN_SAMPLES)
                    .map(|rows| {
                        (
                            scoring::sum(rows.iter().map(|row| {
                                scoring::attacker_trophies(row.stars as i64, row.destruction as f64)
                                    as f64
                            })) / HIDDEN_SAMPLES as f64,
                            scoring::sum(rows.iter().map(|row| row.destruction as f64))
                                / HIDDEN_SAMPLES as f64,
                        )
                    })
                    .collect();
                scoring::scouted_by(&self.scenarios, &utility, scout)
            }
            ScoutPolicy::Random => groups
                .iter()
                .map(|group| {
                    let mut rng = PyRandom::new(seed(&self.scenarios[group[0]], 4, 0));
                    Selection {
                        scenario: group[rng.below(group.len())],
                        weight: scoring::sum(
                            group.iter().map(|index| self.scenarios[*index].weight),
                        ),
                    }
                })
                .collect(),
            ScoutPolicy::Oracle => Vec::new(),
        };
        let mut weights = vec![0.0; self.scenarios.len()];
        for selection in selections {
            weights[selection.scenario] += selection.weight;
        }
        let indices: Vec<_> = (0..self.scenarios.len())
            .filter(|index| policy == ScoutPolicy::Oracle || weights[*index] != 0.0)
            .collect();
        let jobs: Vec<_> = indices
            .iter()
            .map(|index| {
                let scenario = &self.scenarios[*index];
                Job::new(
                    layout_index,
                    self.plan_indices[*index],
                    seed(scenario, 3, 0),
                    town_hall,
                    scenario.modifier.clone(),
                )
            })
            .collect();
        let rows: Vec<_> = self
            .runner
            .run(&jobs, threads)
            .map_err(|error| format!("scout evaluation: {error:?}"))?
            .into_iter()
            .map(Outcome::from)
            .collect();
        let evaluation_battles = rows.len();
        if policy == ScoutPolicy::Oracle {
            for selection in scoring::scouted(&self.scenarios, &rows, scout) {
                weights[selection.scenario] += selection.weight;
            }
        }
        let mut result = ScoutRun {
            scenarios: Vec::new(),
            outcomes: Vec::new(),
            source_indices: Vec::new(),
            planning_battles,
            evaluation_battles,
        };
        for (index, row) in indices.into_iter().zip(rows) {
            if weights[index] == 0.0 {
                continue;
            }
            let mut scenario = self.scenarios[index].clone();
            scenario.seed = seed(&scenario, 3, 0);
            scenario.weight = weights[index];
            result.scenarios.push(scenario);
            result.outcomes.push(row);
            result.source_indices.push(index);
        }
        Ok(result)
    }
}
