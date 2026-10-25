use crate::image::{Image, Mask, Rect};
use crate::ocr::{Reader, Reading};
use crate::probe::{match_score, Regions};
use crate::video;
use std::fs;
use std::io::{self, BufWriter, Write};
use std::path::Path;
use std::time::Instant;

pub const FPS: f64 = 5.0;

pub fn quoted(text: &str) -> String {
    let mut result = String::from("\"");
    for c in text.chars() {
        match c {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            c if c.is_control() => result.push_str(&format!("\\u{:04x}", c as u32)),
            c => result.push(c),
        }
    }
    result.push('"');
    result
}

pub fn optional(value: Option<u32>) -> String {
    value
        .map(|v| v.to_string())
        .unwrap_or_else(|| "null".to_string())
}

fn reading_json(reading: &Reading) -> String {
    format!(
        "{{\"value\":{},\"confidence\":{:.4},\"raw\":{}}}",
        optional(reading.value),
        reading.confidence,
        quoted(&reading.raw)
    )
}

#[derive(Clone)]
pub struct Slot {
    pub index: usize,
    pub rect: Rect,
    pub count: Rect,
}

#[derive(Clone)]
pub struct Frame {
    pub t: f64,
    pub phase: &'static str,
    pub clock: Reading,
    pub damage: Reading,
    pub stars: Option<u32>,
    pub star_confidence: f64,
    pub slots: Vec<Reading>,
    pub label_score: f64,
}

struct Panels {
    clock: Rect,
    damage: Rect,
    top_h: usize,
    width: usize,
}

impl Panels {
    fn new(regions: &Regions) -> Self {
        let clock = Rect::new(
            regions.clock.x,
            regions.battle_label.y.saturating_sub(4),
            regions.clock.w,
            regions.clock.y + regions.clock.h - regions.battle_label.y.saturating_sub(4),
        );
        let damage = Rect::new(
            regions.stars.x,
            regions.damage_label.y,
            regions.damage.x + regions.damage.w - regions.stars.x,
            regions.stars.y + regions.stars.h - regions.damage_label.y,
        );
        Self {
            clock,
            damage,
            top_h: clock.h.max(damage.h),
            width: regions.bar.w.max(clock.w + damage.w),
        }
    }

    fn filter(&self, regions: &Regions) -> String {
        let c = self.clock;
        let d = self.damage;
        let b = regions.bar;
        format!("fps=fps=5:round=near,format=rgb24,split=3[c][d][b];[c]crop={}:{}:{}:{},pad={}:{}[c1];[d]crop={}:{}:{}:{},pad={}:{}[d1];[c1][d1]hstack=inputs=2,pad={}:{}[top];[b]crop={}:{}:{}:{},pad={}:{}[bar];[top][bar]vstack=inputs=2", c.w, c.h, c.x, c.y, c.w, self.top_h, d.w, d.h, d.x, d.y, d.w, self.top_h, self.width, self.top_h, b.w, b.h, b.x, b.y, self.width, b.h)
    }
}

fn scaled_mask(template: &Mask, width: usize, height: usize) -> Mask {
    let mut data = vec![0; width * height];
    for y in 0..height {
        for x in 0..width {
            data[y * width + x] =
                template.data[(y * template.h / height) * template.w + x * template.w / width];
        }
    }
    Mask {
        w: width,
        h: height,
        data,
    }
}

pub fn star_reading(image: &Image) -> (Option<u32>, f64) {
    let scale = image.w as f64 / 80.0;
    let mut count = 0;
    let mut confidence: f64 = 1.0;
    for i in 0..3 {
        let x0 = ((4 + i * 26) as f64 * scale) as usize;
        let y0 = (4.0 * scale) as usize;
        let w = (18.0 * scale) as usize;
        let h = (20.0 * scale) as usize;
        let mut bright = 0;
        let mut total = 0;
        for y in y0..(y0 + h).min(image.h) {
            for x in x0..(x0 + w).min(image.w) {
                let p = image.pixel(x, y);
                if p.iter().min().copied().unwrap() > 165 {
                    bright += 1;
                }
                total += 1;
            }
        }
        let fraction = bright as f64 / total.max(1) as f64;
        if fraction > 0.28 {
            count += 1;
        }
        confidence = confidence.min(if fraction > 0.28 {
            ((fraction - 0.28) * 3.0 + 0.60).min(1.0)
        } else {
            ((0.28 - fraction) * 2.0 + 0.45).min(1.0)
        });
    }
    (Some(count), confidence)
}

fn find_slots(image: &Image, regions: &Regions, reader: &Reader) -> Vec<Slot> {
    // Count anchors are discovered from xN components in each text row. The
    // known game-font scale constrains card dimensions, not the screen width.
    let scale = regions.clock.h as f64 / 25.0;
    let bar = image.crop(regions.bar);
    let mut candidates: Vec<(Rect, f64)> = Vec::new();
    let text_h = (17.0 * scale).round() as usize;
    for row_offset in (0..=24).step_by(2).chain((96..=120).step_by(2)) {
        if regions.layout == "phone_single_row" && row_offset >= 96 {
            continue;
        }
        let y = (row_offset as f64 * scale).round() as usize;
        if y + text_h >= bar.h {
            continue;
        }
        for threshold in [165, 95] {
            let row = Mask::white(&bar.crop(Rect::new(0, y, bar.w, text_h)), threshold);
            let glyphs = row.glyphs();
            for pair in glyphs.windows(2) {
                let a = pair[0].0;
                let b = pair[1].0;
                let gap = b.x.saturating_sub(a.x + a.w);
                if !reader.count_prefix(&pair[0].1) {
                    continue;
                }
                if a.h < (6.0 * scale) as usize
                    || a.h > (18.0 * scale) as usize
                    || a.w < (5.0 * scale) as usize
                    || a.w > (13.0 * scale) as usize
                    || gap > (4.0 * scale) as usize
                {
                    continue;
                }
                let x =
                    (b.x + b.w + (4.0 * scale) as usize).saturating_sub((28.0 * scale) as usize);
                let w = ((28.0 * scale).round() as usize).min(bar.w - x);
                let crop = bar.crop(Rect::new(x, y.saturating_sub(5), w, 24));
                let reading = reader.count(&crop);
                if reading.value.is_none() || reading.confidence < 0.52 {
                    continue;
                }
                // The count window includes the four-pixel lift of a selected
                // card; the reader chooses the best complete text row inside it.
                let count = Rect::new(
                    x + regions.bar.x,
                    y.saturating_sub(5) + regions.bar.y,
                    w,
                    24,
                );
                candidates.push((
                    Rect { ..count },
                    reading.confidence + if a.y >= 2 { 0.02 } else { 0.0 },
                ));
            }
        }
    }
    candidates.sort_by(|a, b| b.1.total_cmp(&a.1));
    let mut anchors: Vec<Rect> = Vec::new();
    for (rect, _) in candidates {
        if !anchors.iter().any(|r| {
            r.x.abs_diff(rect.x) < (15.0 * scale) as usize
                && r.y.abs_diff(rect.y) < (20.0 * scale) as usize
        }) {
            anchors.push(rect);
        }
    }
    anchors.sort_by_key(|r| (r.y / (40.0 * scale) as usize, r.x));
    anchors
        .into_iter()
        .enumerate()
        .map(|(index, count)| {
            let card_w = (61.0 * scale).round() as usize;
            let y = count.y + (2.0 * scale) as usize;
            Slot {
                index,
                rect: Rect::new(
                    (count.x + count.w + 1).saturating_sub(card_w),
                    y,
                    card_w,
                    ((83.0 * scale).round() as usize).min(regions.height - y),
                ),
                count,
            }
        })
        .collect()
}

