//! Supervised whole-label templates beneath the clock; absence is separate
//! from an unrecognized text label and never implies a particular battle mode.
use crate::identity::{object, rect_value, resized};
use crate::image::{Image, Mask, Rect};
use crate::json::Value;
use std::fs;
use std::io;
use std::path::Path;

fn mask(image: &Image, gold: bool) -> Mask {
    if !gold {
        return Mask::white(image, 170);
    }
    Mask {
        w: image.w,
        h: image.h,
        data: image
            .data
            .chunks_exact(3)
            .map(|p| {
                u8::from(
                    p[0] > 150
                        && p[1] > 65
                        && p[0] as f64 > p[1] as f64 * 1.12
                        && p[1] as f64 > p[2] as f64 * 1.3,
                )
            })
            .collect(),
    }
}

pub fn learn(source: &Path, label: &str, rect: Rect, templates: &Path) -> io::Result<()> {
    if !label
        .bytes()
        .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
    {
        return Err(io::Error::other(
            "label must contain letters, digits, underscores or hyphens",
        ));
    }
    let image = crate::identity::read_image(source)?;
    if rect.x + rect.w > image.w || rect.y + rect.h > image.h {
        return Err(io::Error::other("label crop outside source"));
    }
    let crop = image.crop(rect);
    fs::create_dir_all(templates.join("league"))?;
    for gold in [true, false] {
        if !gold && mask(&crop, true).data.iter().filter(|b| **b != 0).count() >= 20 {
            continue;
        }
        let Some((_, glyphs)) = mask(&crop, gold).trimmed() else {
            continue;
        };
        if glyphs.data.iter().filter(|b| **b != 0).count() < 20 {
            continue;
        }
        glyphs.save_text(&templates.join(format!(
            "league/{label}--{}.txt",
            if gold { "gold" } else { "white" }
        )))?;
    }
    Ok(())
}

pub struct Reader {
    templates: Vec<(String, bool, Mask)>,
}

impl Reader {
    pub fn load(root: &Path) -> io::Result<Self> {
        let mut templates = Vec::new();
        let dir = root.join("league");
        if dir.exists() {
            let mut paths = fs::read_dir(dir)?
                .map(|e| e.map(|e| e.path()))
                .collect::<io::Result<Vec<_>>>()?;
            paths.sort();
            for path in paths {
                if path.extension().is_none_or(|s| s != "txt") {
                    continue;
                }
                let stem = path.file_stem().unwrap().to_string_lossy();
                let Some((label, style)) = stem.split_once("--") else {
                    continue;
                };
                templates.push((
                    label.replace('_', " "),
                    style == "gold",
                    Mask::load_text(&path)?,
                ));
            }
        }
        Ok(Self { templates })
    }

    pub fn area(image: &Image, clock: Rect) -> Option<Rect> {
        let scale = clock.h as f64 / 25.0;
        let w = (240.0 * scale) as usize;
        let h = (42.0 * scale) as usize;
        let x = (clock.x + clock.w / 2).saturating_sub(w / 2);
        let y = clock.y + clock.h + (4.0 * scale) as usize;
        (x + w <= image.w && y + h <= image.h).then_some(Rect::new(x, y, w, h))
    }

    pub fn read(&self, image: &Image, clock: Rect) -> Value {
        let Some(area) = Self::area(image, clock) else {
            return object(&[
                ("label", Value::Null),
                ("confidence", Value::from(0.0)),
                ("status", Value::from("league_region_outside_frame")),
            ]);
        };
        let crop = image.crop(area);
        let masks = [mask(&crop, true), mask(&crop, false)];
        let mut scores = std::collections::BTreeMap::<String, f64>::new();
        for (label, gold, template) in &self.templates {
            let m = &masks[usize::from(!gold)];
            for step in 14..=28 {
                let candidate =
                    crate::probe::resize(template, clock.h as f64 / 25.0 * step as f64 / 20.0);
                if candidate.w >= m.w || candidate.h >= m.h {
                    continue;
                }
                let (r, score) = crate::probe::search(
                    m,
                    &candidate,
                    Rect::new(0, 0, m.w - candidate.w, m.h - candidate.h),
                );
                // Do not accept "Legend I" as a prefix of "Legend II".
                let continuation = (r.y..r.y + r.h)
                    .flat_map(|y| (r.x + r.w + 1..(r.x + r.w + 7).min(m.w)).map(move |x| (x, y)))
                    .filter(|(x, y)| m.data[y * m.w + x] != 0)
                    .count();
                if continuation > r.h / 2 {
                    continue;
                }
                scores
                    .entry(label.clone())
                    .and_modify(|s| *s = s.max(score))
                    .or_insert(score);
            }
        }
        let mut ranked: Vec<_> = scores.into_iter().collect();
        ranked.sort_by(|a, b| b.1.total_cmp(&a.1));
        let accepted = ranked
            .first()
            .filter(|(_, score)| *score >= 0.78)
            .filter(|(_, score)| ranked.get(1).is_none_or(|(_, s)| score - s >= 0.035));
        let textlike = masks.iter().any(|m| {
            let parts: Vec<_> = crate::identity::components(m)
                .into_iter()
                .filter(|(r, _)| r.h >= 7 && r.h <= clock.h && r.w <= clock.h)
                .collect();
            parts.iter().any(|(r, _)| {
                let baseline = r.y + r.h;
                parts
                    .iter()
                    .filter(|(p, _)| {
                        (p.y + p.h).abs_diff(baseline) <= 2
                            && (p.x + p.w / 2).abs_diff(crop.w / 2)
                                < (90.0 * clock.h as f64 / 25.0) as usize
                    })
                    .count()
                    >= 5
            })
        });
        object(&[("label", accepted.map(|(s, _)| Value::from(s.as_str())).unwrap_or(Value::Null)),
            ("confidence", Value::from(accepted.map(|(_, s)| *s).unwrap_or(if textlike { 0.0 } else { 0.8 }))),
            ("status", Value::from(if accepted.is_some() { "template_read" } else if textlike { "unrecognized_text_or_scenery" } else { "no_label_visible_in_sample" })),
            ("box", rect_value(area)), ("method", Value::from("supervised whole-label masks; similarity/absence scores are not calibrated probabilities"))])
    }
}

