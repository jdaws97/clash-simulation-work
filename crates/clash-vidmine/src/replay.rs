//! Moving, cropped replay HUDs: retain clock evidence without inventing a bar.
use crate::extract::{optional, quoted};
use crate::image::{Mask, Rect};
use crate::json::Value;
use crate::{ocr::Reader, probe, video};
use std::fs;
use std::io::{self, Write};
use std::path::Path;
use std::time::Instant;

pub fn extract(
    path: &Path,
    out: &Path,
    templates: &Path,
    regions: &probe::Regions,
) -> io::Result<()> {
    let started = Instant::now();
    fs::create_dir_all(out)?;
    fs::write(out.join("regions.json"), regions.json())?;
    let label = Mask::load_text(&templates.join("replay-label.txt"))?;
    let reader = Reader::load(templates)?;
    // Round input PTS upward so the last frame at/before each integer second
    // is selected. Default nearest rounding would assign ~t+0.5 to sample t.
    let mut stream = video::Stream::new(path, "fps=fps=1:round=up:start_time=0,format=rgb24")?;
    let mut readings = fs::File::create(out.join("readings.jsonl"))?;
    let mut tsv = fs::File::create(out.join("readings.tsv"))?;
    writeln!(tsv,"video_t\tphase\tclock\tclock_confidence\tdamage\tdamage_confidence\tstars\tstar_confidence\tslot_counts")?;
    let mut samples: Vec<(f64, Option<u32>, f64, Rect)> = Vec::new();
    let mut previous: Option<(Rect, f64)> = None;
    while let Some(image) = stream.next()? {
        let t = samples.len() as f64;
        let mask = Mask::white(&image, 145);
        let mut best = (Rect::default(), 0.0, 0.5);
        if let Some((r, s)) = previous {
            for factor in [s * 0.95, s, s * 1.05] {
                let template = probe::resize(&label, factor);
                let (r, score) = probe::search(
                    &mask,
                    &template,
                    Rect::new(r.x.saturating_sub(30), r.y.saturating_sub(20), 60, 40),
                );
                if score > best.1 {
                    best = (r, score, factor);
                }
            }
        }
        if best.1 < 0.72 {
            for step in 6..=22 {
                let factor = step as f64 / 10.0;
                let template = probe::resize(&label, factor);
                let (r, score) = probe::search(
                    &mask,
                    &template,
                    Rect::new(0, image.h / 2, image.w, image.h / 2),
                );
                if score > best.1 {
                    best = (r, score, factor);
                }
            }
        }
        let mut clock = crate::ocr::Reading::missing();
        let mut box_source = Rect::default();
        if best.1 >= 0.70 {
            let (r, _, s) = best;
            previous = Some((r, s));
            let x = r.x.saturating_sub((20.0 * s) as usize);
            let rect = Rect::new(
                x,
                r.y + r.h,
                (190.0 * s).round() as usize,
                (45.0 * s).round() as usize,
            );
            if rect.x + rect.w <= image.w && rect.y + rect.h <= image.h {
                clock = reader.clock(&image.crop(rect));
                box_source = Rect::new(
                    rect.x * regions.width / image.w,
                    rect.y * regions.height / image.h,
                    rect.w * regions.width / image.w,
                    rect.h * regions.height / image.h,
                );
            }
        }
        let phase = if clock.value.is_some() {
            "attack"
        } else {
            "other"
        };
        writeln!(readings,"{{\"video_t\":{t},\"phase\":\"{phase}\",\"hud_confidence\":{:.4},\"clock\":{{\"value\":{},\"confidence\":{:.4},\"raw\":{}}},\"clock_box\":{},\"damage\":{{\"value\":null,\"confidence\":0,\"raw\":\"\"}},\"stars\":{{\"value\":null,\"confidence\":0}},\"slots\":[]}}",best.1,optional(clock.value),clock.confidence,quoted(&clock.raw),box_source.json())?;
        writeln!(
            tsv,
            "{t}\t{phase}\t{}\t{:.4}\tnull\t0\tnull\t0\t",
            optional(clock.value),
            clock.confidence
        )?;
        samples.push((t, clock.value, clock.confidence, box_source));
        if samples.len() % 100 == 0 {
            eprintln!(
                "cropped replay {t:.0}/{:.0}s ({:.1}s elapsed)",
                regions.duration,
                started.elapsed().as_secs_f64()
            );
        }
    }
    // Persistent upward clock resets delimit replays. Missing HUD alone cannot
    // identify a battle boundary; retain a gap and mark its timing unavailable.
    let mut intervals = Vec::new();
    let mut start = None;
    let mut last = None;
    let mut old_clock = None;
    for (i, (t, clock, _, _)) in samples.iter().enumerate() {
        let Some(clock) = clock else {
            continue;
        };
        let confirmed = samples[i..samples.len().min(i + 5)]
            .iter()
            .filter_map(|s| s.1)
            .filter(|c| *c >= clock.saturating_sub(10))
            .count()
            >= 3;
        let reset = old_clock.is_some_and(|old| *clock > old + 30 && *clock >= 110) && confirmed;
        let gap = last.is_some_and(|last: usize| *t - samples[last].0 > 90.0);
        if reset || gap {
            if let (Some(s), Some(e)) = (start.take(), last) {
                intervals.push((s, e));
            }
        }
        start.get_or_insert(i);
        last = Some(i);
        old_clock = Some(*clock);
    }
    if let (Some(s), Some(e)) = (start, last) {
        intervals.push((s, e));
    }
    let mut index=String::from("video_id\tattack\tvideo_t_start\tvideo_t_end\tduration\tfinal_damage\tfinal_stars\tdeployments\tclock_coverage\tdamage_coverage\tmean_clock_confidence\tmean_damage_confidence\tedited\n");
    let id = path.file_stem().unwrap().to_string_lossy();
    let mut number = 0;
    for (s, e) in intervals {
        if samples[e].0 - samples[s].0 < 5.0 {
            continue;
        }
        number += 1;
        let series = samples[s..=e]
            .iter()
            .map(|(t, c, conf, rect)| {
                format!(
                    "{{\"video_t\":{t},\"clock_t\":{},\"confidence\":{conf:.4},\"screen_box\":{}}}",
                    optional(*c),
                    rect.json()
                )
            })
            .collect::<Vec<_>>()
            .join(",");
        let keyframe = format!("attack-{number:02}-keyframe.jpg");
        video::jpeg(path, samples[s].0, &out.join(&keyframe))?;
        let mut attack=Value::parse(&format!("{{\"schema_version\":2,\"video_id\":{},\"attack\":{number},\"sample_fps\":1,\"video_t_start\":{},\"video_t_end\":{},\"preparation_t_start\":null,\"clock_series\":[{series}],\"damage_series\":[],\"stars\":[],\"deployments\":[],\"slots\":[],\"cuts\":[],\"hero_abilities\":[],\"hero_ability_status\":\"unavailable: troop bar outside edited crop\",\"deployment_status\":\"unavailable: troop bar and count changes outside edited crop\",\"position_status\":\"unavailable: no deployment events can be identified from cropped HUD\",\"keyframe\":{{\"path\":{},\"video_t\":{},\"undamaged_hud\":false,\"base_visibility\":\"edited zoom crop; full base not established\"}},\"result_screen\":null,\"final_percent\":null,\"final_stars\":null}}",quoted(&id),samples[s].0,samples[e].0,quoted(&keyframe),samples[s].0))?;
        crate::timing::annotate(&mut attack)?;
        // The source has animated crop/zoom edits even where the clock is smooth.
        attack.set("edited", Value::from(true));
        attack.set("usable_for_timing", Value::from(false));
        attack.set(
            "timing_status",
            Value::from(
                "edited moving replay crop; incomplete HUD and battle boundaries require review",
            ),
        );
        let readable = samples[s..=e].iter().filter(|v| v.1.is_some()).count();
        let coverage = readable as f64 / (e - s + 1) as f64;
        index.push_str(&format!(
            "{id}\t{number}\t{}\t{}\t{}\tnull\tnull\t0\t{coverage:.4}\t0\t0\t0\ttrue\n",
            samples[s].0,
            samples[e].0,
            samples[e].0 - samples[s].0
        ));
        fs::write(
            out.join(format!("attack-{number:02}.json")),
            attack.encode() + "\n",
        )?;
    }
    fs::write(out.join("attacks.tsv"), index)?;
    fs::write(
        out.join("slots.tsv"),
        "slot\tx\ty\tw\th\tcount_x\tcount_y\tcount_w\tcount_h\n",
    )?;
    fs::write(out.join("run.json"),format!("{{\"video_id\":{},\"fps\":1,\"frames\":{},\"attacks\":{number},\"elapsed_seconds\":{:.3},\"synthetic\":false,\"purpose\":\"cropped replay clock observations; not engine calibration\"}}\n",quoted(&id),samples.len(),started.elapsed().as_secs_f64()))?;
    Ok(())
}
