//! Stratified paired Hoeffding bounds with explicit alpha spending. Constant
//! observed samples still have uncertainty; an unobserved stratum cannot race.
use std::collections::{BTreeMap, BTreeSet};

use crate::eval::{utility, Row};

#[derive(Clone, Copy, Debug)]
pub struct Interval {
    pub mean: f64,
    pub lower: f64,
    pub upper: f64,
    pub alpha_spent: f64,
}

pub fn paired(
    child: &[Row],
    incumbent: &[Row],
    strata: &BTreeMap<String, f64>,
    mode: &str,
    deterministic_difference: f64,
    alpha: f64,
    look: usize,
) -> Result<Option<Interval>, String> {
    if !(0.0..1.0).contains(&alpha) || alpha == 0.0 || look == 0 {
        return Err("invalid alpha-spending configuration".to_owned());
    }
    let parents: BTreeMap<_, _> = incumbent.iter().map(|row| (&row.group_id, row)).collect();
    let mut values = BTreeMap::<String, Vec<f64>>::new();
    for row in child {
        let Some(other) = parents.get(&row.group_id) else {
            continue;
        };
        if row.stratum != other.stratum || row.population_weight != other.population_weight {
            return Err("paired group has conflicting population identity".to_owned());
        }
        values
            .entry(row.stratum.clone())
            .or_default()
            .push(utility(row.outcome, mode) - utility(other.outcome, mode));
    }
    if strata
        .keys()
        .any(|key| values.get(key).is_none_or(|rows| rows.len() < 2))
    {
        return Ok(None);
    }
    // sum_{look>=1} alpha/(look*(look+1)) = alpha. Union bound over
    // strata and both tails; independent bounded groups are the assumption.
    let spent = alpha / (look as f64 * (look + 1) as f64);
    let total: f64 = strata.values().sum();
    let observation_range = if mode == "ranked" { 101.0 } else { 135.0 };
    let mut mean = deterministic_difference;
    let mut radius = 0.0;
    for (stratum, weight) in strata {
        let samples = &values[stratum];
        let weight = weight / total;
        mean += weight * samples.iter().sum::<f64>() / samples.len() as f64;
        radius += weight
            * 2.0
            * observation_range
            * ((2.0 * strata.len() as f64 / spent).ln() / (2.0 * samples.len() as f64)).sqrt();
    }
    Ok(Some(Interval {
        mean,
        lower: mean - radius,
        upper: mean + radius,
        alpha_spent: spent,
    }))
}

/// Nominal factor-three halving, while reserving new-cell and exploration
/// slots. The caller supplies development scores only. Stable index ties.
pub fn halve(scores: &[f64], protected: &[bool], exploration: usize) -> Vec<usize> {
    let mut order: Vec<_> = (0..scores.len()).collect();
    order.sort_by(|&a, &b| scores[b].total_cmp(&scores[a]).then(a.cmp(&b)));
    let target = scores.len().div_ceil(3).max(1);
    let mut keep: Vec<_> = (0..scores.len()).filter(|&i| protected[i]).collect();
    for index in (0..scores.len())
        .filter(|i| !protected[*i])
        .take(exploration)
    {
        if !keep.contains(&index) {
            keep.push(index);
        }
    }
    for index in order {
        if keep.len() >= target {
            break;
        }
        if !keep.contains(&index) {
            keep.push(index);
        }
    }
    keep.sort_unstable();
    keep
}

/// Protect the strongest screened candidate opening each new cell. Protecting
/// the first arrival would discard a known per-cell winner during halving.
pub fn protect_open_cells(
    scores: &[f64],
    cells: &[usize],
    occupied: &BTreeSet<usize>,
) -> Vec<bool> {
    let mut best = BTreeMap::<usize, usize>::new();
    for (index, cell) in cells.iter().enumerate() {
        if occupied.contains(cell) {
            continue;
        }
        if best
            .get(cell)
            .is_none_or(|&current| scores[index] > scores[current])
        {
            best.insert(*cell, index);
        }
    }
    let mut protected = vec![false; scores.len()];
    for index in best.into_values() {
        protected[index] = true;
    }
    protected
}
