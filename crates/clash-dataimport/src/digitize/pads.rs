//! Cyan footprint proposals and local snap diagnostics. Proposals carry scores;
//! they are never promoted to measured building identities automatically.
use super::buildings::footprint;
use super::fit::Grid;
use clash_data::json::Json;
use clash_data::wire::{arr, num, obj};
use clash_layout::geometry::Tiles;
use clash_layout::model::Tile;
use clash_layout::render::Image;
use std::collections::BTreeSet;

type Pixel = (i32, i32);
pub struct CyanPads {
    mask: BTreeSet<Pixel>,
    width: i32,
    height: i32,
    grid: Grid,
}
impl CyanPads {
    pub fn new(image: &Image, grid: Grid) -> Self {
        let mut mask = BTreeSet::new();
        for y in 0..image.height as i32 {
            for x in 0..image.width as i32 {
                let [r, g, b] = image.get(x, y).expect("bounded pixel").map(i32::from);
                if g > 135 && b > 150 && r < 130 && g - r > 60 {
                    // scipy binary_dilation(iterations=2), cross connectivity.
                    for dx in -2_i32..=2 {
                        for dy in -2_i32..=2 {
                            if dx.abs() + dy.abs() <= 2 {
                                mask.insert((x + dx, y + dy));
                            }
                        }
                    }
                }
            }
        }
        Self {
            mask,
            width: image.width as i32,
            height: image.height as i32,
            grid,
        }
    }
    fn fraction(&self, p: (f64, f64), q: (f64, f64), t0: f64, t1: f64, samples: usize) -> f64 {
        let mut seen = 0;
        let mut hits = 0;
        for i in 0..samples {
            let t = t0 + (t1 - t0) * i as f64 / (samples - 1) as f64;
            let x = p.0 + t * (q.0 - p.0);
            let y = p.1 + t * (q.1 - p.1);
            if x >= 0.0 && y >= 0.0 && x < f64::from(self.width) && y < f64::from(self.height) {
                seen += 1;
                hits += usize::from(self.mask.contains(&(x as i32, y as i32)));
            }
        }
        if seen < samples / 2 {
            0.0
        } else {
            hits as f64 / seen as f64
        }
    }
    /// snap.py's lower-V score, penalizing edges that continue past the corner.
    pub fn score(&self, (x, y): Tile, size: i32) -> f64 {
        let (x, y, s) = (f64::from(x), f64::from(y), f64::from(size));
        let p = |x, y| self.grid.project(x, y);
        let left = self.fraction(p(x, y + s), p(x + s, y + s), 0.1, 0.9, 20);
        let right = self.fraction(p(x + s, y + s), p(x + s, y), 0.1, 0.9, 20);
        let extra_left = self.fraction(p(x - 0.2, y + s), p(x - 0.8, y + s), 0.0, 1.0, 6);
        let extra_right = self.fraction(p(x + s, y - 0.2), p(x + s, y - 0.8), 0.0, 1.0, 6);
        (left + right) / 2.0 - 0.25 * (extra_left + extra_right)
    }
    pub fn snap(&self, position: Tile, size: i32) -> (Tile, f64) {
        let mut best = position;
        let mut score = self.score(position, size);
        let mut displacement = 0;
        for dx in -2_i32..=2 {
            for dy in -2_i32..=2 {
                let p = (position.0 + dx, position.1 + dy);
                if p.0 < 0 || p.1 < 0 || p.0 + size > 44 || p.1 + size > 44 {
                    continue;
                }
                let candidate = self.score(p, size);
                let distance = dx.abs() + dy.abs();
                if candidate > score || (candidate == score && distance < displacement) {
                    best = p;
                    score = candidate;
                    displacement = distance;
                }
            }
        }
        (best, score)
    }
    pub fn proposals(&self, occupied: &Tiles, threshold: f64) -> Json {
        let mut candidates = Vec::new();
        for size in 2..=4 {
            for x in 0..=44 - size {
                for y in 0..=44 - size {
                    let score = self.score((x, y), size);
                    if score >= threshold {
                        candidates.push((score, size, (x, y)));
                    }
                }
            }
        }
        candidates.sort_by(|a, b| {
            b.0.total_cmp(&a.0)
                .then_with(|| b.1.cmp(&a.1))
                .then_with(|| b.2.cmp(&a.2))
        });
        let mut taken = occupied.clone();
        let mut result = Vec::new();
        for (score, size, position) in candidates {
            let tiles = footprint(position, size);
            if !tiles.is_disjoint(&taken) {
                continue;
            }
            taken.extend(tiles);
            result.push(obj([
                ("size", num(size)),
                ("position", super::buildings::tile_json(position)),
                ("score", num(score)),
            ]));
        }
        arr(result)
    }
}
