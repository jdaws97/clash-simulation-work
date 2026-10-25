//! Deterministic development samples and explicit manual-truth scoring.
use crate::icons;
use crate::identity::{read_image, resized};
use crate::image::Image;
use crate::json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::Path;

fn hash(text: &str) -> u64 {
    text.bytes().fold(0xcbf29ce484222325, |h, b| {
        (h ^ b as u64).wrapping_mul(0x100000001b3)
    })
}

pub fn audit(root: &Path) -> io::Result<()> {
    let mut saved = Vec::new();
    let mut selected = Vec::new();
    for dir in icons::directories(root)? {
        let mut army = Vec::new();
        for path in icons::attack_paths(&dir)? {
            let a = Value::parse(&fs::read_to_string(path)?)?;
            let video = a.get("video_id").string().unwrap_or("");
            for family in ["slots", "army_cards"] {
                for s in a.get(family).array() {
                    let Some(icon) = s.get("icon").string() else {
                        continue;
                    };
                    let key = format!(
                        "{video}:{}:{family}:{}",
                        a.get("attack").encode(),
                        s.get("slot").encode()
                    );
                    let row = format!(
                        "{key}\t{}\t{}\t{}\t{}",
                        dir.join(icon).display(),
                        s.get("name").string().unwrap_or("unknown"),
                        s.get("level").get("value").encode(),
                        s.get("level").get("confidence").encode()
                    );
                    let entry = (
                        hash(&key),
                        dir.join(icon),
                        row,
                        s.get("level").get("value").number().is_some(),
                    );
                    if family == "slots" {
                        saved.push(entry);
                    } else {
                        army.push(entry);
                    }
                }
            }
        }
        army.sort_by_key(|e| e.0);
        selected.extend(army.into_iter().take(12));
    }
    saved.sort_by_key(|e| e.0);
    // Declared stratification exposes both accepted legacy reads and missing
    // badges; it must not be reported as a random prevalence estimate.
    for readable in [true, false] {
        selected.extend(saved.iter().filter(|e| e.3 == readable).take(12).cloned());
    }
    let mut table = String::from("sample\tkey\tpath\tname_pred\tlevel_pred\tlevel_confidence\n");
    fs::create_dir_all("/tmp/vidmine-work/m3")?;
    for (page, chunk) in selected.chunks(40).enumerate() {
        let mut sheet = Image::blank(1200, chunk.len().div_ceil(10) * 160);
        for (i, (_, path, row, _)) in chunk.iter().enumerate() {
            let sample = page * 40 + i;
            let image = read_image(path)?;
            sheet.paste(
                &resized(&image, 105, 135),
                i % 10 * 120,
                i / 10 * 160 + 18,
                1,
            );
            icons::digits(&mut sheet, &sample.to_string(), i % 10 * 120, i / 10 * 160);
            table.push_str(&format!("{sample}\t{row}\n"));
        }
        sheet
            .save(&Path::new("/tmp/vidmine-work/m3").join(format!("level-audit-{page:02}.ppm")))?;
    }
    fs::write(root.join("m3-level-audit.tsv"), table)
}

#[derive(Default)]
struct Score {
    labeled: usize,
    correct: usize,
    abstained: usize,
    excluded: usize,
}

impl Score {
    fn add(&mut self, prediction: &str, truth: &str) {
        if truth.is_empty() {
            return;
        }
        if truth == "na" {
            self.excluded += 1;
            return;
        }
        self.labeled += 1;
        self.correct += usize::from(prediction == truth);
        self.abstained += usize::from(prediction == "null" || prediction == "unknown");
    }

    fn line(&self, field: &str) -> String {
        format!(
            "{field}\t{}\t{}\t{}\t{}\t{}\n",
            self.labeled,
            self.correct,
            self.labeled - self.correct,
            self.abstained,
            self.excluded
        )
    }
}

