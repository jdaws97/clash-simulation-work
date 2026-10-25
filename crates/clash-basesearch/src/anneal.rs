//! Fixed-budget maximization over admitted proposals. Evaluation is injected;
//! production callers must adapt the existing scorer, never a second objective.
use crate::layout::AdmittedLayout;

use super::{Proposal, ProposalRng, Rejection};

#[derive(Clone, Copy, Debug)]
pub struct AnnealConfig {
    pub steps: usize,
    pub temperature: f64,
    pub seed: u64,
}

#[derive(Clone, Debug)]
pub struct AnnealResult {
    pub best: AdmittedLayout,
    pub best_score: f64,
    pub current: AdmittedLayout,
    pub current_score: f64,
    pub attempted: usize,
    pub evaluated: usize,
    pub accepted: usize,
    pub rejections: Vec<Rejection>,
    pub trajectory: Vec<String>,
}

pub fn anneal(
    start: AdmittedLayout,
    config: AnnealConfig,
    mut propose: impl FnMut(&AdmittedLayout, usize, u64) -> Result<Proposal, Rejection>,
    mut evaluate: impl FnMut(&AdmittedLayout) -> Result<f64, String>,
) -> Result<AnnealResult, String> {
    if !config.temperature.is_finite() || config.temperature < 0.0 {
        return Err("annealing temperature must be finite and nonnegative".to_owned());
    }
    let initial = evaluate(&start)?;
    if !initial.is_finite() {
        return Err("nonfinite initial objective".to_owned());
    }
    let mut result = AnnealResult {
        best: start.clone(),
        best_score: initial,
        current: start,
        current_score: initial,
        attempted: 0,
        evaluated: 1,
        accepted: 0,
        rejections: Vec::new(),
        trajectory: Vec::new(),
    };
    let mut rng = ProposalRng::new(config.seed);
    for step in 0..config.steps {
        result.attempted += 1;
        let seed = rng.next_u64();
        match propose(&result.current, step, seed) {
            Ok(proposal) => {
                if proposal.parents.first().map(String::as_str)
                    != Some(result.current.physical_identity())
                    || proposal.candidate.account_identity() != result.current.account_identity()
                    || proposal.candidate.rules_identity() != result.current.rules_identity()
                    || proposal.candidate.catalog_identity() != result.current.catalog_identity()
                    || proposal.candidate.policy() != result.current.policy()
                    || !super::repair::conserved(
                        result.current.layout(),
                        proposal.candidate.layout(),
                    )
                {
                    return Err(
                        "proposal lineage/account does not match annealing parent".to_owned()
                    );
                }
                let score = evaluate(&proposal.candidate)?;
                result.evaluated += 1;
                if !score.is_finite() {
                    return Err("nonfinite candidate objective".to_owned());
                }
                let temperature = config.temperature * (1.0 - step as f64 / config.steps as f64);
                let delta = score - result.current_score;
                if delta >= 0.0
                    || (temperature > 0.0 && rng.unit() < crate::detmath::exp(delta / temperature))
                {
                    result.current = proposal.candidate;
                    result.current_score = score;
                    result.accepted += 1;
                    if score > result.best_score {
                        result.best = result.current.clone();
                        result.best_score = score;
                    }
                }
            }
            Err(rejection) => result.rejections.push(rejection),
        }
        result
            .trajectory
            .push(result.current.physical_identity().to_owned());
    }
    Ok(result)
}
