//! Proper distribution scores and weighted defense/duration summaries.

use std::collections::BTreeMap;

use clash_data::json::Json;
use clash_scoring::scoring::defender_trophies;

use super::history::Observation;
use super::io::*;
use super::replay::{ReplayRow, Sample};

pub const BINS: usize = 11;
pub const CELLS: usize = 4 * BINS;
pub const MIX: f64 = 0.02;

#[derive(Clone, Debug)]
pub struct Distribution {
    pub stars: [f64; 4],
    pub cdf: [f64; 100],
    pub joint: [f64; CELLS],
    pub pct: f64,
    pub trophies: f64,
}

pub fn bin(pct: f64) -> usize {
    (pct / 10.0).floor().clamp(0.0, 10.0) as usize
}

impl Distribution {
    pub fn samples(samples: &[Sample]) -> Self {
        let mut out = Self {
            stars: [0.0; 4],
            cdf: [0.0; 100],
            joint: [0.0; CELLS],
            pct: 0.0,
            trophies: 0.0,
        };
        let total: f64 = samples.iter().map(|sample| sample.weight).sum();
        if total == 0.0 {
            return out;
        }
        for sample in samples {
            let weight = sample.weight / total;
            out.stars[sample.stars as usize] += weight;
            out.joint[sample.stars as usize * BINS + bin(sample.pct)] += weight;
            for (index, probability) in out.cdf.iter_mut().enumerate() {
                if sample.pct <= index as f64 {
                    *probability += weight;
                }
            }
            out.pct += weight * sample.pct;
            out.trophies += weight * defender_trophies(sample.stars, sample.pct) as f64;
        }
        out
    }

    pub fn observations(rows: &[Observation]) -> Self {
        Self::samples(
            &rows
                .iter()
                .map(|row| Sample {
                    stars: row.stars,
                    pct: row.pct,
                    time: row.time,
                    weight: 1.0,
                    end_reason: String::new(),
                })
                .collect::<Vec<_>>(),
        )
    }

    pub fn to_json(&self) -> Json {
        obj([
            ("star_probabilities", arr(self.stars.into_iter().map(num))),
            (
                "destruction_cdf_0_to_99",
                arr(self.cdf.into_iter().map(num)),
            ),
            (
                "joint_star_destruction_probabilities",
                arr(self
                    .joint
                    .chunks(BINS)
                    .map(|row| arr(row.iter().copied().map(num)))),
            ),
            ("mean_destruction", num(self.pct)),
            ("mean_defender_trophies", num(self.trophies)),
        ])
    }

    pub fn scores(&self, stars: i64, pct: f64) -> (f64, f64, f64) {
        let target_bin = bin(pct);
        let log_score = -((1.0 - MIX) * self.joint[stars as usize * BINS + target_bin]
            + MIX / CELLS as f64)
            .ln();
        // Sum squared lower-orthant CDF errors on a two-dimensional ordered
        // grid. This is proper without imposing a spurious flattened ordering.
        let mut joint_cdf = [[0.0; BINS]; 4];
        let mut error = 0.0;
        for star in 0..4 {
            for destruction in 0..BINS {
                let probability =
                    (1.0 - MIX) * self.joint[star * BINS + destruction] + MIX / CELLS as f64;
                let above = if star > 0 {
                    joint_cdf[star - 1][destruction]
                } else {
                    0.0
                };
                let left = if destruction > 0 {
                    joint_cdf[star][destruction - 1]
                } else {
                    0.0
                };
                let diagonal = if star > 0 && destruction > 0 {
                    joint_cdf[star - 1][destruction - 1]
                } else {
                    0.0
                };
                joint_cdf[star][destruction] = probability + above + left - diagonal;
                let observed =
                    f64::from(u8::from(stars <= star as i64 && target_bin <= destruction));
                error += (joint_cdf[star][destruction] - observed).powi(2);
            }
        }
        let mut cumulative = 0.0;
        let mut rps = 0.0;
        for threshold in 0..3 {
            cumulative += self.stars[threshold];
            rps += (cumulative - f64::from(u8::from(stars <= threshold as i64))).powi(2) / 3.0;
        }
        (log_score, error / CELLS as f64, rps)
    }
}

