//! M4 spatial evidence. Temporary review pixels have one fixed scratch root.
use crate::camera::{Estimate, Tracker, Transform};
use crate::grid::{Grid, Landmark};
use crate::image::Image;
use crate::json::Value;
use crate::{appearance, grid, icons, townhall, video};
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::Path;

pub const WORK: &str = "/tmp/vidmine-work-m4";
const POSITION_HEADER: &str = "attack\tevent\tvideo_t\tname\tdelta\tx_pred\ty_pred\ttile_x_pred\ttile_y_pred\tcamera_reliable\tstatus\n";

pub fn resize(image: &Image, width: usize) -> Image {
    let height = image.h * width / image.w;
    let mut result = Image::blank(width, height);
    for y in 0..height {
        for x in 0..width {
            let offset = (y * width + x) * 3;
            result.data[offset..offset + 3]
                .copy_from_slice(&image.pixel(x * image.w / width, y * image.h / height));
        }
    }
    result
}

pub fn prepare(path: &Path, out: &Path) -> io::Result<()> {
    let id = path.file_stem().unwrap().to_string_lossy();
    let work = Path::new(WORK).join(id.as_ref());
    fs::create_dir_all(&work)?;
    let mut table = String::from("attack\tcandidate\tvideo_t\n");
    for attack_path in icons::attack_paths(out)? {
        let attack = Value::parse(&fs::read_to_string(attack_path)?)?;
        let number = attack.get("attack").number().unwrap_or(0.0) as usize;
        let start = attack
            .get("video_t_start")
            .number()
            .or_else(|| {
                attack
                    .get("video_interval")
                    .array()
                    .first()
                    .and_then(Value::number)
            })
            .unwrap_or_else(|| attack.get("keyframe").get("video_t").number().unwrap());
        let height = video::metadata(path)?.height * 640 / video::metadata(path)?.width + 22;
        let mut sheet = Image::blank(1280, 3 * height);
        for (index, offset) in [-25.0, -18.0, -12.0, -6.0, -2.0, 0.0].iter().enumerate() {
            let time = (start + offset).max(0.0);
            let frame = video::frame(path, time)?;
            frame.save(&work.join(format!("key-{number:02}-{index}.ppm")))?;
            let thumb = resize(&frame, 640);
            sheet.paste(&thumb, index % 2 * 640, index / 2 * height + 15, 1);
            icons::digits(
                &mut sheet,
                &format!("{index} {}", time as usize),
                index % 2 * 640 + 10,
                index / 2 * height,
            );
            table.push_str(&format!("{number}\t{index}\t{time:.3}\n"));
        }
        sheet.save(&work.join(format!("keys-{number:02}.ppm")))?;
        eprintln!("keyframe review {id} attack {number}");
    }
    fs::write(work.join("key-candidates.tsv"), table)
}

pub fn saved_review(root: &Path) -> io::Result<()> {
    let work = Path::new(WORK).join("saved");
    fs::create_dir_all(&work)?;
    let mut table = String::from("sample\tpath\n");
    let mut sheet = Image::blank(1280, 4 * 210);
    let mut sample = 0;
    for dir in icons::directories(root)? {
        for path in icons::attack_paths(&dir)?.into_iter().take(1) {
            let attack = Value::parse(&fs::read_to_string(path)?)?;
            let Some(key_path) = attack.get("keyframe").get("path").string() else {
                continue;
            };
            let key = video::still(&dir.join(key_path))?;
            let mut thumb = resize(&key, 320);
            icons::digits(&mut thumb, &sample.to_string(), 8, 10);
            sheet.paste(&thumb, sample % 4 * 320, sample % 16 / 4 * 210, 1);
            table.push_str(&format!("{sample}\t{}\n", dir.join(key_path).display()));
            sample += 1;
            if sample % 16 == 0 {
                sheet.save(&work.join(format!("page-{:02}.ppm", sample / 16 - 1)))?;
                sheet = Image::blank(1280, 4 * 210);
            }
        }
    }
    if sample % 16 != 0 {
        sheet.save(&work.join(format!("page-{:02}.ppm", sample / 16)))?;
    }
    fs::write(work.join("samples.tsv"), table)
}

