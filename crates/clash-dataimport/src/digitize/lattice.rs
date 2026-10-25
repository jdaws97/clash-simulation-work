//! Mask-line harmonic fitting and fractional-tile phase diagnostics.
use super::fit::Grid;
use super::walls::Mask;
use clash_data::json::Json;
use clash_data::wire::{arr, num, obj};
use clash_layout::render::Image;
use std::f64::consts::TAU;

pub fn mask_points(image: &Image, mask: Mask) -> Vec<(f64, f64)> {
    let mut points = Vec::new();
    for (index, &pixel) in image.pixels.iter().enumerate() {
        if mask.matches(pixel) {
            points.push(((index % image.width) as f64, (index / image.width) as f64));
        }
    }
    // Fixed deterministic sampling bounds runtime and avoids random subsampling.
    let stride = points.len().div_ceil(8000).max(1);
    points.into_iter().step_by(stride).collect()
}
fn harmonic(points: &[(f64, f64)], a: f64, b: f64) -> (f64, f64, f64) {
    let mut c = (0.0, 0.0);
    let mut d = (0.0, 0.0);
    for &(x, y) in points {
        let (sc, cc) = (TAU * (y / (2.0 * b) - x / (2.0 * a))).sin_cos();
        let (sd, cd) = (TAU * (y / (2.0 * b) + x / (2.0 * a))).sin_cos();
        c.0 += cc;
        c.1 += sc;
        d.0 += cd;
        d.1 += sd;
    }
    let score = (c.0.hypot(c.1) + d.0.hypot(d.1)) / points.len() as f64;
    let c0 = (c.1.atan2(c.0) / TAU * 2.0 * b).rem_euclid(2.0 * b);
    let d0 = (d.1.atan2(d.0) / TAU * 2.0 * b).rem_euclid(2.0 * b);
    (score, c0, d0)
}

/// Equivalent capability to proj.py + lat.py. The user's origin guess resolves
/// the repeating phase ambiguity; lift is explicit and never folded into ground.
pub fn fit(points: &[(f64, f64)], initial: Grid, lift: f64) -> Result<(Grid, f64), String> {
    if points.len() < 4 || !lift.is_finite() {
        return Err("lattice fit needs at least four mask points and finite lift".to_owned());
    }
    let mut a = initial.a;
    let mut b = initial.b;
    let mut best = harmonic(points, a, b).0;
    for ia in -12..=12 {
        for ib in -12..=12 {
            let ca = initial.a * (1.0 + f64::from(ia) * 0.005);
            let cb = initial.b * (1.0 + f64::from(ib) * 0.005);
            let score = harmonic(points, ca, cb).0;
            if score > best {
                a = ca;
                b = cb;
                best = score;
            }
        }
    }
    let mut steps = [initial.a * 0.0025, initial.b * 0.0025];
    for _ in 0..12 {
        for _ in 0..20 {
            let mut improved = false;
            for (da, db) in [
                (steps[0], 0.0),
                (-steps[0], 0.0),
                (0.0, steps[1]),
                (0.0, -steps[1]),
            ] {
                let (ca, cb) = (a + da, b + db);
                if ca < initial.a * 0.94
                    || ca > initial.a * 1.06
                    || cb < initial.b * 0.94
                    || cb > initial.b * 1.06
                {
                    continue;
                }
                let score = harmonic(points, ca, cb).0;
                if score > best {
                    a = ca;
                    b = cb;
                    best = score;
                    improved = true;
                }
            }
            if !improved {
                break;
            }
        }
        steps[0] *= 0.5;
        steps[1] *= 0.5;
    }
    let (_, c0, d0) = harmonic(points, a, b);
    let ratio = b / a;
    let guess_c = initial.top - lift - ratio * initial.cx + b;
    let guess_d = initial.top - lift + ratio * initial.cx + b;
    let kc = ((guess_c - c0) / (2.0 * b)).round_ties_even() as i32;
    let kd = ((guess_d - d0) / (2.0 * b)).round_ties_even() as i32;
    let mut pick = initial;
    let mut distance = f64::INFINITY;
    for ci in kc - 2..=kc + 2 {
        for di in kd - 2..=kd + 2 {
            let c = c0 + 2.0 * b * f64::from(ci);
            let d = d0 + 2.0 * b * f64::from(di);
            let grid = Grid {
                cx: (d - c) / (2.0 * ratio),
                top: (c + d) / 2.0 - b + lift,
                a,
                b,
            };
            let delta = (grid.cx - initial.cx).abs() / a + (grid.top - initial.top).abs() / b;
            if delta < distance {
                pick = grid;
                distance = delta;
            }
        }
    }
    Ok((pick, best))
}

pub fn diagnostics(points: &[(f64, f64)], grid: Grid) -> Json {
    let (mut x_hist, mut y_hist) = ([0_i32; 20], [0_i32; 20]);
    for &(sx, sy) in points {
        let (x, y) = grid.unproject(sx, sy);
        x_hist[(x.rem_euclid(1.0) * 20.0).floor().min(19.0) as usize] += 1;
        y_hist[(y.rem_euclid(1.0) * 20.0).floor().min(19.0) as usize] += 1;
    }
    obj([
        ("samples", num(points.len() as i32)),
        ("fraction_x", arr(x_hist.map(num))),
        ("fraction_y", arr(y_hist.map(num))),
        (
            "harmonic_strength",
            num(if points.is_empty() {
                0.0
            } else {
                harmonic(points, grid.a, grid.b).0
            }),
        ),
    ])
}