pub fn read_full(
    image: &Image,
    regions: &Regions,
    reader: &Reader,
    templates: &Path,
    slots: &[Slot],
    t: f64,
) -> io::Result<Frame> {
    let panels = Panels::new(regions);
    let mut packed = Image::blank(panels.width, panels.top_h + regions.bar.h);
    packed.paste(&image.crop(panels.clock), 0, 0, 1);
    packed.paste(&image.crop(panels.damage), panels.clock.w, 0, 1);
    packed.paste(&image.crop(regions.bar), 0, panels.top_h, 1);
    let battle = Mask::load_text(&templates.join(&regions.battle_template))?;
    let prep = Mask::load_text(&templates.join(
        if regions.battle_template == "battle-q-label.txt" {
            "prep-q-label.txt"
        } else if regions.layout == "phone_single_row" {
            "prep-phone-label.txt"
        } else {
            "prep-label.txt"
        },
    ))?;
    let damage = Mask::load_text(&templates.join(&regions.damage_template))?;
    Ok(read_packed(
        &packed,
        regions,
        &panels,
        reader,
        (&battle, &prep, &damage),
        slots,
        t,
    ))
}

fn read_packed(
    image: &Image,
    regions: &Regions,
    panels: &Panels,
    reader: &Reader,
    labels: (&Mask, &Mask, &Mask),
    slots: &[Slot],
    t: f64,
) -> Frame {
    let mask = Mask::white(image, 145);
    let b_rect = Rect::new(
        regions.battle_label.x - panels.clock.x,
        regions.battle_label.y - panels.clock.y,
        regions.battle_label.w,
        regions.battle_label.h,
    );
    let battle = scaled_mask(labels.0, b_rect.w, b_rect.h);
    // Edited recordings can translate/resize the centered timer a few pixels
    // between battles. Keep the same acceptance threshold while searching only
    // the already-probed label panel; a fixed x otherwise loses entire attacks.
    let mut battle_score = match_score(&mask, &battle, b_rect.x, b_rect.y, 1);
    for factor in [0.95, 1.0, 1.05, 1.10] {
        let label = crate::probe::resize(&battle, factor);
        let area = Rect::new(0, 0, panels.clock.w.saturating_sub(label.w), 8);
        battle_score = battle_score.max(crate::probe::search(&mask, &label, area).1);
    }
    let prep_w = (labels.1.w as f64 * regions.clock.h as f64 / 25.0).round() as usize;
    let prep = scaled_mask(labels.1, prep_w, b_rect.h);
    let prep_score = crate::probe::search(
        &mask,
        &prep,
        Rect::new(0, 0, panels.clock.w.saturating_sub(prep.w), 8),
    )
    .1;
    let damage = scaled_mask(labels.2, regions.damage_label.w, regions.damage_label.h);
    let damage_score = match_score(
        &mask,
        &damage,
        panels.clock.w + regions.damage_label.x - panels.damage.x,
        0,
        1,
    );
    let candidate_clock = reader.clock(&image.crop(Rect::new(
        0,
        regions.clock.y - panels.clock.y,
        regions.clock.w,
        regions.clock.h,
    )));
    let phase = if prep_score > 0.67 && prep_score >= battle_score {
        "preparation"
    } else if battle_score > 0.62 && (candidate_clock.value.is_some() || damage_score > 0.60) {
        "attack"
    } else if prep_score > 0.67 {
        "preparation"
    } else {
        "other"
    };
    let clock = if phase != "other" {
        candidate_clock
    } else {
        Reading::missing()
    };
    let damage = if phase == "attack" {
        reader.percent(
            &image.crop(Rect::new(
                panels.clock.w + regions.damage.x - panels.damage.x,
                regions.damage.y - panels.damage.y,
                regions.damage.w,
                regions.damage.h,
            )),
            false,
        )
    } else {
        Reading::missing()
    };
    let (stars, star_confidence) = if phase == "attack" {
        star_reading(&image.crop(Rect::new(
            panels.clock.w,
            regions.stars.y - panels.damage.y,
            regions.stars.w,
            regions.stars.h,
        )))
    } else {
        (None, 0.0)
    };
    let slot_readings = slots
        .iter()
        .map(|slot| {
            if phase == "other" {
                return Reading::missing();
            }
            reader.count(&image.crop(Rect::new(
                slot.count.x - regions.bar.x,
                slot.count.y - regions.bar.y + panels.top_h,
                slot.count.w,
                slot.count.h,
            )))
        })
        .collect();
    Frame {
        t,
        phase,
        clock,
        damage,
        stars,
        star_confidence,
        slots: slot_readings,
        label_score: battle_score.min(damage_score),
    }
}

