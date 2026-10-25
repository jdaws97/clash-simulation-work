use crate::image::{Mask, Rect};
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
}

pub fn match_score(mask: &Mask, template: &Mask, x: usize, y: usize, stride: usize) -> f64 {
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

fn search(mask: &Mask, template: &Mask, area: Rect) -> (Rect, f64) {
    let mut best = (Rect::new(area.x, area.y, template.w, template.h), 0.0);
    for y in (area.y..(area.y + area.h).min(mask.h - template.h)).step_by(2) {
        for x in (area.x..(area.x + area.w).min(mask.w - template.w)).step_by(2) {
            let score = match_score(mask, template, x, y, 2);
            if score > best.1 {
                best = (Rect::new(x, y, template.w, template.h), score);
            }
        }
    }
    let mut refined = best;
    for y in best.0.y.saturating_sub(2)..=(best.0.y + 2).min(mask.h - template.h) {
        for x in best.0.x.saturating_sub(2)..=(best.0.x + 2).min(mask.w - template.w) {
            let score = match_score(mask, template, x, y, 1);
            if score > refined.1 {
                refined = (Rect::new(x, y, template.w, template.h), score);
            }
        }
    }
    refined
}

fn resize(mask: &Mask, factor: f64) -> Mask {
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

pub fn locate(video_path: &Path, templates: &Path) -> io::Result<Regions> {
    let metadata = video::metadata(video_path)?;
    if metadata.width < 640 || metadata.height < 360 || metadata.duration <= 0.0 {
        return Err(io::Error::other("unsupported video dimensions or duration"));
    }
    let battle = Mask::load_text(&templates.join("battle-label.txt"))?;
    let damage = Mask::load_text(&templates.join("damage-label.txt"))?;
    let mut best = None;
    let mut best_score = 0.0;
    for t in [
        18.0,
        metadata.duration * 0.25,
        metadata.duration * 0.5,
        metadata.duration * 0.75,
        metadata.duration * 0.9,
    ] {
        let image = video::frame(video_path, t)?;
        let mask = Mask::white(&image, 145);
        for relative_scale in [1.0, 0.8, 1.2] {
            let scale = metadata.height as f64 / 720.0 * relative_scale;
            let b = resize(&battle, scale);
            let d = resize(&damage, scale);
            let (b_box, b_score) = search(
                &mask,
                &b,
                Rect::new(image.w / 3, 0, image.w / 3, image.h / 6),
            );
            let (d_box, d_score) = search(
                &mask,
                &d,
                Rect::new(image.w * 2 / 3, image.h / 3, image.w / 3, image.h / 2),
            );
            let score = b_score.min(d_score);
            if score > best_score {
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
                let rect = |dx: f64, dy: f64, w: f64, h: f64, origin: Rect| {
                    Rect::new(
                        (origin.x as f64 + dx * scale).round().max(0.0) as usize,
                        (origin.y as f64 + dy * scale).round().max(0.0) as usize,
                        (w * scale).round() as usize,
                        (h * scale).round() as usize,
                    )
                };
                let bar_y = (d_box.y as f64 + 66.0 * scale).round() as usize;
                best = Some(Regions {
                    width: image.w,
                    height: image.h,
                    duration: metadata.duration,
                    content: Rect::new(left, 0, right - left, image.h),
                    battle_label: b_box,
                    damage_label: d_box,
                    clock: rect(-14.0, 17.0, 128.0, 25.0, b_box),
                    damage: rect(65.0, 20.0, 81.0, 22.0, d_box),
                    stars: rect(-14.0, 17.0, 80.0, 30.0, d_box),
                    bar: Rect::new(left, bar_y, right - left, image.h - bar_y),
                    label_score: score,
                    sample_t: t,
                });
                best_score = score;
            }
        }
        if best_score > 0.94 {
            break;
        }
    }
    if best_score < 0.62 {
        return Err(io::Error::other(format!(
            "unsupported HUD: label match {best_score:.3} < 0.62; no regions guessed"
        )));
    }
    let regions = best.unwrap();
    eprintln!(
        "HUD match {:.3} at {:.1}s; content {}; clock {}; damage {}; bar {}",
        best_score,
        regions.sample_t,
        regions.content.json(),
        regions.clock.json(),
        regions.damage.json(),
        regions.bar.json()
    );
    Ok(regions)
}

impl Regions {
    pub fn json(&self) -> String {
        format!("{{\n  \"schema_version\": 1,\n  \"width\": {}, \"height\": {}, \"duration\": {:.3},\n  \"content\": {},\n  \"battle_label\": {},\n  \"clock\": {},\n  \"damage_label\": {},\n  \"damage\": {},\n  \"stars\": {},\n  \"troop_bar\": {},\n  \"label_match\": {:.4}, \"sample_video_t\": {:.3},\n  \"method\": \"thresholded glyph edge template search at three scales; black-column content detection\",\n  \"coordinate_format\": \"[x, y, width, height], source pixels\"\n}}\n", self.width, self.height, self.duration, self.content.json(), self.battle_label.json(), self.clock.json(), self.damage_label.json(), self.damage.json(), self.stars.json(), self.bar.json(), self.label_score, self.sample_t)
    }
}
