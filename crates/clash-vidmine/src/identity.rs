//! Offline army-level evidence and conservative attacker/defender attribution.
use crate::icons;
use crate::image::{Image, Mask, Rect};
use crate::json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::io::{self, BufReader};
use std::path::Path;

fn number(value: Option<u32>) -> Value {
    value.map(|v| Value::from(v as f64)).unwrap_or(Value::Null)
}

pub(crate) fn rect_value(rect: Rect) -> Value {
    Value::Array(
        [rect.x, rect.y, rect.w, rect.h]
            .map(|v| Value::from(v as f64))
            .to_vec(),
    )
}

#[derive(Clone)]
struct Unit {
    family: String,
    levels: BTreeMap<u32, u32>,
    seasonal: bool,
    siege: bool,
    unlock: u32,
}

struct Catalog {
    units: BTreeMap<String, Unit>,
    max_th: u32,
    fingerprint: String,
}

impl Catalog {
    fn load() -> io::Result<Self> {
        let text = fs::read_to_string(data_path())?;
        let data = Value::parse(&text)?;
        let buildings: BTreeMap<_, _> = data
            .get("buildings")
            .array()
            .iter()
            .filter(|b| b.get("village").string() == Some("home"))
            .filter_map(|b| b.get("name").string().map(|name| (name, b)))
            .collect();
        let max_th = buildings
            .get("Town Hall")
            .map(|b| b.get("levels").array().len() as u32)
            .filter(|v| *v >= 16)
            .ok_or_else(|| io::Error::other("missing home Town Hall levels"))?;
        let building_th = |name: &str, level: u32| -> Option<u32> {
            if level == 0 {
                return Some(1);
            }
            buildings
                .get(name)?
                .get("levels")
                .array()
                .iter()
                .find(|l| l.get("level").number() == Some(level as f64))?
                .get("required_townhall")
                .number()
                .map(|n| n as u32)
        };
        let mut units = BTreeMap::new();
        for family in ["troops", "spells", "heroes", "pets"] {
            for u in data.get(family).array() {
                if u.get("village").string().is_some_and(|v| v != "home") {
                    continue;
                }
                let Some(name) = u.get("name").string() else {
                    continue;
                };
                let production = u.get("production_building").string().unwrap_or("");
                let seasonal = u.get("is_seasonal") == &Value::Bool(true);
                let unlock = building_th(
                    production,
                    u.get("production_building_level").number().unwrap_or(0.0) as u32,
                );
                let mut levels = BTreeMap::new();
                for l in u.get("levels").array() {
                    let Some(level) = l.get("level").number() else {
                        continue;
                    };
                    let Some(th) = l.get("required_townhall").number() else {
                        continue;
                    };
                    // Level one needs the production building, not a laboratory
                    // capable of researching its first upgrade. The source
                    // often repeats the laboratory's TH3 gate on that row.
                    let unresearched = level == 1.0
                        && !seasonal
                        && ["troops", "spells"].contains(&family)
                        && unlock.is_some();
                    let mut required = if unresearched {
                        unlock.unwrap()
                    } else {
                        (th as u32).max(unlock.unwrap_or(1))
                    };
                    for (key, building) in [
                        ("required_lab_level", "Laboratory"),
                        ("required_hero_tavern_level", "Hero Hall"),
                        ("required_pet_house_level", "Pet House"),
                    ] {
                        if unresearched && key == "required_lab_level" {
                            continue;
                        }
                        if let Some(cap) = l.get(key).number() {
                            let Some(cap_th) = building_th(building, cap as u32) else {
                                continue;
                            };
                            required = required.max(cap_th);
                        }
                    }
                    levels.insert(level as u32, required);
                }
                let unit = Unit {
                    family: family.into(),
                    levels,
                    seasonal,
                    siege: production == "Workshop",
                    unlock: unlock.unwrap_or(1),
                };
                // Prefer the permanent record when an event unit reuses a name.
                if !units.contains_key(name) || !seasonal {
                    units.insert(name.into(), unit);
                }
            }
        }
        let super_text = fs::read_to_string(Path::new(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../data/source/catalog.json"
        )))?;
        let supplement = Value::parse(&super_text)?;
        let parents: BTreeMap<_, _> = supplement
            .get("entries")
            .array()
            .iter()
            .map(|e| e.get("entity"))
            .filter(|e| e.get("base").string() == Some("home"))
            .filter_map(|e| Some((e.get("id").string()?, e.get("name").string()?)))
            .collect();
        for entry in supplement.get("entries").array() {
            let entity = entry.get("entity");
            let (Some(name), Some(parent), Some(required)) = (
                entity.get("name").string(),
                entity.get("parentTroop").string(),
                entity.get("regularLevelRequired").number(),
            ) else {
                continue;
            };
            let minimum = parents
                .get(parent)
                .and_then(|name| units.get(*name))
                .and_then(|parent| parent.levels.get(&(required as u32)))
                .copied();
            if let (Some(minimum), Some(unit)) = (minimum, units.get_mut(name)) {
                unit.unlock = unit.unlock.max(minimum);
                for cap in unit.levels.values_mut() {
                    *cap = (*cap).max(unit.unlock);
                }
            }
        }
        let super_hash = super_text.bytes().fold(0xcbf29ce484222325_u64, |h, b| {
            (h ^ b as u64).wrapping_mul(0x100000001b3)
        });
        let hash = text.bytes().fold(0xcbf29ce484222325_u64, |h, b| {
            (h ^ b as u64).wrapping_mul(0x100000001b3)
        });
        Ok(Self {
            units,
            max_th,
            fingerprint: format!("fnv1a64:{hash:016x};super-unlocks:{super_hash:016x}"),
        })
    }

    fn find(&self, name: &str) -> Option<&Unit> {
        let canonical = match name {
            "PEKKA" => "P.E.K.K.A",
            "Heal" | "Heal Spell" => "Healing Spell",
            "Rage" => "Rage Spell",
            "Freeze" => "Freeze Spell",
            "Poison" => "Poison Spell",
            "Invisibility" => "Invisibility Spell",
            "Skeleton" => "Skeleton Spell",
            "Earthquake" => "Earthquake Spell",
            "Haste" => "Haste Spell",
            "Jump" => "Jump Spell",
            "Clone" => "Clone Spell",
            "Recall" => "Recall Spell",
            "Revive" => "Revive Spell",
            "Overgrowth" => "Overgrowth Spell",
            "Lightning" => "Lightning Spell",
            "Bat" => "Bat Spell",
            _ => name,
        };
        self.units.get(canonical)
    }
}

