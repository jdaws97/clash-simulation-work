//! Plans library for the offline Clash workspace.

#![forbid(unsafe_code)]

pub mod armies;
pub mod compile;
pub use clash_engine::*;
#[cfg(test)]
mod test_support;
