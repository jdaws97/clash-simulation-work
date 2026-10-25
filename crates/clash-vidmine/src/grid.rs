//! The digitize convention: (0,0) is the top, x down-right, y down-left.
use crate::image::Image;
use crate::json::Value;
use std::io;

#[derive(Clone, Copy, Debug)]
pub struct Grid {
    pub cx: f64,
    pub top: f64,
    pub a: f64,
    pub b: f64,
    pub residual: f64,
    pub landmarks: usize,
}

impl Grid {
    pub fn project(self, x: f64, y: f64) -> (f64, f64) {
        (self.cx + (x - y) * self.a, self.top + (x + y) * self.b)
    }

    pub fn unproject(self, sx: f64, sy: f64) -> (f64, f64) {
        let difference = (sx - self.cx) / self.a;
        let sum = (sy - self.top) / self.b;
        ((sum + difference) * 0.5, (sum - difference) * 0.5)
    }

    pub fn scaled(self, scale: f64) -> Self {
        Self {
            cx: self.cx * scale,
            top: self.top * scale,
            a: self.a * scale,
            b: self.b * scale,
            residual: self.residual * scale,
            landmarks: self.landmarks,
        }
    }

    pub fn json(self) -> Value {
        let mut value = Value::Object(Default::default());
        value.set("status", "reviewed_boundary_landmark_fit".into());
        value.set("method", "least squares fit of manually reviewed buildable-boundary landmarks; not an automatic origin detector".into());
        value.set(
            "convention",
            "screen_x=cx+(x-y)*a; screen_y=top+(x+y)*b; 44x44; continuous tile coordinates".into(),
        );
        value.set("cx", self.cx.into());
        value.set("top", self.top.into());
        value.set("a", self.a.into());
        value.set("b", self.b.into());
        value.set("landmark_rms_pixels", self.residual.into());
        value.set("landmarks", (self.landmarks as f64).into());
        value.set("tile_coordinates_available", true.into());
        value.set("absolute_origin_independently_verified", false.into());
        value
    }
}

#[derive(Clone, Copy)]
pub struct Landmark {
    pub x: f64,
    pub y: f64,
    pub sx: f64,
    pub sy: f64,
}

pub struct Spacing {
    pub a: f64,
    pub b: f64,
    pub pairs: usize,
}

pub fn wall_spacing(image: &Image, seed_a: f64, bottom: usize) -> Option<Spacing> {
    let mut yellow = vec![false; image.w * image.h];
    for y in 80..bottom.min(image.h) {
        for x in 10..image.w.saturating_sub(10) {
            let p = image.pixel(x, y);
            yellow[y * image.w + x] =
                p[0] > 185 && p[1] > 155 && p[2] < 145 && p[1] as f64 / p[0] as f64 > 0.72;
        }
    }
    let mut centers = Vec::new();
    for start in 0..yellow.len() {
        if !yellow[start] {
            continue;
        }
        yellow[start] = false;
        let mut stack = vec![start];
        let mut xs = Vec::new();
        let mut ys = Vec::new();
        while let Some(index) = stack.pop() {
            let x = index % image.w;
            let y = index / image.w;
            xs.push(x);
            ys.push(y);
            for (nx, ny) in [
                (x.wrapping_sub(1), y),
                (x + 1, y),
                (x, y.wrapping_sub(1)),
                (x, y + 1),
            ] {
                if nx < image.w && ny < image.h && yellow[ny * image.w + nx] {
                    yellow[ny * image.w + nx] = false;
                    stack.push(ny * image.w + nx);
                }
            }
        }
        if (4..=75).contains(&xs.len()) {
            let width = xs.iter().max().unwrap() - xs.iter().min().unwrap() + 1;
            let height = ys.iter().max().unwrap() - ys.iter().min().unwrap() + 1;
            if width <= 16 && height <= 11 && width >= 2 && height >= 2 {
                centers.push((
                    xs.iter().sum::<usize>() as f64 / xs.len() as f64,
                    ys.iter().sum::<usize>() as f64 / ys.len() as f64,
                ));
            }
        }
    }
    let mut steps = Vec::new();
    for (index, a) in centers.iter().enumerate() {
        for b in centers.iter().skip(index + 1) {
            let dx = (a.0 - b.0).abs();
            let dy = (a.1 - b.1).abs();
            if dx >= seed_a * 0.65 && dx <= seed_a * 1.65 && (0.65..0.85).contains(&(dy / dx)) {
                steps.push((dx, dy));
            }
        }
    }
    let mut best = Vec::new();
    for candidate in &steps {
        let neighbors: Vec<_> = steps
            .iter()
            .filter(|p| (p.0 - candidate.0).hypot(p.1 - candidate.1) < 1.1)
            .copied()
            .collect();
        if neighbors.len() > best.len() {
            best = neighbors;
        }
    }
    if best.len() < 18 {
        return None;
    }
    let a = best.iter().map(|p| p.0).sum::<f64>() / best.len() as f64;
    let b = best.iter().map(|p| p.1).sum::<f64>() / best.len() as f64;
    Some(Spacing {
        a,
        b,
        pairs: best.len(),
    })
}

