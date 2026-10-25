//! Native base search. All public candidates pass layout admission; randomness
//! belongs to a logical proposal, never to a worker or battle simulation.
pub mod anneal;
pub mod archive;
pub mod checkpoint;
pub mod cli;
pub mod completion_proof;
pub mod crossover;
pub mod diagnostics;
pub mod eval;
pub mod generate;
pub mod operators;
pub mod oracle;
pub mod proof;
pub mod psro;
pub mod race;
pub mod repair;
pub mod report;
pub mod search;
mod spatial;
mod util;

#[cfg(test)]
mod completion_tests;

use std::sync::Arc;

use crate::catalog::Catalog;
use crate::layout::{AdmissionReport, AdmittedLayout, BaseRules};

#[derive(Clone)]
pub struct Context {
    pub rules: Arc<BaseRules>,
    pub catalog: Arc<Catalog>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Rejection {
    NotApplicable(String),
    ContextMismatch,
    Conservation(String),
    RepairBudget,
    Admission(AdmissionReport),
    StaleGuidance,
    InvalidConfig(String),
}

#[derive(Clone, Debug, PartialEq)]
pub struct RepairAction {
    pub instance: String,
    pub description: String,
}

#[derive(Clone, Debug)]
pub struct Proposal {
    pub candidate: AdmittedLayout,
    pub operator: String,
    pub seed: u64,
    pub parents: Vec<String>,
    pub changed_instances: Vec<String>,
    pub repair_actions: Vec<RepairAction>,
}

impl Context {
    pub fn check(&self, parent: &AdmittedLayout) -> Result<(), Rejection> {
        if parent.rules_identity() != self.rules.identity
            || parent.catalog_identity() != self.rules.catalog_identity
        {
            return Err(Rejection::ContextMismatch);
        }
        Ok(())
    }
}

/// SplitMix64 with a specified integer algorithm and no global mutable state.
#[derive(Clone, Debug)]
pub struct ProposalRng(u64);

impl ProposalRng {
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }

    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut value = self.0;
        value = (value ^ (value >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94d049bb133111eb);
        value ^ (value >> 31)
    }

    pub fn index(&mut self, count: usize) -> usize {
        assert!(count > 0);
        (self.next_u64() % count as u64) as usize
    }

    pub fn unit(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }
}

pub use clash_engine::*;

fn scoring_outcome(result: &clash_engine::state::BattleResult) -> clash_scoring::scoring::Outcome {
    clash_scoring::scoring::Outcome {
        stars: result.stars as i64,
        destruction: result.destruction as f64,
        th_destroyed: result.th_destroyed,
        time: result.time,
    }
}