/// Connected foreground components keep portrait fragments out of the badge's
/// glyph run. All tests and acceptance thresholds are independent of unit caps.
pub(crate) fn components(mask: &Mask) -> Vec<(Rect, Mask)> {
    let mut visited = vec![false; mask.data.len()];
    let mut result = Vec::new();
    for start in 0..mask.data.len() {
        if visited[start] || mask.data[start] == 0 {
            continue;
        }
        let mut stack = vec![start];
        visited[start] = true;
        let mut pixels = Vec::new();
        let (mut x0, mut y0, mut x1, mut y1) = (mask.w, mask.h, 0, 0);
        while let Some(i) = stack.pop() {
            let (x, y) = (i % mask.w, i / mask.w);
            pixels.push(i);
            x0 = x0.min(x);
            y0 = y0.min(y);
            x1 = x1.max(x + 1);
            y1 = y1.max(y + 1);
            for dy in -1_isize..=1 {
                for dx in -1_isize..=1 {
                    let (nx, ny) = (x as isize + dx, y as isize + dy);
                    if nx < 0 || ny < 0 || nx >= mask.w as isize || ny >= mask.h as isize {
                        continue;
                    }
                    let j = ny as usize * mask.w + nx as usize;
                    if !visited[j] && mask.data[j] != 0 {
                        visited[j] = true;
                        stack.push(j);
                    }
                }
            }
        }
        let rect = Rect::new(x0, y0, x1 - x0, y1 - y0);
        let mut glyph = Mask {
            w: rect.w,
            h: rect.h,
            data: vec![0; rect.w * rect.h],
        };
        for p in pixels {
            glyph.data[(p / mask.w - y0) * rect.w + p % mask.w - x0] = 1;
        }
        result.push((rect, glyph));
    }
    result
}

pub struct Levels {
    templates: Vec<(char, Mask)>,
}

impl Levels {
    pub(crate) fn load(root: &Path) -> io::Result<Self> {
        let mut templates = Vec::new();
        let mut paths = fs::read_dir(root)?
            .map(|e| e.map(|e| e.path()))
            .collect::<io::Result<Vec<_>>>()?;
        paths.sort();
        for path in paths {
            let stem = path.file_stem().unwrap_or_default().to_string_lossy();
            let c: Vec<_> = stem.split('-').collect();
            if c.len() >= 3 && c[0] == "level" && c[1].len() == 1 {
                let digit = c[1].chars().next().unwrap();
                if digit.is_ascii_digit() {
                    templates.push((digit, Mask::load_text(&path)?));
                }
            }
        }
        Ok(Self { templates })
    }

    fn digit(&self, glyph: &Mask) -> Option<(char, f64)> {
        // A card outline is often a perfect match to a normalized narrow "1".
        // Preserve the source aspect check instead of trusting that template.
        if glyph.w as f64 / (glyph.h as f64) < 0.18 {
            return None;
        }
        let normalized = glyph.normalized();
        let mut scores = [1.0_f64; 10];
        for (digit, template) in &self.templates {
            let d = digit.to_digit(10).unwrap() as usize;
            scores[d] = scores[d].min(template.distance(&normalized));
        }
        let mut ordered: Vec<_> = scores.into_iter().enumerate().collect();
        ordered.sort_by(|a, b| a.1.total_cmp(&b.1));
        let (digit, distance) = ordered[0];
        let margin = ordered[1].1 - distance;
        (distance <= 0.20 && margin >= 0.018).then(|| {
            (
                char::from_digit(digit as u32, 10).unwrap(),
                1.0 - 2.0 * distance,
            )
        })
    }

    fn sequence(&self, glyph: &Mask) -> Option<(String, f64)> {
        if glyph.w as f64 / (glyph.h as f64) < 0.95 {
            return self.digit(glyph).map(|(c, score)| (c.to_string(), score));
        }
        fn split(
            reader: &Levels,
            glyph: &Mask,
            start: usize,
            remaining: usize,
            raw: String,
            confidence: f64,
            out: &mut BTreeMap<String, f64>,
        ) {
            if remaining == 0 {
                if start == glyph.w {
                    out.entry(raw)
                        .and_modify(|c| *c = c.max(confidence))
                        .or_insert(confidence);
                }
                return;
            }
            let min_width = (glyph.h as f64 * 0.18).ceil() as usize;
            let max_width = (glyph.h as f64 * 0.95).ceil() as usize;
            for width in min_width..=max_width.min(glyph.w - start) {
                let end = start + width;
                if glyph.w - end < (remaining - 1) * min_width {
                    continue;
                }
                let Some((_, part)) = glyph.crop(Rect::new(start, 0, width, glyph.h)).trimmed()
                else {
                    continue;
                };
                let Some((digit, score)) = reader.digit(&part) else {
                    continue;
                };
                let mut next = raw.clone();
                next.push(digit);
                split(
                    reader,
                    glyph,
                    end,
                    remaining - 1,
                    next,
                    confidence.min(score),
                    out,
                );
            }
        }
        let mut candidates = BTreeMap::new();
        for digits in 2..=3 {
            split(self, glyph, 0, digits, String::new(), 1.0, &mut candidates);
        }
        let mut ranked: Vec<_> = candidates.into_iter().collect();
        ranked.sort_by(|a, b| b.1.total_cmp(&a.1));
        let best = ranked.first()?;
        if ranked.get(1).is_some_and(|other| best.1 - other.1 < 0.035) {
            return None;
        }
        Some(best.clone())
    }