pub fn score(root: &Path) -> io::Result<()> {
    let truth = fs::read_to_string(root.join("m3-level-truth.tsv"))?;
    let mut labels = BTreeMap::new();
    for line in truth.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 3 || labels.insert(c[0], (c[1], c[2])).is_some() {
            return Err(io::Error::other("invalid or duplicate M3 truth key"));
        }
        if !["na", ""].contains(&c[2]) && c[2].parse::<u32>().ok().filter(|v| *v > 0).is_none() {
            return Err(io::Error::other("invalid level truth"));
        }
    }
    let mut scores: BTreeMap<String, Score> = BTreeMap::new();
    let mut errors = String::from("key\tfield\tprediction\ttruth\tpath\n");
    let audit = fs::read_to_string(root.join("m3-level-audit.tsv"))?;
    for line in audit.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 6 {
            return Err(io::Error::other("bad M3 audit row"));
        }
        if let Some((name, level)) = labels.get(c[1]) {
            for (field, prediction, truth) in [("name", c[3], *name), ("level", c[4], *level)] {
                if !truth.is_empty() && truth != "na" && prediction != truth {
                    errors.push_str(&format!(
                        "{}\t{field}\t{prediction}\t{truth}\t{}\n",
                        c[1], c[2]
                    ));
                }
            }
            let group = if c[1].contains(":army_cards:") {
                "dev"
            } else {
                "saved"
            };
            scores
                .entry(format!("{group}_name"))
                .or_default()
                .add(c[3], name);
            scores
                .entry(format!("{group}_level"))
                .or_default()
                .add(c[4], level);
        }
    }
    let mut league = Score::default();
    for line in fs::read_to_string(root.join("m3-league-truth.tsv"))?
        .lines()
        .skip(1)
    {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 3 {
            return Err(io::Error::other("league truth needs video, attack, label"));
        }
        let id = c[1].parse::<usize>().map_err(io::Error::other)?;
        let a = Value::parse(&fs::read_to_string(
            root.join(c[0]).join(format!("attack-{id:02}.json")),
        )?)?;
        let l = a.get("league");
        let prediction = l.get("label").string().unwrap_or_else(|| {
            if l.get("status")
                .string()
                .is_some_and(|s| s.starts_with("no_label_visible"))
            {
                "none"
            } else {
                "unknown"
            }
        });
        league.add(prediction, c[2]);
    }
    let mut report = String::from("field\tlabeled_visible\tcorrect\terrors_including_abstentions\tabstentions\tunreadable_excluded\n");
    for (name, score) in scores {
        report.push_str(&score.line(&name));
    }
    report.push_str(&league.line("league"));
    fs::write(root.join("m3-review-errors.tsv"), errors)?;
    fs::write(root.join("m3-accuracy.tsv"), report)
}

pub fn label(root: &Path, manifest: &Path) -> io::Result<()> {
    let text = fs::read_to_string(manifest)?;
    let mut labels = BTreeMap::new();
    for line in text.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 3
            || labels
                .insert(c[0].to_string(), (c[1].to_string(), c[2].to_string()))
                .is_some()
        {
            return Err(io::Error::other(
                "sample truth requires unique sample, name, level",
            ));
        }
    }
    let mut truth = String::from("key\tname\tlevel\n");
    for line in fs::read_to_string(root.join("m3-level-audit.tsv"))?
        .lines()
        .skip(1)
    {
        let c: Vec<_> = line.split('\t').collect();
        if let Some((name, level)) = labels.get(c[0]) {
            truth.push_str(&format!("{}\t{name}\t{level}\n", c[1]));
        }
    }
    fs::write(root.join("m3-level-truth.tsv"), truth)
}

pub fn learn_names(root: &Path, templates: &Path) -> io::Result<()> {
    let text = fs::read_to_string(root.join("m3-level-truth.tsv"))?;
    let labels: BTreeMap<_, _> = text
        .lines()
        .skip(1)
        .filter_map(|l| {
            let c: Vec<_> = l.split('\t').collect();
            (c.len() == 3 && c[1] != "na" && !c[1].is_empty()).then(|| (c[0], c[1]))
        })
        .collect();
    let mut manifest = String::from("path\tx\ty\tw\th\tname\n");
    for line in fs::read_to_string(root.join("m3-level-audit.tsv"))?
        .lines()
        .skip(1)
    {
        let c: Vec<_> = line.split('\t').collect();
        if let Some(name) = labels.get(c[1]) {
            let image = read_image(Path::new(c[2]))?;
            manifest.push_str(&format!(
                "{}\t0\t0\t{}\t{}\t{name}\n",
                c[2], image.w, image.h
            ));
        }
    }
    let path = root.join("m3-reviewed-icon-templates.tsv");
    fs::write(&path, manifest)?;
    icons::learn_cards(&path, templates)
}