pub fn loss(
    observed: &Distribution,
    simulated: &Distribution,
    n: usize,
    correction: f64,
    prior_sd: f64,
) -> Json {
    let star_nll = -(n as f64)
        * observed
            .stars
            .iter()
            .zip(simulated.stars)
            .map(|(p, q)| p * (0.98 * q + 0.005).ln())
            .sum::<f64>();
    let cdf = n as f64
        * observed
            .cdf
            .iter()
            .zip(simulated.cdf)
            .map(|(p, q)| (p - q).powi(2))
            .sum::<f64>()
        / 100.0;
    let prior = 0.5 * (correction.ln() / prior_sd).powi(2);
    obj([
        ("star_nll", num(star_nll)),
        ("destruction_cdf", num(cdf)),
        ("prior", num(prior)),
        ("total", num(star_nll + cdf + prior)),
    ])
}

pub fn mean(values: &[f64]) -> Json {
    if values.is_empty() {
        Json::Null
    } else {
        num(values.iter().sum::<f64>() / values.len() as f64)
    }
}

pub fn weighted_median(values: &[(f64, f64)]) -> Json {
    if values.is_empty() {
        return Json::Null;
    }
    let mut values = values.to_vec();
    values.sort_by(|left, right| left.0.total_cmp(&right.0));
    let total: f64 = values.iter().map(|(_, weight)| weight).sum();
    let mut cumulative = 0.0;
    for (index, (value, weight)) in values.iter().enumerate() {
        cumulative += weight;
        if (cumulative - total / 2.0).abs() < 1e-10 {
            return num((value + values.get(index + 1).map_or(*value, |(value, _)| *value)) / 2.0);
        }
        if cumulative > total / 2.0 {
            return num(*value);
        }
    }
    num(values.last().expect("nonempty median").0)
}