    pub(crate) fn read(&self, image: &Image) -> Value {
        let scale = image.w as f64 / 61.0;
        let area = Rect::new(
            0,
            image.h * 60 / 100,
            image.w * 55 / 100,
            image.h - image.h * 60 / 100,
        );
        let crop = image.crop(area);
        let mut candidates = BTreeMap::<u32, (f64, String, Rect)>::new();
        let mut votes = BTreeMap::<u32, std::collections::BTreeSet<u8>>::new();
        for threshold in [150, 180, 210] {
            let mask = Mask::white(&crop, threshold);
            let mut parts: Vec<_> = components(&mask)
                .into_iter()
                .filter(|(r, _)| {
                    r.h >= (7.0 * scale).max(5.0) as usize
                        && r.h <= (17.0 * scale).ceil() as usize
                        && r.w <= (14.0 * scale).ceil() as usize
                        && r.x >= 2
                        && r.y + r.h + 1 < crop.h
                })
                .collect();
            parts.sort_by_key(|(r, _)| r.x);
            for (i, (first, _)) in parts.iter().enumerate() {
                if first.x > image.w * 28 / 100 || first.y + area.y < image.h * 67 / 100 {
                    continue;
                }
                // A complete dark outline must surround the first glyph. This
                // rejects digits cut by the left/bottom edge of legacy crops.
                let dark = (first.y..first.y + first.h)
                    .filter(|y| {
                        crop.pixel(first.x - 1, *y)
                            .iter()
                            .map(|v| *v as u32)
                            .sum::<u32>()
                            / 3
                            < threshold.min(150) as u32
                    })
                    .count();
                if dark * 4 < first.h * 3 {
                    continue;
                }
                let mut group = Vec::new();
                let mut right = first.x;
                for (r, glyph) in &parts[i..] {
                    if r.x.saturating_sub(right) > (5.0 * scale).ceil() as usize {
                        break;
                    }
                    if (r.y + r.h).abs_diff(first.y + first.h) > (2.0 * scale).ceil() as usize
                        || r.h.abs_diff(first.h) > (3.0 * scale).ceil() as usize
                    {
                        continue;
                    }
                    group.push((*r, glyph));
                    right = r.x + r.w;
                }
                if group.is_empty() || group.len() > 3 {
                    continue;
                }
                // A failed component must not turn a printed "12" into "1".
                let tail_right = (right + (7.0 * scale).ceil() as usize).min(mask.w);
                let tail_ink = (first.y..first.y + first.h)
                    .flat_map(|y| (right + 1..tail_right).map(move |x| (x, y)))
                    .filter(|(x, y)| mask.data[y * mask.w + x] != 0)
                    .count();
                if tail_ink >= first.h {
                    continue;
                }
                let mut raw = String::new();
                let mut confidence = 1.0_f64;
                for (_, glyph) in &group {
                    let Some((digits, score)) = self.sequence(glyph) else {
                        raw.clear();
                        break;
                    };
                    raw.push_str(&digits);
                    confidence = confidence.min(score);
                }
                let Some(value) = raw
                    .parse::<u32>()
                    .ok()
                    .filter(|v| (1..=999).contains(v) && !raw.starts_with('0'))
                else {
                    continue;
                };
                let rect = Rect::new(first.x, first.y + area.y, right - first.x, first.h);
                votes.entry(value).or_default().insert(threshold);
                candidates
                    .entry(value)
                    .and_modify(|v| {
                        if confidence > v.0 {
                            *v = (confidence, raw.clone(), rect);
                        }
                    })
                    .or_insert((confidence, raw, rect));
            }
        }
        let mut candidates: Vec<_> = candidates.into_iter().collect();
        let all = candidates.clone();
        candidates.retain(|(_, (_, raw, rect))| {
            !all.iter().any(|(_, (_, other, larger))| {
                other.len() > raw.len()
                    && larger.x <= rect.x + 1
                    && larger.x + larger.w + 1 >= rect.x + rect.w
                    && (larger.y + larger.h).abs_diff(rect.y + rect.h) <= 3
            })
        });
        candidates.sort_by(|a, b| {
            votes[&b.0]
                .len()
                .cmp(&votes[&a.0].len())
                .then_with(|| b.1 .0.total_cmp(&a.1 .0))
        });
        let best = candidates.first();
        let accepted = best
            .filter(|(_, (c, _, _))| *c >= 0.62)
            .filter(|(value, (c, _, _))| {
                !candidates.iter().skip(1).any(|(v, (s, _, _))| {
                    v != value && votes[v].len() >= votes[value].len() && c - s < 0.06
                })
            });
        object(&[
            ("value", number(accepted.map(|(v, _)| *v))),
            (
                "confidence",
                Value::from(accepted.map(|(_, (c, _, _))| *c).unwrap_or(0.0)),
            ),
            (
                "raw",
                Value::from(best.map(|(_, (_, raw, _))| raw.as_str()).unwrap_or("")),
            ),
            (
                "box",
                accepted
                    .map(|(_, (_, _, r))| rect_value(*r))
                    .unwrap_or(Value::Null),
            ),
            (
                "status",
                Value::from(if accepted.is_some() {
                    "read"
                } else {
                    "badge_missing_clipped_dim_or_ambiguous"
                }),
            ),
            (
                "method",
                Value::from("m3 supervised level glyphs; no unit-cap correction"),
            ),
        ])
    }
}

fn donated_marker(image: &Image) -> bool {
    let mut red = 0;
    let mut white = 0;
    for y in image.h / 25..image.h / 5 {
        for x in image.w / 25..image.w / 3 {
            let p = image.pixel(x, y);
            red += usize::from(
                p[0] > 140 && p[0] > p[1].saturating_add(45) && p[0] > p[2].saturating_add(35),
            );
            white += usize::from(*p.iter().min().unwrap() > 180);
        }
    }
    red >= image.w * image.h / 800 && white >= image.w * image.h / 1000
}

