//! Synthetic accounts in the account-levels schema (see clash_data::private).
//! `caps` puts every non-seasonal item at its Town Hall cap, so tests and
//! goldens never need a real player's levels.

use std::path::{Path, PathBuf};

use clash_data::catalog::{self, Catalog};
use clash_data::json::Json;
use clash_data::wire::{num, obj, put, read, string, write};

const USAGE: &str =
    "usage: clash dataimport account caps --th N [--root REPO] [--catalog C.json] [--out FILE]";

pub fn cli(args: &[String]) -> Result<(), String> {
    if args.first().map(String::as_str) != Some("caps") {
        return Err(USAGE.to_owned());
    }
    let mut th = None;
    let mut root = PathBuf::from(".");
    let mut catalog_path = None;
    let mut out = None;
    let mut rest = args[1..].iter();
    while let Some(flag) = rest.next() {
        let value = rest.next().ok_or(USAGE)?;
        match flag.as_str() {
            "--th" => {
                th = Some(
                    value
                        .parse::<i64>()
                        .map_err(|_| "--th must be an integer")?,
                )
            }
            "--root" => root = PathBuf::from(value),
            "--catalog" => catalog_path = Some(PathBuf::from(value)),
            "--out" => out = Some(PathBuf::from(value)),
            _ => return Err(USAGE.to_owned()),
        }
    }
    let th = th.ok_or(USAGE)?;
    let catalog_path = catalog_path.unwrap_or_else(|| catalog::path(&root));
    let account = caps(&root, &Catalog::load(&catalog_path)?, th)?;
    match out {
        Some(path) => write(&path, &account),
        None => {
            println!("{}", clash_data::wire::encode(&account));
            Ok(())
        }
    }
}

pub fn caps(root: &Path, catalog: &Catalog, th: i64) -> Result<Json, String> {
    let stats = &catalog.stats;
    let cap = |name: &str| {
        stats
            .registry
            .get(name)
            .and_then(|_| stats.max_level(name, th))
            .filter(|level| *level > 0)
    };
    let rules = read(&root.join("data/generated/base_rules.json"))?;
    // The Town Hall row's "required Town Hall" is the hall it upgrades from, so
    // its catalog cap is one level high; the account Town Hall is `th` itself.
    let mut levels = obj([("th", num(th as f64))]);
    for (key, building) in rules.at("buildings").obj() {
        if key == "th" {
            continue;
        }
        if let Some(level) = cap(building.at("name").str()) {
            put(&mut levels, key, num(level as f64));
        }
    }
    let mut fields = [
        ("hero_levels", obj([] as [(&str, Json); 0])),
        ("attack_levels", obj([] as [(&str, Json); 0])),
        ("equipment_levels", obj([] as [(&str, Json); 0])),
        ("pet_levels", obj([] as [(&str, Json); 0])),
    ];
    for (name, record) in stats.registry.obj() {
        if record.get("seasonal") == Some(&Json::Bool(true)) {
            continue;
        }
        let field = match record.at("kind").str() {
            "hero" => 0,
            "troop" | "spell" | "siege" => 1,
            "equipment" => 2,
            "pet" => 3,
            _ => continue,
        };
        if let Some(level) = cap(name) {
            put(&mut fields[field].1, name, num(level as f64));
        }
    }
    let mut account = obj([
        (
            "source",
            string(format!(
                "synthetic public account: every non-seasonal item at its Town Hall {th} cap \
                 (clash dataimport account caps); not a real player"
            )),
        ),
        ("levels", levels),
    ]);
    if let Some(level) = cap("Wall") {
        put(&mut account, "wall_level", num(level as f64));
    }
    for (key, value) in fields {
        put(&mut account, key, value);
    }
    Ok(account)
}
