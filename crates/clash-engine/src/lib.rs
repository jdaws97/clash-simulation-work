//! Engine library for the offline Clash workspace.

#![forbid(unsafe_code)]

pub mod ai;
pub mod battle;
pub mod combat;
pub mod defense;
pub mod detmath;
pub mod effects;
mod field_profile;
pub mod geom;
pub mod grid;
pub mod heroes;
pub mod load;
pub mod movement;
pub mod params;
pub mod pets;
pub mod plans;
pub mod playbook;
pub mod pyrandom;
pub mod runner;
pub mod setup;
pub mod shared;
pub mod source;
pub mod spells;
pub mod state;
pub mod targeting;
pub mod trace;
pub mod traps;
pub mod units;
pub use clash_data::*;
pub use clash_layout as layout;
pub use runner::{Job, JobFailure, JobResult, PreparedInputs, RunError, Runner, SummaryHook};
#[cfg(test)]
mod test_support;