pub fn refresh(root: &Path) -> io::Result<()> {
    let text = fs::read_to_string(root.join("m3-level-audit.tsv"))?;
    let mut report = String::from("sample\tkey\tpath\tname_pred\tlevel_pred\tlevel_confidence\n");
    for line in text.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        let k: Vec<_> = c[1].split(':').collect();
        if k.len() != 4 {
            return Err(io::Error::other("invalid reviewed key"));
        }
        let id = k[1].parse::<usize>().map_err(io::Error::other)?;
        let slot = k[3].parse::<usize>().map_err(io::Error::other)?;
        let a = Value::parse(&fs::read_to_string(
            root.join(k[0]).join(format!("attack-{id:02}.json")),
        )?)?;
        let card = a
            .get(k[2])
            .array()
            .iter()
            .find(|s| s.get("slot").number() == Some(slot as f64))
            .ok_or_else(|| io::Error::other("reviewed slot disappeared"))?;
        report.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\t{}\n",
            c[0],
            c[1],
            c[2],
            card.get("name").string().unwrap_or("unknown"),
            card.get("level").get("value").encode(),
            card.get("level").get("confidence").encode()
        ));
    }
    fs::write(root.join("m3-level-audit.tsv"), report)
}

pub fn freeze(root: &Path) -> io::Result<()> {
    let dir = root.join("m3-reviewed-crops");
    fs::create_dir_all(&dir)?;
    let text = fs::read_to_string(root.join("m3-level-audit.tsv"))?;
    let mut out = String::from("sample\tkey\tpath\tname_pred\tlevel_pred\tlevel_confidence\n");
    for line in text.lines().skip(1) {
        let mut c: Vec<_> = line.split('\t').map(str::to_string).collect();
        let dest = dir.join(format!("{:016x}.ppm", hash(&c[1])));
        if Path::new(&c[2]) != dest {
            fs::copy(&c[2], &dest)?;
        }
        c[2] = dest.display().to_string();
        out.push_str(&(c.join("\t") + "\n"));
    }
    fs::write(root.join("m3-level-audit.tsv"), out)
}

pub fn read_crops(root: &Path, templates: &Path) -> io::Result<()> {
    let levels = crate::identity::Levels::load(templates)?;
    let library = icons::Library::load(templates)?;
    let text = fs::read_to_string(root.join("m3-level-audit.tsv"))?;
    let mut out = String::from("sample\tkey\tpath\tname_pred\tlevel_pred\tlevel_confidence\n");
    let mut inspected = Vec::new();
    for line in text.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        let image = read_image(Path::new(c[2]))?;
        inspected.push((c[0].to_string(), image.clone()));
        let (name, _) = if c[1].contains(":army_cards:") {
            library.identify_card(&image)
        } else {
            library.identify(&image)
        };
        let reading = levels.read(&image);
        out.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\t{}\n",
            c[0],
            c[1],
            c[2],
            name.as_deref().unwrap_or("unknown"),
            reading.get("value").encode(),
            reading.get("confidence").encode()
        ));
    }
    fs::write(root.join("m3-level-audit.tsv"), out)?;
    fs::create_dir_all("/tmp/vidmine-work/m3")?;
    for (page, chunk) in inspected.chunks(12).enumerate() {
        let mut sheet = Image::blank(1200, chunk.len().div_ceil(4) * 400);
        for (i, (sample, image)) in chunk.iter().enumerate() {
            let mut label = Image::blank(40, 12);
            icons::digits(&mut label, sample, 0, 0);
            sheet.paste(&label, i % 4 * 300, i / 4 * 400, 3);
            sheet.paste(&resized(image, 240, 320), i % 4 * 300, i / 4 * 400 + 50, 1);
        }
        sheet
            .save(&Path::new("/tmp/vidmine-work/m3").join(format!("frozen-large-{page:02}.ppm")))?;
    }
    Ok(())
}

