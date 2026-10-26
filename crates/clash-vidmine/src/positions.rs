//! Camera compensated appearance proposals. A proposal is not a verified touch.
use crate::image::{Image, Rect};
use crate::json::Value;
use crate::{icons, video};
use std::fs;
use std::io;
use std::path::Path;

fn resized(image: &Image, w: usize, h: usize) -> Image {
    let mut out = Image::blank(w, h);
    for y in 0..h {
        for x in 0..w {
            let index = (y * w + x) * 3;
            out.data[index..index + 3]
                .copy_from_slice(&image.pixel(x * image.w / w, y * image.h / h));
        }
    }
    out
}

#[derive(Clone, Copy, Debug)]
struct Camera {
    scale: f64,
    dx: f64,
    dy: f64,
    error: f64,
}

fn registration(a: &Image, b: &Image) -> Camera {
    let a = resized(a, 160, 90);
    let b = resized(b, 160, 90);
    let error = |scale: f64, dx: f64, dy: f64| {
        let mut tiles = Vec::new();
        for by in (12..65).step_by(10) {
            for bx in (12..148).step_by(12) {
                let mut sum = 0.0;
                let mut count = 0;
                for y in (by..by + 8).step_by(2) {
                    for x in (bx..bx + 10).step_by(2) {
                        let tx = (x as f64 * scale + dx).round() as isize;
                        let ty = (y as f64 * scale + dy).round() as isize;
                        if tx < 0 || ty < 8 || tx >= 160 || ty >= 72 {
                            continue;
                        }
                        let p = a.pixel(x, y);
                        let q = b.pixel(tx as usize, ty as usize);
                        sum += p
                            .iter()
                            .zip(q)
                            .map(|(p, q)| (*p as f64 - q as f64).abs().min(100.0))
                            .sum::<f64>()
                            / 765.0;
                        count += 1;
                    }
                }
                if count >= 12 {
                    tiles.push(sum / count as f64);
                }
            }
        }
        if tiles.len() < 24 {
            return 1.0;
        }
        tiles.sort_by(f64::total_cmp);
        let retained = tiles.len() * 7 / 10;
        tiles[..retained].iter().sum::<f64>() / retained as f64
    };
    let mut best = Camera {
        scale: 1.0,
        dx: 0.0,
        dy: 0.0,
        error: error(1.0, 0.0, 0.0),
    };
    for s in 6..=16 {
        for dx in (-40..=40).step_by(8) {
            for dy in (-24..=24).step_by(8) {
                let scale = s as f64 / 10.0;
                let score = error(scale, dx as f64, dy as f64);
                if score < best.error {
                    best = Camera {
                        scale,
                        dx: dx as f64,
                        dy: dy as f64,
                        error: score,
                    };
                }
            }
        }
    }
    for (ss, xy) in [(0.025, 2.0), (0.00625, 0.5)] {
        let coarse = best;
        for ds in -3..=3 {
            for dx in -3..=3 {
                for dy in -3..=3 {
                    let scale = coarse.scale + ds as f64 * ss;
                    let x = coarse.dx + dx as f64 * xy;
                    let y = coarse.dy + dy as f64 * xy;
                    let score = error(scale, x, y);
                    if score < best.error {
                        best = Camera {
                            scale,
                            dx: x,
                            dy: y,
                            error: score,
                        };
                    }
                }
            }
        }
    }
    best.dx *= 4.0;
    best.dy *= 4.0;
    best
}

#[derive(Clone)]
struct Candidate {
    x: f64,
    y: f64,
    score: f64,
    area: usize,
    rect: Rect,
}

