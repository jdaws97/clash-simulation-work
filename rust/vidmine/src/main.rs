mod audit;
mod extract;
mod image;
mod ocr;
mod probe;
mod video;

use image::{Image, Mask, Rect};
use std::fs;
use std::io;
use std::path::Path;

const TEMPLATE_DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/templates");

fn argument<'a>(args: &'a [String], index: usize, description: &str) -> io::Result<&'a str> {
    args.get(index)
        .map(String::as_str)
        .ok_or_else(|| io::Error::other(format!("missing {description}; run vidmine --help")))
}

fn timestamp(text: &str) -> io::Result<f64> {
    text.parse::<f64>()
        .ok()
        .filter(|t| t.is_finite() && *t >= 0.0)
        .ok_or_else(|| io::Error::other("time must be a finite, nonnegative number of seconds"))
}

fn bootstrap(video_path: &Path, times: &[f64], kind: &str) -> io::Result<()> {
    let region = match kind {
        "clock" => Rect::new(576, 32, 128, 25),
        "damage" => Rect::new(1063, 480, 80, 21),
        "counts" => Rect::new(150, 533, 900, 16),
        _ => Rect::new(200, 534, 28, 17),
    };
    let mut clusters: Vec<(Mask, usize)> = Vec::new();
    let mut sheet = Image::blank(900, times.len() * 80);
    let out = Path::new("/tmp/vidmine-work/bootstrap");
    fs::create_dir_all(out)?;
    for (i, t) in times.iter().enumerate() {
        let crop = video::frame(video_path, *t)?.crop(region);
        let mask = Mask::white(&crop, 180);
        sheet.paste(&crop, 0, i * 80, 2);
        let mut entries = Vec::new();
        for (j, (_, glyph)) in mask.glyphs().iter().enumerate() {
            let normalized = glyph.normalized();
            let closest = clusters
                .iter()
                .enumerate()
                .map(|(k, (g, _))| (k, g.distance(&normalized)))
                .min_by(|a, b| a.1.total_cmp(&b.1));
            let k = if let Some((k, _)) = closest.filter(|(_, d)| *d < 0.115) {
                clusters[k].1 += 1;
                k
            } else {
                let k = clusters.len();
                normalized.save_text(&out.join(format!("{kind}-{k:03}.txt")))?;
                clusters.push((normalized, 1));
                k
            };
            sheet.paste(&glyph.as_image(), 290 + j * 70, i * 80, 2);
            entries.push(k);
        }
        println!("{t:.1}\t{entries:?}");
    }
    sheet.save(&out.join(format!("{kind}-samples.ppm")))?;
    let mut cluster_sheet = Image::blank(16 * 4 * 12, clusters.len().div_ceil(12) * 110);
    for (i, (glyph, count)) in clusters.iter().enumerate() {
        cluster_sheet.paste(&glyph.as_image(), i % 12 * 64, i / 12 * 110, 3);
        println!("cluster {i}: {count}");
    }
    cluster_sheet.save(&out.join(format!("{kind}-clusters.ppm")))
}