pub fn validate(root: &Path) -> io::Result<()> {
    let mut counts = BTreeMap::<&str, usize>::new();
    for dir in icons::directories(root)? {
        for path in icons::attack_paths(&dir)? {
            let a = Value::parse(&fs::read_to_string(path)?)?;
            if a.get("schema_version").number().unwrap_or(0.0) < 3.0 {
                continue;
            }
            *counts.entry("attacks").or_default() += 1;
            let th = a.get("attacker_th");
            match (th.get("min").number(), th.get("max").number()) {
                (Some(min), Some(max)) if min >= 1.0 && min <= max => {
                    if th
                        .get("consistent")
                        .array()
                        .iter()
                        .any(|n| n.number().is_none_or(|n| n < min || n > max))
                    {
                        return Err(io::Error::other("invalid TH set"));
                    }
                    if th.get("best").number().is_some_and(|n| n < min || n > max) {
                        return Err(io::Error::other("best TH outside bounds"));
                    }
                    *counts.entry("bounded_attacker_th").or_default() += 1;
                }
                (None, None) => {
                    *counts
                        .entry("unknown_or_inconsistent_attacker_th")
                        .or_default() += 1;
                }
                _ => return Err(io::Error::other("invalid TH range")),
            }
            for family in ["slots", "army_cards"] {
                for s in a.get(family).array() {
                    if let Some(icon) = s.get("icon").string() {
                        if !dir.join(icon).is_file() {
                            return Err(io::Error::other("missing M3 card crop"));
                        }
                    }
                    let level = s.get("level");
                    let key = if family == "slots" {
                        if level.get("value").number().is_some() {
                            "saved_badges_read"
                        } else {
                            "saved_levels_unreadable_or_missing"
                        }
                    } else if level.get("value").number().is_some() {
                        "video_badges_read"
                    } else {
                        "video_levels_unconfirmed_or_unreadable"
                    };
                    *counts.entry(key).or_default() += 1;
                    if level
                        .get("value")
                        .number()
                        .is_some_and(|n| n < 1.0 || n > 999.0 || n.fract() != 0.0)
                    {
                        return Err(io::Error::other("invalid level"));
                    }
                }
            }
            if a.get("league")
                .get("confidence")
                .number()
                .is_none_or(|n| !(0.0..=1.0).contains(&n))
            {
                return Err(io::Error::other("invalid league confidence"));
            }
            let league_key = if a.get("league").get("label").string().is_some() {
                "league_labels_read"
            } else if a
                .get("league")
                .get("status")
                .string()
                .is_some_and(|s| s.starts_with("no_label_visible"))
            {
                "league_absent"
            } else {
                "league_unknown"
            };
            *counts.entry(league_key).or_default() += 1;
            if a.get("defender_th") == &Value::Null {
                if a.get("defender_th_reason").string().is_none() {
                    return Err(io::Error::other("missing defender abstention reason"));
                }
                *counts.entry("defender_th_unavailable").or_default() += 1;
            }
        }
    }
    let report = Value::Object(
        counts
            .into_iter()
            .map(|(k, v)| (k.to_string(), Value::from(v as f64)))
            .collect(),
    );
    fs::write(root.join("m3-validation.json"), report.encode() + "\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn blank_truth_is_not_success_and_visible_abstentions_are_errors() {
        // Declared synthetic manual-truth rows, not real-game calibration.
        let mut score = Score::default();
        score.add("12", "");
        score.add("null", "12");
        score.add("null", "na");
        score.add("12", "12");
        assert_eq!(
            (
                score.labeled,
                score.correct,
                score.abstained,
                score.excluded
            ),
            (2, 1, 1, 1)
        );
    }
}
