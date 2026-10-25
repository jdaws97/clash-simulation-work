//! Small reviewed RGB sprite features normalized in fitted village tile units.
use crate::grid::Grid;
use crate::image::Image;
use crate::json::Value;
use std::fs;
use std::io;
use std::path::Path;

const WIDTH: usize = 20;
const HEIGHT: usize = 28;
// Development cutoffs selected on inspected M4 references, not held-out data.
const MAX_ERROR: f64 = 0.22;
const MIN_MARGIN: f64 = 0.008;

pub struct Sprite {
    level: u32,
    pixels: Vec<u8>,
    pub source: String,
}

pub struct Library {
    sprites: Vec<Sprite>,
}

pub struct Classification {
    pub level: Option<u32>,
    pub center: (f64, f64),
    pub score: f64,
    pub margin: f64,
    pub source: String,
    pub candidates: Vec<(u32, f64, (f64, f64))>,
    library_fingerprint: String,
}

fn feature(image: &Image, grid: Grid, center: (f64, f64)) -> Option<Vec<u8>> {
    let mut result = Vec::with_capacity(WIDTH * HEIGHT * 3);
    for y in 0..HEIGHT {
        for x in 0..WIDTH {
            let sx = center.0 + (x as f64 / (WIDTH - 1) as f64 - 0.5) * 9.0 * grid.a;
            let sy = center.1 + (y as f64 / (HEIGHT - 1) as f64 * 10.0 - 8.0) * grid.b;
            if sx < 0.0 || sy < 0.0 || sx >= image.w as f64 || sy >= image.h as f64 {
                return None;
            }
            result.extend(image.pixel(sx as usize, sy as usize));
        }
    }
    Some(result)
}

fn distance(a: &[u8], b: &[u8], stride: usize) -> f64 {
    let mut error = 0.0;
    let mut count = 0;
    let mut sum_a = 0.0;
    let mut sum_b = 0.0;
    let mut squared_a = 0.0;
    let mut squared_b = 0.0;
    let mut product = 0.0;
    for y in (1..HEIGHT - 2).step_by(stride) {
        for x in (2..WIDTH - 2).step_by(stride) {
            // Ignore the rectangular crop's extreme upper corners and outer
            // ground, which mostly contain neighboring sprites.
            if y < 6 && !(5..WIDTH - 5).contains(&x) {
                continue;
            }
            let i = (y * WIDTH + x) * 3;
            error += (0..3)
                .map(|c| (a[i + c] as f64 - b[i + c] as f64).abs())
                .sum::<f64>()
                / 765.0;
            for c in 0..3 {
                let av = a[i + c] as f64 / 255.0;
                let bv = b[i + c] as f64 / 255.0;
                sum_a += av;
                sum_b += bv;
                squared_a += av * av;
                squared_b += bv * bv;
                product += av * bv;
            }
            count += 1;
        }
    }
    let n = (count * 3).max(1) as f64;
    let variance_a = (squared_a - sum_a * sum_a / n).max(0.0001);
    let variance_b = (squared_b - sum_b * sum_b / n).max(0.0001);
    let correlation =
        ((product - sum_a * sum_b / n) / (variance_a * variance_b).sqrt()).clamp(-1.0, 1.0);
    error / count.max(1) as f64 * 0.4 + (1.0 - correlation) * 0.3
}

pub fn learn(
    image: &Image,
    grid: Grid,
    center: (f64, f64),
    level: u32,
    source: &str,
    directory: &Path,
) -> io::Result<()> {
    if !(16..=18).contains(&level) {
        return Err(io::Error::other(
            "M4 TH library supports manually labeled TH16, TH17 and TH18 only",
        ));
    }
    let pixels = feature(image, grid, center)
        .ok_or_else(|| io::Error::other("TH training sprite is clipped"))?;
    fs::create_dir_all(directory)?;
    let safe: String = source
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect();
    let text = format!(
        "{level}\n{source}\n{}\n",
        pixels
            .iter()
            .map(u8::to_string)
            .collect::<Vec<_>>()
            .join(" ")
    );
    fs::write(directory.join(format!("th{level}-{safe}.rgb")), text)
}

impl Library {
    pub fn load(directory: &Path) -> io::Result<Self> {
        let mut sprites = Vec::new();
        for path in fs::read_dir(directory)? {
            let path = path?.path();
            if path.extension().is_none_or(|s| s != "rgb") {
                continue;
            }
            let text = fs::read_to_string(&path)?;
            let mut lines = text.lines();
            let level = lines
                .next()
                .and_then(|s| s.parse::<u32>().ok())
                .filter(|n| (16..=18).contains(n))
                .ok_or_else(|| io::Error::other("invalid TH sprite label"))?;
            let source = lines.next().unwrap_or_default().to_owned();
            let pixels = lines
                .flat_map(str::split_whitespace)
                .map(|s| s.parse::<u8>().map_err(io::Error::other))
                .collect::<io::Result<Vec<_>>>()?;
            if pixels.len() != WIDTH * HEIGHT * 3 {
                return Err(io::Error::other("invalid TH sprite feature length"));
            }
            sprites.push(Sprite {
                level,
                pixels,
                source,
            });
        }
        sprites.sort_by(|a, b| a.source.cmp(&b.source));
        if sprites.is_empty() {
            return Err(io::Error::other("TH sprite library is empty"));
        }
        Ok(Self { sprites })
    }

