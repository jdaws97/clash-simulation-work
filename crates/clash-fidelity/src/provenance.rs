//! Hash-bound calibration ancestry. Unknown training history is never held out.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use clash_data::json::Json;

use super::io::*;

pub const R8_SHA256: &str = "821a486f0e481d58070b61099d0e102a410c3d4b02471efe5c6d71ebb0d565b8";

pub fn ancestry_ids(ancestry: &Json) -> Option<BTreeSet<String>> {
    let Json::Arr(priors) = ancestry else {
        return None;
    };
    let mut fitted = BTreeSet::new();
    for prior in priors {
        if text(prior, "calibration", "").is_empty() {
            return None;
        }
        let Json::Arr(identities) = prior.get("battle_ids")? else {
            return None;
        };
        let ancestors = ancestry_ids(prior.get("ancestry")?)?;
        let public = text(prior, "fit_status", "") == "not defense-fitted"
            && identities.is_empty()
            && matches!(prior.get("ancestry"), Some(Json::Arr(values)) if values.is_empty())
            && text(prior, "sha256", "") == R8_SHA256;
        let digest = text(prior, "sha256", "");
        if !public
            && (digest.len() != 64
                || !digest.bytes().all(|byte| byte.is_ascii_hexdigit())
                || text(prior, "report_calibration_sha256", "") != digest)
        {
            return None;
        }
        for identity in identities {
            let Json::Str(identity) = identity else {
                return None;
            };
            fitted.insert(identity.clone());
        }
        fitted.extend(ancestors);
    }
    Some(fitted)
}

pub struct Binding {
    pub ids: Option<BTreeSet<String>>,
    pub info: Json,
}

pub fn binding(root: &Path, calibration: &Path, report: Option<&Path>) -> Result<Binding, String> {
    let selected = read(calibration)?;
    let hash = file_hash(calibration)?;
    let mut info = obj([
        ("fit_status", string("ancestry unknown")),
        ("calibration", string(calibration.to_string_lossy())),
        ("calibration_sha256", string(&hash)),
        ("ancestry", Json::Null),
    ]);
    let defense_fitted = selected
        .obj()
        .iter()
        .any(|(key, value)| key.starts_with("defense-th") || value.get("defense_group").is_some());
    if !defense_fitted {
        let known = calibration.canonicalize().ok()
            == root
                .join("data/source/meta-calibration-r8.json")
                .canonicalize()
                .ok()
            && hash == R8_SHA256;
        if known {
            put(&mut info, "fit_status", string("not defense-fitted"));
            put(&mut info, "ancestry", arr([]));
        }
        return Ok(Binding {
            ids: known.then(BTreeSet::new),
            info,
        });
    }
    let mut candidates = Vec::<PathBuf>::new();
    if let Some(path) = report {
        candidates.push(path.to_owned());
    } else {
        for (_, value) in selected.obj() {
            if let Some(provenance) = value.get("provenance") {
                let path = text(provenance, "calibration_report", "");
                if !path.is_empty() {
                    candidates.push(resolve(root, path));
                }
            }
        }
        candidates.push(calibration.with_file_name(
            format!("report-{}", calibration.file_name().unwrap_or_default().to_string_lossy()),
        ));
        candidates.push(calibration.with_extension("report.json"));
        {
            let directory = root.join("data/source");
            if let Ok(entries) = std::fs::read_dir(directory) {
                let mut paths: Vec<_> = entries
                    .flatten()
                    .map(|entry| entry.path())
                    .filter(|path| {
                        path.extension().is_some_and(|ext| ext == "json")
                            && path
                                .file_name()
                                .is_some_and(|name| name.to_string_lossy().contains("report"))
                    })
                    .collect();
                paths.sort();
                candidates.extend(paths);
            }
        }
    }
    for path in candidates {
        let Ok(report) = read(&path) else {
            continue;
        };
        if text(&report, "calibration_sha256", "") != hash
            || report.get("inputs_changed_during_run") == Some(&Json::Bool(true))
            || !matches!(report.get("groups"), Some(Json::Obj(values)) if !values.is_empty())
        {
            continue;
        }
        let ancestry = report.get("ancestry").cloned().unwrap_or(Json::Null);
        put(&mut info, "ancestry", ancestry.clone());
        put(
            &mut info,
            "calibration_report",
            string(path.to_string_lossy()),
        );
        let ids = (|| {
            let mut ids = ancestry_ids(&ancestry)?;
            let Json::Arr(identities) = report.get("battle_ids")? else {
                return None;
            };
            if identities.len() as f64 != number(&report, "n", -1.0) {
                return None;
            }
            let mut direct = BTreeSet::new();
            for identity in identities {
                let Json::Str(identity) = identity else {
                    return None;
                };
                direct.insert(identity.clone());
            }
            if direct.len() != identities.len() {
                return None;
            }
            ids.extend(direct);
            Some(ids)
        })();
        if ids.is_some() {
            put(&mut info, "fit_status", string("identified"));
        }
        return Ok(Binding { ids, info });
    }
    Ok(Binding { ids: None, info })
}