#[derive(Clone)]
struct Cut {
    t: f64,
    before: Option<u32>,
    after: Option<u32>,
    kind: &'static str,
}

struct Attack {
    start: usize,
    end: usize,
    prep_start: Option<usize>,
    cuts: Vec<Cut>,
}

fn segment(frames: &[Frame]) -> Vec<Attack> {
    let mut attacks: Vec<Attack> = Vec::new();
    let mut active: Option<Attack> = None;
    let mut prep_start = None;
    let mut previous: Option<usize> = None;
    for (i, frame) in frames.iter().enumerate() {
        if frame.phase == "preparation"
            && frames[i..frames.len().min(i + 3)]
                .iter()
                .filter(|f| f.phase == "preparation")
                .count()
                >= 3
        {
            if prep_start.is_none() {
                prep_start = Some(i);
            }
            if let Some(attack) = active.take() {
                attacks.push(attack);
            }
            previous = None;
            continue;
        }
        if frame.phase != "attack" {
            if let Some(attack) = &active {
                if frame.t - frames[attack.end].t > 60.0 {
                    attacks.push(active.take().unwrap());
                    previous = None;
                }
            }
            continue;
        }
        if frame.clock.value.is_none() {
            if let Some(attack) = &mut active {
                attack.end = i;
            }
            continue;
        }
        let clock = frame.clock.value.unwrap();
        if let Some(p) = previous {
            let mut history: Vec<_> = frames[i.saturating_sub(15)..i]
                .iter()
                .filter_map(|f| f.clock.value.map(|v| v as f64))
                .collect();
            let old = if history.len() >= 5 {
                median(&mut history) as u32
            } else {
                frames[p].clock.value.unwrap()
            };
            let confirmed_reset = frames[i..frames.len().min(i + 10)]
                .iter()
                .filter_map(|f| f.clock.value)
                .filter(|c| *c > old + 20)
                .count()
                >= 4;
            if clock > old + 30 && clock >= 110 && old < 150 && confirmed_reset {
                if let Some(attack) = active.take() {
                    attacks.push(attack);
                }
            }
        }
        let attack = active.get_or_insert_with(|| Attack {
            start: i,
            end: i,
            prep_start: prep_start.take(),
            cuts: Vec::new(),
        });
        attack.end = i;
        previous = Some(i);
    }
    if let Some(attack) = active {
        attacks.push(attack);
    }
    let mut attacks: Vec<Attack> = attacks
        .into_iter()
        .filter(|a| frames[a.end].t - frames[a.start].t >= 5.0)
        .collect();
    for attack in &mut attacks {
        attack.cuts = detect_cuts(frames, attack);
    }
    attacks
}

fn median(values: &mut [f64]) -> f64 {
    values.sort_by(f64::total_cmp);
    values[values.len() / 2]
}

fn detect_cuts(frames: &[Frame], attack: &Attack) -> Vec<Cut> {
    let mut cuts: Vec<Cut> = Vec::new();
    let window = 20;
    if attack.end - attack.start < window * 2 {
        return cuts;
    }
    for i in attack.start + window..=attack.end - window {
        let side = |range: std::ops::Range<usize>| -> Vec<(f64, f64)> {
            frames[range]
                .iter()
                .filter_map(|f| f.clock.value.map(|c| (f.t, c as f64)))
                .collect()
        };
        let before_points = side(i - window..i);
        let after_points = side(i..i + window);
        let Some((before_speed, _)) = crate::timing::rate(&before_points) else {
            continue;
        };
        let Some((after_speed, _)) = crate::timing::rate(&after_points) else {
            continue;
        };
        let speed = (before_speed + after_speed) / 2.0;
        let intercept = |points: &[(f64, f64)]| -> Option<f64> {
            let mut values: Vec<f64> = points.iter().map(|(t, c)| c + speed * t).collect();
            if values.len() < 6 {
                return None;
            }
            let center = median(&mut values);
            let mut errors: Vec<f64> = values.iter().map(|v| (v - center).abs()).collect();
            if median(&mut errors) > 0.65 {
                return None;
            }
            Some(center)
        };
        let Some(before) = intercept(&before_points) else {
            continue;
        };
        let Some(after) = intercept(&after_points) else {
            continue;
        };
        if (after - before).abs() <= 3.0 {
            continue;
        }
        if frames[i].damage.value.unwrap_or(0) >= 98 {
            continue;
        }
        if cuts.last().is_some_and(|cut| frames[i].t - cut.t < 3.0) {
            continue;
        }
        cuts.push(Cut {
            t: frames[i].t,
            before: Some((before - speed * frames[i].t).max(0.0).round() as u32),
            after: Some((after - speed * frames[i].t).max(0.0).round() as u32),
            kind: "clock_discontinuity",
        });
    }
    cuts
}

#[derive(Clone)]
struct Deployment {
    t: f64,
    clock: Option<u32>,
    slot: usize,
    before: u32,
    after: u32,
    confidence: f64,
}

fn initial_count(frames: &[Frame], attack: &Attack, slot: usize) -> Option<(u32, f64)> {
    let start = attack.prep_start.unwrap_or(attack.start);
    let end = (attack.start + 5).min(attack.end + 1);
    let mut frequencies = std::collections::BTreeMap::<u32, (usize, f64)>::new();
    for frame in &frames[start..end] {
        let reading = &frame.slots[slot];
        if let Some(value) = reading.value {
            let entry = frequencies.entry(value).or_default();
            entry.0 += 1;
            entry.1 += reading.confidence;
        }
    }
    frequencies
        .into_iter()
        .max_by_key(|(_, (count, _))| *count)
        .filter(|(_, (count, _))| *count >= 3)
        .map(|(value, (count, score))| (value, score / count as f64))
}

