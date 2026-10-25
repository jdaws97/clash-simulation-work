use std::path::{Path, PathBuf};
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::json::Json;

use super::admit::admit;
use super::json::identity;
use super::model::{AdmissionPolicy, HolePolicy, Layout};
use super::rules::{self, BaseRules};

pub fn command(args: &[PathBuf], catalog: Arc<Catalog>, catalog_path: &Path) -> Result<(), String> {
    let usage = "layout import-rules <repo-root> <output.json> | layout check <rules.json> <layout.json> [--partial] [--all-walls] [--no-holes] | layout roundtrip <input.json> <output.json> | layout proof <repo-root> <report.json>";
    let command = args.first().and_then(|s| s.to_str()).ok_or(usage)?;
    let catalog_bytes = std::fs::read(catalog_path).map_err(|e| e.to_string())?;
    match command {
        "import-rules" if args.len() == 3 => {
            let document = rules::derive(&args[1], &catalog, &catalog_bytes)?;
            std::fs::write(&args[2], rules::pretty(&document)).map_err(|e| e.to_string())?;
            println!(
                "base rules: {} bytes identity={}",
                std::fs::metadata(&args[2])
                    .map_err(|e| e.to_string())?
                    .len(),
                identity(super::json::encode(&document).as_bytes())
            );
            Ok(())
        }
        "roundtrip" if args.len() == 3 => {
            let layout = Layout::load(&args[1]).map_err(|r| super::json::encode(&r.to_json()))?;
            std::fs::write(&args[2], rules::pretty(&layout.to_json())).map_err(|e| e.to_string())
        }
        "check" if args.len() >= 3 => {
            let rules = BaseRules::load(&args[1])?;
            if rules.catalog_identity != identity(&catalog_bytes) {
                return Err(
                    "catalog identity does not match base rules; rerun import-rules".to_owned(),
                );
            }
            let mut policy = AdmissionPolicy::default();
            for arg in &args[3..] {
                match arg.to_str() {
                    Some("--partial") => policy.require_full = false,
                    Some("--all-walls") => policy.require_all_walls = true,
                    Some("--no-holes") => policy.holes = HolePolicy::Forbid,
                    _ => return Err(usage.to_owned()),
                }
            }
            let layout = Layout::load(&args[2]);
            let result = layout.and_then(|layout| admit(layout, &rules, catalog, &policy));
            let report = match result {
                Ok(layout) => layout.receipt(),
                Err(report) => report.to_json(),
            };
            println!("{}", rules::pretty(&report));
            if report.at("accepted") == &Json::Bool(true) {
                Ok(())
            } else {
                Err("layout rejected; see structured report".to_owned())
            }
        }
        "proof" if args.len() == 3 => {
            super::proof::run(&args[1], &args[2], catalog, &catalog_bytes)
        }
        _ => Err(usage.to_owned()),
    }
}