pub fn prior_snapshot(
    root: &Path,
    calibration: &Path,
    report: Option<&Path>,
) -> Result<Json, String> {
    let binding = binding(root, calibration, report)?;
    Ok(obj([
        ("calibration", string(calibration.to_string_lossy())),
        ("sha256", string(file_hash(calibration)?)),
        (
            "report_calibration_sha256",
            binding
                .info
                .get("calibration_sha256")
                .cloned()
                .unwrap_or(Json::Null),
        ),
        (
            "battle_ids",
            binding
                .ids
                .map_or(Json::Null, |ids| arr(ids.into_iter().map(string))),
        ),
        (
            "ancestry",
            binding.info.get("ancestry").cloned().unwrap_or(Json::Null),
        ),
        (
            "fit_status",
            string(text(&binding.info, "fit_status", "ancestry unknown")),
        ),
    ]))
}

pub fn fingerprint(root: &Path, extra: &[&Path]) -> Result<Json, String> {
    fn visit(path: &Path, paths: &mut Vec<PathBuf>) -> Result<(), String> {
        for entry in std::fs::read_dir(path).map_err(|error| error.to_string())? {
            let path = entry.map_err(|error| error.to_string())?.path();
            if path.is_dir() {
                visit(&path, paths)?;
            } else if path
                .extension()
                .is_some_and(|extension| extension == "rs" || extension == "json")
            {
                paths.push(path);
            }
        }
        Ok(())
    }
    let mut paths = Vec::new();
    visit(&root.join("crates"), &mut paths)?;
    visit(&root.join("data/generated"), &mut paths)?;
    visit(&root.join("data/source/playbooks"), &mut paths)?;
    for path in [
        "Cargo.toml",
        "data/source/clashking-static-data.json",
        "data/source/meta-armies-2026-10-15.json",
        "data/source/observed-armies.json",
        "data/source/custom-armies.json",
        "data/source/baselab-calibration.json",
        "data/source/attacker-policy.json",
        "data/source/playbook-gaps.json",
        "data/source/your-levels.json",
        "data/source/live/player-latest.json",
    ] {
        let path = root.join(path);
        if path.is_file() {
            paths.push(path);
        }
    }
    for path in extra {
        paths.push(path.to_path_buf());
    }
    paths.sort();
    paths.dedup();
    Ok(obj(paths
        .into_iter()
        .map(|path| {
            let key = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            file_hash(&path).map(|digest| (key, string(digest)))
        })
        .collect::<Result<Vec<_>, _>>()?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ancestry_requires_recursive_binding() {
        assert!(ancestry_ids(&arr([])).is_some());
        let mut prior = obj([
            ("calibration", string("prior.json")),
            ("sha256", string("a".repeat(64))),
            ("battle_ids", arr([string("train")])),
            ("ancestry", arr([])),
        ]);
        assert!(ancestry_ids(&arr([prior.clone()])).is_none());
        put(
            &mut prior,
            "report_calibration_sha256",
            string("a".repeat(64)),
        );
        assert!(ancestry_ids(&arr([prior.clone()]))
            .unwrap()
            .contains("train"));
        put(&mut prior, "ancestry", Json::Null);
        assert!(ancestry_ids(&arr([prior])).is_none());
    }

    #[test]
    fn synthetic_report_cannot_identify_replaced_calibration_bytes() {
        let directory =
            std::env::temp_dir().join(format!("rf1-binding-test-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let calibration = directory.join("calibration.json");
        let report_path = directory.join("report.json");
        std::fs::write(&calibration, "{\"defense-th16-pooled\":{\"strength\":1}}").unwrap();
        let report = obj([
            (
                "calibration_sha256",
                string(file_hash(&calibration).unwrap()),
            ),
            ("n", num(1.0)),
            ("battle_ids", arr([string("synthetic-training-id")])),
            ("ancestry", arr([])),
            ("groups", obj([("TH16:pooled", obj([("n", num(1.0))]))])),
        ]);
        write(&report_path, &report).unwrap();
        assert!(binding(&directory, &calibration, Some(&report_path))
            .unwrap()
            .ids
            .unwrap()
            .contains("synthetic-training-id"));
        std::fs::write(&calibration, "{\"defense-th16-pooled\":{\"strength\":2}}").unwrap();
        assert!(binding(&directory, &calibration, Some(&report_path))
            .unwrap()
            .ids
            .is_none());
        std::fs::remove_dir_all(directory).unwrap();
    }
}
