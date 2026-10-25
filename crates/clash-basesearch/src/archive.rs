//! An 81-cell, TH-independent archive. Numeric edges are frozen in the run
//! manifest, together with their declared synthetic generator corpus.
use std::collections::BTreeMap;

use crate::eval::{self, Row};
use crate::json::Json;
use crate::layout::{geometry, AdmittedLayout};
use crate::util::{num, object, string};
use crate::Context;

#[derive(Clone, Debug, PartialEq)]
pub struct DescriptorDefinition {
    pub corpus_identity: String,
    pub edges: [[f64; 2]; 4],
}

impl Default for DescriptorDefinition {
    fn default() -> Self {
        Self {
            corpus_identity: "declared-synthetic-generator-v1-44-tile-village".to_owned(),
            edges: [[0.3, 0.6], [6.0, 14.0], [12.0, 22.0], [0.25, 0.5]],
        }
    }
}

impl DescriptorDefinition {
    /// Freeze spread/density terciles from an explicit original-generator
    /// corpus before proposals or battle outcomes are consulted.
    pub fn from_corpus(
        context: &Context,
        corpus: &[AdmittedLayout],
    ) -> Result<(Self, Json), String> {
        if corpus.len() < 3 {
            return Err("descriptor corpus needs at least three layouts".to_owned());
        }
        let initial = Self::default();
        let mut samples = Vec::new();
        for base in corpus {
            samples.push(object([
                ("layout_identity", string(base.physical_identity())),
                (
                    "values",
                    initial
                        .describe(context, base)?
                        .to_json()
                        .at("values")
                        .clone(),
                ),
            ]));
        }
        let receipt = object([
            ("source", string("declared synthetic generator layouts; continuous values frozen before evaluation")),
            ("samples", Json::Arr(samples.clone())),
        ]);
        let mut definition = Self {
            corpus_identity: crate::util::fingerprint(&receipt),
            ..initial
        };
        for dimension in [2, 3] {
            let mut values: Vec<_> = samples
                .iter()
                .map(|sample| sample.at("values").arr()[dimension].f64())
                .collect();
            values.sort_by(f64::total_cmp);
            let lower = values[values.len() / 3];
            let mut upper = values[2 * values.len() / 3];
            if upper <= lower {
                upper = lower + if dimension == 2 { 1.0 } else { 1.0 / 256.0 };
            }
            definition.edges[dimension] = [lower, upper];
        }
        Ok((definition, receipt))
    }

    pub fn to_json(&self) -> Json {
        object([
            ("version", string("recognisable-v1")),
            ("corpus_identity", string(&self.corpus_identity)),
            (
                "names",
                Json::Arr(
                    [
                        "TH offset",
                        "compartments >=4 tiles",
                        "mean AD distance",
                        "core defense area / 256",
                    ]
                    .iter()
                    .map(|name| string(*name))
                    .collect(),
                ),
            ),
            (
                "edges",
                Json::Arr(
                    self.edges
                        .iter()
                        .map(|edge| Json::Arr(edge.iter().copied().map(Json::Num).collect()))
                        .collect(),
                ),
            ),
        ])
    }

    pub fn describe(&self, context: &Context, base: &AdmittedLayout) -> Result<Descriptor, String> {
        let layout = base.layout();
        let town_hall = layout
            .buildings
            .iter()
            .find(|building| building.key == "th")
            .ok_or("descriptor requires a TH")?;
        let center = |key: &str, position: (i32, i32)| -> Result<(f64, f64), String> {
            let size = crate::spatial::size(context, key, false)
                .map_err(|error| format!("{error:?}"))? as f64;
            Ok((
                position.0 as f64 + size / 2.0,
                position.1 as f64 + size / 2.0,
            ))
        };
        let (x, y) = center("th", town_hall.position)?;
        let offset = ((x - 22.0).powi(2) + (y - 22.0).powi(2)).sqrt() / (22.0 * 2.0_f64.sqrt());
        let walls = layout.walls.iter().map(|wall| wall.position).collect();
        let compartments = geometry::compartments(&walls)
            .iter()
            .filter(|region| region.len() >= 4)
            .count() as f64;
        let air_defenses: Vec<_> = layout
            .buildings
            .iter()
            .filter(|building| building.key == "ad")
            .map(|building| center(&building.key, building.position))
            .collect::<Result<_, _>>()?;
        let mut distances = Vec::new();
        for (i, a) in air_defenses.iter().enumerate() {
            for b in &air_defenses[i + 1..] {
                distances.push(((a.0 - b.0).powi(2) + (a.1 - b.1).powi(2)).sqrt());
            }
        }
        let spread = distances.iter().sum::<f64>() / distances.len().max(1) as f64;
        let mut occupied = 0;
        for building in &layout.buildings {
            if !is_defense(&building.key) {
                continue;
            }
            let size = crate::spatial::size(context, &building.key, false)
                .map_err(|error| format!("{error:?}"))?;
            for x in building.position.0..building.position.0 + size {
                for y in building.position.1..building.position.1 + size {
                    if (14..30).contains(&x) && (14..30).contains(&y) {
                        occupied += 1;
                    }
                }
            }
        }
        Ok(self.bin([offset, compartments, spread, occupied as f64 / 256.0]))
    }

