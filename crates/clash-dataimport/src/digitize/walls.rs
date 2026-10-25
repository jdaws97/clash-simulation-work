//! Wall cap/body detectors and explicit manual wall editing.
use super::fit::Grid;
use clash_layout::geometry::{groups, Tiles};
use clash_layout::model::Tile;
use clash_layout::render::Image;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug)]
pub enum Mask {
    Pale,
    Bright,
    Gold,
    Dark,
    Cyan,
}
impl Mask {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "pale" => Ok(Self::Pale),
            "bright" => Ok(Self::Bright),
            "gold" => Ok(Self::Gold),
            "dark" => Ok(Self::Dark),
            "cyan" => Ok(Self::Cyan),
            _ => Err(format!("unknown wall mask {value}")),
        }
    }
    pub fn matches(self, p: [u8; 3]) -> bool {
        let [r, g, b] = p.map(i32::from);
        match self {
            Self::Pale => r > 190 && g > 160 && b > 110 && r - b < 120,
            Self::Bright => r > 228 && g > 205 && b > 150,
            Self::Gold => {
                (r > 215 && g > 195 && b > 145 && r - b < 95)
                    || (r > 200 && g > 150 && b < 110 && r - g < 70)
            }
            Self::Dark => b > r + 8 && b >= g && r < 130 && b > 60 && b < 200,
            Self::Cyan => b > 115 && b > r + 25 && (g - b).abs() < 45 && g > r + 15,
        }
    }
}

fn mean(image: &Image, sx: f64, sy: f64) -> Option<[f64; 3]> {
    if sx < 3.0 || sy < 3.0 || sx >= image.width as f64 - 3.0 || sy >= image.height as f64 - 3.0 {
        return None;
    }
    let mut sum = [0.0; 3];
    for y in sy as i32 - 2..=sy as i32 + 2 {
        for x in sx as i32 - 2..=sx as i32 + 2 {
            let p = image.get(x, y)?;
            for c in 0..3 {
                sum[c] += f64::from(p[c]);
            }
        }
    }
    Some(sum.map(|channel| channel / 25.0))
}

/// The original digitize.py detector: 5x5 RGB means, eight-connected runs,
/// at least three candidates or an entirely strong component.
pub fn detect(image: &Image, grid: Grid, lift: f64, occupied: &Tiles) -> Tiles {
    let (mut candidates, mut strong) = (Tiles::new(), Tiles::new());
    for x in 0..44 {
        for y in 0..44 {
            if occupied.contains(&(x, y)) {
                continue;
            }
            let (sx, sy) = grid.project(f64::from(x) + 0.5, f64::from(y) + 0.5);
            let (Some(c0), Some(cm), Some(c1)) = (
                mean(image, sx, sy),
                mean(image, sx, sy - lift / 2.0),
                mean(image, sx, sy - lift),
            ) else {
                continue;
            };
            let dark = (c0.into_iter().fold(f64::NEG_INFINITY, f64::max) < 110.0
                && cm.into_iter().fold(f64::NEG_INFINITY, f64::max) < 120.0)
                || (c0[2] - c0[1] > 5.0 && c0[2] > c0[0] - 15.0);
            let light = cm[0] > 205.0 && cm[1] > 170.0;
            let cap = c1[2] - c1[1] > -12.0
                && c1.into_iter().fold(f64::INFINITY, f64::min) > 120.0
                && c1[2] - c1[0] > 0.0;
            if dark || light || cap {
                candidates.insert((x, y));
            }
            if (dark && cap) || light {
                strong.insert((x, y));
            }
        }
    }
    groups(candidates)
        .into_iter()
        .filter(|c| c.len() >= 3 || c.is_subset(&strong))
        .flatten()
        .collect()
}

/// Consolidates palewalls/walls2/walls3/walls4 into parameterized cap masks.
/// Scores are retained for review; thresholding never invents a traced wall.
pub fn scores(
    image: &Image,
    grid: Grid,
    lift: f64,
    mask: Mask,
    bx: f64,
    by: f64,
) -> BTreeMap<Tile, f64> {
    let mut out = BTreeMap::new();
    for x in 0..44 {
        for y in 0..44 {
            let (sx, sy) = grid.project(f64::from(x) + 0.5, f64::from(y) + 0.5);
            let (x0, x1, y0, y1) = (
                (sx - grid.a * bx) as i32,
                (sx + grid.a * bx) as i32,
                (sy - lift - grid.b * by) as i32,
                (sy - lift + grid.b * by) as i32,
            );
            if x0 < 0
                || y0 < 0
                || x1 >= image.width as i32
                || y1 >= image.height as i32
                || x1 <= x0
                || y1 <= y0
            {
                continue;
            }
            let mut hits = 0;
            for yy in y0..y1 {
                for xx in x0..x1 {
                    hits += usize::from(mask.matches(image.get(xx, yy).expect("bounded pixel")));
                }
            }
            out.insert((x, y), hits as f64 / f64::from((x1 - x0) * (y1 - y0)));
        }
    }
    out
}

pub fn threshold(
    scores: &BTreeMap<Tile, f64>,
    occupied: &Tiles,
    threshold: f64,
    min_run: usize,
    strong: f64,
) -> Tiles {
    let mut left: Tiles = scores
        .iter()
        .filter(|(t, s)| **s >= threshold && !occupied.contains(t))
        .map(|(t, _)| *t)
        .collect();
    let mut keep = Tiles::new();
    while let Some(start) = left.pop_first() {
        let mut component = Tiles::from([start]);
        let mut stack = vec![start];
        while let Some((x, y)) = stack.pop() {
            for n in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)] {
                if left.remove(&n) {
                    component.insert(n);
                    stack.push(n);
                }
            }
        }
        if component.len() >= min_run || component.iter().all(|t| scores[t] > strong) {
            keep.extend(component);
        }
    }
    keep
}

/// Inclusive straight tile segments. Diagonal traces are rejected.
pub fn segment(start: Tile, end: Tile) -> Result<Tiles, String> {
    if start.0 != end.0 && start.1 != end.1 {
        return Err("wall segments must be horizontal or vertical".to_owned());
    }
    if [start.0, start.1, end.0, end.1]
        .iter()
        .any(|v| !(0..44).contains(v))
    {
        return Err("wall trace outside 44x44 village".to_owned());
    }
    let mut out = Tiles::new();
    for x in start.0.min(end.0)..=start.0.max(end.0) {
        for y in start.1.min(end.1)..=start.1.max(end.1) {
            out.insert((x, y));
        }
    }
    Ok(out)
}

pub fn fill_gaps(walls: &mut Tiles, occupied: &Tiles, max_gap: i32) -> Tiles {
    let mut added = BTreeSet::new();
    loop {
        let mut next = Tiles::new();
        for &(x, y) in walls.iter() {
            for (dx, dy) in [(1, 0), (0, 1)] {
                for k in 2..=max_gap.clamp(0, 42) + 1 {
                    if !walls.contains(&(x + dx * k, y + dy * k)) {
                        continue;
                    }
                    let gap: Tiles = (1..k).map(|i| (x + dx * i, y + dy * i)).collect();
                    if gap.is_disjoint(walls) && gap.is_disjoint(occupied) {
                        next.extend(gap);
                    }
                    break;
                }
            }
        }
        if next.is_empty() {
            break;
        }
        added.extend(&next);
        walls.extend(next);
    }
    added
}