fn run() -> io::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let input = || argument(&args, 2, "video or directory").map(Path::new);
    match args.get(1).map(String::as_str) {
        Some("cleanup") => match fs::remove_dir_all("/tmp/vidmine-work") {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        },
        Some("debug-counts") => {
            fs::create_dir_all("/tmp/vidmine-work")?;
            let image = video::frame(input()?, 18.0)?;
            let reader = ocr::Reader::load(Path::new(TEMPLATE_DIR))?;
            for threshold in [95, 130, 165, 180] {
                let mask = Mask::white(&image.crop(Rect::new(150, 630, 900, 17)), threshold);
                println!("threshold {threshold}");
                for (rect, glyph) in mask.glyphs() {
                    println!("{rect:?} prefix {}", reader.count_prefix(&glyph));
                }
                mask.as_image()
                    .save(&Path::new("/tmp/vidmine-work").join(format!("count-{threshold}.ppm")))?;
            }
            for x in [196, 261, 325, 390, 454, 523, 805, 943] {
                let crop = image.crop(Rect::new(x, 630, 28, 17));
                println!("{x} {:?}", reader.count(&crop));
            }
            Ok(())
        }
        Some("sample") => {
            let t = timestamp(argument(&args, 3, "time")?)?;
            let out = Path::new(argument(&args, 4, "temporary PPM path")?);
            if !out.starts_with("/tmp/vidmine-work")
                || out
                    .components()
                    .any(|c| c == std::path::Component::ParentDir)
            {
                return Err(io::Error::other(
                    "sample frames must stay under /tmp/vidmine-work/",
                ));
            }
            fs::create_dir_all(out.parent().unwrap())?;
            video::frame(input()?, t)?.save(out)
        }
        Some("bootstrap") => {
            let kind = argument(&args, 3, "glyph kind")?;
            if !["clock", "damage", "count", "counts"].contains(&kind) {
                return Err(io::Error::other(
                    "bootstrap kind must be clock, damage, count or counts",
                ));
            }
            let times = args
                .get(4..)
                .unwrap_or_default()
                .iter()
                .map(|s| timestamp(s))
                .collect::<io::Result<Vec<_>>>()?;
            if times.is_empty() {
                return Err(io::Error::other("bootstrap needs at least one timestamp"));
            }
            bootstrap(input()?, &times, kind)
        }
        Some("learn-labels") => {
            if input()?.file_stem().and_then(|s| s.to_str()) != Some("mnJOtLowhqs") {
                return Err(io::Error::other("learn-labels is the manually labeled mnJOtLowhqs coordinate manifest; use bootstrap and inspect clusters for another source"));
            }
            let image = video::frame(input()?, 90.0)?;
            for (name, rect) in [
                ("battle", Rect::new(590, 15, 102, 12)),
                ("damage", Rect::new(998, 460, 130, 12)),
            ] {
                Mask::white(&image.crop(rect), 145)
                    .save_text(&Path::new(TEMPLATE_DIR).join(format!("{name}-label.txt")))?;
            }
            let prep = video::frame(input()?, 5.0)?;
            Mask::white(&prep.crop(Rect::new(582, 15, 118, 12)), 145)
                .save_text(&Path::new(TEMPLATE_DIR).join("prep-label.txt"))?;
            let result = video::frame(input()?, 154.0)?;
            Mask::white(&result.crop(Rect::new(592, 79, 98, 14)), 145)
                .save_text(&Path::new(TEMPLATE_DIR).join("result-label.txt"))?;
            let counts = video::frame(input()?, 18.0)?;
            for (x, y, label) in [
                (264, 534, '1'),
                (199, 534, '2'),
                (330, 534, '3'),
                (395, 630, '4'),
                (395, 534, '0'),
            ] {
                for threshold in [95, 145, 175] {
                    let glyphs =
                        Mask::white(&counts.crop(Rect::new(x, y, 26, 17)), threshold).glyphs();
                    if glyphs.len() == 2 {
                        glyphs[1].1.normalized().save_text(
                            &Path::new(TEMPLATE_DIR).join(format!("count-{label}-{threshold}.txt")),
                        )?;
                        glyphs[0].1.normalized().save_text(
                            &Path::new(TEMPLATE_DIR)
                                .join(format!("count-x-{x}-{y}-{threshold}.txt")),
                        )?;
                    }
                }
            }
            Ok(())
        }
        Some("probe") => {
            let regions = probe::locate(input()?, Path::new(TEMPLATE_DIR))?;
            let default_out = format!(
                "output/web-videos/{}",
                input()?.file_stem().unwrap().to_string_lossy()
            );
            let out = args
                .iter()
                .position(|v| v == "--out")
                .and_then(|i| args.get(i + 1))
                .unwrap_or(&default_out);
            fs::create_dir_all(out)?;
            fs::write(Path::new(out).join("regions.json"), regions.json())
        }
        Some("extract") => {
            let out = args
                .iter()
                .position(|v| v == "--out")
                .and_then(|i| args.get(i + 1))
                .ok_or_else(|| io::Error::other("extract requires --out DIR"))?;
            extract::extract(input()?, Path::new(out), Path::new(TEMPLATE_DIR))
        }
        Some("audit") => {
            let out = args
                .iter()
                .position(|v| v == "--out")
                .and_then(|i| args.get(i + 1))
                .ok_or_else(|| io::Error::other("audit requires --out DIR"))?;
            audit::audit(input()?, Path::new(out), Path::new(TEMPLATE_DIR))
        }
        Some("score") => audit::score(Path::new(
            args.get(2)
                .ok_or_else(|| io::Error::other("score requires DIR"))?,
        )),
        Some("summary") => {
            fn visit(path: &Path) -> io::Result<()> {
                if path.join("attacks.tsv").exists() {
                    let text = fs::read_to_string(path.join("attacks.tsv"))?;
                    for line in text.lines().skip(1) {
                        println!("{line}");
                    }
                } else {
                    let mut paths: Vec<_> = fs::read_dir(path)?
                        .filter_map(Result::ok)
                        .map(|e| e.path())
                        .filter(|p| p.is_dir())
                        .collect();
                    paths.sort();
                    for path in paths {
                        visit(&path)?;
                    }
                }
                Ok(())
            }
            println!("video_id\tattack\tstart\tend\tduration\tfinal_%\tstars\tdeployments\tclock_coverage\tdamage_coverage\tclock_confidence\tdamage_confidence\tedited");
            visit(Path::new(
                args.get(2)
                    .ok_or_else(|| io::Error::other("summary requires DIR"))?,
            ))
        }
        Some("--help" | "-h") => {
            println!("vidmine probe VIDEO [--out DIR]\nvidmine extract VIDEO --out DIR\nvidmine summary DIR\nvidmine audit VIDEO --out DIR\nvidmine score DIR\nvidmine cleanup\nvidmine bootstrap VIDEO clock|damage|count|counts TIME...\nvidmine sample VIDEO TIME /tmp/vidmine-work/frame.ppm");
            Ok(())
        }
        _ => Err(io::Error::other(
            "usage: vidmine probe VIDEO | extract VIDEO --out DIR | summary DIR",
        )),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("vidmine: {error}");
        std::process::exit(1);
    }
}