fn deployments(frames: &[Frame], attack: &Attack) -> Vec<Deployment> {
    let count = frames[attack.start].slots.len();
    let mut events = Vec::new();
    for slot in 0..count {
        let initial = initial_count(frames, attack, slot);
        let mut previous = initial.map(|(value, score)| (value, score, frames[attack.start].t));
        for i in attack.start..=attack.end {
            let frame = &frames[i];
            let reading = &frame.slots[slot];
            let Some(value) = reading.value else {
                continue;
            };
            let stable = frames.get(i + 1).and_then(|f| f.slots[slot].value) == Some(value);
            if !stable {
                continue;
            }
            if initial.is_some_and(|(ceiling, _)| value > ceiling) {
                continue;
            }
            if let Some((old, old_score, old_t)) = previous {
                // A larger OCR value must never become the source of a later
                // false decrease. Recall/refill/scroll cases remain unresolved
                // in the raw stream rather than becoming invented deployments.
                if value > old {
                    continue;
                }
                if value < old
                    && frame.t - old_t <= 2.0
                    && !attack
                        .cuts
                        .iter()
                        .any(|cut| cut.t > old_t && cut.t <= frame.t)
                {
                    events.push(Deployment {
                        t: frame.t,
                        clock: frame.clock.value,
                        slot,
                        before: old,
                        after: value,
                        confidence: reading.confidence.min(old_score),
                    });
                }
            }
            previous = Some((value, reading.confidence, frame.t));
        }
    }
    events.sort_by(|a, b| a.t.total_cmp(&b.t).then(a.slot.cmp(&b.slot)));
    events
}

fn result_screen(
    video_path: &Path,
    regions: &Regions,
    reader: &Reader,
    templates: &Path,
    end: f64,
) -> io::Result<Option<(f64, Reading, u32)>> {
    let scale = regions.height as f64 / 720.0;
    let rect = |x: f64, y: f64, w: f64, h: f64| {
        Rect::new(
            (regions.width as f64 / 2.0 + x * scale) as usize,
            (y * scale) as usize,
            (w * scale) as usize,
            (h * scale) as usize,
        )
    };
    let label = Mask::load_text(&templates.join("result-label.txt"))?;
    let mut best: Option<(f64, Reading, u32)> = None;
    for offset in [1.0, 2.0, 3.0, 4.0, 5.0] {
        let t = end + offset;
        if t >= regions.duration {
            continue;
        }
        let image = video::frame(video_path, t)?;
        let label_rect = rect(-48.0, 79.0, 98.0, 14.0);
        let mask = Mask::white(&image.crop(label_rect), 145);
        let label_match = match_score(
            &mask,
            &scaled_mask(&label, label_rect.w, label_rect.h),
            0,
            0,
            1,
        );
        if label_match < 0.55 {
            continue;
        }
        let damage = reader.percent(&image.crop(rect(-53.0, 98.0, 108.0, 25.0)), true);
        if damage.value.is_none() {
            continue;
        }
        let mut stars = 0;
        for (x, y) in [(-120.0, 130.0), (0.0, 50.0), (120.0, 130.0)] {
            let patch = image.crop(rect(x - 15.0, y - 15.0, 30.0, 30.0));
            let fraction = patch
                .data
                .chunks_exact(3)
                .filter(|p| p.iter().min().copied().unwrap() > 170)
                .count() as f64
                / (patch.w * patch.h) as f64;
            if fraction > 0.50 {
                stars += 1;
            }
        }
        if best
            .as_ref()
            .is_none_or(|(_, old, old_stars)| (damage.value, stars) >= (old.value, *old_stars))
        {
            best = Some((t, damage, stars));
        }
    }
    Ok(best)
}

