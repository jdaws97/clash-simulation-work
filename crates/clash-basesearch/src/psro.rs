//! Deterministic multiplicative weights for the restricted empirical zero-sum
//! game. Rows maximize defender utility, columns minimize it.
use crate::json::Json;
use crate::util::{num, object, string};

#[derive(Clone, Debug)]
pub struct Solution {
    pub defender: Vec<f64>,
    pub attacker: Vec<f64>,
    pub lower: f64,
    pub upper: f64,
    pub iterations: usize,
}

impl Solution {
    pub fn to_json(&self) -> Json {
        object([
            (
                "scope",
                string("restricted empirical game; no full-game equilibrium claim"),
            ),
            (
                "defender",
                Json::Arr(self.defender.iter().copied().map(Json::Num).collect()),
            ),
            (
                "attacker",
                Json::Arr(self.attacker.iter().copied().map(Json::Num).collect()),
            ),
            ("lower", Json::Num(self.lower)),
            ("upper", Json::Num(self.upper)),
            ("residual", Json::Num((self.upper - self.lower).max(0.0))),
            ("iterations", num(self.iterations)),
        ])
    }
}

fn softmax(logits: &[f64]) -> Vec<f64> {
    let max = logits.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let weights: Vec<_> = logits.iter().map(|value| (value - max).exp()).collect();
    let total: f64 = weights.iter().sum();
    weights.into_iter().map(|weight| weight / total).collect()
}

pub fn solve(payoffs: &[Vec<f64>], iterations: usize) -> Result<Solution, String> {
    let columns = payoffs.first().map_or(0, Vec::len);
    if columns == 0
        || iterations == 0
        || payoffs
            .iter()
            .any(|row| row.len() != columns || row.iter().any(|value| !value.is_finite()))
    {
        return Err("solver needs a finite rectangular payoff matrix and iterations".to_owned());
    }
    let low = payoffs
        .iter()
        .flatten()
        .copied()
        .fold(f64::INFINITY, f64::min);
    let high = payoffs
        .iter()
        .flatten()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let range = (high - low).max(1e-12);
    let rate = ((2.0 * payoffs.len().max(columns) as f64).ln() / iterations as f64).sqrt();
    let mut row_logits = vec![0.0; payoffs.len()];
    let mut column_logits = vec![0.0; columns];
    let mut defender = vec![0.0; payoffs.len()];
    let mut attacker = vec![0.0; columns];
    for _ in 0..iterations {
        let rows = softmax(&row_logits);
        let cols = softmax(&column_logits);
        for i in 0..payoffs.len() {
            defender[i] += rows[i] / iterations as f64;
            row_logits[i] += rate
                * payoffs[i]
                    .iter()
                    .zip(&cols)
                    .map(|(value, weight)| (value - low) / range * weight)
                    .sum::<f64>();
        }
        for j in 0..columns {
            attacker[j] += cols[j] / iterations as f64;
            column_logits[j] -= rate
                * payoffs
                    .iter()
                    .zip(&rows)
                    .map(|(row, weight)| (row[j] - low) / range * weight)
                    .sum::<f64>();
        }
    }
    // Normalize accumulated iterates before publishing probability mixtures.
    let defender_total: f64 = defender.iter().sum();
    let attacker_total: f64 = attacker.iter().sum();
    for probability in &mut defender {
        *probability /= defender_total;
    }
    for probability in &mut attacker {
        *probability /= attacker_total;
    }
    let lower = (0..columns)
        .map(|j| {
            payoffs
                .iter()
                .zip(&defender)
                .map(|(row, weight)| row[j] * weight)
                .sum::<f64>()
        })
        .fold(f64::INFINITY, f64::min);
    let upper = payoffs
        .iter()
        .map(|row| {
            row.iter()
                .zip(&attacker)
                .map(|(value, weight)| value * weight)
                .sum::<f64>()
        })
        .fold(f64::NEG_INFINITY, f64::max);
    Ok(Solution {
        defender,
        attacker,
        lower,
        upper,
        iterations,
    })
}
