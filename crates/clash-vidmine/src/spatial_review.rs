//! Explicit manual labels, abstention-aware scoring, and spatial invariants.
use crate::camera::Transform;
use crate::grid::Grid;
use crate::icons;
use crate::json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

fn directory(root: &Path, video: &str) -> PathBuf {
    let normal = root.join(video);
    if normal.join("pending-output").is_dir() {
        normal.join("pending-output")
    } else {
        normal
    }
}

fn pair(value: &Value) -> Option<(f64, f64)> {
    let values = value.array();
    if values.len() != 2 {
        return None;
    }
    Some((values[0].number()?, values[1].number()?))
}

fn number(cells: &[&str], index: usize) -> io::Result<f64> {
    cells
        .get(index)
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|v| v.is_finite())
        .ok_or_else(|| io::Error::other("manual truth requires finite coordinates"))
}

fn summary(errors: &mut [f64]) -> (f64, f64, f64) {
    errors.sort_by(f64::total_cmp);
    if errors.is_empty() {
        return (0.0, 0.0, 0.0);
    }
    let n = errors.len();
    let mean = errors.iter().sum::<f64>() / n as f64;
    let median = if n.is_multiple_of(2) {
        (errors[n / 2 - 1] + errors[n / 2]) * 0.5
    } else {
        errors[n / 2]
    };
    let p90 = errors[((n as f64 * 0.9).ceil() as usize).saturating_sub(1)];
    (mean, median, p90)
}

pub fn score(root: &Path, truth: &Path, destination: &Path) -> io::Result<()> {
    let mut seen = BTreeSet::new();
    let mut pixels = Vec::new();
    let mut tiles = Vec::new();
    let mut visible = 0;
    let mut ambiguous = 0;
    let mut no_event = 0;
    let mut detail = String::from("video\tattack\tevent\tx_truth\ty_truth\tx_pred\ty_pred\tpixel_error\ttile_error_conditional\tvisible\tnote\n");
    for line in fs::read_to_string(truth)?.lines().skip(1) {
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let c: Vec<_> = line.split('\t').collect();
        if c.len() < 7 {
            return Err(io::Error::other(
                "truth needs video, attack, event, x, y, visible, note",
            ));
        }
        if !seen.insert((c[0].to_owned(), c[1].to_owned(), c[2].to_owned())) {
            return Err(io::Error::other("duplicate deployment truth key"));
        }
        if c[5].is_empty() || c[5] == "unlabeled" {
            continue;
        }
        match c[5] {
            "ambiguous" => {
                ambiguous += 1;
                continue;
            }
            "no_event" => {
                no_event += 1;
                continue;
            }
            "yes" => (),
            _ => {
                return Err(io::Error::other(
                    "visibility must be yes, ambiguous, no_event or blank",
                ))
            }
        }
        let attack_number = number(&c, 1)? as usize;
        let event_number = number(&c, 2)? as usize;
        let attack = Value::parse(&fs::read_to_string(
            directory(root, c[0]).join(format!("attack-{attack_number:02}.json")),
        )?)?;
        let event = attack
            .get("deployments")
            .array()
            .get(event_number)
            .ok_or_else(|| io::Error::other("manual truth points to missing event"))?;
        let position = event.get("position");
        let truth = (number(&c, 3)?, number(&c, 4)?);
        visible += 1;
        let predicted = pair(position.get("screen"));
        let pixel_error = predicted.map(|p| (p.0 - truth.0).hypot(p.1 - truth.1));
        if let Some(error) = pixel_error {
            pixels.push(error);
        }
        let grid = attack.get("grid_fit");
        let camera = position.get("keyframe_to_after").array();
        let tile_error = if let (Some(pred), Some(scale), Some(dx), Some(dy)) = (
            pair(position.get("tile")),
            camera.first().and_then(Value::number),
            camera.get(1).and_then(Value::number),
            camera.get(2).and_then(Value::number),
        ) {
            let grid = Grid {
                cx: grid
                    .get("cx")
                    .number()
                    .ok_or_else(|| io::Error::other("grid cx missing"))?,
                top: grid.get("top").number().unwrap(),
                a: grid.get("a").number().unwrap(),
                b: grid.get("b").number().unwrap(),
                residual: 0.0,
                landmarks: 0,
            };
            let key = Transform { scale, dx, dy }.inverse(truth.0, truth.1);
            let target = grid.unproject(key.0, key.1);
            Some((pred.0 - target.0).hypot(pred.1 - target.1))
        } else {
            None
        };
        if let Some(error) = tile_error {
            tiles.push(error);
        }
        let text = |v: Option<f64>| {
            v.map(|v| format!("{v:.3}"))
                .unwrap_or_else(|| "null".into())
        };
        detail.push_str(&format!(
            "{}\t{attack_number}\t{event_number}\t{:.1}\t{:.1}\t{}\t{}\t{}\t{}\tyes\t{}\n",
            c[0],
            truth.0,
            truth.1,
            text(predicted.map(|p| p.0)),
            text(predicted.map(|p| p.1)),
            text(pixel_error),
            text(tile_error),
            c[6]
        ));
    }
    let pixel_stats = summary(&mut pixels);
    let tile_stats = summary(&mut tiles);
    let stats_text = |count: usize, stats: (f64, f64, f64)| {
        if count == 0 {
            "null\tnull\tnull".to_owned()
        } else {
            format!("{:.3}\t{:.3}\t{:.3}", stats.0, stats.1, stats.2)
        }
    };
    let mut report = String::from("metric\tvisible_labels\tpredicted\tmissing\twithin_1\twithin_2\twithin_24\twithin_48\tmean\tmedian\tp90\n");
    report.push_str(&format!(
        "source_pixels\t{visible}\t{}\t{}\tna\tna\t{}\t{}\t{}\n",
        pixels.len(),
        visible - pixels.len(),
        pixels.iter().filter(|v| **v <= 24.0).count(),
        pixels.iter().filter(|v| **v <= 48.0).count(),
        stats_text(pixels.len(), pixel_stats),
    ));
    report.push_str(&format!(
        "tiles_conditional_on_fitted_grid_and_camera\t{visible}\t{}\t{}\t{}\t{}\tna\tna\t{}\n",
        tiles.len(),
        visible - tiles.len(),
        tiles.iter().filter(|v| **v <= 1.0).count(),
        tiles.iter().filter(|v| **v <= 2.0).count(),
        stats_text(tiles.len(), tile_stats),
    ));
    report.push_str(&format!(
        "ambiguous_excluded\t{ambiguous}\nupstream_no_event_excluded\t{no_event}\n"
    ));
    fs::create_dir_all(destination)?;
    fs::write(destination.join("m4-deployment-check.tsv"), detail)?;
    fs::write(destination.join("m4-deployment-accuracy.tsv"), &report)?;
    println!("{report}");
    Ok(())
}

