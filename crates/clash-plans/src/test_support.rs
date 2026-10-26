//! Declared synthetic unit-test battles, never real-game calibration.

use std::path::Path;
use std::sync::{Arc, OnceLock};

use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::{self, Json};

pub fn catalog() -> Arc<Catalog> {
    static CATALOG: OnceLock<Arc<Catalog>> = OnceLock::new();
    Arc::clone(CATALOG.get_or_init(|| {
        Arc::new(
            Catalog::load(
                &Path::new(env!("CARGO_MANIFEST_DIR")).join("../../data/generated/catalog.json"),
            )
            .unwrap(),
        )
    }))
}

pub fn with_compiler<T>(run: impl FnOnce(Compiler<'_>) -> T) -> T {
    let catalog = catalog();
    let mut compiler = Compiler::load(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap(),
        &catalog.stats,
    )
    .unwrap();
    compiler.gaps = None;
    run(compiler)
}

pub fn json(source: &str) -> Json {
    json::parse(source).unwrap()
}