fn infer(cards: &[Value], catalog: &Catalog) -> Value {
    let mut evidence = Vec::new();
    let mut consistent: Vec<u32> = (1..=catalog.max_th).collect();
    let mut constraints = 0;
    let mut missing = 0;
    let mut inconsistent = false;
    let mut distinct = std::collections::BTreeSet::new();
    for card in cards {
        let name = card.get("name").string();
        let level = card.get("level").get("value").number().map(|n| n as u32);
        let unit = name
            .filter(|_| card.get("name_confidence").number().unwrap_or(1.0) >= 0.70)
            .and_then(|n| catalog.find(n));
        let mut required = None;
        let status = match (unit, level) {
            (None, _) => {
                missing += 1;
                "unknown_unit_or_catalog_entry"
            }
            (Some(u), _) if u.siege => "siege_may_be_donated_own_workshop_cap_not_applicable",
            (Some(_), _) if card.get("donated") == &Value::Bool(true) => {
                "donated_card_own_upgrade_cap_not_applicable"
            }
            (Some(u), Some(l)) => {
                required = u.levels.get(&l).copied();
                if let Some(minimum) = required {
                    consistent.retain(|th| *th >= minimum);
                    constraints += 1;
                    if let Some(name) = name {
                        distinct.insert(name);
                    }
                    "level_and_unlock_constraint"
                } else {
                    // An accepted glyph outside the table is a contradiction,
                    // never silently clipped to the highest catalog level.
                    consistent.clear();
                    inconsistent = true;
                    "observed_level_not_in_catalog"
                }
            }
            (Some(u), None) => {
                missing += 1;
                required = Some(u.unlock);
                consistent.retain(|th| *th >= u.unlock);
                constraints += 1;
                "availability_only_level_badge_unavailable"
            }
        };
        evidence.push(object(&[
            ("slot", card.get("slot").clone()),
            ("icon", card.get("icon").clone()),
            ("name", card.get("name").clone()),
            ("level", number(level)),
            ("raw_level", card.get("level").get("raw").clone()),
            ("level_status", card.get("level").get("status").clone()),
            (
                "level_confidence",
                card.get("level").get("confidence").clone(),
            ),
            ("name_confidence", card.get("name_confidence").clone()),
            ("video_t", card.get("video_t").clone()),
            ("donated", card.get("donated").clone()),
            ("required_th", number(required)),
            ("status", Value::from(status)),
            (
                "family",
                unit.map(|u| Value::from(u.family.as_str()))
                    .unwrap_or(Value::Null),
            ),
            ("seasonal", Value::from(unit.is_some_and(|u| u.seasonal))),
        ]));
    }
    let minimum = consistent.first().copied().filter(|_| constraints > 0);
    let maximum = consistent.last().copied().filter(|_| constraints > 0);
    let status = if minimum.is_some() {
        if missing == 0 {
            "observed_constraints_only"
        } else {
            "partial_observed_constraints"
        }
    } else if inconsistent || constraints > 0 {
        "inconsistent_observations"
    } else {
        "insufficient_observations"
    };
    let levels = if constraints > 0 {
        consistent
            .into_iter()
            .map(|n| Value::from(n as f64))
            .collect()
    } else {
        Vec::new()
    };
    object(&[
        ("min", number(minimum)),
        ("max", number(maximum)),
        ("best", number(minimum.filter(|_| distinct.len() >= 3))),
        ("consistent", Value::Array(levels)),
        ("best_method", Value::from("smallest consistent TH with at least three readable constraints; underleveling allows higher TH; not an exact identity")),
        ("status", Value::from(status)),
        ("missing_cards", Value::from(missing as f64)),
        ("catalog", Value::from("data/source/clashking-static-data.json: TH/lab/production/hero/pet caps; data/source/catalog.json: super parent-level unlocks")),
        ("catalog_fingerprint", Value::from(catalog.fingerprint.as_str())),
        ("catalog_max_th", Value::from(catalog.max_th as f64)),
        ("evidence", Value::Array(evidence)),
    ])
}

fn reconcile_levels(attack: &mut Value) {
    let mut observations = BTreeMap::<(String, bool), std::collections::BTreeSet<u32>>::new();
    for family in ["slots", "army_cards"] {
        for card in attack.get(family).array() {
            if let (Some(name), Some(level)) = (
                card.get("name").string(),
                card.get("level").get("value").number(),
            ) {
                if card.get("name_confidence").number().unwrap_or(0.0) < 0.70 {
                    continue;
                }
                observations
                    .entry((name.to_string(), card.get("donated") == &Value::Bool(true)))
                    .or_default()
                    .insert(level as u32);
            }
        }
    }
    for family in ["slots", "army_cards"] {
        if let Some(cards) = attack.object_array_mut(family) {
            for card in cards {
                let Some(name) = card.get("name").string() else {
                    continue;
                };
                let key = (name.to_string(), card.get("donated") == &Value::Bool(true));
                if !observations.get(&key).is_some_and(|v| v.len() > 1) {
                    continue;
                }
                if card.get("level").get("value").number().is_none() {
                    continue;
                }
                let mut reading = card.get("level").clone();
                reading.set("observed_value", reading.get("value").clone());
                reading.set("observed_confidence", reading.get("confidence").clone());
                reading.set("value", Value::Null);
                reading.set("confidence", Value::from(0.0));
                reading.set(
                    "status",
                    Value::from("conflicting_levels_for_same_unit_and_donation_role"),
                );
                card.set("level", reading);
            }
        }
    }
}