pub fn score_townhalls(root: &Path, truth: &Path, destination: &Path) -> io::Result<()> {
    let mut seen = BTreeSet::new();
    let mut correct = 0;
    let mut labeled = 0;
    let mut missing = 0;
    let mut training = 0;
    let mut training_correct = 0;
    let mut excluded = 0;
    let mut per_class = [[0_usize; 3]; 3];
    let mut check = String::from("video\tattack\tth_truth\tth_pred\ttraining\tcorrect\tnote\n");
    for line in fs::read_to_string(truth)?.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() < 5 || c[2].is_empty() {
            continue;
        }
        if !seen.insert((c[0].to_owned(), c[1].to_owned())) {
            return Err(io::Error::other("duplicate TH truth"));
        }
        if c[2] == "na" {
            excluded += 1;
            continue;
        }
        let attack_number = number(&c, 1)? as usize;
        let truth = number(&c, 2)?;
        if ![16.0, 17.0, 18.0].contains(&truth) {
            return Err(io::Error::other("invalid TH truth label"));
        }
        if !["yes", "no"].contains(&c[3]) {
            return Err(io::Error::other("TH template membership must be yes or no"));
        }
        let attack = Value::parse(&fs::read_to_string(
            directory(root, c[0]).join(format!("attack-{attack_number:02}.json")),
        )?)?;
        let predicted = attack.get("defender_th").number();
        let success = predicted == Some(truth);
        if c[3] == "yes" {
            training += 1;
            training_correct += usize::from(success);
        } else {
            labeled += 1;
            correct += usize::from(success);
            missing += usize::from(predicted.is_none());
            let class = &mut per_class[truth as usize - 16];
            class[0] += 1;
            class[1] += usize::from(success);
            class[2] += usize::from(predicted.is_none());
        }
        check.push_str(&format!(
            "{}\t{attack_number}\t{truth}\t{}\t{}\t{success}\t{}\n",
            c[0],
            attack.get("defender_th").encode(),
            c[3],
            c[4]
        ));
    }
    let mut report = format!("subset\tlabeled\tcorrect\tabstained\nnon_template_keyframes_development\t{labeled}\t{correct}\t{missing}\ntemplate_keyframes_resubstitution\t{training}\t{training_correct}\tna\nunidentifiable_excluded\t{excluded}\tna\tna\n");
    for (index, class) in per_class.iter().enumerate() {
        report.push_str(&format!(
            "non_template_TH{}\t{}\t{}\t{}\n",
            index + 16,
            class[0],
            class[1],
            class[2]
        ));
    }
    fs::write(destination.join("m4-th-check.tsv"), check)?;
    fs::write(destination.join("m4-th-accuracy.tsv"), &report)?;
    println!("{report}");
    Ok(())
}

