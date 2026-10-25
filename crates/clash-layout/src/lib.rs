//! Physical layouts, data-derived rules, admission and eight-way tile geometry.
//! No proposal or battle scoring implementation belongs in this module.

pub mod admit;
pub mod geometry;
pub mod json;
pub mod model;
pub mod rules;

pub use admit::{admit, AdmissionIssue, AdmissionReport, AdmittedLayout};
pub use model::{AdmissionPolicy, Layout, SearchConfig};
pub use rules::BaseRules;

pub use clash_data::{catalog, content, stats};
