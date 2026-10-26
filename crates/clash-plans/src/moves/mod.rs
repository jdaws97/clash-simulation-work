//! Cited technique registry with typed parameters, source reconstruction and
//! strict evidence-scope admission. Execution stays in the existing compiler
//! and engine; move search and human scheduling remain later milestones.
pub mod library;
pub mod lower;
pub mod schema;
pub mod validate;

pub use library::MoveLibrary;
pub use schema::{MoveDefinition, MoveInstance};

#[cfg(test)]
mod tests;