fn candidates(before: &Image, after: &Image, camera: Camera, bar_y: usize) -> Vec<Candidate> {
    let before = resized(before, 640, 360);
    let after = resized(after, 640, 360);
    let width = 160;
    let height = 90;
    let mut changes = vec![0.0; width * height];
    let bottom = bar_y.min(310); // caller passes 640×360 analysis pixels
    for cy in 18..(bottom / 4).min(80) {
        for cx in 2..158 {
            // Fixed commentary/facecam area and right-side score HUD.
            if cx > 130 && cy < 43 || cx > 132 && cy > 57 {
                continue;
            }
            let mut change = 0.0;
            for dy in 0..4 {
                for dx in 0..4 {
                    let x = cx * 4 + dx;
                    let y = cy * 4 + dy;
                    let px = ((x as f64 - camera.dx) / camera.scale).round() as isize;
                    let py = ((y as f64 - camera.dy) / camera.scale).round() as isize;
                    if px < 0 || py < 0 || px >= 640 || py >= 360 {
                        continue;
                    }
                    let p = before.pixel(px as usize, py as usize);
                    let q = after.pixel(x, y);
                    let delta = p
                        .iter()
                        .zip(q)
                        .map(|(p, q)| (*p as f64 - q as f64).abs())
                        .sum::<f64>()
                        / 3.0;
                    // Appearance and departure are both visible in differences; retain
                    // proposals explicitly because moving troops can win this score.
                    change += (delta - 25.0).max(0.0);
                }
            }
            changes[cy * width + cx] = change / 16.0;
        }
    }
    let mut nonzero: Vec<_> = changes.iter().copied().filter(|v| *v > 0.0).collect();
    if nonzero.is_empty() {
        return Vec::new();
    }
    nonzero.sort_by(f64::total_cmp);
    let threshold = (nonzero[nonzero.len() * 9 / 10] * 0.65).max(22.0);
    let mut visited = vec![false; changes.len()];
    let mut result = Vec::new();
    for index in 0..changes.len() {
        if visited[index] || changes[index] < threshold {
            continue;
        }
        let mut stack = vec![index];
        visited[index] = true;
        let mut sum = 0.0;
        let mut sx = 0.0;
        let mut sy = 0.0;
        let mut count = 0;
        let mut minx = width;
        let mut miny = height;
        let mut maxx = 0;
        let mut maxy = 0;
        while let Some(i) = stack.pop() {
            let x = i % width;
            let y = i / width;
            let weight = changes[i];
            sum += weight;
            sx += (x as f64 * 4.0 + 2.0) * weight;
            sy += (y as f64 * 4.0 + 2.0) * weight;
            count += 1;
            minx = minx.min(x);
            maxx = maxx.max(x);
            miny = miny.min(y);
            maxy = maxy.max(y);
            for (nx, ny) in [
                (x.wrapping_sub(1), y),
                (x + 1, y),
                (x, y.wrapping_sub(1)),
                (x, y + 1),
            ] {
                if nx < width && ny < height {
                    let j = ny * width + nx;
                    if !visited[j] && changes[j] >= threshold {
                        visited[j] = true;
                        stack.push(j);
                    }
                }
            }
        }
        if !(2..=400).contains(&count) {
            continue;
        }
        let score = sum / (count as f64).sqrt() / (1.0 + count as f64 / 60.0);
        result.push(Candidate {
            x: sx / sum,
            y: sy / sum,
            score,
            area: count * 16,
            rect: Rect::new(
                minx * 4,
                miny * 4,
                (maxx - minx + 1) * 4,
                (maxy - miny + 1) * 4,
            ),
        });
    }
    result.sort_by(|a, b| b.score.total_cmp(&a.score));
    result.truncate(3);
    result
}

fn mark(image: &mut Image, x: usize, y: usize, color: [u8; 3]) {
    for offset in -12_isize..=12 {
        for (dx, dy) in [(offset, 0), (0, offset)] {
            let px = x as isize + dx;
            let py = y as isize + dy;
            if px >= 0 && py >= 0 && px < image.w as isize && py < image.h as isize {
                let i = (py as usize * image.w + px as usize) * 3;
                image.data[i..i + 3].copy_from_slice(&color);
            }
        }
    }
}