struct Label {
    attack: usize,
    time: f64,
    grid: Grid,
    wall_pairs: usize,
}

fn labels(path: &Path) -> io::Result<Vec<Label>> {
    let mut labels = Vec::new();
    for line in fs::read_to_string(path)?.lines().skip(1) {
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let cells: Vec<_> = line.split('\t').collect();
        if cells.len() < 6 {
            return Err(io::Error::other(
                "grid labels require attack, video_t, cx, top, a, b",
            ));
        }
        let number = |i: usize| -> io::Result<f64> {
            cells[i]
                .parse::<f64>()
                .ok()
                .filter(|v| v.is_finite())
                .ok_or_else(|| io::Error::other("invalid finite grid label"))
        };
        let time = number(1)?;
        let cx = number(2)?;
        let top = number(3)?;
        let a = number(4)?;
        let b = number(5)?;
        if time < 0.0 {
            return Err(io::Error::other("negative keyframe time"));
        }
        // Parameters are the manual line-intersection fit. Reconstructing the
        // boundary intersections here checks orientation, not independent truth.
        let corners: Vec<_> = [(0.0, 0.0), (44.0, 0.0), (0.0, 44.0), (44.0, 44.0)]
            .iter()
            .map(|&(x, y)| Landmark {
                x,
                y,
                sx: cx + (x - y) * a,
                sy: top + (x + y) * b,
            })
            .collect();
        let fitted = grid::fit(&corners)?;
        let attack = number(0)?;
        if attack < 1.0 || attack.fract() != 0.0 {
            return Err(io::Error::other("attack index must be a positive integer"));
        }
        let wall_pairs = cells
            .get(6)
            .and_then(|s| s.parse::<usize>().ok())
            .unwrap_or(0);
        labels.push(Label {
            attack: attack as usize,
            time,
            grid: fitted,
            wall_pairs,
        });
    }
    labels.sort_by_key(|l| l.attack);
    if labels
        .windows(2)
        .any(|pair| pair[0].attack == pair[1].attack)
    {
        return Err(io::Error::other("duplicate attack in grid labels"));
    }
    Ok(labels)
}

fn copy_labels(source: &Path, destination: &Path) -> io::Result<()> {
    if destination.exists() && source.canonicalize()? == destination.canonicalize()? {
        return Ok(());
    }
    fs::copy(source, destination)?;
    Ok(())
}

pub fn learn(manifest: &Path, templates: &Path) -> io::Result<()> {
    // source, image path, cx, top, a, b, center_x, center_y, TH label.
    for line in fs::read_to_string(manifest)?.lines().skip(1) {
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 9 {
            return Err(io::Error::other(
                "TH manifest needs nine tab-separated fields",
            ));
        }
        let n = |i: usize| -> io::Result<f64> {
            c[i].parse::<f64>()
                .ok()
                .filter(|n| n.is_finite())
                .ok_or_else(|| io::Error::other("invalid TH manifest number"))
        };
        let image = video::still(Path::new(c[1]))?;
        let grid = Grid {
            cx: n(2)?,
            top: n(3)?,
            a: n(4)?,
            b: n(5)?,
            residual: 0.0,
            landmarks: 0,
        };
        townhall::learn(
            &image,
            grid,
            (n(6)?, n(7)?),
            n(8)? as u32,
            c[0],
            &templates.join("townhalls"),
        )?;
        eprintln!("learned inspected TH{} sprite {}", c[8], c[0]);
    }
    Ok(())
}

fn png(image: &Image, path: &Path) -> io::Result<()> {
    let ppm = path.with_extension("ppm");
    image.save(&ppm)?;
    let result = std::process::Command::new("ffmpeg")
        .args(["-v", "error", "-threads", "1", "-y", "-i"])
        .arg(&ppm)
        .arg(path)
        .output()?;
    if !result.status.success() {
        return Err(io::Error::other(String::from_utf8_lossy(&result.stderr)));
    }
    fs::remove_file(ppm)
}

