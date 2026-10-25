use crate::image::{Image, Mask, Rect};
use crate::video;
use std::io;
use std::path::Path;

#[derive(Clone)]
pub struct Regions {
    pub width: usize,
    pub height: usize,
    pub duration: f64,
    pub content: Rect,
    pub battle_label: Rect,
    pub damage_label: Rect,
    pub clock: Rect,
    pub damage: Rect,
    pub stars: Rect,
    pub bar: Rect,
    pub label_score: f64,
    pub sample_t: f64,
    pub layout: &'static str,
    pub battle_template: String,
    pub damage_template: String,
}

pub fn match_score(mask: &Mask, template: &Mask, x: usize, y: usize, stride: usize) -> f64 {
    if x + template.w > mask.w || y + template.h > mask.h {
        return 0.0;
    }
    let mut intersection = 0;
    let mut total = 0;
    for ty in (0..template.h).step_by(stride) {
        for tx in (0..template.w).step_by(stride) {
            let a = template.data[ty * template.w + tx];
            let b = mask.data[(y + ty) * mask.w + x + tx];
            intersection += (a & b) as usize;
            total += (a + b) as usize;
        }
    }
    if total == 0 {
        return 0.0;
    }
    intersection as f64 * 2.0 / total as f64
}

pub fn search(mask: &Mask, template: &Mask, area: Rect) -> (Rect, f64) {
    let mut best = (Rect::new(area.x, area.y, template.w, template.h), 0.0);
    let mut candidates = Vec::new();
    if template.w >= mask.w || template.h >= mask.h {
        return best;
    }
    let landmarks: Vec<_> = template
        .data
        .iter()
        .enumerate()
        .filter(|(_, v)| **v != 0)
        .step_by((template.data.iter().filter(|v| **v != 0).count() / 12).max(1))
        .take(12)
        .map(|(i, _)| (i % template.w, i / template.w))
        .collect();
    for y in (area.y..=(area.y + area.h).min(mask.h - template.h)).step_by(2) {
        for x in (area.x..=(area.x + area.w).min(mask.w - template.w)).step_by(2) {
            let hits = landmarks
                .iter()
                .filter(|(tx, ty)| mask.data[(y + ty) * mask.w + x + tx] != 0)
                .count();
            if hits < 3 {
                continue;
            }
            let score = match_score(mask, template, x, y, 2);
            if score > best.1 {
                best = (Rect::new(x, y, template.w, template.h), score);
            }
            if candidates.len() < 16
                || score > candidates.last().map(|c: &(Rect, f64)| c.1).unwrap_or(0.0)
            {
                candidates.push((Rect::new(x, y, template.w, template.h), score));
                candidates.sort_by(|a, b| b.1.total_cmp(&a.1));
                candidates.truncate(16);
            }
        }
    }
    let mut refined = (best.0, match_score(mask, template, best.0.x, best.0.y, 1));
    for (candidate, _) in candidates {
        for y in candidate.y.saturating_sub(3)..=(candidate.y + 3).min(mask.h - template.h) {
            for x in candidate.x.saturating_sub(3)..=(candidate.x + 3).min(mask.w - template.w) {
                let score = match_score(mask, template, x, y, 1);
                if score > refined.1 {
                    refined = (Rect::new(x, y, template.w, template.h), score);
                }
            }
        }
    }
    refined
}

pub fn resize(mask: &Mask, factor: f64) -> Mask {
    let w = (mask.w as f64 * factor).round().max(1.0) as usize;
    let h = (mask.h as f64 * factor).round().max(1.0) as usize;
    let mut data = vec![0; w * h];
    for y in 0..h {
        for x in 0..w {
            data[y * w + x] = mask.data[(y * mask.h / h) * mask.w + x * mask.w / w];
        }
    }
    Mask { w, h, data }
}

fn best_label(
    mask: &Mask,
    templates: &Path,
    names: &[&str],
    area: Rect,
    nominal: f64,
) -> io::Result<(Rect, f64, String)> {
    let mut best = (Rect::default(), 0.0, String::new());
    for name in names {
        let path = templates.join(name);
        if !path.exists() {
            continue;
        }
        let original = Mask::load_text(&path)?;
        for step in 11..=29 {
            let factor = nominal * step as f64 / 20.0;
            let template = resize(&original, factor);
            let (rect, score) = search(mask, &template, area);
            if score > best.1 {
                best = (rect, score, name.to_string());
            }
        }
    }
    Ok(best)
}

pub fn content(image: &Image) -> Rect {
    let occupied = |x: usize| {
        (0..image.h)
            .step_by(8)
            .filter(|y| image.pixel(x, *y).iter().any(|v| *v > 20))
            .count()
            > image.h / 32
    };
    let left = (0..image.w / 3).find(|x| occupied(*x)).unwrap_or(0);
    let right = (image.w * 2 / 3..image.w)
        .rev()
        .find(|x| occupied(*x))
        .unwrap_or(image.w - 1)
        + 1;
    Rect::new(left, 0, right - left, image.h)
}