pub fn extract(video_path: &Path, out: &Path, templates: &Path) -> io::Result<()> {
    let started = Instant::now();
    let regions = crate::probe::locate(video_path, templates)?;
    if regions.layout == "cropped_replay" {
        crate::replay::extract(video_path, out, templates, &regions)?;
        crate::icons::update(out, templates)?;
        crate::timing::update(out)?;
        return crate::identity::update(out, templates);
    }
    fs::create_dir_all(out)?;
    fs::write(out.join("regions.json"), regions.json())?;
    let reader = Reader::load(templates)?;
    let sample = video::frame(video_path, regions.sample_t)?;
    let mut slots = find_slots(&sample, &regions, &reader);
    for t in [10.0_f64, 30.0, 60.0] {
        let image = video::frame(video_path, t.min(regions.duration - 0.1))?;
        for slot in find_slots(&image, &regions, &reader) {
            if !slots.iter().any(|s| {
                s.count.x.abs_diff(slot.count.x) < 18 && s.count.y.abs_diff(slot.count.y) < 25
            }) {
                slots.push(slot);
            }
        }
    }
    slots.sort_by_key(|s| (s.count.y / 40, s.count.x));
    for (i, slot) in slots.iter_mut().enumerate() {
        slot.index = i;
    }
    eprintln!(
        "discovered {} count slots: {:?}",
        slots.len(),
        slots.iter().map(|s| (s.index, s.count)).collect::<Vec<_>>()
    );
    let panels = Panels::new(&regions);
    let battle = Mask::load_text(&templates.join(&regions.battle_template))?;
    let prep = Mask::load_text(&templates.join(
        if regions.battle_template == "battle-q-label.txt" {
            "prep-q-label.txt"
        } else if regions.layout == "phone_single_row" {
            "prep-phone-label.txt"
        } else {
            "prep-label.txt"
        },
    ))?;
    let damage = Mask::load_text(&templates.join(&regions.damage_template))?;
    let mut stream = video::Stream::new(video_path, &panels.filter(&regions))?;
    let mut readings = BufWriter::new(fs::File::create(out.join("readings.jsonl"))?);
    let mut tsv = BufWriter::new(fs::File::create(out.join("readings.tsv"))?);
    writeln!(tsv, "video_t\tphase\tclock\tclock_confidence\tdamage\tdamage_confidence\tstars\tstar_confidence\tslot_counts")?;
    let mut frames = Vec::new();
    while let Some(image) = stream.next()? {
        let frame = read_packed(
            &image,
            &regions,
            &panels,
            &reader,
            (&battle, &prep, &damage),
            &slots,
            frames.len() as f64 / FPS,
        );
        let slot_json = frame
            .slots
            .iter()
            .map(reading_json)
            .collect::<Vec<_>>()
            .join(",");
        writeln!(readings, "{{\"video_t\":{:.1},\"phase\":{},\"hud_confidence\":{:.4},\"clock\":{},\"damage\":{},\"stars\":{{\"value\":{},\"confidence\":{:.4}}},\"slots\":[{}]}}", frame.t, quoted(frame.phase), frame.label_score, reading_json(&frame.clock), reading_json(&frame.damage), optional(frame.stars), frame.star_confidence, slot_json)?;
        writeln!(
            tsv,
            "{:.1}\t{}\t{}\t{:.4}\t{}\t{:.4}\t{}\t{:.4}\t{}",
            frame.t,
            frame.phase,
            optional(frame.clock.value),
            frame.clock.confidence,
            optional(frame.damage.value),
            frame.damage.confidence,
            optional(frame.stars),
            frame.star_confidence,
            frame
                .slots
                .iter()
                .map(|r| optional(r.value))
                .collect::<Vec<_>>()
                .join(",")
        )?;
        if frames.len() % 1500 == 0 {
            eprintln!(
                "{:.0}/{:.0}s ({:.1}s elapsed)",
                frame.t,
                regions.duration,
                started.elapsed().as_secs_f64()
            );
        }
        frames.push(frame);
    }
    readings.flush()?;
    tsv.flush()?;
    let attacks = segment(&frames);
    let video_id = video_path.file_stem().unwrap().to_string_lossy();
    let mut index = String::from("video_id\tattack\tvideo_t_start\tvideo_t_end\tduration\tfinal_damage\tfinal_stars\tdeployments\tclock_coverage\tdamage_coverage\tmean_clock_confidence\tmean_damage_confidence\tedited\n");
    for (number, attack) in attacks.iter().enumerate() {
        let start_t = frames[attack.start].t;
        let end_t = frames[attack.end].t;
        let events = deployments(&frames, attack);
        let result = result_screen(video_path, &regions, &reader, templates, end_t)?;
        let samples = &frames[attack.start..=attack.end];
        let last_damage = samples.iter().rev().find_map(|f| f.damage.value);
        let last_stars = samples.iter().rev().find_map(|f| f.stars);
        let final_damage = result.as_ref().and_then(|r| r.1.value).max(last_damage);
        let final_stars = result.as_ref().map(|r| r.2).max(last_stars);
        let zero = (attack.prep_start.unwrap_or(attack.start)..=attack.end)
            .find(|i| frames[*i].phase == "preparation" || frames[*i].damage.value == Some(0));
        let keyframe_t = zero.map(|i| frames[i].t + 0.2).unwrap_or(start_t);
        let keyframe_name = format!("attack-{:02}-keyframe.jpg", number + 1);
        video::jpeg(video_path, keyframe_t, &out.join(&keyframe_name))?;
        let icon_frame = video::frame(
            video_path,
            zero.map(|i| frames[i].t + 0.4).unwrap_or(start_t),
        )?;
        let slot_dir = out.join("slots");
        fs::create_dir_all(&slot_dir)?;
        let mut slot_json = Vec::new();
        let mut icon_slots = slots.clone();
        let scale = regions.clock.h as f64 / 25.0;
        let first_row: Vec<&Slot> = slots
            .iter()
            .filter(|s| s.count.y < regions.bar.y + 50)
            .collect();
        if regions.layout == "phone_single_row" {
            let card_w = (61.0 * scale).round() as usize;
            for pair in first_row.windows(2) {
                let gap = pair[1].rect.x.saturating_sub(pair[0].rect.x);
                if gap < card_w * 3 / 2 || gap > card_w * 8 {
                    continue;
                }
                let missing = (gap as f64 / (card_w as f64 + 3.0)).round() as usize;
                for n in 1..missing {
                    icon_slots.push(Slot {
                        index: icon_slots.len(),
                        rect: Rect::new(
                            pair[0].rect.x + gap * n / missing,
                            pair[0].rect.y,
                            card_w,
                            pair[0].rect.h,
                        ),
                        count: Rect::default(),
                    });
                }
            }
        } else if let Some(pair) = first_row
            .windows(2)
            .find(|pair| pair[1].rect.x - pair[0].rect.x > (220.0 * scale) as usize)
        {
            let right = pair[1].rect.x;
            for (dx, dy, h) in [
                (210.0, -8.0, 95.0),
                (137.0, -8.0, 95.0),
                (69.0, -8.0, 95.0),
                (137.0, 88.0, 93.0),
                (69.0, 88.0, 93.0),
            ] {
                icon_slots.push(Slot {
                    index: icon_slots.len(),
                    rect: Rect::new(
                        right.saturating_sub((dx * scale) as usize),
                        (regions.bar.y as f64 + dy * scale) as usize,
                        (60.0 * scale) as usize,
                        (h * scale) as usize,
                    ),
                    count: Rect::default(),
                });
            }
        }
        for slot in &icon_slots {
            let name = format!("attack-{:02}-slot-{:02}.ppm", number + 1, slot.index);
            icon_frame.crop(slot.rect).save(&slot_dir.join(&name))?;
            slot_json.push(format!(
                "{{\"slot\":{},\"kind\":{},\"box\":{},\"count_box\":{},\"initial_count\":{},\"icon\":{}}}",
                slot.index,
                quoted(if slot.count.w == 0 {
                    "hero_or_siege"
                } else {
                    "counted_card"
                }),
                slot.rect.json(),
                if slot.count.w == 0 {
                    "null".to_string()
                } else {
                    slot.count.json()
                },
                if slot.count.w == 0 {
                    "null".to_string()
                } else {
                    optional(initial_count(&frames, attack, slot.index).map(|r| r.0))
                },
                quoted(&format!("slots/{name}"))
            ));
        }
        let clock_json = samples
            .iter()
            .map(|f| {
                format!(
                    "{{\"video_t\":{:.1},\"clock_t\":{},\"confidence\":{:.4}}}",
                    f.t,
                    optional(f.clock.value),
                    f.clock.confidence
                )
            })
            .collect::<Vec<_>>()
            .join(",\n    ");
        let damage_json = samples
            .iter()
            .map(|f| {
                format!(
                    "{{\"video_t\":{:.1},\"percent\":{},\"confidence\":{:.4}}}",
                    f.t,
                    optional(f.damage.value),
                    f.damage.confidence
                )
            })
            .collect::<Vec<_>>()
            .join(",\n    ");
        let mut star_json = Vec::new();
        let mut star = 0;
        for (i, frame) in samples.iter().enumerate() {
            if let Some(value) = frame.stars {
                if value > star
                    && samples
                        .get(i + 1)
                        .and_then(|f| f.stars)
                        .is_some_and(|next| next >= value)
                {
                    for earned in star + 1..=value {
                        star_json.push(format!(
                            "{{\"video_t\":{:.1},\"clock_t\":{},\"star\":{},\"confidence\":{:.4}}}",
                            frame.t,
                            optional(frame.clock.value),
                            earned,
                            frame.star_confidence
                        ));
                    }
                    star = value;
                }
            }
        }
        let event_json = events.iter().map(|e| format!("{{\"clock_t\":{},\"video_t\":{:.1},\"slot\":{},\"count_before\":{},\"count_after\":{},\"delta\":{},\"confidence\":{:.4}}}", optional(e.clock), e.t, e.slot, e.before, e.after, e.before - e.after, e.confidence)).collect::<Vec<_>>().join(",\n    ");
        let cuts = attack
            .cuts
            .iter()
            .map(|c| {
                format!(
                    "{{\"video_t\":{:.1},\"clock_before\":{},\"clock_after\":{},\"kind\":{}}}",
                    c.t,
                    optional(c.before),
                    optional(c.after),
                    quoted(c.kind)
                )
            })
            .collect::<Vec<_>>()
            .join(",");
        let result_json = result
            .as_ref()
            .map(|(t, damage, stars)| {
                format!(
                    "{{\"video_t\":{t:.1},\"damage\":{},\"stars\":{stars},\"settled\":{}}}",
                    reading_json(damage),
                    damage.value >= last_damage && Some(*stars) >= last_stars
                )
            })
            .unwrap_or_else(|| "null".to_string());
        let coverage = |clock: bool| -> (f64, f64) {
            let values: Vec<&Reading> = samples
                .iter()
                .map(|f| if clock { &f.clock } else { &f.damage })
                .filter(|r| r.value.is_some())
                .collect();
            (
                values.len() as f64 / samples.len() as f64,
                values.iter().map(|r| r.confidence).sum::<f64>() / values.len().max(1) as f64,
            )
        };
        let (clock_coverage, clock_confidence) = coverage(true);
        let (damage_coverage, damage_confidence) = coverage(false);
        let json = format!("{{\n  \"schema_version\":1,\n  \"video_id\":{},\n  \"attack\":{},\n  \"video_t_start\":{start_t:.1},\n  \"video_t_end\":{end_t:.1},\n  \"preparation_t_start\":{},\n  \"edited\":{},\n  \"cuts\":[{cuts}],\n  \"clock_series\":[\n    {clock_json}\n  ],\n  \"damage_series\":[\n    {damage_json}\n  ],\n  \"stars\":[{}],\n  \"deployments\":[\n    {event_json}\n  ],\n  \"hero_abilities\":[],\n  \"hero_ability_status\":\"unresolved: portrait greying alone cannot distinguish ability use from death\",\n  \"slots\":[{}],\n  \"keyframe\":{{\"path\":{},\"video_t\":{keyframe_t:.1},\"undamaged_hud\":{},\"base_visibility\":\"candidate_requires_visual_review\"}},\n  \"result_screen\":{result_json},\n  \"final_percent\":{},\n  \"final_stars\":{},\n  \"confidence\":{{\"clock_coverage\":{clock_coverage:.4},\"damage_coverage\":{damage_coverage:.4},\"mean_clock\":{clock_confidence:.4},\"mean_damage\":{damage_confidence:.4}}}\n}}\n", quoted(&video_id), number + 1, attack.prep_start.map(|i| format!("{:.1}", frames[i].t)).unwrap_or_else(|| "null".to_string()), !attack.cuts.is_empty(), star_json.join(","), slot_json.join(","), quoted(&keyframe_name), zero.is_some(), optional(final_damage), optional(final_stars));
        fs::write(out.join(format!("attack-{:02}.json", number + 1)), json)?;
        index.push_str(&format!("{}\t{}\t{start_t:.1}\t{end_t:.1}\t{:.1}\t{}\t{}\t{}\t{clock_coverage:.4}\t{damage_coverage:.4}\t{clock_confidence:.4}\t{damage_confidence:.4}\t{}\n", video_id, number + 1, end_t - start_t, optional(final_damage), optional(final_stars), events.len(), !attack.cuts.is_empty()));
    }
    fs::write(out.join("attacks.tsv"), index)?;
    for directory in [out.to_path_buf(), out.join("slots")] {
        if !directory.exists() {
            continue;
        }
        for entry in fs::read_dir(directory)? {
            let path = entry?.path();
            let name = path.file_name().unwrap_or_default().to_string_lossy();
            if let Some(rest) = name.strip_prefix("attack-") {
                if let Some(number) = rest
                    .split(['-', '.'])
                    .next()
                    .and_then(|s| s.parse::<usize>().ok())
                {
                    if number > attacks.len()
                        && matches!(
                            path.extension().and_then(|s| s.to_str()),
                            Some("json" | "jpg" | "ppm")
                        )
                    {
                        fs::remove_file(path)?;
                    }
                }
            }
        }
    }
    fs::write(
        out.join("slots.tsv"),
        format!(
            "slot\tx\ty\tw\th\tcount_x\tcount_y\tcount_w\tcount_h\n{}",
            slots
                .iter()
                .map(|s| format!(
                    "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
                    s.index,
                    s.rect.x,
                    s.rect.y,
                    s.rect.w,
                    s.rect.h,
                    s.count.x,
                    s.count.y,
                    s.count.w,
                    s.count.h
                ))
                .collect::<String>()
        ),
    )?;
    fs::write(out.join("run.json"), format!("{{\"video_id\":{},\"fps\":5,\"frames\":{},\"attacks\":{},\"elapsed_seconds\":{:.3},\"synthetic\":false,\"purpose\":\"video HUD observations; not real-game engine calibration\"}}\n", quoted(&video_id), frames.len(), attacks.len(), started.elapsed().as_secs_f64()))?;
    eprintln!(
        "{}: {} attacks in {:.1}s",
        video_id,
        attacks.len(),
        started.elapsed().as_secs_f64()
    );
    crate::icons::update(out, templates)?;
    crate::timing::update(out)?;
    crate::identity::video(video_path, out, templates)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(t: f64, clock: u32) -> Frame {
        Frame {
            t,
            phase: "attack",
            clock: Reading {
                value: Some(clock),
                confidence: 0.9,
                raw: String::new(),
            },
            damage: Reading::missing(),
            stars: Some(0),
            star_confidence: 1.0,
            slots: vec![],
            label_score: 1.0,
        }
    }

    #[test]
    fn separates_new_attack_and_keeps_internal_cut() {
        // Declared synthetic fixture: a 30-second omitted interval, then a
        // new battle. No image or game-calibration claims are made here.
        let mut frames: Vec<Frame> = (0..100)
            .map(|i| frame(i as f64 / 5.0, 180 - i / 5 - if i >= 50 { 30 } else { 0 }))
            .collect();
        frames.extend((0..50).map(|i| frame(20.0 + i as f64 / 5.0, 180 - i / 5)));
        let attacks = segment(&frames);
        assert_eq!(attacks.len(), 2);
        assert!(attacks[0]
            .cuts
            .iter()
            .any(|c| c.kind == "clock_discontinuity"));
    }

    #[test]
    fn brief_ocr_error_does_not_mark_a_cut() {
        let mut frames: Vec<Frame> = (0..100)
            .map(|i| frame(i as f64 / 5.0, 180 - i / 5))
            .collect();
        for f in &mut frames[45..48] {
            f.clock.value = Some(95);
        }
        let attacks = segment(&frames);
        assert_eq!(attacks.len(), 1);
        assert!(attacks[0].cuts.is_empty());
    }

    #[test]
    fn obscured_hud_keeps_one_battle_and_speed_is_separate_from_cuts() {
        // Declared synthetic 2x battle with an eight-second commentary overlay.
        let mut frames: Vec<_> = (0..250)
            .map(|i| frame(i as f64 / 5.0, 180 - i * 2 / 5))
            .collect();
        for f in &mut frames[70..110] {
            f.phase = "other";
            f.clock = Reading::missing();
        }
        let attacks = segment(&frames);
        assert_eq!(attacks.len(), 1);
        assert!(attacks[0].cuts.is_empty());
    }

    #[test]
    fn count_decrease_requires_agreement_and_never_crosses_a_cut() {
        let mut frames: Vec<Frame> = (0..60)
            .map(|i| frame(i as f64 / 5.0, 180 - i / 5))
            .collect();
        for (i, f) in frames.iter_mut().enumerate() {
            f.slots.push(Reading {
                value: Some(if i < 20 {
                    4
                } else if i < 40 {
                    3
                } else {
                    0
                }),
                confidence: 0.9,
                raw: String::new(),
            });
        }
        frames[10].slots[0].value = Some(0);
        for frame in &mut frames[25..30] {
            frame.slots[0].value = Some(31);
        }
        let attack = Attack {
            start: 0,
            end: 59,
            prep_start: None,
            cuts: vec![Cut {
                t: 8.0,
                before: Some(172),
                after: Some(140),
                kind: "clock_discontinuity",
            }],
        };
        let events = deployments(&frames, &attack);
        assert_eq!(events.len(), 1);
        assert_eq!((events[0].before, events[0].after), (4, 3));
    }

    #[test]
    fn json_escaping() {
        assert_eq!(quoted("a\"b\n\\c"), "\"a\\\"b\\n\\\\c\"");
    }
}