pub fn run(path: &Path, out: &Path) -> io::Result<()> {
    let metadata = video::metadata(path)?;
    let regions = Value::parse(&fs::read_to_string(out.join("regions.json"))?)?;
    let bar_y = regions
        .get("troop_bar")
        .array()
        .get(1)
        .and_then(Value::number)
        .unwrap_or(metadata.height as f64 * 0.78);
    let work = Path::new("/tmp/vidmine-work/positions").join(path.file_stem().unwrap());
    fs::create_dir_all(&work)?;
    let mut report=String::from("attack\tevent\tvideo_t\tslot\tx_pred\ty_pred\tcamera_error\tx_truth\ty_truth\tvisible\tnote\n");
    let mut audit = Image::blank(1280, 5 * 360);
    let mut audit_row = 0;
    let mut page = 0;
    for attack_path in icons::attack_paths(out)? {
        let mut attack = Value::parse(&fs::read_to_string(&attack_path)?)?;
        let number = attack.get("attack").number().unwrap_or(0.0) as usize;
        let key_t = attack
            .get("keyframe")
            .get("video_t")
            .number()
            .unwrap_or(0.0);
        let key = video::frame(path, key_t)?;
        attack.set("grid_fit",Value::parse("{\"status\":\"unreliable\",\"tile_coordinates_available\":false,\"reason\":\"no reviewed tile origin or building correspondences; retain screen coordinates and estimated camera similarity\"}")?);
        if let Some(events) = attack.object_array_mut("deployments") {
            for (event_id, event) in events.iter_mut().enumerate() {
                let t = event.get("video_t").number().unwrap_or(0.0);
                let before_t = (t - 0.4).max(0.0);
                let after_t = (t + 0.1).min(metadata.duration - 0.1);
                let before = video::frame(path, before_t)?;
                let after = video::frame(path, after_t)?;
                let camera = registration(&before, &after);
                let key_camera = registration(&key, &after);
                let found = candidates(
                    &before,
                    &after,
                    camera,
                    (bar_y * 360.0 / metadata.height as f64) as usize,
                );
                let sx = metadata.width as f64 / 640.0;
                let sy = metadata.height as f64 / 360.0;
                let top = found.first();
                let screen = top
                    .map(|p| format!("[{:.1},{:.1}]", p.x * sx, p.y * sy))
                    .unwrap_or_else(|| "null".into());
                let proposals = found.iter().map(|proposal| {
                    let rect = Rect::new(
                        (proposal.rect.x as f64 * sx) as usize,
                        (proposal.rect.y as f64 * sy) as usize,
                        (proposal.rect.w as f64 * sx) as usize,
                        (proposal.rect.h as f64 * sy) as usize,
                    );
                    format!(
                        "{{\"screen\":[{:.1},{:.1}],\"score\":{:.3},\"changed_area_pixels\":{},\"box\":{}}}",
                        proposal.x * sx, proposal.y * sy, proposal.score,
                        (proposal.area as f64 * sx * sy).round() as usize,
                        rect.json(),
                    )
                }).collect::<Vec<_>>().join(",");
                let position = Value::parse(&format!(
                    concat!(
                        "{{\"screen\":{},\"tile\":null,\"status\":\"unverified_appearance_candidate\",",
                        "\"accepted\":false,\"method\":\"camera-compensated pre/post RGB connected components; combat motion may dominate\",",
                        "\"before_video_t\":{:.3},\"after_video_t\":{:.3},\"source_dimensions\":[{},{}],",
                        "\"camera\":{{\"model\":\"uniform scale and translation\",",
                        "\"before_to_after\":[{:.5},{:.2},{:.2}],\"keyframe_to_after\":[{:.5},{:.2},{:.2}],",
                        "\"before_after_trimmed_rgb_error\":{:.5},\"keyframe_trimmed_rgb_error\":{:.5},",
                        "\"reliable\":{},\"keyframe_reliable\":{}}},\"candidates\":[{}]}}",
                    ),
                    screen, before_t, after_t, metadata.width, metadata.height,
                    camera.scale, camera.dx * sx, camera.dy * sy,
                    key_camera.scale, key_camera.dx * sx, key_camera.dy * sy,
                    camera.error, key_camera.error,
                    camera.error < 0.075, key_camera.error < 0.075, proposals,
                ))?;
                event.set("position", position);
                report.push_str(&format!(
                    "{number}\t{event_id}\t{t:.1}\t{}\t{}\t{}\t{:.5}\t\t\t\t\n",
                    event.get("slot").encode(),
                    top.map(|p| format!("{:.1}", p.x * sx))
                        .unwrap_or_else(|| "null".into()),
                    top.map(|p| format!("{:.1}", p.y * sy))
                        .unwrap_or_else(|| "null".into()),
                    camera.error
                ));
                let before = resized(&before, 640, 360);
                let mut after = resized(&after, 640, 360);
                if let Some(p) = top {
                    mark(&mut after, p.x as usize, p.y as usize, [255, 0, 0]);
                }
                audit.paste(&before, 0, audit_row * 360, 1);
                audit.paste(&after, 640, audit_row * 360, 1);
                audit_row += 1;
                if audit_row == 5 {
                    audit.save(&work.join(format!("page-{page:03}.ppm")))?;
                    page += 1;
                    audit_row = 0;
                    audit = Image::blank(1280, 1800);
                }
            }
        }
        fs::write(attack_path, attack.encode() + "\n")?;
        eprintln!("deployment positions: attack {number}");
    }
    if audit_row > 0 {
        audit.save(&work.join(format!("page-{page:03}.ppm")))?;
    }
    fs::write(out.join("position-check.tsv"), report)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn synthetic_static_camera_and_new_patch() {
        // Declared synthetic textured scene and one newly appearing red patch.
        let mut a = Image::blank(640, 360);
        for y in 0..360 {
            for x in 0..640 {
                let i = (y * 640 + x) * 3;
                let v = ((x * 13 + y * 7 + x * y) % 150 + 30) as u8;
                a.data[i..i + 3].copy_from_slice(&[v, v / 2, v / 3]);
            }
        }
        let mut b = a.clone();
        for y in 170..186 {
            for x in 250..266 {
                let i = (y * 640 + x) * 3;
                b.data[i..i + 3].copy_from_slice(&[250, 20, 160]);
            }
        }
        let camera = registration(&a, &b);
        assert!((camera.scale - 1.0).abs() < 0.01);
        assert!(camera.dx.abs() < 1.0 && camera.dy.abs() < 1.0);
        let found = candidates(&a, &b, camera, 280);
        assert!(!found.is_empty());
        assert!((found[0].x - 258.0).abs() < 8.0);
        assert!((found[0].y - 178.0).abs() < 8.0);
    }

    #[test]
    fn synthetic_translation_is_measured_in_analysis_pixels() {
        // Declared synthetic building-like colored blocks with a 32-pixel pan.
        let mut before = Image::blank(640, 360);
        for y in 0..360 {
            for x in 0..640 {
                let cell = (x / 12 * 71 + y / 12 * 43 + x / 12 * (y / 12) * 17) % 180 + 30;
                let i = (y * 640 + x) * 3;
                before.data[i..i + 3].copy_from_slice(&[
                    cell as u8,
                    (cell / 2) as u8,
                    (cell / 3) as u8,
                ]);
            }
        }
        let mut after = Image::blank(640, 360);
        after.paste(&before, 32, 0, 1);
        let camera = registration(&before, &after);
        assert!((camera.scale - 1.0).abs() < 0.01);
        assert!((camera.dx - 32.0).abs() < 2.0);
        assert!(camera.dy.abs() < 2.0);
        assert!(candidates(&before, &after, camera, 280).is_empty());
    }
}
