//! Deployment appearance proposals from camera-compensated temporal changes.
use crate::camera::Transform;
use crate::grid::Grid;
use crate::image::Image;
use crate::json::Value;

#[derive(Clone)]
pub struct Appearance {
    pub x: f64,
    pub y: f64,
    pub score: f64,
    pub pixels: usize,
    pub marker: f64,
}

impl Appearance {
    pub fn json(&self, pixel_scale: f64, grid: Option<Grid>, camera: Option<Transform>) -> Value {
        let mut value = Value::Object(Default::default());
        value.set(
            "screen",
            Value::Array(vec![
                (self.x * pixel_scale).into(),
                (self.y * pixel_scale).into(),
            ]),
        );
        let tile = grid
            .zip(camera)
            .map(|(grid, camera)| {
                let key = camera.inverse(self.x, self.y);
                let tile = grid.unproject(key.0 * pixel_scale, key.1 * pixel_scale);
                Value::Array(vec![tile.0.into(), tile.1.into()])
            })
            .unwrap_or(Value::Null);
        value.set("tile", tile);
        value.set("score", self.score.into());
        value.set("changed_analysis_pixels", (self.pixels as f64).into());
        value.set("marker_color_fraction", self.marker.into());
        value
    }
}

fn pixel(image: &Image, x: f64, y: f64) -> Option<[u8; 3]> {
    if x < 1.0 || y < 1.0 || x >= image.w as f64 - 1.0 || y >= image.h as f64 - 1.0 {
        None
    } else {
        Some(image.pixel(x.round() as usize, y.round() as usize))
    }
}

