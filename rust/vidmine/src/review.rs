use crate::icons;
use crate::image::Image;
use crate::json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::io::{self, BufReader};
use std::path::Path;

pub fn icon_audit(root: &Path) -> io::Result<()> {
    let representatives: BTreeSet<String> =
        fs::read_to_string(root.join("icon-cluster-labels.tsv"))?
            .lines()
            .skip(1)
            .filter_map(|l| l.split('\t').nth(2).map(str::to_string))
            .collect();
    let mut entries = Vec::new();
    for dir in icons::directories(root)? {
        for path in icons::attack_paths(&dir)? {
            let value = Value::parse(&fs::read_to_string(path)?)?;
            for slot in value.get("slots").array() {
                let Some(icon) = slot.get("icon").string() else {
                    continue;
                };
                let path = dir.join(icon);
                if representatives.contains(&path.display().to_string()) {
                    continue;
                }
                entries.push((
                    path,
                    slot.get("name").clone(),
                    slot.get("name_confidence").clone(),
                ));
            }
        }
    }
    let mut seed = 0x7669646d696e6532_u64;
    let mut selected = BTreeSet::new();
    while selected.len() < 40.min(entries.len()) {
        seed = seed
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        selected.insert((seed >> 32) as usize % entries.len());
    }
    let mut sheet = Image::blank(1000, selected.len().div_ceil(10) * 140);
    let mut table = String::from("sample\tpath\tname_pred\tconfidence\tname_truth\n");
    for (i, index) in selected.into_iter().enumerate() {
        let (path, name, confidence) = &entries[index];
        let image = Image::read(&mut BufReader::new(fs::File::open(path)?))?
            .ok_or_else(|| io::Error::other("empty icon"))?;
        let mut thumb = Image::blank(90, 120);
        for y in 0..120 {
            for x in 0..90 {
                let j = (y * 90 + x) * 3;
                thumb.data[j..j + 3]
                    .copy_from_slice(&image.pixel(x * image.w / 90, y * image.h / 120));
            }
        }
        sheet.paste(&thumb, i % 10 * 100, i / 10 * 140, 1);
        table.push_str(&format!(
            "{i}\t{}\t{}\t{}\t\n",
            path.display(),
            name.string().unwrap_or("unknown"),
            confidence.encode()
        ));
    }
    fs::create_dir_all("/tmp/vidmine-work")?;
    sheet.save(Path::new("/tmp/vidmine-work/icon-audit.ppm"))?;
    fs::write(root.join("icon-spot-check.tsv"), table)
}

pub fn score_positions(out: &Path) -> io::Result<()> {
    let text = fs::read_to_string(out.join("position-check.tsv"))?;
    let mut errors = Vec::new();
    let mut unidentifiable = 0;
    let mut missing = 0;
    for line in text.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() < 10 {
            return Err(io::Error::other("position-check.tsv needs 10 columns"));
        }
        if c[9] == "no" {
            unidentifiable += 1;
            continue;
        }
        if c[9] != "yes" {
            continue;
        }
        let parse = |s: &str| s.parse::<f64>().ok().filter(|v| v.is_finite());
        if let (Some(x), Some(y), Some(tx), Some(ty)) =
            (parse(c[4]), parse(c[5]), parse(c[7]), parse(c[8]))
        {
            errors.push(((x - tx).powi(2) + (y - ty).powi(2)).sqrt());
        } else {
            missing += 1;
        }
    }
    errors.sort_by(f64::total_cmp);
    let mean = errors.iter().sum::<f64>() / errors.len().max(1) as f64;
    let median = errors.get(errors.len() / 2).copied().unwrap_or(0.0);
    let within = errors.iter().filter(|e| **e <= 48.0).count();
    let report=format!("field\tlabeled_visible\tmissing\tunidentifiable\twithin_48_source_pixels\tmean_error_pixels\tmedian_error_pixels\nposition_candidate\t{}\t{missing}\t{unidentifiable}\t{within}\t{mean:.2}\t{median:.2}\n",errors.len()+missing);
    fs::write(out.join("position-accuracy.tsv"), report)
}