pub fn defense_metrics(rows: &[ReplayRow], baseline: Option<&Distribution>) -> Json {
    let mut attackers = BTreeMap::new();
    let mut fallbacks = BTreeMap::new();
    let mut reasons = BTreeMap::new();
    let mut setups = BTreeMap::new();
    let mut real3 = Vec::new();
    let mut sim3 = Vec::new();
    let mut brier = Vec::new();
    let mut mae = Vec::new();
    let mut time_ratios = Vec::new();
    let mut real_fails = Vec::new();
    let mut sim_fails = Vec::new();
    let mut matched_fails = Vec::new();
    let mut real_timeouts = Vec::new();
    let mut sim_timeouts = Vec::new();
    let mut joint_log = Vec::new();
    let mut joint_cdf = Vec::new();
    let mut star_rps = Vec::new();
    let mut base_brier = Vec::new();
    let mut base_mae = Vec::new();
    let mut base_log = Vec::new();
    let mut base_cdf = Vec::new();
    let mut base_rps = Vec::new();
    for row in rows {
        *attackers.entry(row.attacker.clone()).or_default() += 1;
        if let Some(note) = &row.fallback {
            *fallbacks.entry(note.clone()).or_default() += 1;
        }
        *setups
            .entry(row.observation.setup_source.clone())
            .or_default() += 1;
        for (key, count) in &row.reasons {
            *reasons.entry(key.clone()).or_default() += count;
        }
        let dist = Distribution::samples(&row.samples);
        let real = f64::from(u8::from(row.observation.stars == 3));
        real3.push(real);
        sim3.push(dist.stars[3]);
        brier.push((dist.stars[3] - real).powi(2));
        mae.push((dist.pct - row.observation.pct).abs());
        let p3 = dist.stars[3];
        if real == 1.0 && p3 > 0.0 && row.observation.time > 0.0 {
            let t3: f64 = row
                .samples
                .iter()
                .filter(|sample| sample.stars == 3)
                .map(|sample| sample.weight * sample.time)
                .sum();
            time_ratios.push(t3 / p3 / row.observation.time);
        }
        if real == 0.0 {
            real_fails.push((row.observation.time, 1.0));
        }
        for sample in &row.samples {
            if sample.stars < 3 {
                sim_fails.push((sample.time, sample.weight));
                if real == 0.0 {
                    matched_fails.push((sample.time, sample.weight));
                }
            }
        }
        real_timeouts.push(f64::from(u8::from(row.observation.time >= 179.0)));
        sim_timeouts.push(
            row.samples
                .iter()
                .filter(|sample| sample.time >= 179.5)
                .map(|sample| sample.weight)
                .sum(),
        );
        let (log, cdf, rps) = dist.scores(row.observation.stars, row.observation.pct);
        joint_log.push(log);
        joint_cdf.push(cdf);
        star_rps.push(rps);
        if let Some(base) = baseline {
            base_brier.push((base.stars[3] - real).powi(2));
            base_mae.push((base.pct - row.observation.pct).abs());
            let (log, cdf, rps) = base.scores(row.observation.stars, row.observation.pct);
            base_log.push(log);
            base_cdf.push(cdf);
            base_rps.push(rps);
        }
    }
    obj([
        ("defenses", num(rows.len() as f64)),
        ("attacker_counts", count_map(&attackers)),
        ("attacker_fallback_counts", count_map(&fallbacks)),
        ("setup_sources", count_map(&setups)),
        ("sim_end_reason_counts", count_map(&reasons)),
        (
            "sim_end_reason_unrecorded_defenses",
            num(rows
                .iter()
                .filter(|row| row.reasons.values().sum::<usize>() < row.evaluations)
                .count() as f64),
        ),
        ("real_3star", mean(&real3)),
        ("sim_3star", mean(&sim3)),
        ("brier", mean(&brier)),
        ("destruction_mae", mean(&mae)),
        ("time_to_3star_ratio", mean(&time_ratios)),
        ("real_failed_median_s", weighted_median(&real_fails)),
        ("real_failed_n", num(real_fails.len() as f64)),
        ("sim_failed_median_s", weighted_median(&sim_fails)),
        ("sim_failed_n", num(sim_fails.len() as f64)),
        (
            "sim_failed_weight",
            num(sim_fails.iter().map(|(_, weight)| weight).sum::<f64>()),
        ),
        (
            "sim_failed_matched_median_s",
            weighted_median(&matched_fails),
        ),
        ("sim_failed_matched_n", num(matched_fails.len() as f64)),
        ("real_timeout_share", mean(&real_timeouts)),
        ("sim_timeout_share", mean(&sim_timeouts)),
        ("joint_log_score", mean(&joint_log)),
        ("joint_cdf_score", mean(&joint_cdf)),
        ("star_rps", mean(&star_rps)),
        ("constant_predictor_brier", mean(&base_brier)),
        ("constant_destruction_mae", mean(&base_mae)),
        ("constant_joint_log_score", mean(&base_log)),
        ("constant_joint_cdf_score", mean(&base_cdf)),
        ("constant_star_rps", mean(&base_rps)),
        (
            "baseline_training_distribution",
            baseline.map_or(Json::Null, Distribution::to_json),
        ),
        (
            "distribution_scoring",
            string(concat!(
                "4 stars x 11 destruction bins [0,10,...,90,100,101]; ",
                "2% uniform mixture for joint log/CDF scores; lower is better",
            )),
        ),
        (
            "event_metrics",
            string(concat!(
                "battle logs supply final outcomes/durations only; ",
                "use observed for curve, star-time and defense-fall metrics",
            )),
        ),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn proper_scores_reward_the_observed_joint_cell() {
        let sample = Sample {
            stars: 3,
            pct: 100.0,
            time: 100.0,
            weight: 1.0,
            end_reason: String::new(),
        };
        let dist = Distribution::samples(&[sample]);
        let good = dist.scores(3, 100.0);
        let wrong = dist.scores(1, 60.0);
        assert!(good.0 < wrong.0 && good.1 < wrong.1 && good.2 < wrong.2);
        assert_eq!(dist.joint.iter().sum::<f64>(), 1.0);
        assert_eq!(weighted_median(&[(1.0, 1.0), (3.0, 1.0)]), num(2.0));
        let objective = loss(&dist, &dist, 2, 1.0, 0.2);
        assert!((number(&objective, "total", 0.0) + 2.0 * 0.985_f64.ln()).abs() < 1e-12);
    }
}