pub fn run(
    path: &Path,
    out: &Path,
    label_path: &Path,
    templates: &Path,
    preview: bool,
    only_attack: Option<usize>,
) -> io::Result<()> {
    let metadata = video::metadata(path)?;
    let regions = Value::parse(&fs::read_to_string(out.join("regions.json"))?)?;
    let bar_y = regions
        .get("troop_bar")
        .array()
        .get(1)
        .and_then(Value::number)
        .unwrap_or(metadata.height as f64 * 0.78);
    let pixel_scale = metadata.width as f64 / 640.0;
    let id = path.file_stem().unwrap().to_string_lossy();
    let work = Path::new(WORK).join(id.as_ref());
    fs::create_dir_all(&work)?;
    let destination = if preview {
        work.join("pending-output")
    } else {
        out.to_path_buf()
    };
    fs::create_dir_all(&destination)?;
    let library = townhall::Library::load(&templates.join("townhalls"))?;
    let labels = labels(label_path)?;
    let paths = icons::attack_paths(out)?;
    // Check all selected references before changing any attack artifact.
    for attack_path in &paths {
        let attack = Value::parse(&fs::read_to_string(attack_path)?)?;
        let number = attack
            .get("attack")
            .number()
            .ok_or_else(|| io::Error::other("missing attack index"))? as usize;
        if only_attack.is_some_and(|n| n != number) {
            continue;
        }
        let label = labels
            .iter()
            .find(|l| l.attack == number)
            .ok_or_else(|| io::Error::other(format!("no reviewed grid for attack {number}")))?;
        let start = attack
            .get("video_t_start")
            .number()
            .ok_or_else(|| io::Error::other("missing attack start"))?;
        if label.time > start || label.time >= metadata.duration {
            return Err(io::Error::other(
                "spatial reference must be before or at attack start",
            ));
        }
        if attack.get("video_id").string() != Some(id.as_ref()) {
            return Err(io::Error::other(
                "source video filename does not match attack video ID",
            ));
        }
    }
    let probe = destination.join(format!(".vidmine-m4-write-probe-{}", std::process::id()));
    let probe_file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&probe)?;
    drop(probe_file);
    fs::remove_file(probe)?;
    let mut positions = String::from(POSITION_HEADER);
    let mut th_report =
        String::from("attack\tkeyframe_t\tth_pred\terror\tmargin\tx_pred\ty_pred\n");
    let mut camera_report =
        String::from("attack\tvideo_t\tscale\tdx\tdy\tinliers\trms_pixels\treliable\n");
    for attack_path in paths {
        let mut attack = Value::parse(&fs::read_to_string(&attack_path)?)?;
        let number = attack.get("attack").number().unwrap_or(0.0) as usize;
        if only_attack.is_some_and(|n| n != number) {
            continue;
        }
        let label = labels
            .iter()
            .find(|l| l.attack == number)
            .ok_or_else(|| io::Error::other(format!("no reviewed grid for attack {number}")))?;
        let key = video::frame(path, label.time)?;
        let tracker = Tracker::new(&key, Some(label.grid), bar_y);
        let th = library.classify(&key, label.grid, None);
        th_report.push_str(&format!(
            "{number}\t{:.3}\t{}\t{:.5}\t{:.5}\t{:.1}\t{:.1}\n",
            label.time,
            th.level
                .map(|n| n.to_string())
                .unwrap_or_else(|| "null".into()),
            th.score,
            th.margin,
            th.center.0,
            th.center.1
        ));
        attack.set(
            "defender_th",
            th.level
                .map(|n| Value::from(n as f64))
                .unwrap_or(Value::Null),
        );
        attack.set(
            "defender_th_reason",
            if th.level.is_some() {
                "reviewed grid-normalized sprite library match; development classifier"
            } else {
                "grid-normalized sprite search weak or ambiguous"
            }
            .into(),
        );
        attack.set("defender_th_evidence", th.json());
        let mut grid_value = label.grid.json();
        grid_value.set("status", "provisional_boundary_origin_fit".into());
        grid_value.set("landmark_rms_pixels", Value::Null);
        grid_value.set("method", "manual fit to visible buildable-boundary line intersections and wall spacing; clipped corners extrapolated".into());
        grid_value.set(
            "origin_uncertainty",
            "boundary/scenery fit; absolute tile origin lacks independent game-layout verification"
                .into(),
        );
        grid_value.set("landmarks", 0.0.into());
        grid_value.set("labels", "m4-grid-labels.tsv".into());
        grid_value.set("wall_spacing_pairs", (label.wall_pairs as f64).into());
        grid_value.set(
            "scale_method",
            if label.wall_pairs > 0 {
                "reviewed yellow wall-cap displacement mode"
            } else {
                "manual spacing estimate; insufficient reliable wall-cap pairs"
            }
            .into(),
        );
        attack.set("grid_fit", grid_value);
        let mut key_metadata = Value::Object(Default::default());
        key_metadata.set("video_t", label.time.into());
        key_metadata.set(
            "base_visibility",
            "preparation_reference_manually_reviewed".into(),
        );
        key_metadata.set(
            "frame_storage",
            "transient under /tmp/vidmine-work-m4; no new source frames retained in output".into(),
        );
        key_metadata.set(
            "dimensions",
            Value::Array(vec![
                (metadata.width as f64).into(),
                (metadata.height as f64).into(),
            ]),
        );
        key_metadata.set("rgb_fingerprint", fingerprint(&key).as_str().into());
        attack.set("spatial_keyframe", key_metadata);
        png(
            &grid::overlay(&key, label.grid),
            &work.join(format!("grid-{number:02}.png")),
        )?;
        let start = attack
            .get("video_t_start")
            .number()
            .ok_or_else(|| io::Error::other("missing attack start"))?;
        let end = attack
            .get("video_t_end")
            .number()
            .ok_or_else(|| io::Error::other("missing attack end"))?;
        let mut times = Vec::new();
        let mut time = label.time;
        while time < start {
            times.push((time * 1000.0).round() as i64);
            time += 1.0;
        }
        let mut time = start;
        while time <= end {
            times.push((time * 1000.0).round() as i64);
            time += 2.0;
        }
        times.push((end * 1000.0).round() as i64);
        for event in attack.get("deployments").array() {
            let time = event
                .get("video_t")
                .number()
                .ok_or_else(|| io::Error::other("event missing video_t"))?;
            times.push(((time - 0.65).max(0.0) * 1000.0).round() as i64);
            times.push(((time + 0.15).min(metadata.duration - 0.05) * 1000.0).round() as i64);
        }
        times.sort();
        times.dedup();
        let mut frames: BTreeMap<i64, (Image, Estimate)> = BTreeMap::new();
        let mut last_image = tracker.key.clone();
        let mut last_camera = Transform::identity();
        let mut last_time = label.time;
        let mut camera_samples = Vec::new();
        for time in times {
            let frame = resize(&video::frame(path, time as f64 / 1000.0)?, 640);
            let current_time = time as f64 / 1000.0;
            let previous_grid = Grid {
                cx: label.grid.cx / pixel_scale * last_camera.scale + last_camera.dx,
                top: label.grid.top / pixel_scale * last_camera.scale + last_camera.dy,
                a: label.grid.a / pixel_scale * last_camera.scale,
                b: label.grid.b / pixel_scale * last_camera.scale,
                residual: 0.0,
                landmarks: 0,
            };
            let pair_tracker = Tracker::new(&last_image, Some(previous_grid), bar_y / pixel_scale);
            let mut estimate = pair_tracker.estimate_pair(&frame);
            let mut reference_time = last_time;
            if estimate.reliable {
                for track in &mut estimate.tracks {
                    track.key = last_camera.inverse(track.key.0, track.key.1);
                }
                estimate.transform = last_camera.then(estimate.transform);
            } else if current_time - last_time < 5.0 {
                estimate = pair_tracker.estimate(&frame, Some(Transform::identity()));
                for track in &mut estimate.tracks {
                    track.key = last_camera.inverse(track.key.0, track.key.1);
                }
                estimate.transform = last_camera.then(estimate.transform);
            } else {
                estimate = tracker.estimate(&frame, Some(last_camera));
                reference_time = label.time;
            }
            let mut sample = estimate.json(current_time, pixel_scale);
            sample.set("tracked_from_video_t", reference_time.into());
            sample.set("reference", "tracks expressed in original keyframe coordinates after composing adjacent-frame fits".into());
            if estimate.reliable {
                last_camera = estimate.transform;
                last_image = frame.clone();
                last_time = current_time;
            }
            camera_report.push_str(&format!(
                "{number}\t{:.3}\t{:.6}\t{:.2}\t{:.2}\t{}\t{:.3}\t{}\n",
                time as f64 / 1000.0,
                estimate.transform.scale,
                estimate.transform.dx * pixel_scale,
                estimate.transform.dy * pixel_scale,
                estimate.tracks.len(),
                estimate.rms * pixel_scale,
                estimate.reliable
            ));
            camera_samples.push(sample);
            frames.insert(time, (frame, estimate));
            if frames.len().is_multiple_of(20) {
                eprintln!(
                    "M4 {id} attack {number} frame {:.1}: {} inliers, reliable {}",
                    current_time,
                    frames[&time].1.tracks.len(),
                    frames[&time].1.reliable
                );
            }
        }
        let mut model = Value::Object(Default::default());
        model.set(
            "model",
            "screen_frame = scale * screen_keyframe + [dx,dy]; no rotation; source pixels".into(),
        );
        model.set("reference", "spatial_keyframe, selected preparation frame; original saved keyframe metadata is unchanged".into());
        model.set("method", "textured static building patches; adjacent-frame scale/pan fits composed from the keyframe, deterministic pair consensus and least squares inliers; direct keyframe recovery on tracking failure".into());
        model.set("interpolation", "none; one-second preparation and two-second battle samples plus event brackets; unreliable fits must not map tiles; composition can accumulate drift".into());
        model.set("samples", Value::Array(camera_samples));
        attack.set("camera_model", model);
        if let Some(events) = attack.object_array_mut("deployments") {
            for (index, event) in events.iter_mut().enumerate() {
                let t = event.get("video_t").number().unwrap();
                let bt = ((t - 0.65).max(0.0) * 1000.0).round() as i64;
                let at = ((t + 0.15).min(metadata.duration - 0.05) * 1000.0).round() as i64;
                let (before, bc) = &frames[&bt];
                let (after, ac) = &frames[&at];
                let name = event.get("name").string().unwrap_or("unknown").to_owned();
                let context = EventContext {
                    grid: label.grid,
                    before_camera: bc.transform,
                    after_camera: ac.transform,
                    after_reliable: ac.reliable,
                    before_t: bt as f64 / 1000.0,
                    after_t: at as f64 / 1000.0,
                    width: metadata.width,
                    height: metadata.height,
                    bar_y,
                };
                event.set("position", context.locate(before, after, &name));
                positions.push_str(&position_row(number, index, event));
                // Review raw before/after pairs without prediction marks so manual
                // truth need not be copied from the classifier's preferred point.
                let height = after.h + 20;
                let mut pair = Image::blank(1280, height);
                pair.paste(before, 0, 20, 1);
                pair.paste(after, 640, 20, 1);
                icons::digits(
                    &mut pair,
                    &format!("{number} {index} {}", (t * 10.0).round() as usize),
                    10,
                    4,
                );
                png(
                    &pair,
                    &work.join(format!("event-{number:02}-{index:03}.png")),
                )?;
            }
        }
        fs::write(
            destination.join(attack_path.file_name().unwrap()),
            attack.encode() + "\n",
        )?;
        eprintln!(
            "M4 {id} attack {number}: {} camera samples, TH {:?}",
            frames.len(),
            th.level
        );
    }
    fs::write(destination.join("m4-positions.tsv"), positions)?;
    fs::write(destination.join("m4-townhalls.tsv"), th_report)?;
    fs::write(destination.join("m4-camera.tsv"), camera_report)?;
    copy_labels(label_path, &destination.join("m4-grid-labels.tsv"))?;
    Ok(())
}