fn analysis_directories(root: &Path) -> io::Result<Vec<PathBuf>> {
    if !icons::attack_paths(root)?.is_empty() {
        return Ok(vec![root.to_path_buf()]);
    }
    let mut directories = Vec::new();
    for entry in fs::read_dir(root)? {
        let path = entry?.path();
        if !path.is_dir() {
            continue;
        }
        let path = if path.join("pending-output").is_dir() {
            path.join("pending-output")
        } else {
            path
        };
        if !icons::attack_paths(&path)?.is_empty() {
            directories.push(path);
        }
    }
    directories.sort();
    Ok(directories)
}

fn preserved(original: &Value, updated: &Value) -> io::Result<()> {
    let Value::Object(fields) = original else {
        return Err(io::Error::other("original attack is not an object"));
    };
    for (key, value) in fields {
        if [
            "defender_th",
            "defender_th_reason",
            "defender_th_evidence",
            "grid_fit",
            "camera_model",
            "spatial_keyframe",
            "deployments",
        ]
        .contains(&key.as_str())
        {
            continue;
        }
        if updated.get(key) != value {
            return Err(io::Error::other(format!(
                "M4 changed preserved field {key}"
            )));
        }
    }
    let before = original.get("deployments").array();
    let after = updated.get("deployments").array();
    if before.len() != after.len() {
        return Err(io::Error::other("M4 changed event count"));
    }
    for (before, after) in before.iter().zip(after) {
        let Value::Object(fields) = before else {
            return Err(io::Error::other("original event is not an object"));
        };
        for (key, value) in fields {
            if key != "position" && after.get(key) != value {
                return Err(io::Error::other(format!("M4 changed event field {key}")));
            }
        }
    }
    Ok(())
}

pub fn verify(root: &Path, originals: Option<&Path>) -> io::Result<()> {
    let mut attacks = 0;
    let mut camera_samples = 0;
    let mut positions = 0;
    let mut tile_positions = 0;
    for directory in analysis_directories(root)? {
        for path in icons::attack_paths(&directory)? {
            let attack = Value::parse(&fs::read_to_string(path)?)?;
            if attack.get("camera_model") == &Value::Null {
                continue;
            }
            if let Some(originals) = originals {
                let id = attack
                    .get("video_id")
                    .string()
                    .ok_or_else(|| io::Error::other("missing video ID"))?;
                let number = attack.get("attack").number().unwrap() as usize;
                let original = Value::parse(&fs::read_to_string(
                    originals.join(id).join(format!("attack-{number:02}.json")),
                )?)?;
                preserved(&original, &attack)?;
            }
            attacks += 1;
            for sample in attack.get("camera_model").get("samples").array() {
                let camera = sample.get("keyframe_to_frame").array();
                if camera.len() != 3 || camera[0].number().is_none_or(|s| s <= 0.0) {
                    return Err(io::Error::other("invalid camera transform"));
                }
                camera_samples += 1;
            }
            for event in attack.get("deployments").array() {
                let p = event.get("position");
                if p == &Value::Null {
                    return Err(io::Error::other("missing M4 deployment record"));
                }
                positions += 1;
                if p.get("tile") != &Value::Null {
                    if p.get("camera_reliable") != &Value::Bool(true)
                        || pair(p.get("tile")).is_none()
                    {
                        return Err(io::Error::other(
                            "unreliable camera published tile position",
                        ));
                    }
                    let screen = pair(p.get("screen"))
                        .ok_or_else(|| io::Error::other("tile without source screen position"))?;
                    let tile = pair(p.get("tile")).unwrap();
                    let fitted = attack.get("grid_fit");
                    let grid = Grid {
                        cx: fitted.get("cx").number().unwrap(),
                        top: fitted.get("top").number().unwrap(),
                        a: fitted.get("a").number().unwrap(),
                        b: fitted.get("b").number().unwrap(),
                        residual: 0.0,
                        landmarks: 0,
                    };
                    let camera = p.get("keyframe_to_after").array();
                    let camera = Transform {
                        scale: camera[0].number().unwrap(),
                        dx: camera[1].number().unwrap(),
                        dy: camera[2].number().unwrap(),
                    };
                    let key = grid.project(tile.0, tile.1);
                    let projected = camera.apply(key.0, key.1);
                    if (projected.0 - screen.0).hypot(projected.1 - screen.1) > 0.01 {
                        return Err(io::Error::other("tile/screen projection inconsistency"));
                    }
                    tile_positions += 1;
                }
            }
        }
    }
    if attacks == 0 {
        return Err(io::Error::other("no M4 attacks found to validate"));
    }
    println!("M4 invariants: {attacks} attacks, {camera_samples} camera samples, {positions} positions, {tile_positions} conditional tile positions");
    Ok(())
}