pub fn locate(video_path: &Path, templates: &Path) -> io::Result<Regions> {
    let metadata = video::metadata(video_path)?;
    if metadata.width < 640 || metadata.height < 360 || metadata.duration <= 0.0 {
        return Err(io::Error::other("unsupported video dimensions or duration"));
    }
    let mut best = None;
    let mut best_score = 0.0;
    for t in [
        18.0,
        120.0_f64.min(metadata.duration * 0.3),
        180.0_f64.min(metadata.duration * 0.4),
        metadata.duration * 0.25,
        metadata.duration * 0.5,
        metadata.duration * 0.75,
        metadata.duration * 0.9,
    ] {
        let image = video::frame(video_path, t)?;
        let mask = Mask::white(&image, 145);
        let nominal = metadata.height as f64 / 720.0;
        let (b_box, b_score, b_name) = best_label(
            &mask,
            templates,
            &[
                "battle-label.txt",
                "battle-phone-label.txt",
                "battle-q-label.txt",
            ],
            Rect::new(image.w / 4, 0, image.w / 2, image.h / 4),
            nominal,
        )?;
        let (d_box, d_score, d_name) = best_label(
            &mask,
            templates,
            &[
                "damage-label.txt",
                "damage-phone-label.txt",
                "damage-modern-label.txt",
            ],
            Rect::new(image.w * 2 / 3, image.h / 3, image.w / 3, image.h * 2 / 3),
            nominal,
        )?;
        let score = b_score.min(d_score);
        eprintln!("probe {t:.1}s: clock label {b_score:.3}, damage label {d_score:.3}");
        if score > best_score {
            let scale = b_box.h as f64 / 12.0;
            let ds = d_box.h as f64 / 12.0;
            let bounds = content(&image);
            let rect = |dx: f64, dy: f64, w: f64, h: f64, origin: Rect, s: f64| {
                Rect::new(
                    (origin.x as f64 + dx * s).round().max(0.0) as usize,
                    (origin.y as f64 + dy * s).round().max(0.0) as usize,
                    (w * s).round() as usize,
                    (h * s).round() as usize,
                )
            };
            let bar_y = (d_box.y as f64 + 66.0 * ds).round() as usize;
            if bar_y >= image.h {
                continue;
            }
            let layout = if bounds.w as f64 / image.h as f64 > 1.65 {
                "phone_single_row"
            } else {
                "tablet_two_rows"
            };
            best = Some(Regions {
                width: image.w,
                height: image.h,
                duration: metadata.duration,
                content: bounds,
                battle_label: b_box,
                damage_label: d_box,
                clock: rect(-14.0, 17.0, 128.0, 25.0, b_box, scale),
                damage: rect(65.0, 20.0, 81.0, 22.0, d_box, ds),
                stars: rect(-14.0, 17.0, 80.0, 30.0, d_box, ds),
                bar: Rect::new(bounds.x, bar_y, bounds.w, image.h - bar_y),
                label_score: score,
                sample_t: t,
                layout,
                battle_template: b_name,
                damage_template: d_name,
            });
            best_score = score;
        }
        if best_score > 0.94 {
            break;
        }
    }
    if best_score < 0.62 {
        // Cropped replays have an independently moving clock and no visible bar.
        let replay_path = templates.join("replay-label.txt");
        if replay_path.exists() {
            let template = Mask::load_text(&replay_path)?;
            for t in [90.0, metadata.duration * 0.4, metadata.duration * 0.7] {
                let image = video::frame(video_path, t.min(metadata.duration - 0.1))?;
                let mask = Mask::white(&image, 145);
                let mut found = (Rect::default(), 0.0);
                for step in 12..=28 {
                    let scaled = resize(
                        &template,
                        step as f64 / 20.0 * metadata.height as f64 / 720.0,
                    );
                    let candidate = search(
                        &mask,
                        &scaled,
                        Rect::new(0, image.h / 2, image.w, image.h / 2),
                    );
                    if candidate.1 > found.1 {
                        found = candidate;
                    }
                }
                if found.1 < 0.72 {
                    continue;
                }
                let r = found.0;
                let s = r.h as f64 / template.h as f64;
                return Ok(Regions {
                    width: image.w,
                    height: image.h,
                    duration: metadata.duration,
                    content: content(&image),
                    battle_label: r,
                    clock: Rect::new(
                        r.x.saturating_sub((20.0 * s) as usize),
                        r.y + r.h,
                        (190.0 * s) as usize,
                        (45.0 * s) as usize,
                    ),
                    damage_label: Rect::default(),
                    damage: Rect::default(),
                    stars: Rect::default(),
                    bar: Rect::default(),
                    label_score: found.1,
                    sample_t: t,
                    layout: "cropped_replay",
                    battle_template: "replay-label.txt".into(),
                    damage_template: String::new(),
                });
            }
        }
        return Err(io::Error::other(format!(
            "unsupported HUD: label match {best_score:.3} < 0.62; no regions guessed"
        )));
    }
    let regions = best.unwrap();
    eprintln!(
        "HUD match {:.3} at {:.1}s; {}; clock {}; damage {}; bar {}",
        best_score,
        regions.sample_t,
        regions.layout,
        regions.clock.json(),
        regions.damage.json(),
        regions.bar.json()
    );
    Ok(regions)
}

impl Regions {
    pub fn json(&self) -> String {
        format!("{{\n\"schema_version\":2,\"width\":{},\"height\":{},\"duration\":{:.3},\n\"content\":{},\"battle_label\":{},\"clock\":{},\"damage_label\":{},\"damage\":{},\"stars\":{},\"troop_bar\":{},\n\"layout\":\"{}\",\"battle_template\":\"{}\",\"damage_template\":\"{}\",\"label_match\":{:.4},\"sample_video_t\":{:.3},\n\"method\":\"independent label search at 19 scales, phone/tablet geometry; moving cropped replay clock fallback\",\"coordinate_format\":\"[x,y,width,height], source pixels\"\n}}\n",self.width,self.height,self.duration,self.content.json(),self.battle_label.json(),self.clock.json(),self.damage_label.json(),self.damage.json(),self.stars.json(),self.bar.json(),self.layout,self.battle_template,self.damage_template,self.label_score,self.sample_t)
    }
}
