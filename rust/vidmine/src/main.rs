mod appearance;
mod audit;
mod camera;
mod extract;
mod grid;
mod icons;
mod identity;
mod identity_review;
mod image;
mod json;
mod league;
mod ocr;
mod positions;
mod probe;
mod replay;
mod review;
mod spatial;
mod spatial_review;
mod timing;
mod townhall;
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

fn bootstrap(
    video_path: &Path,
    times: &[f64],
    kind: &str,
    supplied: Option<Rect>,
) -> io::Result<()> {
    let region = supplied.unwrap_or_else(|| match kind {
        "clock" => Rect::new(576, 32, 128, 25),
        "damage" => Rect::new(1063, 480, 80, 21),
        "counts" => Rect::new(150, 533, 900, 16),
        _ => Rect::new(200, 534, 28, 17),
    });
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
        Some("spatial-prepare") => {
            let out = argument(&args, 4, "output directory after --out")?;
            if argument(&args, 3, "--out")? != "--out" {
                return Err(io::Error::other("spatial-prepare VIDEO --out DIR"));
            }
            spatial::prepare(input()?, Path::new(out))
        }
        Some("spatial-saved-review") => spatial::saved_review(input()?),
        Some("spatial") => {
            let option = |name: &str| -> io::Result<&str> {
                args.iter()
                    .position(|a| a == name)
                    .and_then(|i| args.get(i + 1))
                    .map(String::as_str)
                    .ok_or_else(|| io::Error::other(format!("spatial requires {name}")))
            };
            spatial::run(
                input()?,
                Path::new(option("--out")?),
                Path::new(option("--labels")?),
                Path::new(TEMPLATE_DIR),
                args.iter().any(|a| a == "--preview"),
                args.iter()
                    .position(|a| a == "--attack")
                    .and_then(|i| args.get(i + 1))
                    .map(|s| s.parse::<usize>().map_err(io::Error::other))
                    .transpose()?,
            )
        }
        Some("spatial-learn") => spatial::learn(input()?, Path::new(TEMPLATE_DIR)),
        Some("spatial-keyframes") => spatial::keyframes(
            input()?,
            Path::new(argument(&args, 3, "grid labels")?),
            Path::new(TEMPLATE_DIR),
        ),
        Some("spatial-score") => spatial_review::score(
            input()?,
            Path::new(argument(&args, 3, "deployment truth TSV")?),
            Path::new(argument(&args, 4, "score destination")?),
        ),
        Some("spatial-score-th") => spatial_review::score_townhalls(
            input()?,
            Path::new(argument(&args, 3, "Town Hall truth TSV")?),
            Path::new(argument(&args, 4, "score destination")?),
        ),
        Some("spatial-verify") => spatial_review::verify(input()?, args.get(3).map(Path::new)),
        Some("spatial-summary") => spatial_review::overview(input()?),
        Some("spatial-camera-check") => spatial::camera_check(
            input()?,
            timestamp(argument(&args, 3, "key time")?)?,
            timestamp(argument(&args, 4, "frame time")?)?,
        ),
        Some("spatial-reposition") => spatial::reposition(
            input()?,
            Path::new(argument(&args, 3, "M4 output directory")?),
            Path::new(argument(&args, 4, "regions JSON")?),
        ),
        Some("spatial-spacing") => {
            spatial::spacing(input()?, Path::new(argument(&args, 3, "grid labels")?))
        }
        Some("spatial-refresh") => spatial::refresh(
            input()?,
            Path::new(argument(&args, 3, "M4 output directory")?),
            Path::new(argument(&args, 4, "grid labels")?),
            Path::new(TEMPLATE_DIR),
        ),
        Some("identity-data") => identity::inspect_data(),
        Some("identity-caps") => identity::caps(input()?),
        Some("league-audit") => league::audit(input()?),
        Some("league-learn") => {
            let label = argument(&args, 3, "league label")?;
            let n = (4..8)
                .map(|i| {
                    argument(&args, i, "rectangle")?
                        .parse::<usize>()
                        .map_err(io::Error::other)
                })
                .collect::<io::Result<Vec<_>>>()?;
            league::learn(
                input()?,
                label,
                Rect::new(n[0], n[1], n[2], n[3]),
                Path::new(TEMPLATE_DIR),
            )
        }
        Some("level-sheet") => identity::sheet(input()?, false),
        Some("army-sheet") => identity::sheet(input()?, true),
        Some("identity-learn") => identity::learn(input()?, Path::new(TEMPLATE_DIR)),
        Some("card-learn") => icons::learn_cards(input()?, Path::new(TEMPLATE_DIR)),
        Some("identity") => identity::update(input()?, Path::new(TEMPLATE_DIR)),
        Some("identity-audit") => identity_review::audit(input()?),
        Some("identity-score") => identity_review::score(input()?),
        Some("identity-label-audit") => {
            identity_review::label(input()?, Path::new(argument(&args, 3, "sample truth TSV")?))
        }
        Some("identity-learn-audit") => {
            identity_review::learn_names(input()?, Path::new(TEMPLATE_DIR))
        }
        Some("identity-refresh-audit") => identity_review::refresh(input()?),
        Some("identity-freeze-audit") => identity_review::freeze(input()?),
        Some("identity-read-crops") => {
            identity_review::read_crops(input()?, Path::new(TEMPLATE_DIR))
        }
        Some("identity-video") => {
            let out = args
                .iter()
                .position(|v| v == "--out")
                .and_then(|i| args.get(i + 1))
                .ok_or_else(|| io::Error::other("identity-video requires --out DIR"))?;
            identity::video(input()?, Path::new(out), Path::new(TEMPLATE_DIR))
        }
        Some("label-crop") => {
            let name = argument(&args, 3, "template name")?;
            if !name.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-') {
                return Err(io::Error::other("invalid template name"));
            }
            let t = timestamp(argument(&args, 4, "time")?)?;
            let n = (5..9)
                .map(|i| {
                    argument(&args, i, "rectangle")?
                        .parse::<usize>()
                        .map_err(|_| io::Error::other("invalid rectangle"))
                })
                .collect::<io::Result<Vec<_>>>()?;
            let crop = video::frame(input()?, t)?.crop(Rect::new(n[0], n[1], n[2], n[3]));
            Mask::white(&crop, 145).save_text(&Path::new(TEMPLATE_DIR).join(format!("{name}.txt")))
        }
        Some("bootstrap-box") => {
            let kind = argument(&args, 3, "kind")?;
            if !kind
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
            {
                return Err(io::Error::other("invalid bootstrap kind"));
            }
            let n = (4..8)
                .map(|i| {
                    argument(&args, i, "rectangle")?
                        .parse::<usize>()
                        .map_err(|_| io::Error::other("invalid rectangle"))
                })
                .collect::<io::Result<Vec<_>>>()?;
            let times = args
                .get(8..)
                .unwrap_or_default()
                .iter()
                .map(|s| timestamp(s))
                .collect::<io::Result<Vec<_>>>()?;
            if times.is_empty() || n[2] == 0 || n[3] == 0 {
                return Err(io::Error::other(
                    "bootstrap-box needs a nonempty rectangle and timestamps",
                ));
            }
            bootstrap(
                input()?,
                &times,
                kind,
                Some(Rect::new(n[0], n[1], n[2], n[3])),
            )
        }
        Some("label-hud") => review::labels(input()?, "hud"),
        Some("label-icons") => review::labels(input()?, "icons"),
        Some("label-positions") => review::labels(input()?, "positions"),
        Some("icon-audit") => review::icon_audit(input()?),
        Some("score-positions") => review::score_positions(input()?),
        Some("verify") => {
            review::verify(input()?)?;
            identity_review::validate(input()?)
        }
        Some("positions") => {
            let out = args
                .iter()
                .position(|v| v == "--out")
                .and_then(|i| args.get(i + 1))
                .ok_or_else(|| io::Error::other("positions requires --out DIR"))?;
            positions::run(input()?, Path::new(out))
        }
        Some("resegment") => extract::resegment(input()?),
        Some("timing") => timing::update(input()?),
        Some("icon-cluster") => icons::cluster(input()?),
        Some("icon-learn") => icons::learn(input()?, Path::new(TEMPLATE_DIR)),
        Some("icons") => icons::update(input()?, Path::new(TEMPLATE_DIR)),
        Some("cleanup-m4") => match fs::remove_dir_all(spatial::WORK) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        },
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
            if (!out.starts_with(spatial::WORK) && !out.starts_with("/tmp/vidmine-work"))
                || out
                    .components()
                    .any(|c| c == std::path::Component::ParentDir)
            {
                return Err(io::Error::other(
                    "sample frames must stay under a vidmine scratch directory",
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
            bootstrap(input()?, &times, kind, None)
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
                        let fields: Vec<_> = line.split('\t').collect();
                        let id = fields
                            .get(1)
                            .and_then(|v| v.parse::<usize>().ok())
                            .ok_or_else(|| io::Error::other("invalid attack index"))?;
                        let attack = json::Value::parse(&fs::read_to_string(
                            path.join(format!("attack-{id:02}.json")),
                        )?)?;
                        let th = attack.get("attacker_th");
                        let league = attack.get("league");
                        let label = league.get("label").string().unwrap_or_else(|| {
                            if league
                                .get("status")
                                .string()
                                .is_some_and(|s| s.starts_with("no_label_visible"))
                            {
                                "none"
                            } else {
                                "unknown"
                            }
                        });
                        println!(
                            "{line}\t{}\t{}\t{}\t{label}\t{}\t{}",
                            th.get("min").encode(),
                            th.get("max").encode(),
                            th.get("best").encode(),
                            league.get("confidence").encode(),
                            attack.get("defender_th").encode()
                        );
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
            println!("video_id\tattack\tstart\tend\tduration\tfinal_%\tstars\tdeployments\tclock_coverage\tdamage_coverage\tclock_confidence\tdamage_confidence\tedited\tattacker_th_min\tattacker_th_max\tattacker_th_best\tleague\tleague_confidence\tdefender_th");
            visit(Path::new(
                args.get(2)
                    .ok_or_else(|| io::Error::other("summary requires DIR"))?,
            ))
        }
        Some("--help" | "-h") => {
            println!(concat!(
                "vidmine spatial VIDEO --out DIR --labels GRID_TSV [--preview] [--attack N]\n",
                "vidmine spatial-prepare VIDEO --out DIR\n",
                "vidmine spatial-spacing|spatial-keyframes VIDEO GRID_TSV\n",
                "vidmine spatial-refresh VIDEO DIR GRID_TSV\n",
                "vidmine spatial-reposition VIDEO DIR REGIONS_JSON\n",
                "vidmine spatial-score|spatial-score-th ROOT TRUTH_TSV SCORE_DIR\n",
                "vidmine spatial-verify ROOT [ORIGINAL_ROOT]\n",
                "vidmine spatial-summary ROOT\n",
                "vidmine spatial-learn SPRITE_MANIFEST_TSV\n",
                "vidmine spatial-camera-check VIDEO KEY_TIME FRAME_TIME\n",
                "vidmine spatial-saved-review ROOT\n",
                "vidmine cleanup-m4"
            ));
            println!("vidmine probe VIDEO [--out DIR]\nvidmine extract VIDEO --out DIR\nvidmine positions VIDEO --out DIR\nvidmine resegment DIR\nvidmine icons DIR\nvidmine timing DIR\nvidmine verify DIR\nvidmine summary DIR\nvidmine audit VIDEO --out DIR\nvidmine score DIR\nvidmine icon-cluster DIR\nvidmine icon-learn DIR\nvidmine icon-audit DIR\nvidmine label-hud|label-icons|label-positions DIR\nvidmine score-positions DIR\nvidmine cleanup\nvidmine bootstrap VIDEO clock|damage|count|counts TIME...\nvidmine bootstrap-box VIDEO KIND X Y W H TIME...\nvidmine label-crop VIDEO NAME TIME X Y W H\nvidmine sample VIDEO TIME /tmp/vidmine-work/frame.ppm");
            println!(concat!(
                "vidmine identity DIR\n",
                "vidmine identity-video VIDEO --out DIR\n",
                "vidmine identity-caps DIR\n",
                "vidmine level-sheet|army-sheet|league-audit DIR\n",
                "vidmine identity-audit DIR\n",
                "vidmine identity-label-audit DIR SAMPLE_TRUTH_TSV\n",
                "vidmine identity-freeze-audit DIR\n",
                "vidmine identity-read-crops DIR\n",
                "vidmine identity-score DIR\n",
                "vidmine identity-learn LABEL_TSV\n",
                "vidmine card-learn CARD_LABEL_TSV\n",
                "vidmine identity-learn-audit DIR\n",
                "vidmine league-learn PPM LABEL X Y W H"
            ));
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
