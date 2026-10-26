//! Data import tools: catalog and rules building from game data, battle-log
//! decoding and fetching (keyless sources only), and screenshot digitising.
//! These are tools built on the engine's data formats; the simulation itself
//! lives in clash-engine.

pub mod account;
pub mod battlelog;
pub mod catalog;
pub mod digitize;

/// `clash dataimport <account|catalog|battlelog|digitize> ...`
pub fn cli(args: &[String]) -> Result<(), String> {
    let rest = args.get(1..).unwrap_or(&[]);
    match args.first().map(String::as_str) {
        Some("account") => account::cli(rest),
        Some("catalog") => catalog::cli(rest),
        Some("battlelog") => battlelog::cli(rest),
        Some("digitize") => digitize::cli(rest),
        _ => Err("usage: clash dataimport <account|catalog|battlelog|digitize> ...".to_owned()),
    }
}
