//! Frozen defensive snapshots take precedence over legacy inclusive-day hints.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use clash_data::json::Json;
pub use clash_data::snapshots::{battles, setup, timestamp};

use super::decode::{identity, Decoder};
use super::io::*;

#[derive(Clone)]
pub struct Observation {
    pub id: String,
    pub build: Json,
    pub family: String,
    pub th: i64,
    pub layout: Json,
    pub layout_path: String,
    pub layout_hash: String,
    pub setup_source: String,
    pub modifier: Option<String>,
    pub stars: i64,
    pub pct: f64,
    pub time: f64,
}

pub fn observations(
    root: &Path,
    log: &Path,
    history_path: &Path,
    historical: bool,
    base: Option<&str>,
) -> Result<(Vec<Observation>, BTreeMap<String, usize>), String> {
    let decoder = Decoder::load(root)?;
    let history = read(history_path)?;
    let mut rows = Vec::new();
    let mut skipped = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for battle in battles(log)? {
        if text(&battle, "battleType", "") != "ranked"
            || battle.get("attack") != Some(&Json::Bool(false))
        {
            continue;
        }
        let parsed = (|| {
            let th = number(&battle, "opponentTownHallLevel", 0.0);
            let stars = number(&battle, "stars", -1.0);
            let pct = number(&battle, "destructionPercentage", -1.0);
            if !(1.0..=18.0).contains(&th)
                || th.fract() != 0.0
                || !(0.0..=3.0).contains(&stars)
                || stars.fract() != 0.0
                || !(0.0..=100.0).contains(&pct)
                || (stars == 3.0) != (pct == 100.0)
            {
                return Err("invalid_outcome_or_timestamp".to_owned());
            }
            let when = text(&battle, "battleTimestamp", "");
            timestamp(when)?;
            let id = identity(&battle)?;
            if !seen.insert(id.clone()) {
                return Err("duplicate".to_owned());
            }
            let build = decoder.build(text(&battle, "armyShareCode", ""), th as i64, rows.len())?;
            let (layout, path, source) = setup(root, &history, when, base, historical)?;
            let league = text(&battle, "player_league", "").to_lowercase();
            let modifier = if let Some((_, suffix)) = league.split_once("legend") {
                Some(
                    match suffix.trim() {
                        "i" => "legend1",
                        "ii" => "legend2",
                        "iii" => "legend3",
                        _ => return Err("unknown_league_modifier".to_owned()),
                    }
                    .to_owned(),
                )
            } else {
                None
            };
            let family = clash_plans::armies::family_of(&build)
                .unwrap_or("unclassified")
                .to_owned();
            Ok(Observation {
                id,
                build,
                family,
                th: th as i64,
                layout,
                layout_hash: file_hash(&resolve(root, &path))?,
                layout_path: path,
                setup_source: source,
                modifier,
                stars: stars as i64,
                pct,
                time: number(&battle, "battleTime", 0.0),
            })
        })();
        match parsed {
            Ok(row) => rows.push(row),
            Err(reason) => *skipped.entry(reason).or_default() += 1,
        }
    }
    Ok((rows, skipped))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utc_boundaries_and_invalid_dates() {
        assert_eq!(
            timestamp("20261021T183738.123Z"),
            timestamp("2026-10-21T14:37:38.123-04:00")
        );
        assert_eq!(timestamp("1970-01-01").unwrap(), 0);
        assert!(timestamp("2026-02-29").is_err());
        assert!(timestamp("20261021T250000Z").is_err());
    }

    #[test]
    fn synthetic_snapshots_are_half_open_hash_checked_and_unambiguous() {
        let directory =
            std::env::temp_dir().join(format!("rf1-snapshot-test-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let raw = "{\"name\":\"declared synthetic fixture\",\"levels\":{\"cannon\":1}}";
        std::fs::write(directory.join("frozen.json"), raw).unwrap();
        let entry = obj([
            ("from", string("2026-10-21T00:00:00Z")),
            ("to", string("2026-10-22T00:00:00Z")),
            ("layout", string("frozen.json")),
            ("sha256", string(sha256(canonical(raw).unwrap().as_bytes()))),
        ]);
        let history = obj([("snapshots", arr([entry.clone()]))]);
        assert_eq!(
            setup(&directory, &history, "20261021T000000Z", None, true)
                .unwrap()
                .2,
            "frozen_snapshot"
        );
        assert!(setup(&directory, &history, "20261022T000000Z", None, true).is_err());
        let overlap = obj([("snapshots", arr([entry.clone(), entry]))]);
        assert_eq!(
            setup(&directory, &overlap, "20261021T000000Z", None, true).unwrap_err(),
            "overlapping_snapshots"
        );
        std::fs::write(directory.join("frozen.json"), "{}").unwrap();
        assert_eq!(
            setup(&directory, &history, "20261021T000000Z", None, true).unwrap_err(),
            "snapshot_hash_mismatch"
        );
        std::fs::remove_dir_all(directory).unwrap();
    }
}
