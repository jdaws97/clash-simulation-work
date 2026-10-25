//! Static, textured building-patch correspondences and a robust zoom/pan model.
use crate::grid::Grid;
use crate::image::Image;
use crate::json::Value;
use crate::spatial::resize;

#[derive(Clone, Copy, Debug)]
pub struct Transform {
    pub scale: f64,
    pub dx: f64,
    pub dy: f64,
}

impl Transform {
    pub fn identity() -> Self {
        Self {
            scale: 1.0,
            dx: 0.0,
            dy: 0.0,
        }
    }

    pub fn apply(self, x: f64, y: f64) -> (f64, f64) {
        (x * self.scale + self.dx, y * self.scale + self.dy)
    }

    pub fn inverse(self, x: f64, y: f64) -> (f64, f64) {
        ((x - self.dx) / self.scale, (y - self.dy) / self.scale)
    }

    pub fn then(self, next: Self) -> Self {
        Self {
            scale: self.scale * next.scale,
            dx: self.dx * next.scale + next.dx,
            dy: self.dy * next.scale + next.dy,
        }
    }

    pub fn inverted(self) -> Self {
        Self {
            scale: 1.0 / self.scale,
            dx: -self.dx / self.scale,
            dy: -self.dy / self.scale,
        }
    }

    pub fn json(self, pixel_scale: f64) -> Value {
        Value::Array(vec![
            self.scale.into(),
            (self.dx * pixel_scale).into(),
            (self.dy * pixel_scale).into(),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Track {
    pub key: (f64, f64),
    pub frame: (f64, f64),
    pub error: f64,
}

pub struct Estimate {
    pub transform: Transform,
    pub tracks: Vec<Track>,
    pub rms: f64,
    pub reliable: bool,
    pub photometric_error: f64,
}

impl Estimate {
    pub fn json(&self, time: f64, pixel_scale: f64) -> Value {
        let mut result = Value::Object(Default::default());
        result.set("video_t", time.into());
        result.set("keyframe_to_frame", self.transform.json(pixel_scale));
        result.set("reliable", self.reliable.into());
        result.set("inliers", (self.tracks.len() as f64).into());
        result.set("rms_pixels", (self.rms * pixel_scale).into());
        result.set("photometric_error", self.photometric_error.into());
        result.set(
            "tracks",
            Value::Array(
                self.tracks
                    .iter()
                    .map(|track| {
                        Value::Array(vec![
                            (track.key.0 * pixel_scale).into(),
                            (track.key.1 * pixel_scale).into(),
                            (track.frame.0 * pixel_scale).into(),
                            (track.frame.1 * pixel_scale).into(),
                            track.error.into(),
                        ])
                    })
                    .collect(),
            ),
        );
        result
    }
}

fn inside(image: &Image, x: f64, y: f64, bottom: f64) -> bool {
    x >= 8.0
        && y >= 45.0
        && x < image.w as f64 - 8.0
        && y < bottom - 36.0
        && !(x < image.w as f64 * 0.24 && y < 110.0)
        && !(x > image.w as f64 * 0.74 && y < 95.0)
        && !(x > image.w as f64 * 0.82 && y > bottom - 45.0)
}

fn sample(image: &Image, x: f64, y: f64) -> [f64; 3] {
    let x = x.clamp(0.0, image.w as f64 - 1.001);
    let y = y.clamp(0.0, image.h as f64 - 1.001);
    let x0 = x as usize;
    let y0 = y as usize;
    let fx = x - x0 as f64;
    let fy = y - y0 as f64;
    let a = image.pixel(x0, y0);
    let b = image.pixel(x0 + 1, y0);
    let c = image.pixel(x0, y0 + 1);
    let d = image.pixel(x0 + 1, y0 + 1);
    std::array::from_fn(|i| {
        (a[i] as f64 * (1.0 - fx) + b[i] as f64 * fx) * (1.0 - fy)
            + (c[i] as f64 * (1.0 - fx) + d[i] as f64 * fx) * fy
    })
}

fn patch_error(key: &Image, frame: &Image, p: (f64, f64), q: (f64, f64), scale: f64) -> f64 {
    let mut error = 0.0;
    for oy in [-6.0, -3.0, 0.0, 3.0, 6.0] {
        for ox in [-6.0, -3.0, 0.0, 3.0, 6.0] {
            let a = sample(key, p.0 + ox, p.1 + oy);
            let b = sample(frame, q.0 + ox * scale, q.1 + oy * scale);
            error += (0..3).map(|i| (a[i] - b[i]).abs().min(110.0)).sum::<f64>() / 765.0;
        }
    }
    error / 25.0
}

pub struct Tracker {
    pub key: Image,
    pub bottom: f64,
    anchors: Vec<(f64, f64)>,
    coarse_key: Image,
}

fn averaged(image: &Image) -> Image {
    let mut small = Image::blank(image.w / 4, image.h / 4);
    for y in 0..small.h {
        for x in 0..small.w {
            let mut color = [0_u32; 3];
            for dy in 0..4 {
                for dx in 0..4 {
                    let p = image.pixel(x * 4 + dx, y * 4 + dy);
                    for c in 0..3 {
                        color[c] += p[c] as u32;
                    }
                }
            }
            for (c, value) in color.iter().enumerate() {
                small.data[(y * small.w + x) * 3 + c] = (value / 16) as u8;
            }
        }
    }
    small
}

impl Tracker {
    pub fn new(image: &Image, grid: Option<Grid>, bar_y: f64) -> Self {
        let factor = 640.0 / image.w as f64;
        let key = resize(image, 640);
        let bottom = bar_y * factor;
        let grid = grid.map(|grid| grid.scaled(factor));
        let mut ranked = Vec::new();
        for y in (48..bottom.max(50.0) as usize).step_by(9) {
            for x in (15..625).step_by(9) {
                if !inside(&key, x as f64, y as f64, bottom) {
                    continue;
                }
                if let Some(grid) = grid {
                    let (tx, ty) = grid.unproject(x as f64, y as f64);
                    if !(1.0..43.0).contains(&tx) || !(1.0..43.0).contains(&ty) {
                        continue;
                    }
                }
                let mut horizontal = 0.0;
                let mut vertical = 0.0;
                for oy in [-3.0, 0.0, 3.0] {
                    for ox in [-3.0, 0.0, 3.0] {
                        let a = sample(&key, x as f64 + ox - 2.0, y as f64 + oy);
                        let b = sample(&key, x as f64 + ox + 2.0, y as f64 + oy);
                        let c = sample(&key, x as f64 + ox, y as f64 + oy - 2.0);
                        let d = sample(&key, x as f64 + ox, y as f64 + oy + 2.0);
                        horizontal += (0..3).map(|i| (a[i] - b[i]).abs()).sum::<f64>();
                        vertical += (0..3).map(|i| (c[i] - d[i]).abs()).sum::<f64>();
                    }
                }
                let strength = horizontal.min(vertical);
                if strength > 400.0 {
                    ranked.push((strength, x as f64, y as f64));
                }
            }
        }
        ranked.sort_by(|a, b| b.0.total_cmp(&a.0));
        let mut anchors: Vec<(f64, f64)> = Vec::new();
        for (_, x, y) in ranked {
            if anchors.iter().all(|p| (p.0 - x).hypot(p.1 - y) >= 19.0) {
                anchors.push((x, y));
                if anchors.len() == 90 {
                    break;
                }
            }
        }
        let coarse_key = averaged(&key);
        Self {
            key,
            bottom,
            anchors,
            coarse_key,
        }
    }

    fn coarse(&self, frame: &Image, prior: Option<Transform>, recover: bool) -> (Transform, f64) {
        let small = averaged(frame);
        // Trim high-error patches (troops, fire, destroyed buildings). Require
        // broad overlap so a single matching roof cannot explain the camera.
        let score = |transform: Transform| {
            let mut errors = Vec::new();
            for &p in self.anchors.iter().step_by(3) {
                let q = transform.apply(p.0, p.1);
                if inside(frame, q.0, q.1, self.bottom) {
                    let mut error = 0.0;
                    for (ox, oy) in [
                        (-1.0, -1.0),
                        (1.0, -1.0),
                        (0.0, 0.0),
                        (-1.0, 1.0),
                        (1.0, 1.0),
                    ] {
                        let a = sample(&self.coarse_key, p.0 / 4.0 + ox, p.1 / 4.0 + oy);
                        let b = sample(
                            &small,
                            q.0 / 4.0 + ox * transform.scale,
                            q.1 / 4.0 + oy * transform.scale,
                        );
                        error +=
                            (0..3).map(|i| (a[i] - b[i]).abs().min(110.0)).sum::<f64>() / 765.0;
                    }
                    errors.push(error / 5.0);
                }
            }
            if errors.len() < 12.min(self.anchors.len() / 3).max(4) {
                return 1.0;
            }
            errors.sort_by(f64::total_cmp);
            let keep = (errors.len() * 3 / 5).max(1);
            errors[..keep].iter().sum::<f64>() / keep as f64
                + 0.02 * (1.0 - errors.len() as f64 / self.anchors.len().div_ceil(3).max(1) as f64)
        };
        let mut best = prior.unwrap_or(Transform::identity());
        let mut best_error = score(best);
        // First try the previous camera, then recover globally if necessary.
        if recover && (prior.is_none() || best_error > 0.085) {
            for s in 10..=48 {
                let scale = s as f64 / 20.0;
                for px in (-400..=400).step_by(16) {
                    for py in (-256..=256).step_by(16) {
                        let transform = Transform {
                            scale,
                            dx: 320.0 * (1.0 - scale) + px as f64,
                            dy: self.key.h as f64 * 0.5 * (1.0 - scale) + py as f64,
                        };
                        let error = score(transform);
                        if error < best_error {
                            best = transform;
                            best_error = error;
                        }
                    }
                }
            }
        }
        for (scale_step, pixel_step) in
            [(0.05, 8.0), (0.0125, 2.0), (0.003125, 0.5), (0.0008, 0.125)]
        {
            let center = best;
            for ds in -2..=2 {
                for dx in -2..=2 {
                    for dy in -2..=2 {
                        let transform = Transform {
                            scale: center.scale + ds as f64 * scale_step,
                            dx: center.dx + dx as f64 * pixel_step,
                            dy: center.dy + dy as f64 * pixel_step,
                        };
                        let error = score(transform);
                        if error < best_error {
                            best = transform;
                            best_error = error;
                        }
                    }
                }
            }
        }
        (best, best_error)
    }

    pub fn estimate(&self, frame: &Image, prior: Option<Transform>) -> Estimate {
        self.estimate_inner(frame, prior, true)
    }

    pub fn estimate_pair(&self, frame: &Image) -> Estimate {
        let frame = resize(frame, 640);
        let small = averaged(&frame);
        let mut rough = Vec::new();
        // Pyramidal block matching permits different displacement at each
        // anchor. Consensus then recovers zoom rather than fixing the scale
        // during optical flow. This also avoids a scenery-biased global fit.
        for &p in &self.anchors {
            let mut best = (1.0, p);
            let rough_error = |q: (f64, f64)| {
                let mut error = 0.0;
                for oy in -1..=1 {
                    for ox in -1..=1 {
                        let a = sample(
                            &self.coarse_key,
                            p.0 / 4.0 + ox as f64,
                            p.1 / 4.0 + oy as f64,
                        );
                        let b = sample(&small, q.0 / 4.0 + ox as f64, q.1 / 4.0 + oy as f64);
                        error += (0..3).map(|c| (a[c] - b[c]).abs()).sum::<f64>() / 765.0;
                    }
                }
                error / 9.0
            };
            for dy in (-14..=14).step_by(2) {
                for dx in (-14..=14).step_by(2) {
                    let q = (p.0 + dx as f64 * 4.0, p.1 + dy as f64 * 4.0);
                    if !inside(&frame, q.0, q.1, self.bottom) {
                        continue;
                    }
                    let error = rough_error(q);
                    if error < best.0 {
                        best = (error, q);
                    }
                }
            }
            let center = best.1;
            for dy in -1..=1 {
                for dx in -1..=1 {
                    let q = (center.0 + dx as f64 * 4.0, center.1 + dy as f64 * 4.0);
                    if inside(&frame, q.0, q.1, self.bottom) {
                        let error = rough_error(q);
                        if error < best.0 {
                            best = (error, q);
                        }
                    }
                }
            }
            if best.0 < 0.11 {
                rough.push(Track {
                    key: p,
                    frame: best.1,
                    error: best.0,
                });
            }
        }
        let (coarse, _, _) = robust_fit(&rough, Transform::identity());
        let mut refined = Vec::new();
        for &p in &self.anchors {
            let predicted = coarse.apply(p.0, p.1);
            if !inside(&frame, predicted.0, predicted.1, self.bottom) {
                continue;
            }
            let mut best = (1.0, predicted);
            for dy in -4..=4 {
                for dx in -4..=4 {
                    let q = (predicted.0 + dx as f64, predicted.1 + dy as f64);
                    let error = patch_error(&self.key, &frame, p, q, coarse.scale);
                    if error < best.0 {
                        best = (error, q);
                    }
                }
            }
            if best.0 < 0.115 {
                refined.push(Track {
                    key: p,
                    frame: best.1,
                    error: best.0,
                });
            }
        }
        let (transform, tracks, rms) = robust_fit(&refined, coarse);
        let photometric_error =
            tracks.iter().map(|t| t.error).sum::<f64>() / tracks.len().max(1) as f64;
        let reliable = tracks.len() >= 20
            && rms < 1.7
            && photometric_error < 0.065
            && (0.65..1.55).contains(&transform.scale);
        Estimate {
            transform,
            tracks,
            rms,
            reliable,
            photometric_error,
        }
    }

    fn estimate_inner(&self, frame: &Image, prior: Option<Transform>, recover: bool) -> Estimate {
        let frame = resize(frame, 640);
        let (coarse, photometric_error) = self.coarse(&frame, prior, recover);
        let mut matches = Vec::new();
        for &p in &self.anchors {
            let predicted = coarse.apply(p.0, p.1);
            if !inside(&frame, predicted.0, predicted.1, self.bottom) {
                continue;
            }
            let mut q = predicted;
            let mut error = patch_error(&self.key, &frame, p, q, coarse.scale);
            for dy in -5..=5 {
                for dx in -5..=5 {
                    let candidate = (predicted.0 + dx as f64, predicted.1 + dy as f64);
                    let distance = patch_error(&self.key, &frame, p, candidate, coarse.scale);
                    if distance < error {
                        error = distance;
                        q = candidate;
                    }
                }
            }
            if error < 0.115 {
                matches.push(Track {
                    key: p,
                    frame: q,
                    error,
                });
            }
        }
        let (transform, tracks, rms) = robust_fit(&matches, coarse);
        let spread = tracks
            .iter()
            .map(|t| (t.key.0 - 320.0).powi(2) + (t.key.1 - self.key.h as f64 * 0.5).powi(2))
            .sum::<f64>()
            / tracks.len().max(1) as f64;
        let reliable =
            tracks.len() >= 20 && rms < 1.7 && spread > 1600.0 && photometric_error < 0.09;
        Estimate {
            transform,
            tracks,
            rms,
            reliable,
            photometric_error,
        }
    }
}

fn least_squares(tracks: &[Track]) -> Option<Transform> {
    if tracks.len() < 3 {
        return None;
    }
    let n = tracks.len() as f64;
    let px = tracks.iter().map(|t| t.key.0).sum::<f64>() / n;
    let py = tracks.iter().map(|t| t.key.1).sum::<f64>() / n;
    let qx = tracks.iter().map(|t| t.frame.0).sum::<f64>() / n;
    let qy = tracks.iter().map(|t| t.frame.1).sum::<f64>() / n;
    let variance = tracks
        .iter()
        .map(|t| (t.key.0 - px).powi(2) + (t.key.1 - py).powi(2))
        .sum::<f64>();
    if variance < 100.0 {
        return None;
    }
    let scale = tracks
        .iter()
        .map(|t| (t.key.0 - px) * (t.frame.0 - qx) + (t.key.1 - py) * (t.frame.1 - qy))
        .sum::<f64>()
        / variance;
    Some(Transform {
        scale,
        dx: qx - scale * px,
        dy: qy - scale * py,
    })
}

fn robust_fit(tracks: &[Track], initial: Transform) -> (Transform, Vec<Track>, f64) {
    let residual = |transform: Transform, t: &Track| {
        let q = transform.apply(t.key.0, t.key.1);
        (q.0 - t.frame.0).hypot(q.1 - t.frame.1)
    };
    let mut best = initial;
    let mut best_count = 0;
    // Deterministic pair consensus. No random global state or external solver.
    for (i, a) in tracks.iter().enumerate() {
        for b in tracks.iter().skip(i + 1).step_by(3) {
            let px = b.key.0 - a.key.0;
            let py = b.key.1 - a.key.1;
            let variance = px * px + py * py;
            if variance < 2500.0 {
                continue;
            }
            let scale = (px * (b.frame.0 - a.frame.0) + py * (b.frame.1 - a.frame.1)) / variance;
            let transform = Transform {
                scale,
                dx: a.frame.0 - scale * a.key.0,
                dy: a.frame.1 - scale * a.key.1,
            };
            let count = tracks
                .iter()
                .filter(|t| residual(transform, t) < 2.2)
                .count();
            if count > best_count {
                best_count = count;
                best = transform;
            }
        }
    }
    let mut inliers: Vec<_> = tracks
        .iter()
        .filter(|t| residual(best, t) < 2.2)
        .cloned()
        .collect();
    for _ in 0..2 {
        if let Some(fit) = least_squares(&inliers) {
            best = fit;
            inliers = tracks
                .iter()
                .filter(|t| residual(best, t) < 2.2)
                .cloned()
                .collect();
        }
    }
    let rms = (inliers
        .iter()
        .map(|t| residual(best, t).powi(2))
        .sum::<f64>()
        / inliers.len().max(1) as f64)
        .sqrt();
    (best, inliers, rms)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_image_zoom_pan_ignores_stationary_preparation_buttons() {
        // Declared synthetic textured buildings, zoom/pan and stationary HUD.
        let mut key = Image::blank(640, 360);
        for y in 0..360 {
            for x in 0..640 {
                let cell = ((x / 8) * 71 + (y / 8) * 43 + (x / 8) * (y / 8) * 17) % 170 + 25;
                let i = (y * 640 + x) * 3;
                key.data[i..i + 3].copy_from_slice(&[
                    cell as u8,
                    (cell * 3 / 4) as u8,
                    (cell / 2) as u8,
                ]);
            }
        }
        let expected = Transform {
            scale: 1.025,
            dx: -9.0,
            dy: 3.0,
        };
        let mut frame = Image::blank(640, 360);
        for y in 0..360 {
            for x in 0..640 {
                let p = expected.inverse(x as f64, y as f64);
                if p.0 >= 0.0 && p.1 >= 0.0 && p.0 < 640.0 && p.1 < 360.0 {
                    let i = (y * 640 + x) * 3;
                    frame.data[i..i + 3].copy_from_slice(&key.pixel(p.0 as usize, p.1 as usize));
                }
            }
        }
        for image in [&mut key, &mut frame] {
            for y in 279..308 {
                for x in 15..420 {
                    let i = (y * 640 + x) * 3;
                    let v = if (x + y) % 6 < 3 { 255 } else { 5 };
                    image.data[i..i + 3].copy_from_slice(&[v, 20, 220]);
                }
            }
        }
        let estimate = Tracker::new(&key, None, 310.0).estimate_pair(&frame);
        assert!(estimate.reliable, "only {} matches", estimate.tracks.len());
        assert!((estimate.transform.scale - expected.scale).abs() < 0.012);
        assert!((estimate.transform.dx - expected.dx).abs() < 3.0);
        assert!((estimate.transform.dy - expected.dy).abs() < 3.0);
        assert!(estimate.tracks.iter().all(|t| t.key.1 < 274.0));
    }

    #[test]
    fn synthetic_similarity_consensus_rejects_moving_units() {
        // Declared synthetic static tracks plus independently moving outliers.
        let expected = Transform {
            scale: 1.37,
            dx: -53.0,
            dy: 17.0,
        };
        let mut tracks: Vec<_> = (0..24)
            .map(|i| {
                let p = ((i % 6) as f64 * 42.0 + 80.0, (i / 6) as f64 * 39.0 + 70.0);
                Track {
                    key: p,
                    frame: expected.apply(p.0, p.1),
                    error: 0.01,
                }
            })
            .collect();
        for track in tracks.iter_mut().take(7) {
            track.frame.0 += 18.0;
            track.frame.1 -= 11.0;
        }
        let (fit, inliers, rms) = robust_fit(&tracks, Transform::identity());
        assert_eq!(inliers.len(), 17);
        assert!((fit.scale - expected.scale).abs() < 1e-8);
        assert!((fit.dx - expected.dx).abs() < 1e-8 && rms < 1e-8);
        let p = fit.inverse(300.0, 210.0);
        let q = fit.apply(p.0, p.1);
        assert!((q.0 - 300.0).hypot(q.1 - 210.0) < 1e-8);
    }
}
