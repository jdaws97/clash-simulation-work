use crate::json::Value;
use std::fs;
use std::io;
use std::path::Path;

fn median(values: &mut [f64]) -> f64 {
    values.sort_by(f64::total_cmp);
    values[values.len() / 2]
}

pub fn rate(points: &[(f64, f64)]) -> Option<(f64, f64)> {
    if points.len() < 6 || points.last()?.0 - points.first()?.0 < 3.0 {
        return None;
    }
    let mut slopes = Vec::new();
    for (i, (t, c)) in points.iter().enumerate().step_by(2) {
        for (u, d) in points.iter().skip(i + 1).step_by(3) {
            if u - t >= 2.0 {
                slopes.push((c - d) / (u - t));
            }
        }
    }
    if slopes.is_empty() {
        return None;
    }
    let speed = median(&mut slopes);
    if !(0.0..=8.0).contains(&speed) {
        return None;
    }
    let mut offsets: Vec<_> = points.iter().map(|(t, c)| c + speed * t).collect();
    let intercept = median(&mut offsets);
    let mut residuals: Vec<_> = offsets.iter().map(|v| (v - intercept).abs()).collect();
    let residual = median(&mut residuals);
    (residual <= 1.2).then_some((speed, residual))
}

pub fn annotate(attack: &mut Value) -> io::Result<()> {
    let points: Vec<_> = attack
        .get("clock_series")
        .array()
        .iter()
        .filter_map(|f| Some((f.get("video_t").number()?, f.get("clock_t").number()?)))
        .collect();
    let start = attack.get("video_t_start").number().unwrap_or(0.0);
    let end = attack.get("video_t_end").number().unwrap_or(start);
    let mut segments = Vec::new();
    let mut rates = Vec::new();
    let mut left = start;
    while left + 4.0 <= end {
        let right = (left + 8.0).min(end);
        let samples: Vec<_> = points
            .iter()
            .copied()
            .filter(|(t, _)| *t >= left && *t < right)
            .collect();
        if let Some((speed, residual)) = rate(&samples) {
            let state = if speed < 0.25 {
                "paused"
            } else if speed > 1.25 {
                "sped_up"
            } else if speed < 0.75 {
                "slowed"
            } else {
                "normal"
            };
            segments.push(Value::parse(&format!("{{\"video_t_start\":{left:.1},\"video_t_end\":{right:.1},\"clock_seconds_per_video_second\":{speed:.4},\"median_clock_residual_seconds\":{residual:.4},\"state\":\"{state}\"}}"))?);
            rates.push(speed);
        }
        left = right;
    }
    let nonstandard = rates.iter().any(|r| *r < 0.75 || *r > 1.25);
    let cuts = !attack.get("cuts").array().is_empty();
    let gap = points.windows(2).any(|w| w[1].0 - w[0].0 > 3.0);
    let fps = attack.get("sample_fps").number().unwrap_or(5.0);
    let coverage = points.len() as f64 / ((end - start) * fps + 1.0).max(1.0);
    let reason = if cuts {
        "clock discontinuity or merged obscured fragment"
    } else if nonstandard {
        "non-unit playback speed"
    } else if gap || coverage < 0.7 {
        "insufficient continuous clock observations"
    } else {
        "continuous clock consistent with real-time playback; clock-preserving edits remain undetectable"
    };
    let median_rate = if rates.is_empty() {
        Value::Null
    } else {
        Value::from(median(&mut rates))
    };
    attack.set("playback_speed", median_rate);
    attack.set("speed_segments", Value::Array(segments));
    attack.set("sped_up", Value::from(rates.iter().any(|r| *r > 1.25)));
    attack.set("edited", Value::from(cuts || nonstandard));
    attack.set(
        "usable_for_timing",
        Value::from(!cuts && !nonstandard && !gap && coverage >= 0.7 && !rates.is_empty()),
    );
    attack.set("timing_status", Value::from(reason));
    if attack
        .get("deployment_status")
        .string()
        .is_some_and(|s| s.contains("outside edited crop"))
    {
        attack.set("edited", Value::from(true));
        attack.set("usable_for_timing", Value::from(false));
        attack.set(
            "timing_status",
            Value::from(
                "edited moving replay crop; incomplete HUD and battle boundaries require review",
            ),
        );
    }
    Ok(())
}

pub fn update(root: &Path) -> io::Result<()> {
    let mut report =
        String::from("video\tattack\tplayback_speed\tsped_up\tedited\tusable_for_timing\n");
    let mut segments = String::from("video\tattack\tstart\tend\trate\tstate\n");
    for dir in crate::icons::directories(root)? {
        let mut states = std::collections::BTreeMap::new();
        for path in crate::icons::attack_paths(&dir)? {
            let mut attack = Value::parse(&fs::read_to_string(&path)?)?;
            annotate(&mut attack)?;
            let number = attack.get("attack").number().unwrap_or(0.0) as usize;
            for segment in attack.get("speed_segments").array() {
                segments.push_str(&format!(
                    "{}\t{number}\t{}\t{}\t{}\t{}\n",
                    dir.file_name().unwrap().to_string_lossy(),
                    segment.get("video_t_start").encode(),
                    segment.get("video_t_end").encode(),
                    segment.get("clock_seconds_per_video_second").encode(),
                    segment.get("state").string().unwrap_or("unknown")
                ));
            }
            states.insert(number, attack.get("edited").encode());
            report.push_str(&format!(
                "{}\t{number}\t{}\t{}\t{}\t{}\n",
                dir.file_name().unwrap().to_string_lossy(),
                attack.get("playback_speed").encode(),
                attack.get("sped_up").encode(),
                attack.get("edited").encode(),
                attack.get("usable_for_timing").encode()
            ));
            fs::write(path, attack.encode() + "\n")?;
        }
        let text = fs::read_to_string(dir.join("attacks.tsv"))?;
        let mut lines = Vec::new();
        for (i, line) in text.lines().enumerate() {
            let mut columns: Vec<_> = line.split('\t').map(str::to_string).collect();
            if i > 0 && columns.len() >= 13 {
                if let Some(state) = columns[1]
                    .parse::<usize>()
                    .ok()
                    .and_then(|n| states.get(&n))
                {
                    columns[12] = state.clone();
                }
            }
            lines.push(columns.join("\t"));
        }
        fs::write(dir.join("attacks.tsv"), lines.join("\n") + "\n")?;
    }
    fs::write(root.join("speed-segments.tsv"), segments)?;
    fs::write(root.join("timing-summary.tsv"), report)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn robust_speed_ignores_isolated_bad_glyphs() {
        // Declared synthetic clock samples at 2x, with one incorrect reading.
        let mut samples: Vec<_> = (0..40)
            .map(|i| (i as f64 / 5.0, 180.0 - (i * 2 / 5) as f64))
            .collect();
        samples[15].1 = 20.0;
        let (speed, residual) = rate(&samples).unwrap();
        assert!((speed - 2.0).abs() < 0.15);
        assert!(residual < 0.6);
    }
}