struct EventContext {
    grid: Grid,
    before_camera: Transform,
    after_camera: Transform,
    after_reliable: bool,
    before_t: f64,
    after_t: f64,
    width: usize,
    height: usize,
    bar_y: f64,
}

impl EventContext {
    fn locate(&self, before: &Image, after: &Image, name: &str) -> Value {
        let pixel_scale = self.width as f64 / 640.0;
        let local = Tracker::new(before, None, self.bar_y / pixel_scale).estimate_pair(after);
        let reliable = local.reliable && self.after_reliable;
        let camera = self.after_camera;
        let after_grid = reliable.then_some(Grid {
            cx: self.grid.cx / pixel_scale * camera.scale + camera.dx,
            top: self.grid.top / pixel_scale * camera.scale + camera.dy,
            a: self.grid.a / pixel_scale * camera.scale,
            b: self.grid.b / pixel_scale * camera.scale,
            residual: 0.0,
            landmarks: 0,
        });
        let spell_or_unknown = name.contains("Spell") || name == "unknown";
        let found = if local.reliable {
            appearance::detect(
                before,
                after,
                local.transform.inverted(),
                Transform::identity(),
                after_grid,
                (self.bar_y / pixel_scale) as usize,
                spell_or_unknown,
            )
        } else {
            Vec::new()
        };
        let candidates: Vec<_> = found
            .iter()
            .map(|p| p.json(pixel_scale, Some(self.grid), reliable.then_some(camera)))
            .collect();
        let top = candidates.first().cloned().unwrap_or(Value::Null);
        let mut position = Value::Object(Default::default());
        position.set("screen", top.get("screen").clone());
        position.set("tile", top.get("tile").clone());
        position.set("accepted", false.into());
        position.set("version", "m4-local-registration-v2".into());
        position.set(
            "status",
            if reliable {
                "unverified_new_appearance_candidate"
            } else if local.reliable {
                "local_camera_only_no_tile"
            } else {
                "unreliable_camera_no_position"
            }
            .into(),
        );
        position.set("method", "local camera-compensated RGB onset components with deployment-color cues and a troop edge prior when identity is known; appearance/effect center, not touch coordinate".into());
        position.set("before_video_t", self.before_t.into());
        position.set("after_video_t", self.after_t.into());
        position.set(
            "source_dimensions",
            Value::Array(vec![
                (self.width as f64).into(),
                (self.height as f64).into(),
            ]),
        );
        position.set("camera_reliable", reliable.into());
        position.set("local_camera_reliable", local.reliable.into());
        position.set("before_to_after", local.transform.json(pixel_scale));
        position.set("keyframe_to_after", camera.json(pixel_scale));
        position.set("keyframe_to_before", self.before_camera.json(pixel_scale));
        position.set("individual_unit_positions_resolved", false.into());
        position.set("candidates", Value::Array(candidates));
        position
    }
}