    pub fn classify(
        &self,
        image: &Image,
        grid: Grid,
        exclude_source: Option<&str>,
    ) -> Classification {
        let mut coarse = Vec::new();
        for x in 4..86 {
            for y in 4..86 {
                let center = grid.project(x as f64 / 2.0, y as f64 / 2.0);
                let Some(pixels) = feature(image, grid, center) else {
                    continue;
                };
                for level in 16..=18 {
                    let error = self
                        .sprites
                        .iter()
                        .filter(|s| s.level == level && exclude_source != Some(s.source.as_str()))
                        .map(|s| distance(&pixels, &s.pixels, 1))
                        .min_by(f64::total_cmp)
                        .unwrap_or(1.0);
                    coarse.push((error, x as f64 / 2.0, y as f64 / 2.0, level));
                }
            }
        }
        coarse.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut best: Vec<(u32, f64, (f64, f64), String)> = Vec::new();
        for level in 16..=18 {
            let mut candidates: Vec<(f64, f64, f64, u32)> = Vec::new();
            for candidate in coarse.iter().filter(|c| c.3 == level) {
                if candidates
                    .iter()
                    .all(|p| (p.1 - candidate.1).hypot(p.2 - candidate.2) >= 1.0)
                {
                    candidates.push(*candidate);
                    if candidates.len() == 30 {
                        break;
                    }
                }
            }
            let mut current = (level, 1.0, (0.0, 0.0), String::new());
            for (_, x, y, _) in candidates.drain(..) {
                for dx in -2..=2 {
                    for dy in -2..=2 {
                        let center = grid.project(x + dx as f64 * 0.25, y + dy as f64 * 0.25);
                        for scale in [0.85, 0.94, 1.0, 1.06, 1.15] {
                            let scaled = Grid {
                                a: grid.a * scale,
                                b: grid.b * scale,
                                ..grid
                            };
                            let Some(pixels) = feature(image, scaled, center) else {
                                continue;
                            };
                            for sprite in self.sprites.iter().filter(|s| {
                                s.level == level && exclude_source != Some(s.source.as_str())
                            }) {
                                let error = distance(&pixels, &sprite.pixels, 1);
                                if error < current.1 {
                                    current = (level, error, center, sprite.source.clone());
                                }
                            }
                        }
                    }
                }
            }
            best.push(current);
        }
        best.sort_by(|a, b| a.1.total_cmp(&b.1));
        let winner = &best[0];
        let margin = best[1].1 - winner.1;
        Classification {
            level: (winner.1 < MAX_ERROR && margin >= MIN_MARGIN).then_some(winner.0),
            center: winner.2,
            score: winner.1,
            margin,
            source: winner.3.clone(),
            candidates: best.iter().map(|c| (c.0, c.1, c.2)).collect(),
            library_fingerprint: self.fingerprint(),
        }
    }

    fn fingerprint(&self) -> String {
        let mut hash = 0xcbf29ce484222325_u64;
        for sprite in &self.sprites {
            for byte in sprite
                .source
                .bytes()
                .chain([sprite.level as u8])
                .chain(sprite.pixels.iter().copied())
            {
                hash ^= byte as u64;
                hash = hash.wrapping_mul(0x100000001b3);
            }
        }
        format!("fnv1a64-th-features:{hash:016x}")
    }
}

impl Classification {
    pub fn json(&self) -> Value {
        let mut value = Value::Object(Default::default());
        value.set(
            "status",
            if self.level.is_some() {
                "sprite_match_development_classifier"
            } else {
                "unknown_weak_or_ambiguous_sprite"
            }
            .into(),
        );
        value.set("method", "full keyframe search of reviewed 20x28 RGB features in fitted tile units; TH16-18 only; scores are not probabilities".into());
        value.set("error", self.score.into());
        value.set("winner_margin", self.margin.into());
        value.set("maximum_error", MAX_ERROR.into());
        value.set("minimum_margin", MIN_MARGIN.into());
        value.set(
            "library_fingerprint",
            self.library_fingerprint.as_str().into(),
        );
        value.set("template_source", self.source.as_str().into());
        value.set(
            "screen_center",
            Value::Array(vec![self.center.0.into(), self.center.1.into()]),
        );
        value.set(
            "candidates",
            Value::Array(
                self.candidates
                    .iter()
                    .map(|c| {
                        Value::Array(vec![
                            (c.0 as f64).into(),
                            c.1.into(),
                            c.2 .0.into(),
                            c.2 .1.into(),
                        ])
                    })
                    .collect(),
            ),
        );
        value
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_sprite_features_are_invariant_to_grid_and_image_scale() {
        // Declared synthetic colored sprite, not a game Town Hall or accuracy sample.
        let mut image = Image::blank(320, 240);
        for y in 0..240 {
            for x in 0..320 {
                let index = (y * 320 + x) * 3;
                image.data[index..index + 3].copy_from_slice(&[
                    ((x * 17 + y * 3) % 230) as u8,
                    ((x * 5 + y * 19) % 220) as u8,
                    ((x * 13 + y * 7) % 210) as u8,
                ]);
            }
        }
        let grid = Grid {
            cx: 160.0,
            top: -30.0,
            a: 8.0,
            b: 6.0,
            residual: 0.0,
            landmarks: 0,
        };
        let normal = feature(&image, grid, (160.0, 160.0)).unwrap();
        let enlarged = crate::spatial::resize(&image, 640);
        let scaled = feature(&enlarged, grid.scaled(2.0), (320.0, 320.0)).unwrap();
        assert_eq!(normal, scaled);
        assert!(distance(&normal, &scaled, 1) < 1e-8);
        assert!(distance(&normal, &vec![80; normal.len()], 1) > 0.1);
    }
}