pub fn update(root: &Path, templates: &Path) -> io::Result<()> {
    let catalog = Catalog::load()?;
    let levels = Levels::load(templates)?;
    let league = crate::league::Reader::load(templates)?;
    let library = icons::Library::load(templates)?;
    let mut table = String::from(
        "video\tattack\tslot\ticon\tname\tlevel\tconfidence\tstatus\traw\tobserved_value\n",
    );
    for dir in icons::directories(root)? {
        let regions = Value::parse(&fs::read_to_string(dir.join("regions.json"))?)?;
        let clock = crate::league::rectangle(regions.get("clock"));
        for path in icons::attack_paths(&dir)? {
            let mut attack = Value::parse(&fs::read_to_string(&path)?)?;
            let id = attack.get("attack").encode();
            if let Some(slots) = attack.object_array_mut("slots") {
                for slot in slots {
                    let Some(icon) = slot.get("icon").string().map(str::to_string) else {
                        continue;
                    };
                    let image = read_image(&dir.join(&icon))?;
                    let reading = levels.read(&image);
                    slot.set("level", reading.clone());
                    slot.set(
                        "donated",
                        Value::from(
                            !slot.get("name").string().is_some_and(|n| {
                                catalog.find(n).is_some_and(|u| u.family == "heroes")
                            }) && donated_marker(&image),
                        ),
                    );
                }
            }
            if let Some(cards) = attack.object_array_mut("army_cards") {
                for card in cards {
                    let Some(icon) = card.get("icon").string() else {
                        continue;
                    };
                    let image = read_image(&dir.join(icon))?;
                    let (name, confidence) = library.identify_card(&image);
                    card.set(
                        "name",
                        name.as_deref().map(Value::from).unwrap_or(Value::Null),
                    );
                    card.set("name_confidence", Value::from(confidence));
                    card.set("level", levels.read(&image));
                    let hero = name
                        .as_deref()
                        .and_then(|n| catalog.find(n))
                        .is_some_and(|u| u.family == "heroes");
                    card.set("donated", Value::from(!hero && donated_marker(&image)));
                    let reading = card.get("level").clone();
                    let count = card.get("level_observation_times").array().len();
                    let unchanged = card.get("level_observation_value") == reading.get("value");
                    if reading.get("value").number().is_some() && (count < 2 || !unchanged) {
                        let mut unconfirmed = reading;
                        unconfirmed.set("observed_value", unconfirmed.get("value").clone());
                        unconfirmed
                            .set("observed_confidence", unconfirmed.get("confidence").clone());
                        unconfirmed.set("value", Value::Null);
                        unconfirmed.set("confidence", Value::from(0.0));
                        unconfirmed.set(
                            "status",
                            Value::from("level_requires_two_independent_sample_times_for_th"),
                        );
                        card.set("level", unconfirmed);
                    }
                }
            }
            reconcile_levels(&mut attack);
            for slot in attack.get("slots").array() {
                let reading = slot.get("level");
                table.push_str(&format!(
                    "{}\t{id}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
                    dir.file_name().unwrap().to_string_lossy(),
                    slot.get("slot").encode(),
                    slot.get("icon").string().unwrap_or(""),
                    slot.get("name").string().unwrap_or("unknown"),
                    reading.get("value").encode(),
                    reading.get("confidence").encode(),
                    reading.get("status").string().unwrap_or(""),
                    reading.get("raw").string().unwrap_or(""),
                    reading.get("observed_value").encode()
                ));
            }
            let cards: Vec<_> = attack
                .get("slots")
                .array()
                .iter()
                .chain(attack.get("army_cards").array())
                .cloned()
                .collect();
            attack.set("attacker_th", infer(&cards, &catalog));
            if attack.get("league_observations").array().is_empty() {
                let reading = if regions.get("layout").string() != Some("cropped_replay") {
                    if let (Some(clock), Some(key)) =
                        (clock, attack.get("keyframe").get("path").string())
                    {
                        league.read(&crate::video::frame(&dir.join(key), 0.0)?, clock)
                    } else {
                        object(&[
                            ("label", Value::Null),
                            ("confidence", Value::from(0.0)),
                            ("status", Value::from("no_sampled_league_region")),
                        ])
                    }
                } else {
                    object(&[
                        ("label", Value::Null),
                        ("confidence", Value::from(0.0)),
                        ("status", Value::from("cropped_replay_league_unavailable")),
                    ])
                };
                attack.set("league", reading);
            }
            attack.set("defender_th", Value::Null);
            attack.set("defender_th_reason", Value::from("keyframe grid has no reviewed tile scale/origin; no independently labeled scale-normalized TH sprite library; apparent TH not inferred from video title"));
            attack.set("schema_version", Value::from(3.0));
            attack.set("army_icon_library_version", Value::from("m3-v1"));
            fs::write(path, attack.encode() + "\n")?;
        }
    }
    fs::write(root.join("levels.tsv"), table)
}

fn frame_cards(image: &Image, levels: &Levels) -> Vec<(Rect, Value)> {
    let top = image.h * 65 / 100;
    let area = Rect::new(0, top, image.w, image.h - top);
    let mask = Mask::white(&image.crop(area), 150);
    let scale = image.w as f64 / 1280.0;
    let mut parts: Vec<_> = components(&mask)
        .into_iter()
        .filter(|(r, _)| {
            r.h >= (8.0 * scale).max(5.0) as usize
                && r.h <= (18.0 * scale).ceil() as usize
                && r.w <= (15.0 * scale).ceil() as usize
                && r.x > 3
                && r.y > 1
                && r.y + r.h + 2 < area.h
        })
        .collect();
    parts.sort_by_key(|(r, _)| r.x);
    let mut groups = Vec::new();
    for (i, (first, _)) in parts.iter().enumerate() {
        if parts[..i].iter().any(|(r, _)| {
            (r.y + r.h).abs_diff(first.y + first.h) <= 2
                && first.x.saturating_sub(r.x + r.w) <= (4.0 * scale).ceil() as usize
        }) {
            continue;
        }
        let mut group = Vec::new();
        let mut right = first.x;
        for (r, glyph) in &parts[i..] {
            if r.x.saturating_sub(right) > (4.0 * scale).ceil() as usize {
                break;
            }
            if (r.y + r.h).abs_diff(first.y + first.h) > 2 || r.h.abs_diff(first.h) > 3 {
                continue;
            }
            group.push((*r, glyph));
            right = r.x + r.w;
        }
        if group.is_empty() || group.len() > 3 {
            continue;
        }
        let mut raw = String::new();
        let mut confidence = 1.0_f64;
        for (_, glyph) in &group {
            let Some((digit, score)) = levels.digit(glyph) else {
                raw.clear();
                break;
            };
            raw.push(digit);
            confidence = confidence.min(score);
        }
        let Some(value) = raw
            .parse::<u32>()
            .ok()
            .filter(|v| (1..=999).contains(v) && !raw.starts_with('0'))
        else {
            continue;
        };
        let edge_dark = |x| {
            (first.y..first.y + first.h)
                .filter(|y| {
                    let p = image.pixel(x, y + top);
                    p.iter().map(|v| *v as u32).sum::<u32>() / 3 < 140
                })
                .count()
        };
        if edge_dark(first.x - 1) * 4 < first.h * 3 || edge_dark(right) * 4 < first.h * 3 {
            continue;
        }
        groups.push((
            Rect::new(first.x, first.y + top, right - first.x, first.h),
            value,
            confidence,
            raw,
        ));
    }
    // All normal/selected troop and hero badges share the bottom baseline.
    let baseline = groups.iter().map(|(r, _, _, _)| r.y + r.h).max_by_key(|y| {
        groups
            .iter()
            .filter(|(r, _, _, _)| (r.y + r.h).abs_diff(*y) <= 3)
            .count()
    });
    let Some(baseline) = baseline else {
        return vec![];
    };
    groups.retain(|(r, _, _, _)| (r.y + r.h).abs_diff(baseline) <= 3);
    if groups.len() < 5 {
        return vec![];
    }
    groups.sort_by_key(|(r, _, _, _)| r.x);
    let mut pitches: Vec<_> = groups
        .windows(2)
        .map(|p| p[1].0.x - p[0].0.x)
        .filter(|d| *d >= (50.0 * scale) as usize && *d <= (105.0 * scale) as usize)
        .collect();
    pitches.sort();
    let Some(pitch) = pitches.get(pitches.len() / 2).copied() else {
        return vec![];
    };
    let width = pitch.saturating_sub((5.0 * scale).round() as usize);
    let height = width * 5 / 4;
    let mut result: Vec<_> = groups
        .iter()
        .filter_map(|(badge, value, confidence, raw)| {
            let left = badge.x.checked_sub(pitch / 9)?;
            let bottom = badge.y + badge.h + pitch / 10;
            let rect = Rect::new(left, bottom.checked_sub(height)?, width, height);
            if rect.x + rect.w > image.w || bottom > image.h {
                return None;
            }
            if *confidence < 0.70 {
                return None;
            }
            Some((
                rect,
                object(&[
                    ("value", number(Some(*value))),
                    ("confidence", Value::from(*confidence)),
                    ("raw", Value::from(raw.as_str())),
                    (
                        "box",
                        rect_value(Rect::new(
                            badge.x - left,
                            badge.y - rect.y,
                            badge.w,
                            badge.h,
                        )),
                    ),
                    ("status", Value::from("read")),
                    (
                        "method",
                        Value::from("m3 level glyphs at shared card baseline"),
                    ),
                ]),
            ))
        })
        .collect();
    for pair in groups.windows(2) {
        let gap = pair[1].0.x - pair[0].0.x;
        if gap < pitch * 3 / 2 || gap > pitch * 7 / 2 {
            continue;
        }
        let count = (gap as f64 / pitch as f64).round() as usize;
        for n in 1..count {
            let left = (pair[0].0.x + gap * n / count).saturating_sub(pitch / 9);
            let bottom = baseline + pitch / 10;
            if left + width > image.w || bottom < height {
                continue;
            }
            let rect = Rect::new(left, bottom - height, width, height);
            let reading = levels.read(&image.crop(rect));
            result.push((rect, reading));
        }
    }
    result.sort_by_key(|(r, _)| r.x);
    result
}