pub fn detect(
    before: &Image,
    after: &Image,
    before_camera: Transform,
    after_camera: Transform,
    grid: Option<Grid>,
    bottom: usize,
    spell: bool,
) -> Vec<Appearance> {
    let w = after.w / 2;
    let h = after.h / 2;
    let mut change = vec![0.0; w * h];
    let mut marker = vec![0.0; w * h];
    for cy in 24..(bottom / 2).min(h).saturating_sub(3) {
        for cx in 5..w.saturating_sub(5) {
            let x = cx * 2;
            let y = cy * 2;
            // Fixed player/score HUD, bar and preparation buttons are excluded.
            if x < after.w * 24 / 100 && y < 115
                || x > after.w * 78 / 100 && y < 100
                || x > after.w * 82 / 100 && y > bottom.saturating_sub(48)
                || x < after.w * 43 / 100 && y > bottom.saturating_sub(33)
            {
                continue;
            }
            let mut delta = 0.0;
            let mut cue = 0.0;
            for dy in 0..2 {
                for dx in 0..2 {
                    let sx = (x + dx) as f64;
                    let sy = (y + dy) as f64;
                    let key = after_camera.inverse(sx, sy);
                    let prior = before_camera.apply(key.0, key.1);
                    let Some(p) = pixel(before, prior.0, prior.1) else {
                        continue;
                    };
                    let q = after.pixel(x + dx, y + dy);
                    let difference = (0..3)
                        .map(|i| (p[i] as f64 - q[i] as f64).abs())
                        .sum::<f64>()
                        / 3.0;
                    // Existing sprites and projectiles usually move only a few
                    // pixels between these observations. A local color search
                    // suppresses their translated pixels and newly uncovered
                    // ground; genuinely new colors retain onset evidence.
                    let mut novelty = difference;
                    for oy in [-6.0, -3.0, 0.0, 3.0, 6.0] {
                        for ox in [-6.0, -3.0, 0.0, 3.0, 6.0] {
                            if let Some(old) = pixel(before, prior.0 + ox, prior.1 + oy) {
                                let local_difference = (0..3)
                                    .map(|c| (old[c] as f64 - q[c] as f64).abs())
                                    .sum::<f64>()
                                    / 3.0;
                                novelty = novelty.min(local_difference);
                            }
                        }
                    }
                    delta += (novelty - 18.0).max(0.0) + (difference - 45.0).max(0.0) * 0.1;
                    // Yellow/orange deploy sparks or magenta spell/deploy rings.
                    // This is a cue, never a claim that a touch marker was read.
                    if difference > 45.0
                        && (q[0] > 200 && q[1] > 120 && q[2] < 130
                            || q[0] > 185 && q[2] > 150 && q[1] < 125)
                    {
                        cue += 1.0;
                    }
                }
            }
            change[cy * w + cx] = delta / 4.0;
            marker[cy * w + cx] = cue / 4.0;
        }
    }
    // Dilate one analysis cell to join sprite fragments without merging whole
    // combat fronts. Scores below retain the actual changed-pixel support.
    let mut connected = vec![false; w * h];
    for y in 1..h - 1 {
        for x in 1..w - 1 {
            if change[y * w + x] > 14.0 {
                for dy in -1..=1 {
                    for dx in -1..=1 {
                        connected[(y as isize + dy) as usize * w + (x as isize + dx) as usize] =
                            true;
                    }
                }
            }
        }
    }
    let mut visited = vec![false; w * h];
    let mut found = Vec::new();
    for start in 0..connected.len() {
        if visited[start] || !connected[start] {
            continue;
        }
        visited[start] = true;
        let mut stack = vec![start];
        let mut weight = 0.0;
        let mut wx = 0.0;
        let mut wy = 0.0;
        let mut support = 0;
        let mut cue = 0.0;
        let mut size = 0;
        while let Some(i) = stack.pop() {
            let x = i % w;
            let y = i / w;
            size += 1;
            if change[i] > 14.0 {
                let v = change[i];
                weight += v;
                wx += (x * 2 + 1) as f64 * v;
                wy += (y * 2 + 1) as f64 * v;
                support += 1;
                cue += marker[i];
            }
            for (nx, ny) in [
                (x.wrapping_sub(1), y),
                (x + 1, y),
                (x, y.wrapping_sub(1)),
                (x, y + 1),
            ] {
                if nx < w && ny < h {
                    let j = ny * w + nx;
                    if connected[j] && !visited[j] {
                        visited[j] = true;
                        stack.push(j);
                    }
                }
            }
        }
        if support < 3 || size > if spell { 2200 } else { 1200 } {
            continue;
        }
        let x = wx / weight;
        let y = wy / weight;
        let mut score = weight / (support as f64).sqrt() / (1.0 + support as f64 / 110.0);
        let marker_fraction = cue / support as f64;
        if spell || support < 20 {
            score *= 1.0 + marker_fraction.min(0.3) * 2.0;
        }
        if let Some(grid) = grid {
            let key = after_camera.inverse(x, y);
            let (tx, ty) = grid.unproject(key.0, key.1);
            let edge = tx.min(ty).min(44.0 - tx).min(44.0 - ty);
            if !spell {
                score *= if edge > 8.0 {
                    0.3
                } else if edge > 4.0 {
                    0.7
                } else {
                    1.1
                };
            }
        }
        found.push(Appearance {
            x,
            y,
            score,
            pixels: support * 4,
            marker: marker_fraction,
        });
    }
    found.sort_by(|a, b| b.score.total_cmp(&a.score));
    found.truncate(5);
    found
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_pan_compensation_and_new_unit() {
        // Declared synthetic textured static scene, a pan and a new gold unit.
        let mut before = Image::blank(640, 360);
        for y in 0..360 {
            for x in 0..640 {
                let i = (y * 640 + x) * 3;
                let v = ((x / 4 * 17 + y / 4 * 23) % 120 + 40) as u8;
                before.data[i..i + 3].copy_from_slice(&[v / 2, v, v / 3]);
            }
        }
        let mut after = Image::blank(640, 360);
        after.paste(&before, 14, 7, 1);
        for y in 180..191 {
            for x in 320..331 {
                let i = (y * 640 + x) * 3;
                after.data[i..i + 3].copy_from_slice(&[250, 180, 25]);
            }
        }
        let pan = Transform {
            scale: 1.0,
            dx: 14.0,
            dy: 7.0,
        };
        let found = detect(
            &before,
            &after,
            Transform::identity(),
            pan,
            None,
            300,
            false,
        );
        assert!(!found.is_empty());
        assert!((found[0].x - 325.0).hypot(found[0].y - 185.0) < 5.0);
    }
}