    pub fn bin(&self, values: [f64; 4]) -> Descriptor {
        let bins = std::array::from_fn(|index| {
            self.edges[index]
                .iter()
                .filter(|edge| values[index] >= **edge)
                .count()
        });
        let cell = bins.iter().fold(0, |cell, bin| cell * 3 + bin);
        Descriptor { values, bins, cell }
    }
}

pub(crate) fn is_defense(key: &str) -> bool {
    matches!(
        key,
        "th" | "mono"
            | "inferno"
            | "eagle"
            | "revenge"
            | "st"
            | "scatter"
            | "firespitter"
            | "swt"
            | "mgt"
            | "mat"
            | "ric"
            | "crafting"
            | "xbow"
            | "ad"
            | "wt"
            | "bt"
            | "sweeper"
            | "tesla"
            | "mortar"
            | "at"
            | "cannon"
    )
}

#[derive(Clone, Debug)]
pub struct Descriptor {
    pub values: [f64; 4],
    pub bins: [usize; 4],
    pub cell: usize,
}

impl Descriptor {
    pub fn to_json(&self) -> Json {
        object([
            (
                "values",
                Json::Arr(self.values.iter().copied().map(Json::Num).collect()),
            ),
            (
                "bins",
                Json::Arr(self.bins.iter().copied().map(num).collect()),
            ),
            ("cell", num(self.cell)),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Elite {
    pub base: AdmittedLayout,
    pub descriptor: Descriptor,
    pub lineage: Json,
    pub screen: Vec<Row>,
    pub confirmation: Vec<Row>,
    pub objective: f64,
    pub robustness: f64,
    pub archive_version: usize,
}

impl Elite {
    pub fn to_json(&self) -> Json {
        object([
            ("layout", self.base.engine_json()),
            ("admission", self.base.receipt()),
            ("descriptor", self.descriptor.to_json()),
            ("lineage", self.lineage.clone()),
            (
                "screen",
                Json::Arr(self.screen.iter().map(Row::to_json).collect()),
            ),
            (
                "confirmation",
                Json::Arr(self.confirmation.iter().map(Row::to_json).collect()),
            ),
            ("objective", Json::Num(self.objective)),
            ("robustness", Json::Num(self.robustness)),
            ("archive_version", num(self.archive_version)),
        ])
    }
}

#[derive(Clone, Debug, Default)]
pub struct Archive {
    pub cells: BTreeMap<usize, Elite>,
    pub pareto: Vec<Elite>,
}

impl Archive {
    pub fn insert(&mut self, elite: Elite) -> Result<bool, String> {
        if self
            .cells
            .values()
            .any(|current| current.archive_version != elite.archive_version)
        {
            return Err("archive-growth invalidation required before elite comparison".to_owned());
        }
        let keep = self
            .cells
            .get(&elite.descriptor.cell)
            .is_none_or(|current| {
                elite.objective > current.objective
                    || (elite.objective == current.objective
                        && (elite.robustness > current.robustness
                            || (elite.robustness == current.robustness
                                && elite.base.physical_identity()
                                    < current.base.physical_identity())))
            });
        if !self
            .pareto
            .iter()
            .any(|current| current.base.physical_identity() == elite.base.physical_identity())
        {
            self.pareto.push(elite.clone());
        }
        self.retain_pareto();
        if keep {
            self.cells.insert(elite.descriptor.cell, elite);
        }
        Ok(keep)
    }

    pub(crate) fn retain_pareto(&mut self) {
        let candidates = self.pareto.clone();
        self.pareto.retain(|candidate| {
            !candidates.iter().any(|other| {
                other.objective >= candidate.objective
                    && other.robustness >= candidate.robustness
                    && (other.objective > candidate.objective
                        || other.robustness > candidate.robustness)
            })
        });
        self.pareto.sort_by(|a, b| {
            b.objective
                .total_cmp(&a.objective)
                .then(a.base.physical_identity().cmp(b.base.physical_identity()))
        });
        self.pareto.truncate(16);
    }

    pub fn ranked(&self) -> Vec<&Elite> {
        let mut elites: Vec<_> = self.cells.values().collect();
        elites.sort_by(|a, b| {
            b.objective
                .total_cmp(&a.objective)
                .then(b.robustness.total_cmp(&a.robustness))
                .then(a.base.physical_identity().cmp(b.base.physical_identity()))
        });
        elites
    }

    /// Preserve ordinary/robustness tradeoffs beyond the single cell winner.
    pub fn frontier(&self) -> Vec<&Elite> {
        let unique: BTreeMap<_, _> = self
            .cells
            .values()
            .chain(&self.pareto)
            .map(|elite| (elite.base.physical_identity(), elite))
            .collect();
        let mut elites: Vec<_> = unique.into_values().collect();
        elites.sort_by(|a, b| {
            b.objective
                .total_cmp(&a.objective)
                .then(b.robustness.total_cmp(&a.robustness))
                .then(a.base.physical_identity().cmp(b.base.physical_identity()))
        });
        elites
    }

    pub fn to_json(&self) -> Json {
        object([
            (
                "cells",
                Json::Arr(self.cells.values().map(Elite::to_json).collect()),
            ),
            (
                "pareto",
                Json::Arr(self.pareto.iter().map(Elite::to_json).collect()),
            ),
        ])
    }
}

pub(crate) fn score(elite: &mut Elite, mode: &str, penalty: Option<f64>) -> Result<(), String> {
    elite.objective = eval::objective(&elite.confirmation, mode, elite.base.hole_tiles(), penalty)?;
    Ok(())
}