pub fn video(video: &Path, out: &Path, templates: &Path) -> io::Result<()> {
    let levels = Levels::load(templates)?;
    let library = icons::Library::load(templates)?;
    let league = crate::league::Reader::load(templates)?;
    let regions = Value::parse(&fs::read_to_string(out.join("regions.json"))?)?;
    let clock = crate::league::rectangle(regions.get("clock"));
    fs::create_dir_all(out.join("army"))?;
    for path in icons::attack_paths(out)? {
        let mut a = Value::parse(&fs::read_to_string(&path)?)?;
        let start = a.get("video_t_start").number().unwrap_or(0.0);
        let end = a.get("video_t_end").number().unwrap_or(start);
        let key = a.get("keyframe").get("video_t").number().unwrap_or(start);
        let mut times = vec![
            key + 0.4,
            start + 2.0,
            start + 8.0,
            start + 25.0,
            start + (end - start) * 0.55,
            end - 5.0,
        ];
        times.retain(|t| *t >= 0.0 && *t <= end);
        times.sort_by(f64::total_cmp);
        times.dedup_by(|a, b| (*a - *b).abs() < 0.5);
        let id = a.get("attack").number().unwrap_or(0.0) as usize;
        let mut cards: BTreeMap<String, (Value, Image)> = BTreeMap::new();
        let mut league_observations = Vec::new();
        for t in &times {
            let image = crate::video::frame(video, *t)?;
            if let Some(clock) = clock {
                let mut reading = league.read(&image, clock);
                reading.set("video_t", Value::from(*t));
                league_observations.push(reading);
            }
            for (rect, _) in frame_cards(&image, &levels) {
                let crop = image.crop(rect);
                let level = levels.read(&crop);
                let (name, confidence) = library.identify_card(&crop);
                let donated = !name.as_deref().is_some_and(|n| {
                    [
                        "Barbarian King",
                        "Archer Queen",
                        "Grand Warden",
                        "Royal Champion",
                        "Minion Prince",
                        "Dragon Duke",
                    ]
                    .contains(&n)
                }) && donated_marker(&crop);
                let identity = format!(
                    "{}:{}:{donated}",
                    name.clone()
                        .unwrap_or_else(|| format!("unknown-at-{}", rect.x / 30)),
                    level.get("value").encode()
                );
                let mut card = object(&[
                    (
                        "name",
                        name.as_deref().map(Value::from).unwrap_or(Value::Null),
                    ),
                    ("name_confidence", Value::from(confidence)),
                    (
                        "name_method",
                        Value::from(
                            "existing supervised icon library on complete badge-anchored crop",
                        ),
                    ),
                    ("level", level),
                    ("box", rect_value(rect)),
                    ("video_t", Value::from(*t)),
                    ("donated", Value::from(donated)),
                ]);
                let mut observations = cards
                    .get(&identity)
                    .map(|(old, _)| old.get("level_observation_times").array().to_vec())
                    .unwrap_or_default();
                if !observations
                    .iter()
                    .any(|v| v.number().is_some_and(|old| (old - t).abs() < 0.5))
                {
                    observations.push(Value::from(*t));
                }
                card.set(
                    "level_observation_times",
                    Value::Array(observations.clone()),
                );
                card.set(
                    "level_observation_value",
                    card.get("level").get("value").clone(),
                );
                if cards.get(&identity).is_none_or(|(old, _)| {
                    confidence > old.get("name_confidence").number().unwrap_or(0.0)
                }) {
                    cards.insert(identity, (card, crop));
                } else if let Some((old, _)) = cards.get_mut(&identity) {
                    old.set("level_observation_times", Value::Array(observations));
                }
            }
        }
        let mut saved = Vec::new();
        for (i, (_, (mut card, image))) in cards.into_iter().enumerate() {
            let name = format!("army/attack-{id:02}-card-{i:02}.ppm");
            image.save(&out.join(&name))?;
            card.set("icon", Value::from(name.as_str()));
            card.set("slot", Value::from(i as f64));
            saved.push(card);
        }
        a.set("army_cards", Value::Array(saved));
        a.set("league", crate::league::aggregate(&league_observations));
        a.set("league_observations", Value::Array(league_observations));
        a.set(
            "army_observation_times",
            Value::Array(times.into_iter().map(Value::from).collect()),
        );
        a.set("army_observation_status", Value::from("six sampled bar views; deduplicated name/level/donation; offscreen/clipped/dim badges may remain missing; no separate pet cards observed"));
        fs::write(path, a.encode() + "\n")?;
    }
    update(out, templates)
}

