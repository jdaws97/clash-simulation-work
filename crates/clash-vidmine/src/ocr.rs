use crate::image::{Image, Mask};
use std::fs;
use std::io;
use std::path::Path;

#[derive(Clone, Debug)]
pub struct Reading {
    pub value: Option<u32>,
    pub confidence: f64,
    pub raw: String,
}

impl Reading {
    pub fn missing() -> Self {
        Self {
            value: None,
            confidence: 0.0,
            raw: String::new(),
        }
    }
}

pub struct Reader {
    templates: Vec<(String, char, Mask)>,
}

impl Reader {
    pub fn count_prefix(&self, glyph: &Mask) -> bool {
        let normalized = glyph.normalized();
        self.templates
            .iter()
            .filter(|(kind, label, _)| kind == "count" && *label == 'x')
            .any(|(_, _, template)| normalized.distance(template) < 0.29)
    }
    pub fn load(root: &Path) -> io::Result<Self> {
        let mut paths = fs::read_dir(root)?
            .map(|entry| entry.map(|e| e.path()))
            .collect::<io::Result<Vec<_>>>()?;
        paths.sort();
        let mut templates = Vec::new();
        for path in paths {
            let name = path.file_stem().unwrap().to_string_lossy();
            let parts: Vec<&str> = name.split('-').collect();
            if parts.len() >= 3 && parts[1].len() == 1 {
                templates.push((
                    parts[0].to_string(),
                    parts[1].chars().next().unwrap(),
                    Mask::load_text(&path)?,
                ));
            }
        }
        if templates.is_empty() {
            return Err(io::Error::other("no glyph templates"));
        }
        Ok(Self { templates })
    }

    fn digit(&self, glyph: &Mask, kind: &str) -> (char, f64) {
        if glyph.w as f64 / (glyph.h as f64) < 0.50 {
            return ('1', 0.90);
        }
        let normalized = glyph.normalized();
        let mut scores = [1.0_f64; 10];
        for (family, label, template) in &self.templates {
            if family == kind || kind == "count" && family == "damage" {
                if let Some(digit) = label.to_digit(10) {
                    scores[digit as usize] =
                        scores[digit as usize].min(normalized.distance(template));
                }
            }
        }
        let mut order: Vec<(usize, f64)> = scores.into_iter().enumerate().collect();
        order.sort_by(|a, b| a.1.total_cmp(&b.1));
        let (digit, distance) = order[0];
        let margin = order[1].1 - distance;
        let confidence = (1.0 - distance * 2.5).clamp(0.0, 1.0) * (0.65 + (margin * 3.0).min(0.35));
        (char::from_digit(digit as u32, 10).unwrap(), confidence)
    }

    pub fn clock(&self, image: &Image) -> Reading {
        let primary = self.clock_at(image, 175);
        if primary.value.is_some() {
            return primary;
        }
        let mut best = primary;
        for threshold in [195, 215] {
            let reading = self.clock_at(image, threshold);
            if reading.value.is_some()
                && (best.value.is_none() || reading.confidence > best.confidence)
            {
                best = reading;
            }
        }
        best
    }