pub fn verify(root: &Path) -> io::Result<()> {
    let mut attacks = 0;
    let mut slots = 0;
    let mut named = 0;
    let mut events = 0;
    let mut positions = 0;
    let mut edited = 0;
    let mut timing = 0;
    let mut sped = 0;
    let dirs = icons::directories(root)?;
    let mut details=String::from("video\tattacks\tslots\tnamed_slots\tdeployments\tpositions\tedited\tsped_up\ttiming_usable\n");
    for dir in &dirs {
        let mut counts = [0_usize; 9];
        for path in icons::attack_paths(dir)? {
            let a = Value::parse(&fs::read_to_string(&path)?)?;
            attacks += 1;
            counts[0] += 1;
            if a.get("edited") == &Value::Bool(true) {
                edited += 1;
                counts[5] += 1;
            }
            if a.get("usable_for_timing") == &Value::Bool(true) {
                timing += 1;
                counts[7] += 1;
            }
            if a.get("sped_up") == &Value::Bool(true) {
                sped += 1;
                counts[6] += 1;
            }
            let key = a
                .get("keyframe")
                .get("path")
                .string()
                .ok_or_else(|| io::Error::other("missing keyframe path"))?;
            if !dir.join(key).exists() {
                return Err(io::Error::other(format!(
                    "missing keyframe {}",
                    dir.join(key).display()
                )));
            }
            let mut inventory = std::collections::BTreeMap::new();
            let mut consumed = std::collections::BTreeMap::<usize, u32>::new();
            for slot in a.get("slots").array() {
                slots += 1;
                counts[1] += 1;
                if slot.get("name").string().is_some() {
                    named += 1;
                    counts[2] += 1;
                }
                let icon = slot
                    .get("icon")
                    .string()
                    .ok_or_else(|| io::Error::other("missing icon path"))?;
                if !dir.join(icon).exists() {
                    return Err(io::Error::other(format!(
                        "missing icon {}",
                        dir.join(icon).display()
                    )));
                }
                if let (Some(id), Some(initial)) = (
                    slot.get("slot").number(),
                    slot.get("initial_count").number(),
                ) {
                    inventory.insert(id as usize, initial as u32);
                }
            }
            for event in a.get("deployments").array() {
                events += 1;
                counts[3] += 1;
                if event.get("position") != &Value::Null {
                    positions += 1;
                    counts[4] += 1;
                }
                let id = event
                    .get("slot")
                    .number()
                    .ok_or_else(|| io::Error::other("deployment slot missing"))?
                    as usize;
                let before = event.get("count_before").number().unwrap_or(0.0) as u32;
                let after = event.get("count_after").number().unwrap_or(0.0) as u32;
                let delta = event.get("delta").number().unwrap_or(0.0) as u32;
                if before <= after || before - after != delta {
                    return Err(io::Error::other("invalid deployment delta"));
                }
                *consumed.entry(id).or_default() += delta;
                if inventory
                    .get(&id)
                    .is_some_and(|initial| consumed[&id] > *initial)
                {
                    return Err(io::Error::other("deployment exceeds initial inventory"));
                }
                let t = event.get("video_t").number().unwrap_or(-1.0);
                if t < a.get("video_t_start").number().unwrap_or(0.0)
                    || t > a.get("video_t_end").number().unwrap_or(0.0)
                {
                    return Err(io::Error::other("deployment outside attack"));
                }
            }
        }
        details.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
            dir.file_name().unwrap().to_string_lossy(),
            counts[0],
            counts[1],
            counts[2],
            counts[3],
            counts[4],
            counts[5],
            counts[6],
            counts[7]
        ));
    }
    fs::write(root.join("m2-artifact-summary.tsv"), details)?;
    let report=format!("{{\"video_directories\":{},\"attacks\":{attacks},\"slots\":{slots},\"named_slots\":{named},\"unknown_slots\":{},\"deployment_events\":{events},\"position_records\":{positions},\"edited_attacks\":{edited},\"sped_up_attacks\":{sped},\"usable_for_timing\":{timing},\"json_and_artifact_checks\":\"pass\"}}\n",dirs.len(),slots-named);
    fs::write(root.join("m2-validation.json"), &report)?;
    print!("{report}");
    Ok(())
}