pub fn object(fields: &[(&str, Value)]) -> Value {
    Value::Object(
        fields
            .iter()
            .map(|(k, v)| (k.to_string(), v.clone()))
            .collect(),
    )
}

pub fn read_image(path: &Path) -> io::Result<Image> {
    Image::read(&mut BufReader::new(fs::File::open(path)?))?
        .ok_or_else(|| io::Error::other("empty PPM"))
}

pub fn resized(image: &Image, w: usize, h: usize) -> Image {
    let mut out = Image::blank(w, h);
    for y in 0..h {
        for x in 0..w {
            let i = (y * w + x) * 3;
            out.data[i..i + 3].copy_from_slice(&image.pixel(x * image.w / w, y * image.h / h));
        }
    }
    out
}

fn data_path() -> &'static Path {
    Path::new(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../data/source/clashking-static-data.json"
    ))
}

pub fn inspect_data() -> io::Result<()> {
    let data = Value::parse(&fs::read_to_string(data_path())?)?;
    for family in ["buildings", "troops", "spells", "heroes", "pets"] {
        for unit in data.get(family).array() {
            let name = unit.get("name").string().unwrap_or("");
            if family == "buildings"
                && ![
                    "Town Hall",
                    "Laboratory",
                    "Hero Hall",
                    "Barracks",
                    "Dark Barracks",
                    "Spell Factory",
                    "Dark Spell Factory",
                    "Workshop",
                    "Pet House",
                ]
                .contains(&name)
            {
                continue;
            }
            if unit.get("village").string().is_some_and(|v| v != "home") {
                continue;
            }
            let caps: BTreeMap<u32, u32> =
                unit.get("levels")
                    .array()
                    .iter()
                    .fold(BTreeMap::new(), |mut caps, l| {
                        let th = l.get("required_townhall").number().unwrap_or(0.0) as u32;
                        let level = l.get("level").number().unwrap_or(0.0) as u32;
                        caps.entry(th)
                            .and_modify(|v| *v = (*v).max(level))
                            .or_insert(level);
                        caps
                    });
            println!(
                "{family}\t{name}\t{} {}\t{caps:?}",
                unit.get("production_building").encode(),
                unit.get("production_building_level").encode()
            );
        }
    }
    Ok(())
}

pub fn caps(out: &Path) -> io::Result<()> {
    let catalog = Catalog::load()?;
    let mut report = String::from(
        "name\tfamily\ttown_hall\tmax_own_level\tproduction_unlock_th\tsiege_may_be_donated\n",
    );
    for (name, unit) in &catalog.units {
        for th in 1..=catalog.max_th {
            let cap = unit
                .levels
                .iter()
                .filter(|(_, required)| **required <= th)
                .map(|(level, _)| *level)
                .max();
            report.push_str(&format!(
                "{name}\t{}\t{th}\t{}\t{}\t{}\n",
                unit.family,
                cap.map(|n| n.to_string()).unwrap_or_default(),
                unit.unlock,
                unit.siege
            ));
        }
    }
    fs::write(out.join("m3-unit-caps.tsv"), report)
}

pub fn sheet(root: &Path, army: bool) -> io::Result<()> {
    let mut entries = Vec::new();
    for dir in icons::directories(root)? {
        for path in icons::attack_paths(&dir)?
            .into_iter()
            .take(if army { usize::MAX } else { 1 })
        {
            let a = Value::parse(&fs::read_to_string(path)?)?;
            for s in a.get(if army { "army_cards" } else { "slots" }).array() {
                if let Some(icon) = s.get("icon").string() {
                    entries.push((
                        dir.join(icon),
                        format!(
                            "{}\t{}\t{}\t{}",
                            s.get("name").encode(),
                            s.get("level").get("value").encode(),
                            s.get("video_t").encode(),
                            s.get("level").get("confidence").encode()
                        ),
                    ));
                }
            }
        }
    }
    let work = Path::new("/tmp/vidmine-work/m3");
    fs::create_dir_all(work)?;
    let mut table = String::from("sample\tpath\tname\n");
    for (page, chunk) in entries.chunks(80).enumerate() {
        let mut sheet = Image::blank(1200, chunk.len().div_ceil(10) * 145);
        for (i, (path, name)) in chunk.iter().enumerate() {
            let image = read_image(path)?;
            sheet.paste(&resized(&image, 105, 135), i % 10 * 120, i / 10 * 145, 1);
            table.push_str(&format!("{}\t{}\t{name}\n", page * 80 + i, path.display()));
        }
        sheet.save(&work.join(format!("slots-{page:02}.ppm")))?;
    }
    fs::write(work.join("slots.tsv"), table)
}

