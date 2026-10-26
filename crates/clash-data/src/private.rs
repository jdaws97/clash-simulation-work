//! Player-private inputs live outside git, under the gitignored `private/`
//! directory: `private/your-levels.json` (account levels) and `private/live/`
//! (battle log, player snapshot, base history). Without them every tool uses
//! the committed synthetic account, so clean checkouts and CI behave alike.
//!
//! `CLASH_PRIVATE=none` forces that public mode (the verification gate uses
//! it); any other value names a different private directory.

use std::path::{Path, PathBuf};

/// Synthetic Town Hall 16 account: every item at its TH16 cap, no real player.
pub const PUBLIC_ACCOUNT: &str = "data/source/accounts/public-th16.json";

/// The private directory, or `None` when private data is disabled.
pub fn dir(root: &Path) -> Option<PathBuf> {
    match std::env::var_os("CLASH_PRIVATE") {
        Some(value) if value.is_empty() || value == "none" => None,
        Some(value) => Some(root.join(value)),
        None => Some(root.join("private")),
    }
}

/// The account levels file: the private one when present, else the public one.
pub fn account(root: &Path) -> PathBuf {
    dir(root)
        .map(|directory| directory.join("your-levels.json"))
        .filter(|path| path.is_file())
        .unwrap_or_else(|| root.join(PUBLIC_ACCOUNT))
}

/// A file under `private/live/`, or `None` when private data is disabled.
pub fn live(root: &Path, name: &str) -> Option<PathBuf> {
    dir(root).map(|directory| directory.join("live").join(name))
}

/// Repository-relative display path, used in provenance strings.
pub fn display(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