/// Rebuild intervals and events from saved observations; no replay decoding.
pub fn resegment(root: &Path) -> io::Result<()> {
    use crate::json::Value;
    let mut changes = String::from("video\tinput_attacks\tm2_attacks\n");
    for dir in crate::icons::directories(root)? {
        if fs::read_to_string(dir.join("regions.json"))?.contains("cropped_replay") {
            continue;
        }
        let paths = crate::icons::attack_paths(&dir)?;
        let old = paths
            .iter()
            .map(|p| Value::parse(&fs::read_to_string(p)?))
            .collect::<io::Result<Vec<_>>>()?;
        let mut frames = Vec::new();
        for line in fs::read_to_string(dir.join("readings.jsonl"))?.lines() {
            let f = Value::parse(line)?;
            let reading = |v: &Value| Reading {
                value: v.get("value").number().map(|v| v as u32),
                confidence: v.get("confidence").number().unwrap_or(0.0),
                raw: v.get("raw").string().unwrap_or("").into(),
            };
            let phase = match f.get("phase").string() {
                Some("attack") => "attack",
                Some("preparation") => "preparation",
                _ => "other",
            };
            frames.push(Frame {
                t: f.get("video_t").number().unwrap_or(0.0),
                phase,
                clock: reading(f.get("clock")),
                damage: reading(f.get("damage")),
                stars: f.get("stars").get("value").number().map(|v| v as u32),
                star_confidence: f.get("stars").get("confidence").number().unwrap_or(0.0),
                slots: f.get("slots").array().iter().map(reading).collect(),
                label_score: f.get("hud_confidence").number().unwrap_or(0.0),
            });
        }
        let attacks = segment(&frames);
        if old.is_empty() {
            continue;
        }
        changes.push_str(&format!(
            "{}\t{}\t{}\n",
            dir.file_name().unwrap().to_string_lossy(),
            old.len(),
            attacks.len()
        ));
        let mut index=String::from("video_id\tattack\tvideo_t_start\tvideo_t_end\tduration\tfinal_damage\tfinal_stars\tdeployments\tclock_coverage\tdamage_coverage\tmean_clock_confidence\tmean_damage_confidence\tedited\n");
        for (n, a) in attacks.iter().enumerate() {
            let start = frames[a.start].t;
            let end = frames[a.end].t;
            let sources: Vec<_> = old
                .iter()
                .filter(|v| {
                    v.get("video_t_start").number().unwrap_or(f64::MAX) <= end
                        && v.get("video_t_end").number().unwrap_or(0.0) >= start
                })
                .collect();
            let Some(first) = sources.first() else {
                continue;
            };
            let mut value = (*first).clone();
            value.set("attack", Value::from((n + 1) as f64));
            value.set("schema_version", Value::from(2.0));
            value.set("video_t_start", Value::from(start));
            value.set("video_t_end", Value::from(end));
            value.set(
                "preparation_t_start",
                a.prep_start
                    .map(|i| Value::from(frames[i].t))
                    .unwrap_or(Value::Null),
            );
            let provenance = sources.iter().map(|s| s.get("attack").clone()).collect();
            value.set("source_attack_fragments", Value::Array(provenance));
            let samples = &frames[a.start..=a.end];
            for (field, key, clock) in [
                ("clock_series", "clock_t", true),
                ("damage_series", "percent", false),
            ] {
                let series = samples
                    .iter()
                    .map(|f| {
                        let r = if clock { &f.clock } else { &f.damage };
                        Value::parse(&format!(
                            "{{\"video_t\":{:.1},\"{key}\":{},\"confidence\":{:.4}}}",
                            f.t,
                            optional(r.value),
                            r.confidence
                        ))
                    })
                    .collect::<io::Result<Vec<_>>>()?;
                value.set(field, Value::Array(series));
            }
            let events = deployments(&frames, a);
            value.set("deployments",Value::Array(events.iter().map(|e|Value::parse(&format!("{{\"clock_t\":{},\"video_t\":{:.1},\"slot\":{},\"count_before\":{},\"count_after\":{},\"delta\":{},\"confidence\":{:.4}}}",optional(e.clock),e.t,e.slot,e.before,e.after,e.before-e.after,e.confidence))).collect::<io::Result<_>>()?));
            let stars=samples.windows(2).scan(0,|old,w| {
                let mut earned=Vec::new();
                if let Some(next)=w[0].stars.filter(|s|*s>*old && w[1].stars.is_some_and(|v|v>=*s)) {
                    for star in *old+1..=next {earned.push(Value::parse(&format!("{{\"video_t\":{:.1},\"clock_t\":{},\"star\":{star},\"confidence\":{:.4}}}",w[0].t,optional(w[0].clock.value),w[0].star_confidence)));}
                    *old=next;
                }
                Some(earned)
            }).flatten().collect::<io::Result<Vec<_>>>()?;
            value.set("stars", Value::Array(stars));
            value.set("cuts",Value::Array(a.cuts.iter().map(|c|Value::parse(&format!("{{\"video_t\":{:.1},\"clock_before\":{},\"clock_after\":{},\"kind\":{}}}",c.t,optional(c.before),optional(c.after),quoted(c.kind)))).collect::<io::Result<_>>()?));
            if let Some(slots) = value.object_array_mut("slots") {
                for slot in slots {
                    if slot.get("count_box") != &Value::Null {
                        let id = slot.get("slot").number().unwrap_or(0.0) as usize;
                        slot.set(
                            "initial_count",
                            initial_count(&frames, a, id)
                                .map(|r| Value::from(r.0 as f64))
                                .unwrap_or(Value::Null),
                        );
                    }
                }
            }
            let final_damage = samples.iter().rev().find_map(|f| f.damage.value);
            let final_stars = samples.iter().rev().find_map(|f| f.stars);
            value.set(
                "final_percent",
                final_damage
                    .map(|v| Value::from(v as f64))
                    .unwrap_or(Value::Null),
            );
            value.set(
                "final_stars",
                final_stars
                    .map(|v| Value::from(v as f64))
                    .unwrap_or(Value::Null),
            );
            if let Some(last) = sources.last() {
                value.set("result_screen", last.get("result_screen").clone());
            }
            crate::timing::annotate(&mut value)?;
            let coverage = |clock: bool| {
                let readings: Vec<_> = samples
                    .iter()
                    .map(|f| if clock { &f.clock } else { &f.damage })
                    .filter(|r| r.value.is_some())
                    .collect();
                (
                    readings.len() as f64 / samples.len() as f64,
                    readings.iter().map(|r| r.confidence).sum::<f64>()
                        / readings.len().max(1) as f64,
                )
            };
            let (cc, cm) = coverage(true);
            let (dc, dm) = coverage(false);
            value.set("confidence",Value::parse(&format!("{{\"clock_coverage\":{cc:.4},\"damage_coverage\":{dc:.4},\"mean_clock\":{cm:.4},\"mean_damage\":{dm:.4}}}"))?);
            index.push_str(&format!("{}\t{}\t{start:.1}\t{end:.1}\t{:.1}\t{}\t{}\t{}\t{cc:.4}\t{dc:.4}\t{cm:.4}\t{dm:.4}\t{}\n",dir.file_name().unwrap().to_string_lossy(),n+1,end-start,optional(final_damage),optional(final_stars),events.len(),value.get("edited").encode()));
            fs::write(
                dir.join(format!("attack-{:02}.json", n + 1)),
                value.encode() + "\n",
            )?;
        }
        for path in paths {
            let n = path
                .file_stem()
                .and_then(|s| s.to_str())
                .and_then(|s| s.strip_prefix("attack-"))
                .and_then(|s| s.parse::<usize>().ok())
                .unwrap_or(0);
            if n > attacks.len() {
                fs::remove_file(path)?;
            }
        }
        fs::write(dir.join("attacks.tsv"), index)?;
        let run_path = dir.join("run.json");
        let mut run = Value::parse(&fs::read_to_string(&run_path)?)?;
        run.set("attacks", Value::from(attacks.len() as f64));
        run.set("segmentation_version", Value::from("m2"));
        fs::write(run_path, run.encode() + "\n")?;
    }
    fs::write(root.join("resegmentation.tsv"), changes)
}