/// A reviewed TSV contains source PPM, x/y/w/h, family and literal glyph text.
/// Only tiny normalized masks are retained; source crops stay temporary.
pub fn learn(manifest: &Path, templates: &Path) -> io::Result<()> {
    let text = fs::read_to_string(manifest)?;
    let mut sheet = Image::blank(900, text.lines().count() * 110);
    for (i, line) in text.lines().skip(1).enumerate() {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 7 {
            return Err(io::Error::other("expected path, x, y, w, h, family, text"));
        }
        let n = c[1..5]
            .iter()
            .map(|s| s.parse::<usize>().map_err(io::Error::other))
            .collect::<io::Result<Vec<_>>>()?;
        if !["level", "league"].contains(&c[5]) || !c[6].chars().all(|c| c.is_ascii_alphanumeric())
        {
            return Err(io::Error::other("unsupported template family or label"));
        }
        let image = read_image(Path::new(c[0]))?;
        let rect = Rect::new(n[0], n[1], n[2], n[3]);
        if rect.x + rect.w > image.w || rect.y + rect.h > image.h {
            return Err(io::Error::other("template crop outside image"));
        }
        sheet.paste(&image.crop(rect), 0, i * 110, 5);
        for threshold in [150, 180, 210] {
            let foreground = Mask::white(&image.crop(rect), threshold);
            let mut glyphs: Vec<_> = components(&foreground)
                .into_iter()
                .filter(|(r, g)| {
                    r.h >= 5
                        && r.h < rect.h
                        && r.w <= rect.h
                        && r.x > 0
                        && r.y > 0
                        && r.x + r.w < rect.w
                        && r.y + r.h < rect.h
                        && g.data.iter().filter(|v| **v != 0).count() >= 6
                })
                .collect();
            glyphs.sort_by_key(|(r, _)| r.x);
            let column = (threshold as usize - 150) / 30;
            sheet.paste(
                &Mask::white(&image.crop(rect), threshold).as_image(),
                180 + column * 220,
                i * 110,
                5,
            );
            if glyphs.len() != c[6].len() {
                eprintln!(
                    "line {} threshold {threshold}: {} glyphs for {}",
                    i + 2,
                    glyphs.len(),
                    c[6]
                );
                continue;
            }
            for (j, ((_, glyph), label)) in glyphs.iter().zip(c[6].chars()).enumerate() {
                glyph.normalized().save_text(
                    &templates.join(format!("{}-{label}-m3-{i}-{j}-{threshold}.txt", c[5])),
                )?;
            }
        }
    }
    fs::create_dir_all("/tmp/vidmine-work/m3")?;
    sheet.save(Path::new("/tmp/vidmine-work/m3/training.ppm"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn catalog() -> Catalog {
        // Declared synthetic caps/units used to test inference semantics only.
        Catalog {
            units: BTreeMap::from([
                (
                    "Hero".into(),
                    Unit {
                        family: "heroes".into(),
                        levels: BTreeMap::from([(95, 16), (100, 17)]),
                        seasonal: false,
                        siege: false,
                        unlock: 11,
                    },
                ),
                (
                    "Freeze Spell".into(),
                    Unit {
                        family: "spells".into(),
                        levels: BTreeMap::from([(7, 12), (8, 18)]),
                        seasonal: false,
                        siege: false,
                        unlock: 9,
                    },
                ),
                (
                    "Siege".into(),
                    Unit {
                        family: "troops".into(),
                        levels: BTreeMap::from([(6, 18)]),
                        seasonal: false,
                        siege: true,
                        unlock: 12,
                    },
                ),
            ]),
            max_th: 18,
            fingerprint: "synthetic".into(),
        }
    }

    fn card(name: &str, level: Option<u32>, donated: bool) -> Value {
        object(&[
            ("name", Value::from(name)),
            ("name_confidence", Value::from(1.0)),
            ("level", object(&[("value", number(level))])),
            ("donated", Value::from(donated)),
        ])
    }

    #[test]
    fn underleveling_keeps_higher_town_halls_and_donations_do_not_raise_cap() {
        let result = infer(
            &[
                card("Hero", Some(95), false),
                card("Freeze Spell", Some(8), true),
                card("Siege", Some(6), false),
            ],
            &catalog(),
        );
        assert_eq!(result.get("min").number(), Some(16.0));
        assert_eq!(result.get("max").number(), Some(18.0));
        assert_eq!(result.get("consistent").array().len(), 3);
        assert_eq!(result.get("best"), &Value::Null);
    }

    #[test]
    fn availability_is_used_without_a_readable_level_and_conflicts_abstain() {
        let result = infer(&[card("Hero", None, false)], &catalog());
        assert_eq!(result.get("min").number(), Some(11.0));
        let conflict = infer(
            &[
                card("Hero", Some(95), false),
                card("Freeze Spell", Some(99), false),
            ],
            &catalog(),
        );
        assert!(conflict.get("consistent").array().is_empty());
        assert_eq!(conflict.get("best"), &Value::Null);
        assert_eq!(
            conflict.get("status").string(),
            Some("inconsistent_observations")
        );
    }

    #[test]
    fn a_border_stroke_is_not_a_level_one_and_clipped_badges_abstain() {
        let stroke = Mask {
            w: 2,
            h: 16,
            data: vec![1; 32],
        };
        let reader = Levels {
            templates: vec![('1', stroke.normalized())],
        };
        assert!(reader.digit(&stroke).is_none());
        let mut crop = Image::blank(61, 83);
        let glyph = Image {
            w: 4,
            h: 12,
            data: vec![255; 4 * 12 * 3],
        };
        crop.paste(&glyph, 7, 76, 1);
        assert_eq!(reader.read(&crop).get("value"), &Value::Null);
    }

    #[test]
    fn touching_digit_run_is_split_without_a_unit_level_prior() {
        // Declared synthetic glyphs, with no game level/cap information.
        let make = |rows: &[&str]| Mask {
            w: rows[0].len(),
            h: rows.len(),
            data: rows
                .iter()
                .flat_map(|r| r.bytes().map(|c| u8::from(c == b'#')))
                .collect(),
        };
        let one = make(&[".##", "..#", "..#", "..#", "..#", "..#", "###"]);
        let two = make(&["####", "...#", "...#", "####", "#...", "#...", "####"]);
        let mut run = Mask {
            w: 7,
            h: 7,
            data: vec![0; 49],
        };
        for y in 0..7 {
            run.data[y * 7..y * 7 + 3].copy_from_slice(&one.data[y * 3..y * 3 + 3]);
            run.data[y * 7 + 3..y * 7 + 7].copy_from_slice(&two.data[y * 4..y * 4 + 4]);
        }
        let reader = Levels {
            templates: vec![('1', one.normalized()), ('2', two.normalized())],
        };
        assert_eq!(reader.sequence(&run).map(|v| v.0).as_deref(), Some("12"));
    }

    #[test]
    fn conflicting_own_levels_do_not_erase_a_separate_donated_level() {
        let mut attack = object(&[(
            "slots",
            Value::Array(vec![
                card("Freeze Spell", Some(7), false),
                card("Freeze Spell", Some(8), false),
                card("Freeze Spell", Some(8), true),
            ]),
        )]);
        reconcile_levels(&mut attack);
        let cards = attack.get("slots").array();
        assert_eq!(cards[0].get("level").get("value"), &Value::Null);
        assert_eq!(
            cards[0].get("level").get("observed_value").number(),
            Some(7.0)
        );
        assert_eq!(cards[2].get("level").get("value").number(), Some(8.0));
    }
}