pub fn overview(root: &Path) -> io::Result<()> {
    println!("video\tattacks\tcamera_samples\treliable_camera_samples\tdeployments\tscreen_candidates\ttile_candidates\tdefender_th_matches");
    for directory in analysis_directories(root)? {
        let mut id = String::new();
        let mut counts = [0_usize; 7];
        for path in icons::attack_paths(&directory)? {
            let attack = Value::parse(&fs::read_to_string(path)?)?;
            if attack.get("camera_model") == &Value::Null {
                continue;
            }
            id = attack
                .get("video_id")
                .string()
                .unwrap_or("unknown")
                .to_owned();
            counts[0] += 1;
            let samples = attack.get("camera_model").get("samples").array();
            counts[1] += samples.len();
            counts[2] += samples
                .iter()
                .filter(|s| s.get("reliable") == &Value::Bool(true))
                .count();
            let events = attack.get("deployments").array();
            counts[3] += events.len();
            counts[4] += events
                .iter()
                .filter(|e| pair(e.get("position").get("screen")).is_some())
                .count();
            counts[5] += events
                .iter()
                .filter(|e| pair(e.get("position").get("tile")).is_some())
                .count();
            counts[6] += usize::from(attack.get("defender_th").number().is_some());
        }
        if counts[0] > 0 {
            println!(
                "{id}\t{}",
                counts
                    .iter()
                    .map(usize::to_string)
                    .collect::<Vec<_>>()
                    .join("\t")
            );
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_error_summary_uses_even_median_and_missing_pair_is_not_zero() {
        // Declared synthetic scoring inputs, not real-game measurements.
        assert_eq!(summary(&mut [8.0, 2.0, 4.0, 6.0]), (5.0, 5.0, 8.0));
        assert_eq!(pair(&Value::Null), None);
        assert_eq!(pair(&Value::Array(vec![1.0.into()])), None);
    }

    #[test]
    fn synthetic_visible_abstention_counts_as_error_and_duplicate_truth_is_rejected() {
        // Declared synthetic saved observations and manual-label schema.
        let root =
            Path::new(crate::spatial::WORK).join(format!("score-test-{}", std::process::id()));
        fs::create_dir_all(root.join("synthetic-video")).unwrap();
        let attack = r#"{"deployments":[{"position":{"screen":null,"tile":null}},{"position":{"screen":[100,100],"tile":null}}]}"#;
        fs::write(root.join("synthetic-video/attack-01.json"), attack).unwrap();
        let truth="video\tattack\tevent\tx\ty\tvisible\tnote\nsynthetic-video\t1\t0\t100\t100\tyes\tsynthetic\nsynthetic-video\t1\t1\t100\t100\tyes\tsynthetic\n";
        fs::write(root.join("truth.tsv"), truth).unwrap();
        score(&root, &root.join("truth.tsv"), &root).unwrap();
        let report = fs::read_to_string(root.join("m4-deployment-accuracy.tsv")).unwrap();
        assert!(report.contains("source_pixels\t2\t1\t1\tna\tna\t1\t1"));
        fs::write(
            root.join("truth.tsv"),
            format!("{truth}synthetic-video\t1\t1\t100\t100\tyes\tsynthetic\n"),
        )
        .unwrap();
        assert!(score(&root, &root.join("truth.tsv"), &root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
