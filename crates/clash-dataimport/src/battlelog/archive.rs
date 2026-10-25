//! Collector identity deliberately differs from fidelity's army observation hash.

use std::collections::BTreeSet;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use clash_data::json::Json;
use clash_data::wire::*;

use super::provider::{normalize_tag, parse_battles, validate_player, BattleLogSource};
use super::snapshots::utc;
use super::{object, required_text, timestamp};

static SERIAL: AtomicU64 = AtomicU64::new(0);

#[derive(Debug)]
pub struct CollectReport {
    pub added: usize,
    pub total: usize,
    pub player_captured: bool,
}

fn key(battle: &Json) -> Result<(String, String, bool), String> {
    object(battle)?;
    let when = required_text(battle, "battleTimestamp")?;
    timestamp(when)?;
    let opponent = required_text(battle, "opponentPlayerTag")?;
    let Some(Json::Bool(attack)) = battle.get("attack") else {
        return Err("missing or invalid attack boolean".to_owned());
    };
    // Preserve the original collector's timestamp string, opponent, side tuple.
    Ok((when.to_owned(), opponent.to_owned(), *attack))
}

/// Atomic replacement on the same filesystem. Failed writes leave the original intact.
/// Unix files are private at creation; callers must choose private directories on Windows.
pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let temporary = parent.join(format!(
        ".clash-write-{}-{}",
        std::process::id(),
        SERIAL.fetch_add(1, Ordering::Relaxed)
    ));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&temporary)
        .map_err(|error| error.to_string())?;
    let result = (|| {
        file.write_all(bytes).map_err(|error| error.to_string())?;
        file.sync_all().map_err(|error| error.to_string())?;
        drop(file);
        fs::rename(&temporary, path).map_err(|error| format!("{}: {error}", path.display()))
    })();
    if result.is_err() {
        let _ = fs::remove_file(temporary);
    }
    result
}

/// Advisory create-new lock serializes native writers; never removes someone else's lock.
/// A crash leaves a lock for explicit recovery after checking no writer is running.
pub(crate) struct WriteLock {
    path: PathBuf,
    _file: File,
}

impl WriteLock {
    pub(crate) fn acquire(path: &Path) -> Result<Self, String> {
        let parent = path
            .parent()
            .filter(|path| !path.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        let mut name = path.as_os_str().to_os_string();
        name.push(".lock");
        let path = PathBuf::from(name);
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .map_err(|error| format!("cannot lock {}: {error}", path.display()))?;
        Ok(Self { path, _file: file })
    }
}

impl Drop for WriteLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

/// Fetch everything and validate it before changing the archive. Archive and player
/// files are individually atomic; an interrupted multi-file collection is safe to retry.
pub fn collect(
    source: &mut dyn BattleLogSource,
    tag: &str,
    directory: &Path,
    fetched_at: &str,
) -> Result<CollectReport, String> {
    let tag = normalize_tag(tag).map_err(|error| error.to_string())?;
    let fetched_at = utc(timestamp(fetched_at)?)?;
    let mut collection = source.fetch(&tag).map_err(|error| error.to_string())?;
    if let Some(player) = &collection.player {
        validate_player(player, &tag).map_err(|error| error.to_string())?;
    }
    for battle in &collection.battles {
        key(battle)?;
        if let Some(recorded) = battle.get("player_tag") {
            let Json::Str(recorded) = recorded else {
                return Err("invalid archived player_tag".to_owned());
            };
            if normalize_tag(recorded).map_err(|error| error.to_string())? != tag {
                return Err("input battle belongs to a different player".to_owned());
            }
        }
    }
    let archive = directory.join("battles.jsonl");
    let _lock = WriteLock::acquire(&archive)?;
    let existing = match fs::read_to_string(&archive) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
        Err(error) => return Err(error.to_string()),
    };
    let mut seen = BTreeSet::new();
    for battle in parse_battles(&existing, true).map_err(|error| error.to_string())? {
        key(&battle)?;
        if let Some(Json::Str(recorded)) = battle.get("player_tag") {
            if normalize_tag(recorded).map_err(|error| error.to_string())? != tag {
                return Err("archive belongs to a different player".to_owned());
            }
        }
        seen.insert(key(&battle)?);
    }
    // Store exact input bytes separately: the shared runtime parser uses f64.
    let mut payload_hashes = Vec::new();
    for raw in &collection.raw_payloads {
        let hash = sha256(raw.as_bytes());
        atomic_write(
            &directory.join("raw").join(format!("{hash}.json")),
            raw.as_bytes(),
        )?;
        payload_hashes.push(string(hash));
    }
    let receipt = obj([
        ("provider", string(source.name())),
        ("fetched_at", string(&fetched_at)),
        ("player_tag", string(&tag)),
        ("raw_sha256", arr(payload_hashes)),
    ]);
    let receipt_bytes = format!("{}\n", encode(&receipt));
    atomic_write(
        &directory
            .join("collections")
            .join(format!("{}.json", sha256(receipt_bytes.as_bytes()))),
        receipt_bytes.as_bytes(),
    )?;
    let player = collection.player.as_ref();
    let league = player
        .and_then(|player| player.get("leagueTier"))
        .and_then(|league| league.get("name"))
        .cloned()
        .unwrap_or(Json::Null);
    let trophies = player
        .and_then(|player| player.get("trophies"))
        .cloned()
        .unwrap_or(Json::Null);
    let mut output = existing;
    let mut added = 0;
    for battle in &mut collection.battles {
        if !seen.insert(key(battle)?) {
            continue;
        }
        // Already archived local rows retain their original fetch context.
        for (name, value) in [
            ("fetched", string(&fetched_at[..10])),
            ("fetched_at", string(&fetched_at)),
            ("provider", string(source.name())),
            ("player_tag", string(&tag)),
            ("player_league", league.clone()),
            ("player_trophies", trophies.clone()),
        ] {
            if battle.get(name).is_none() {
                put(battle, name, value);
            }
        }
        if !output.is_empty() && !output.ends_with('\n') {
            output.push('\n');
        }
        output.push_str(&encode(battle));
        output.push('\n');
        added += 1;
    }
    // Preserve all original rows byte-for-byte; no-op polling leaves the archive unchanged.
    if added != 0 || !archive.exists() {
        atomic_write(&archive, output.as_bytes())?;
    }
    if let Some(player) = &collection.player {
        atomic_write(
            &directory.join("player-latest.json"),
            format!("{}\n", encode(player)).as_bytes(),
        )?;
        let context = obj([
            ("provider", string(source.name())),
            ("fetched_at", string(&fetched_at)),
            ("player_tag", string(&tag)),
            ("player", player.clone()),
        ]);
        let digest = sha256(encode(&context).as_bytes());
        atomic_write(
            &directory.join("players").join(format!("{digest}.json")),
            format!("{}\n", encode(&context)).as_bytes(),
        )?;
    }
    Ok(CollectReport {
        added,
        total: seen.len(),
        player_captured: player.is_some(),
    })
}