pub fn rectangle(value: &Value) -> Option<Rect> {
    let a = value.array();
    if a.len() != 4 {
        return None;
    }
    let mut n = [0; 4];
    for (i, v) in a.iter().enumerate() {
        let x = v.number()?;
        if x < 0.0 || x.fract() != 0.0 {
            return None;
        }
        n[i] = x as usize;
    }
    Some(Rect::new(n[0], n[1], n[2], n[3]))
}

pub fn aggregate(readings: &[Value]) -> Value {
    let labels: std::collections::BTreeSet<_> = readings
        .iter()
        .filter_map(|r| r.get("label").string())
        .collect();
    let absent = readings
        .iter()
        .filter(|r| r.get("status").string() == Some("no_label_visible_in_sample"))
        .count();
    let best = readings
        .iter()
        .filter(|r| r.get("label").string().is_some())
        .max_by(|a, b| {
            a.get("confidence")
                .number()
                .unwrap_or(0.0)
                .total_cmp(&b.get("confidence").number().unwrap_or(0.0))
        });
    let (label, confidence, status) = if labels.len() == 1 {
        (
            Value::from(*labels.first().unwrap()),
            best.unwrap().get("confidence").clone(),
            "template_read",
        )
    } else if labels.len() > 1 {
        (Value::Null, Value::from(0.0), "conflicting_labels")
    } else if absent >= 2 {
        (
            Value::Null,
            Value::from(0.8),
            "no_label_visible_in_sampled_hud",
        )
    } else {
        (
            Value::Null,
            Value::from(0.0),
            "unrecognized_or_insufficient_league_samples",
        )
    };
    object(&[("label", label), ("confidence", confidence), ("status", Value::from(status)),
        ("samples", Value::from(readings.len() as f64)), ("absence_samples", Value::from(absent as f64)),
        ("mode", Value::Null), ("mode_reason", Value::from("absence of a league label does not distinguish older ranked UI, war, friendly or unranked modes"))])
}

pub fn audit(root: &Path) -> io::Result<()> {
    let mut entries = Vec::new();
    let mut table = String::from("sample\tvideo\tkeyframe\tbox\n");
    for dir in crate::icons::directories(root)? {
        let regions = Value::parse(&fs::read_to_string(dir.join("regions.json"))?)?;
        let Some(clock) = rectangle(regions.get("clock")) else {
            continue;
        };
        let Some(path) = crate::icons::attack_paths(&dir)?.first().cloned() else {
            continue;
        };
        let a = Value::parse(&fs::read_to_string(path)?)?;
        let Some(key) = a.get("keyframe").get("path").string() else {
            continue;
        };
        let image = crate::video::frame(&dir.join(key), 0.0)?;
        let Some(area) = Reader::area(&image, clock) else {
            continue;
        };
        table.push_str(&format!(
            "{}\t{}\t{key}\t{}\n",
            entries.len(),
            dir.file_name().unwrap().to_string_lossy(),
            area.json()
        ));
        entries.push(image.crop(area));
    }
    let mut sheet = Image::blank(1200, entries.len().div_ceil(4).max(1) * 100);
    for (i, crop) in entries.iter().enumerate() {
        sheet.paste(&resized(crop, 290, 90), i % 4 * 300, i / 4 * 100, 1);
    }
    fs::create_dir_all("/tmp/vidmine-work/m3")?;
    sheet.save(Path::new("/tmp/vidmine-work/m3/league-audit.ppm"))?;
    fs::write("/tmp/vidmine-work/m3/league-audit.tsv", table)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn absent_unknown_and_conflicting_labels_remain_distinct() {
        // Declared synthetic league observations, not video calibration.
        let absent = object(&[
            ("label", Value::Null),
            ("status", Value::from("no_label_visible_in_sample")),
        ]);
        let unknown = object(&[
            ("label", Value::Null),
            ("status", Value::from("unrecognized_text_or_scenery")),
        ]);
        assert_eq!(
            aggregate(&[unknown.clone(), unknown])
                .get("confidence")
                .number(),
            Some(0.0)
        );
        assert_eq!(
            aggregate(&[absent.clone(), absent]).get("status").string(),
            Some("no_label_visible_in_sampled_hud")
        );
        let labels = ["Legend I", "Legend II"]
            .map(|s| object(&[("label", Value::from(s)), ("confidence", Value::from(0.99))]));
        assert_eq!(
            aggregate(&labels).get("status").string(),
            Some("conflicting_labels")
        );
        assert_eq!(aggregate(&labels).get("label"), &Value::Null);
    }
}