fn position_row(attack: usize, index: usize, event: &Value) -> String {
    let p = event.get("position");
    let field = |key: &str, i: usize| {
        p.get(key)
            .array()
            .get(i)
            .map(Value::encode)
            .unwrap_or_else(|| "null".into())
    };
    format!(
        "{attack}\t{index}\t{:.3}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
        event.get("video_t").number().unwrap(),
        event.get("name").string().unwrap_or("unknown"),
        event.get("delta").encode(),
        field("screen", 0),
        field("screen", 1),
        field("tile", 0),
        field("tile", 1),
        p.get("camera_reliable").encode(),
        p.get("status").string().unwrap()
    )
}

pub fn reposition(path: &Path, out: &Path, regions_path: &Path) -> io::Result<()> {
    let metadata = video::metadata(path)?;
    let regions = Value::parse(&fs::read_to_string(regions_path)?)?;
    let bar_y = regions
        .get("troop_bar")
        .array()
        .get(1)
        .and_then(Value::number)
        .ok_or_else(|| io::Error::other("regions file lacks troop bar"))?;
    let mut report = String::from(POSITION_HEADER);
    for attack_path in icons::attack_paths(out)? {
        let mut attack = Value::parse(&fs::read_to_string(&attack_path)?)?;
        let number = attack.get("attack").number().unwrap_or(0.0) as usize;
        let grid = attack.get("grid_fit");
        let grid = Grid {
            cx: grid
                .get("cx")
                .number()
                .ok_or_else(|| io::Error::other("missing M4 grid"))?,
            top: grid.get("top").number().unwrap(),
            a: grid.get("a").number().unwrap(),
            b: grid.get("b").number().unwrap(),
            residual: 0.0,
            landmarks: 0,
        };
        let samples = attack.get("camera_model").get("samples").array().to_vec();
        let pixel_scale = metadata.width as f64 / 640.0;
        let camera_at = |time: f64| -> io::Result<(Transform, bool)> {
            let sample = samples
                .iter()
                .find(|s| {
                    s.get("video_t")
                        .number()
                        .is_some_and(|t| (t - time).abs() < 0.001)
                })
                .ok_or_else(|| {
                    io::Error::other(
                        "event bracket not present in camera model; run full spatial pass",
                    )
                })?;
            let c = sample.get("keyframe_to_frame").array();
            if c.len() != 3 {
                return Err(io::Error::other("invalid saved camera"));
            }
            Ok((
                Transform {
                    scale: c[0].number().unwrap(),
                    dx: c[1].number().unwrap() / pixel_scale,
                    dy: c[2].number().unwrap() / pixel_scale,
                },
                sample.get("reliable") == &Value::Bool(true),
            ))
        };
        if let Some(events) = attack.object_array_mut("deployments") {
            for (index, event) in events.iter_mut().enumerate() {
                let time = event.get("video_t").number().unwrap();
                let before_t = ((time - 0.65).max(0.0) * 1000.0).round() / 1000.0;
                let after_t =
                    ((time + 0.15).min(metadata.duration - 0.05) * 1000.0).round() / 1000.0;
                let before = resize(&video::frame(path, before_t)?, 640);
                let after = resize(&video::frame(path, after_t)?, 640);
                let (before_camera, _) = camera_at(before_t)?;
                let (after_camera, after_reliable) = camera_at(after_t)?;
                let context = EventContext {
                    grid,
                    before_camera,
                    after_camera,
                    after_reliable,
                    before_t,
                    after_t,
                    width: metadata.width,
                    height: metadata.height,
                    bar_y,
                };
                let name = event.get("name").string().unwrap_or("unknown").to_owned();
                event.set("position", context.locate(&before, &after, &name));
                report.push_str(&position_row(number, index, event));
            }
        }
        fs::write(attack_path, attack.encode() + "\n")?;
        eprintln!("M4 local position update attack {number}");
    }
    fs::write(out.join("m4-positions.tsv"), report)
}