pub fn labels(dir: &Path, kind: &str) -> io::Result<()> {
    let (target, truth, keys) = match kind {
        "hud" => ("spot-check.tsv", "m2-truth.tsv", vec!["sample"]),
        "icons" => ("icon-spot-check.tsv", "icon-truth.tsv", vec!["sample"]),
        "positions" => (
            "position-check.tsv",
            "position-truth.tsv",
            vec!["video_t", "slot"],
        ),
        _ => return Err(io::Error::other("unknown label table kind")),
    };
    let source = fs::read_to_string(dir.join(truth))?;
    let target_text = fs::read_to_string(dir.join(target))?;
    let mut source_lines = source.lines();
    let source_header: Vec<_> = source_lines
        .next()
        .ok_or_else(|| io::Error::other("empty truth table"))?
        .split('\t')
        .collect();
    let mut target_lines = target_text.lines();
    let header = target_lines
        .next()
        .ok_or_else(|| io::Error::other("empty target table"))?;
    let columns: Vec<_> = header.split('\t').collect();
    let indices = |names: &[&str]| -> io::Result<Vec<usize>> {
        keys.iter()
            .map(|key| {
                names
                    .iter()
                    .position(|name| name == key)
                    .ok_or_else(|| io::Error::other("truth table key missing"))
            })
            .collect()
    };
    let source_keys = indices(&source_header)?;
    let target_keys = indices(&columns)?;
    let mut truths = std::collections::BTreeMap::new();
    for line in source_lines {
        let values: Vec<_> = line.split('\t').collect();
        let key = source_keys
            .iter()
            .map(|i| values.get(*i).copied().unwrap_or(""))
            .collect::<Vec<_>>()
            .join("|");
        if truths.insert(key, values).is_some() {
            return Err(io::Error::other("duplicate truth key"));
        }
    }
    let mut output = header.to_string() + "\n";
    for line in target_lines {
        let mut values: Vec<_> = line.split('\t').map(str::to_string).collect();
        values.resize(columns.len(), String::new());
        let key = target_keys
            .iter()
            .map(|i| values[*i].as_str())
            .collect::<Vec<_>>()
            .join("|");
        if let Some(truth) = truths.get(&key) {
            for (i, name) in columns.iter().enumerate() {
                if keys.contains(name) {
                    continue;
                }
                if let Some(j) = source_header.iter().position(|column| column == name) {
                    if let Some(value) = truth.get(j) {
                        values[i] = value.to_string();
                    }
                }
            }
        }
        output.push_str(&(values.join("\t") + "\n"));
    }
    fs::write(dir.join(target), output)?;
    if kind == "hud" {
        return crate::audit::score(dir);
    }
    if kind == "positions" {
        return score_positions(dir);
    }
    let mut identifiable = 0;
    let mut unknown = 0;
    let mut errors = 0;
    let mut abstentions = 0;
    let mut correct = 0;
    for line in fs::read_to_string(dir.join(target))?.lines().skip(1) {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() < 5 || c[4].is_empty() {
            continue;
        }
        if c[4] == "unknown" {
            unknown += 1;
            continue;
        }
        identifiable += 1;
        if c[2] == "unknown" {
            abstentions += 1;
        }
        if c[2] == c[4] {
            correct += 1;
        } else {
            errors += 1;
        }
    }
    fs::write(dir.join("icon-accuracy.tsv"),format!("field\tidentifiable\tcorrect\terrors\tabstentions\tunidentifiable_crops\nslot_name\t{identifiable}\t{correct}\t{errors}\t{abstentions}\t{unknown}\n"))
}