    fn clock_at(&self, image: &Image, threshold: u8) -> Reading {
        let mask = Mask::white(image, threshold).keep_components(
            (image.h as f64 * 0.40) as usize,
            image.h + 3,
            12,
        );
        let glyphs = mask.glyphs();
        if !(2..=5).contains(&glyphs.len()) {
            return Reading::missing();
        }
        let mut digits = String::new();
        let mut confidence: f64 = 1.0;
        let has_minutes = glyphs.len() >= 4
            && (glyphs[1].1.w as f64 / glyphs[1].1.h as f64 > 1.05
                || self.templates.iter().any(|(family, label, template)| {
                    family == "clock"
                        && *label == 'm'
                        && template.distance(&glyphs[1].1.normalized()) <= 0.20
                }));
        if glyphs.len() >= 4 && !has_minutes {
            return Reading::missing();
        }
        for (i, (_, glyph)) in glyphs.iter().enumerate() {
            if i == glyphs.len() - 1 || has_minutes && i == 1 {
                continue;
            }
            let (digit, score) = self.digit(glyph, "clock");
            digits.push(digit);
            confidence = confidence.min(score);
        }
        let value = if has_minutes {
            let minutes = digits[..1].parse::<u32>().ok();
            let seconds = digits[1..].parse::<u32>().ok();
            minutes
                .zip(seconds)
                .filter(|(m, s)| *m <= 3 && *s < 60)
                .map(|(m, s)| m * 60 + s)
        } else {
            digits.parse::<u32>().ok().filter(|v| *v < 60)
        };
        let raw = if has_minutes {
            format!("{}m{}s", &digits[..1], &digits[1..])
        } else {
            format!("{digits}s")
        };
        Reading {
            value: value.filter(|_| confidence >= 0.52),
            confidence,
            raw,
        }
    }

    pub fn percent(&self, image: &Image, green: bool) -> Reading {
        let mask = if green {
            let data = image
                .data
                .chunks_exact(3)
                .map(|p| {
                    u8::from(
                        p[1] > 130
                            && p[1] > p[0].saturating_add(15)
                            && p[1] > p[2].saturating_add(15),
                    )
                })
                .collect();
            Mask {
                w: image.w,
                h: image.h,
                data,
            }
        } else {
            Mask::white(image, 170).keep_components(
                (image.h as f64 * 0.40) as usize,
                image.h + 3,
                10,
            )
        };
        let glyphs = mask.glyphs();
        if !(2..=4).contains(&glyphs.len()) {
            return Reading::missing();
        }
        let mut raw = String::new();
        let mut confidence: f64 = 1.0;
        for (_, glyph) in &glyphs[..glyphs.len() - 1] {
            let (digit, score) = self.digit(glyph, "damage");
            raw.push(digit);
            confidence = confidence.min(score);
        }
        let value = raw
            .parse::<u32>()
            .ok()
            .filter(|v| *v <= 100 && confidence >= 0.50);
        raw.push('%');
        Reading {
            value,
            confidence,
            raw,
        }
    }

    pub fn count(&self, image: &Image) -> Reading {
        // Empty cards retain a dim x0. The lower threshold reads that printed zero
        // rather than treating an unreadable or occluded card as an empty slot.
        let mut best = Reading::missing();
        let height = image.h.min(12);
        for y in 0..=image.h.saturating_sub(height) {
            let window = image.crop(crate::image::Rect::new(0, y, image.w, height));
            for threshold in [175, 145, 115, 95, 75] {
                let candidate = self.count_at(&window, threshold);
                if candidate.value.is_some() && candidate.confidence > best.confidence {
                    best = candidate;
                }
            }
        }
        best
    }

    fn count_at(&self, image: &Image, threshold: u8) -> Reading {
        let mask = Mask::white(image, threshold);
        let mut glyphs = mask.glyphs();
        // A selected card has a thin white border next to the printed count.
        // Unlike a numeral, that stroke spans the entire text window.
        glyphs.retain(|(rect, _)| !(rect.w <= 3 && rect.h == image.h));
        if !(2..=3).contains(&glyphs.len()) {
            return Reading::missing();
        }
        if !self.count_prefix(&glyphs[0].1) {
            return Reading::missing();
        }
        if glyphs[1..]
            .iter()
            .any(|(r, _)| r.h < 9 || r.h >= image.h || r.w < 2)
        {
            return Reading::missing();
        }
        let mut raw = String::new();
        let mut confidence: f64 = 1.0;
        for (_, glyph) in &glyphs[1..] {
            let (digit, score) = self.digit(glyph, "count");
            raw.push(digit);
            confidence = confidence.min(score);
        }
        let value = raw
            .parse::<u32>()
            .ok()
            .filter(|v| *v <= 99 && confidence >= 0.47);
        Reading {
            value,
            confidence,
            raw: format!("x{raw}"),
        }
    }
}
