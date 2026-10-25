//! Scoring library for the offline Clash workspace.

#![forbid(unsafe_code)]

pub mod scoring;
pub mod scouting;
pub use clash_engine::*;
pub use clash_plans::{armies, compile};
