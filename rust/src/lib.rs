//! Battle engine and reusable prepared-job runner (std only).

#![forbid(unsafe_code)]

pub mod ai;
pub mod armies;
pub mod armysearch;
pub mod battle;
pub mod catalog;
pub mod combat;
pub mod compile;
pub mod compile_cli;
pub mod content;
pub mod defense;
pub mod detmath;
pub mod effects;
pub mod fast_hash;
mod field_profile;
pub mod geom;
pub mod golden;
pub mod grid;
pub mod heroes;
pub mod jobs;
pub mod json;
pub mod labels;
pub mod layout;
pub mod load;
pub mod movement;
pub mod params;
pub mod pets;
pub mod plan_golden;
pub mod plans;
pub mod playbook;
pub mod pyrandom;
pub mod runner;
#[path = "scoring_cli.rs"]
pub mod score_cli;
pub mod scoring;
pub mod scouting;
pub mod setup;
pub mod shared;
pub mod source;
pub mod spells;
pub mod state;
pub mod stats;
pub mod targeting;
pub mod trace;
pub mod traps;
pub mod units;

pub use runner::{Job, JobFailure, JobResult, PreparedInputs, RunError, Runner, SummaryHook};

#[cfg(test)]
mod test_support;
