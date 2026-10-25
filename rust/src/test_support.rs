//! Declared synthetic unit-test battles, never real-game calibration.

use std::path::Path;
use std::sync::{Arc, OnceLock};

use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::{self, Json};
use crate::state::Battle;

pub fn catalog() -> Arc<Catalog> {
    static CATALOG: OnceLock<Arc<Catalog>> = OnceLock::new();
    Arc::clone(CATALOG.get_or_init(|| {
        Arc::new(
            Catalog::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("data/catalog.json"))
                .unwrap(),
        )
    }))
}

pub fn with_compiler<T>(run: impl FnOnce(Compiler<'_>) -> T) -> T {
    let catalog = catalog();
    let mut compiler = Compiler::load(
        Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap(),
        &catalog.stats,
    )
    .unwrap();
    compiler.gaps = None;
    run(compiler)
}

pub fn json(source: &str) -> Json {
    json::parse(source).unwrap()
}

pub fn battle() -> Battle {
    let layout = json(
        r#"{"buildings":[{"key":"gs","x":20,"y":20}],"walls":[],"traps":[],"heroes":[],"cc_troops":[],"levels":{"gs":1}}"#,
    );
    let plan = json(
        r#"{"$type":"Stage","drops":[],"ticks":[],"town_hall":18,"strength":1,"loadouts":{},"revives_left":0}"#,
    );
    let options = json(r#"{"seed":2,"town_hall":18,"record":true}"#);
    crate::setup::build(&layout, &plan, &options, catalog()).unwrap()
}
