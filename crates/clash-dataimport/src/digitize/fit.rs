//! The 44x44 isometric projection, anchor fitting and lattice diagnostics.
use clash_data::json::Json;
use clash_data::wire::{num, obj};
use clash_layout::render::Image;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Grid {
    pub cx: f64,
    pub top: f64,
    pub a: f64,
    pub b: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct Anchor {
    pub tile: (f64, f64),
    pub screen: (f64, f64),
}

impl Grid {
    pub fn from_json(value: &Json) -> Result<Self, String> {
        let field = |key| {
            value
                .get(key)
                .and_then(Json::opt_f64)
                .filter(|v| v.is_finite())
                .ok_or_else(|| format!("grid requires finite {key}"))
        };
        let grid = Self {
            cx: field("cx")?,
            top: field("top")?,
            a: field("a")?,
            b: field("b")?,
        };
        if grid.a <= 0.0 || grid.b <= 0.0 {
            return Err("grid scales must be positive".to_owned());
        }
        Ok(grid)
    }

    pub fn to_json(self) -> Json {
        obj([
            ("cx", num(self.cx)),
            ("top", num(self.top)),
            ("a", num(self.a)),
            ("b", num(self.b)),
        ])
    }

    pub fn project(self, x: f64, y: f64) -> (f64, f64) {
        (self.cx + (x - y) * self.a, self.top + (x + y) * self.b)
    }

    pub fn unproject(self, sx: f64, sy: f64) -> (f64, f64) {
        let u = (sx - self.cx) / self.a;
        let v = (sy - self.top) / self.b;
        ((u + v) / 2.0, (v - u) / 2.0)
    }

    /// Footprint bottom tip conversion used by conv.py; ties round to even.
    pub fn bottom_tip(self, sx: f64, sy: f64, size: i32, margin: f64) -> (i32, i32) {
        let (x, y) = self.unproject(sx, sy);
        let snap = |v: f64| {
            (v - f64::from(size) + margin)
                .round_ties_even()
                .clamp(0.0, f64::from(44 - size)) as i32
        };
        (snap(x), snap(y))
    }

    /// Least-squares fit to declared corresponding tile and image coordinates.
    pub fn fit(anchors: &[Anchor]) -> Result<(Self, f64), String> {
        if anchors.len() < 2
            || anchors.iter().any(|p| {
                ![p.tile.0, p.tile.1, p.screen.0, p.screen.1]
                    .iter()
                    .all(|v| v.is_finite())
            })
        {
            return Err("fit needs at least two finite anchor correspondences".to_owned());
        }
        fn regression(points: impl Iterator<Item = (f64, f64)>) -> Result<(f64, f64), String> {
            let points: Vec<_> = points.collect();
            let n = points.len() as f64;
            let mx = points.iter().map(|p| p.0).sum::<f64>() / n;
            let my = points.iter().map(|p| p.1).sum::<f64>() / n;
            let variance = points.iter().map(|p| (p.0 - mx).powi(2)).sum::<f64>();
            if variance < 1e-12 {
                return Err("anchor geometry does not determine both grid scales".to_owned());
            }
            let slope = points.iter().map(|p| (p.0 - mx) * (p.1 - my)).sum::<f64>() / variance;
            Ok((my - slope * mx, slope))
        }
        let (cx, a) = regression(anchors.iter().map(|p| (p.tile.0 - p.tile.1, p.screen.0)))?;
        let (top, b) = regression(anchors.iter().map(|p| (p.tile.0 + p.tile.1, p.screen.1)))?;
        let grid = Self::from_json(&Self { cx, top, a, b }.to_json())?;
        let rms = (anchors
            .iter()
            .map(|p| {
                let q = grid.project(p.tile.0, p.tile.1);
                (q.0 - p.screen.0).powi(2) + (q.1 - p.screen.1).powi(2)
            })
            .sum::<f64>()
            / anchors.len() as f64)
            .sqrt();
        Ok((grid, rms))
    }

    /// Refine a manually selected lattice using clipped squared tile residuals.
    /// The initial phase is intentionally explicit: repeated walls alone cannot
    /// identify the village origin. This is a local deterministic search.
    pub fn refine(self, points: &[(f64, f64)], center: bool) -> Result<(Self, f64), String> {
        if points.is_empty() {
            return Err("no lattice points".to_owned());
        }
        let loss = |g: Self| -> f64 {
            points
                .iter()
                .map(|&(sx, sy)| {
                    let (mut x, mut y) = g.unproject(sx, sy);
                    if center {
                        x -= 0.5;
                        y -= 0.5;
                    }
                    ((x - x.round_ties_even()).hypot(y - y.round_ties_even()))
                        .min(0.3)
                        .powi(2)
                })
                .sum::<f64>()
                / points.len() as f64
        };
        let mut best = self;
        let mut score = loss(best);
        let mut steps = [self.a / 8.0, self.b / 8.0, self.a * 0.01, self.b * 0.01];
        for _ in 0..16 {
            for _ in 0..40 {
                let mut improved = false;
                for axis in 0..4 {
                    for sign in [-1.0, 1.0] {
                        let mut candidate = best;
                        match axis {
                            0 => candidate.cx += sign * steps[0],
                            1 => candidate.top += sign * steps[1],
                            2 => candidate.a += sign * steps[2],
                            _ => candidate.b += sign * steps[3],
                        }
                        if candidate.a <= 0.0 || candidate.b <= 0.0 {
                            continue;
                        }
                        let next = loss(candidate);
                        if next < score {
                            best = candidate;
                            score = next;
                            improved = true;
                        }
                    }
                }
                if !improved {
                    break;
                }
            }
            for step in &mut steps {
                *step *= 0.5;
            }
        }
        Ok((best, score.sqrt()))
    }
}

pub fn overlay(image: &Image, grid: Grid) -> Image {
    let mut out = image.clone();
    for i in 0..=44 {
        let major = i % 4 == 0;
        let color = if major { [255, 255, 0] } else { [255; 3] };
        let alpha = if major { 200 } else { 90 };
        out.line(
            grid.project(f64::from(i), 0.0),
            grid.project(f64::from(i), 44.0),
            color,
            alpha,
        );
        out.line(
            grid.project(0.0, f64::from(i)),
            grid.project(44.0, f64::from(i)),
            color,
            alpha,
        );
    }
    for x in (0..44).step_by(2) {
        for y in (0..44).step_by(4) {
            let p = grid.project(f64::from(x) + 0.5, f64::from(y) + 0.5);
            out.text(
                p.0 as i32 - 6,
                p.1 as i32 - 2,
                &format!("{x},{y}"),
                [255; 3],
            );
        }
    }
    out
}
