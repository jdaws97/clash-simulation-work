use crate::extract::{optional, read_full, Slot};
use crate::image::{Image, Rect};
use crate::ocr::Reader;
use crate::{probe, video};
use std::fs;
use std::io;
use std::path::Path;
use std::process::Command;

pub fn audit(video_path: &Path, out: &Path, templates: &Path) -> io::Result<()> {
    let regions = probe::locate(video_path, templates)?;
    let reader = Reader::load(templates)?;
    let replay = regions.layout == "cropped_replay";
    let replay_readings = if replay {
        fs::read_to_string(out.join("readings.jsonl"))?
            .lines()
            .map(crate::json::Value::parse)
            .collect::<io::Result<Vec<_>>>()?
    } else {
        Vec::new()
    };
    let slot_text = fs::read_to_string(out.join("slots.tsv"))?;
    let mut slots = Vec::new();
    for line in slot_text.lines().skip(1) {
        let n: Vec<usize> = line
            .split('\t')
            .map(|v| v.parse().map_err(|_| io::Error::other("invalid slots.tsv")))
            .collect::<io::Result<_>>()?;
        if n.len() != 9 {
            return Err(io::Error::other("invalid slots.tsv width"));
        }
        slots.push(Slot {
            index: n[0],
            rect: Rect::new(n[1], n[2], n[3], n[4]),
            count: Rect::new(n[5], n[6], n[7], n[8]),
        });
    }
    let id = video_path.file_stem().unwrap().to_string_lossy();
    let mut seed = 0xcbf29ce484222325_u64;
    for b in id.bytes() {
        seed = (seed ^ b as u64).wrapping_mul(0x100000001b3);
    }
    let mut samples = Vec::new();
    for _ in 0..10 {
        seed = seed
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        let mut t =
            ((seed >> 32) as f64 / u32::MAX as f64 * (regions.duration - 1.0) * 5.0).floor() / 5.0;
        if replay {
            t = t.floor();
        }
        let slot = (seed as usize >> 16) % slots.len().max(1);
        samples.push((t, slot));
    }
    samples.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut sheet = Image::blank(1200, 10 * 240);
    let mut text = String::from("sample\tvideo_t\tphase_pred\tclock_pred\tdamage_pred\tstars_pred\tslot\tcount_pred\tphase_truth\tclock_truth\tdamage_truth\tstars_truth\tcount_truth\n");
    for (i, (t, slot)) in samples.iter().enumerate() {
        let image = video::frame(video_path, *t)?;
        let replay_sample = replay_readings.get(*t as usize);
        let dynamic = replay_sample.map(|v| {
            v.get("clock_box")
                .array()
                .iter()
                .filter_map(crate::json::Value::number)
                .map(|v| v as usize)
                .collect::<Vec<_>>()
        });
        let dynamic = dynamic
            .filter(|v| v.len() == 4 && v[2] > 0)
            .map(|v| Rect::new(v[0], v[1], v[2], v[3]));
        let reading = if replay {
            crate::extract::Frame {
                t: *t,
                phase: replay_sample
                    .and_then(|v| v.get("phase").string())
                    .map(|v| if v == "attack" { "attack" } else { "other" })
                    .unwrap_or("other"),
                clock: dynamic
                    .map(|r| reader.clock(&image.crop(r)))
                    .unwrap_or_else(crate::ocr::Reading::missing),
                damage: crate::ocr::Reading::missing(),
                stars: None,
                star_confidence: 0.0,
                slots: vec![],
                label_score: 0.0,
            }
        } else {
            read_full(&image, &regions, &reader, templates, &slots, *t)?
        };
        let mut thumb = Image::blank(image.w / 3, image.h / 3);
        for y in 0..thumb.h {
            for x in 0..thumb.w {
                let j = (y * thumb.w + x) * 3;
                thumb.data[j..j + 3].copy_from_slice(&image.pixel(x * 3, y * 3));
            }
        }
        let y = i * 240;
        sheet.paste(&thumb, 0, y, 1);
        if replay {
            let r = dynamic.unwrap_or(Rect::new(
                0,
                image.h.saturating_sub(110),
                image.w.min(360),
                110,
            ));
            let crop = image.crop(r);
            sheet.paste(&crop, 440, y + 5, 1);
        } else {
            sheet.paste(
                &image.crop(Rect::new(
                    regions.clock.x,
                    regions.battle_label.y,
                    regions.clock.w,
                    47,
                )),
                440,
                y + 5,
                2,
            );
        }
        sheet.paste(
            &image.crop(Rect::new(
                regions.stars.x,
                regions.damage_label.y,
                regions.damage.x + regions.damage.w - regions.stars.x,
                55,
            )),
            440,
            y + 110,
            2,
        );
        if let Some(slot) = slots.get(*slot) {
            sheet.paste(&image.crop(slot.rect), 810, y + 5, 2);
            sheet.paste(&image.crop(slot.count), 960, y + 20, 4);
        }
        let count = reading.slots.get(*slot).and_then(|r| r.value);
        text.push_str(&format!(
            "{}\t{t:.1}\t{}\t{}\t{}\t{}\t{slot}\t{}\t\t\t\t\t\n",
            i + 1,
            reading.phase,
            optional(reading.clock.value),
            optional(reading.damage.value),
            optional(reading.stars),
            optional(count)
        ));
    }
    fs::create_dir_all("/tmp/vidmine-work")?;
    let ppm = format!("/tmp/vidmine-work/{id}-audit.ppm");
    let png = format!("/tmp/vidmine-work/{id}-audit.png");
    sheet.save(Path::new(&ppm))?;
    let status = Command::new("ffmpeg")
        .args(["-v", "error", "-y", "-i", &ppm, &png])
        .status()?;
    if !status.success() {
        return Err(io::Error::other("audit PNG conversion failed"));
    }
    fs::remove_file(ppm)?;
    fs::write(out.join("spot-check.tsv"), &text)?;
    println!("{text}");
    eprintln!("View {png}. Truth fields are intentionally blank until a human labels them. Random seed: FNV-1a(video_id), LCG; ten uniform times.");
    Ok(())
}

pub fn score(out: &Path) -> io::Result<()> {
    let text = fs::read_to_string(out.join("spot-check.tsv"))?;
    let fields = [
        ("phase", 2, 8),
        ("clock", 3, 9),
        ("damage", 4, 10),
        ("stars", 5, 11),
        ("count", 7, 12),
    ];
    let mut report = String::from("field\tlabeled\terrors\tabstentions\terror_rate\n");
    for (name, pred, truth) in fields {
        let mut total = 0;
        let mut errors = 0;
        let mut missing = 0;
        for line in text.lines().skip(1) {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() < 13 {
                return Err(io::Error::other("spot-check.tsv requires all 13 columns"));
            }
            if parts[truth].is_empty() || parts[truth] == "na" {
                continue;
            }
            total += 1;
            if parts[pred] == "null" {
                missing += 1;
            }
            if parts[pred] != parts[truth] {
                errors += 1;
            }
        }
        report.push_str(&format!(
            "{name}\t{total}\t{errors}\t{missing}\t{:.4}\n",
            errors as f64 / total.max(1) as f64
        ));
    }
    fs::write(out.join("accuracy.tsv"), &report)?;
    print!("{report}");
    Ok(())
}