fn fingerprint(image: &Image) -> String {
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in &image.data {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("fnv1a64-rgb:{hash:016x}")
}

pub fn keyframes(path: &Path, label_path: &Path, templates: &Path) -> io::Result<()> {
    let library = townhall::Library::load(&templates.join("townhalls"))?;
    let id = path.file_stem().unwrap().to_string_lossy();
    let work = Path::new(WORK).join(id.as_ref());
    fs::create_dir_all(&work)?;
    println!("attack\tkey_t\tth_pred\terror\tmargin\tx\ty");
    for label in labels(label_path)? {
        let image = video::frame(path, label.time)?;
        let th = library.classify(&image, label.grid, None);
        println!(
            "{}\t{}\t{:?}\t{:.4}\t{:.4}\t{:.1}\t{:.1}",
            label.attack, label.time, th.level, th.score, th.margin, th.center.0, th.center.1
        );
        let mut overlay = grid::overlay(&image, label.grid);
        grid::cross(&mut overlay, th.center.0, th.center.1, [255, 30, 20]);
        png(
            &overlay,
            &work.join(format!("grid-{:02}.png", label.attack)),
        )?;
    }
    Ok(())
}

pub fn camera_check(path: &Path, key_time: f64, time: f64) -> io::Result<()> {
    let key = video::frame(path, key_time)?;
    let frame = video::frame(path, time)?;
    let tracker = Tracker::new(&key, None, key.h as f64 * 0.8);
    for (name, estimate) in [
        ("pair", tracker.estimate_pair(&frame)),
        ("global", tracker.estimate(&frame, None)),
    ] {
        println!(
            "{name}\t{}",
            estimate.json(time, key.w as f64 / 640.0).encode()
        );
    }
    Ok(())
}

pub fn spacing(path: &Path, label_path: &Path) -> io::Result<()> {
    println!("attack\tvideo_t\tcx\ttop\ta\tb\twall_pairs");
    for label in labels(label_path)? {
        let image = video::frame(path, label.time)?;
        if let Some(spacing) = grid::wall_spacing(&image, label.grid.a, image.h * 4 / 5) {
            let top = label.grid.top + 44.0 * (label.grid.b - spacing.b);
            println!(
                "{}\t{:.3}\t{:.3}\t{:.3}\t{:.4}\t{:.4}\t{}",
                label.attack, label.time, label.grid.cx, top, spacing.a, spacing.b, spacing.pairs
            );
        } else {
            println!(
                "{}\t{:.3}\t{:.3}\t{:.3}\t{:.4}\t{:.4}\t0",
                label.attack, label.time, label.grid.cx, label.grid.top, label.grid.a, label.grid.b
            );
        }
    }
    Ok(())
}

pub fn refresh(path: &Path, out: &Path, label_path: &Path, templates: &Path) -> io::Result<()> {
    let labels = labels(label_path)?;
    let library = townhall::Library::load(&templates.join("townhalls"))?;
    let mut report = String::from("attack\tkeyframe_t\tth_pred\terror\tmargin\tx_pred\ty_pred\n");
    for attack_path in icons::attack_paths(out)? {
        let mut attack = Value::parse(&fs::read_to_string(&attack_path)?)?;
        let number = attack.get("attack").number().unwrap() as usize;
        let label = labels
            .iter()
            .find(|l| l.attack == number)
            .ok_or_else(|| io::Error::other("missing reviewed grid label"))?;
        if attack
            .get("spatial_keyframe")
            .get("video_t")
            .number()
            .is_none_or(|t| (t - label.time).abs() > 0.001)
        {
            return Err(io::Error::other(
                "grid refresh must preserve camera reference time",
            ));
        }
        let key = video::frame(path, label.time)?;
        let mut fitted = label.grid.json();
        fitted.set("status", "provisional_boundary_origin_fit".into());
        fitted.set("method","manual boundary origin with reviewed wall-cap spacing where available; clipped corners extrapolated".into());
        fitted.set("landmark_rms_pixels", Value::Null);
        fitted.set("landmarks", 0.0.into());
        fitted.set("wall_spacing_pairs", (label.wall_pairs as f64).into());
        fitted.set("labels", "m4-grid-labels.tsv".into());
        fitted.set("origin_uncertainty","no independent game-layout origin verification; tile errors must be reported conditionally".into());
        attack.set("grid_fit", fitted);
        let th = library.classify(&key, label.grid, None);
        attack.set(
            "defender_th",
            th.level
                .map(|n| Value::from(n as f64))
                .unwrap_or(Value::Null),
        );
        attack.set("defender_th_evidence", th.json());
        attack.set(
            "defender_th_reason",
            if th.level.is_some() {
                "grid-normalized sprite match; development classifier"
            } else {
                "grid-normalized sprite search weak or ambiguous"
            }
            .into(),
        );
        report.push_str(&format!(
            "{number}\t{:.3}\t{}\t{:.5}\t{:.5}\t{:.1}\t{:.1}\n",
            label.time,
            attack.get("defender_th").encode(),
            th.score,
            th.margin,
            th.center.0,
            th.center.1
        ));
        fs::write(attack_path, attack.encode() + "\n")?;
    }
    fs::write(out.join("m4-townhalls.tsv"), report)?;
    copy_labels(label_path, &out.join("m4-grid-labels.tsv"))?;
    Ok(())
}