fn regression(points: &[(f64, f64)]) -> io::Result<(f64, f64)> {
    let n = points.len() as f64;
    let mean_x = points.iter().map(|p| p.0).sum::<f64>() / n;
    let mean_y = points.iter().map(|p| p.1).sum::<f64>() / n;
    let variance = points.iter().map(|p| (p.0 - mean_x).powi(2)).sum::<f64>();
    if variance < 1.0 {
        return Err(io::Error::other(
            "grid landmarks do not constrain both axes",
        ));
    }
    let slope = points
        .iter()
        .map(|p| (p.0 - mean_x) * (p.1 - mean_y))
        .sum::<f64>()
        / variance;
    Ok((mean_y - slope * mean_x, slope))
}

pub fn fit(points: &[Landmark]) -> io::Result<Grid> {
    if points.len() < 3
        || points
            .iter()
            .any(|p| ![p.x, p.y, p.sx, p.sy].iter().all(|v| v.is_finite()))
    {
        return Err(io::Error::other(
            "need at least three finite grid landmarks",
        ));
    }
    let horizontal: Vec<_> = points.iter().map(|p| (p.x - p.y, p.sx)).collect();
    let vertical: Vec<_> = points.iter().map(|p| (p.x + p.y, p.sy)).collect();
    let (cx, a) = regression(&horizontal)?;
    let (top, b) = regression(&vertical)?;
    if a <= 1.0 || b <= 1.0 || !(0.4..1.0).contains(&(b / a)) {
        return Err(io::Error::other("implausible grid scale or orientation"));
    }
    let mut grid = Grid {
        cx,
        top,
        a,
        b,
        residual: 0.0,
        landmarks: points.len(),
    };
    grid.residual = (points
        .iter()
        .map(|p| {
            let q = grid.project(p.x, p.y);
            (p.sx - q.0).powi(2) + (p.sy - q.1).powi(2)
        })
        .sum::<f64>()
        / points.len() as f64)
        .sqrt();
    if grid.residual > a * 0.7 {
        return Err(io::Error::other(
            "grid landmark residual exceeds 0.7 horizontal tile steps",
        ));
    }
    Ok(grid)
}

pub fn dot(image: &mut Image, x: f64, y: f64, color: [u8; 3]) {
    let x = x.round() as isize;
    let y = y.round() as isize;
    if x >= 0 && y >= 0 && x < image.w as isize && y < image.h as isize {
        let i = (y as usize * image.w + x as usize) * 3;
        image.data[i..i + 3].copy_from_slice(&color);
    }
}

pub fn cross(image: &mut Image, x: f64, y: f64, color: [u8; 3]) {
    for offset in -8..=8 {
        dot(image, x + offset as f64, y, color);
        dot(image, x, y + offset as f64, color);
    }
}

pub fn overlay(image: &Image, grid: Grid) -> Image {
    let mut image = image.clone();
    for i in 0..=44 {
        let color = if i % 4 == 0 {
            [240, 225, 20]
        } else {
            [95, 135, 95]
        };
        for step in 0..=880 {
            let j = step as f64 / 20.0;
            for p in [grid.project(i as f64, j), grid.project(j, i as f64)] {
                dot(&mut image, p.0, p.1, color);
            }
        }
    }
    image
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_wall_cap_lattice_recovers_spacing() {
        // Declared synthetic yellow caps on two wall diagonals.
        let mut image = Image::blank(640, 360);
        for i in 0..24 {
            for (x, y) in [(80 + i * 12, 85 + i * 9), (530 - i * 12, 85 + i * 9)] {
                for dy in 0..3 {
                    for dx in 0..4 {
                        dot(&mut image, (x + dx) as f64, (y + dy) as f64, [250, 220, 30]);
                    }
                }
            }
        }
        let spacing = wall_spacing(&image, 10.0, 330).unwrap();
        assert!((spacing.a - 12.0).abs() < 0.2 && (spacing.b - 9.0).abs() < 0.2);
        assert!(spacing.pairs >= 18);
    }

    #[test]
    fn synthetic_grid_fit_roundtrip_and_degenerate_rejection() {
        // Declared synthetic 44x44 projection; no game calibration data.
        let expected = Grid {
            cx: 600.0,
            top: -30.0,
            a: 12.0,
            b: 9.0,
            residual: 0.0,
            landmarks: 4,
        };
        let points: Vec<_> = [(0.0, 0.0), (44.0, 0.0), (0.0, 44.0), (44.0, 44.0)]
            .iter()
            .map(|&(x, y)| {
                let (sx, sy) = expected.project(x, y);
                Landmark { x, y, sx, sy }
            })
            .collect();
        let grid = fit(&points).unwrap();
        assert!((grid.a - 12.0).abs() < 1e-8);
        assert!((grid.b - 9.0).abs() < 1e-8);
        let (sx, sy) = grid.project(-2.5, 46.0);
        let tile = grid.unproject(sx, sy);
        assert!((tile.0 + 2.5).abs() < 1e-8 && (tile.1 - 46.0).abs() < 1e-8);
        assert!(fit(&[points[0]; 4]).is_err());
    }
}
