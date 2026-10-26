use crate::image::{Image, Rect};
use crate::json::Value;
use std::fs;
use std::io::{self, BufReader};
use std::path::{Path, PathBuf};

const WIDTH: usize = 16;
const HEIGHT: usize = 20;

fn read(path: &Path) -> io::Result<Image> {
    Image::read(&mut BufReader::new(fs::File::open(path)?))?
        .ok_or_else(|| io::Error::other("empty icon"))
}

fn feature(image: &Image) -> Vec<u8> {
    // Ignore counts, card border, level badge and most selected-card highlights.
    let crop = image.crop(Rect::new(
        image.w / 10,
        image.h / 5,
        image.w * 8 / 10,
        image.h * 6 / 10,
    ));
    let mut result = Vec::new();
    for y in 0..HEIGHT {
        for x in 0..WIDTH {
            let pixel = crop.pixel(x * crop.w / WIDTH, y * crop.h / HEIGHT);
            result.extend(pixel);
        }
    }
    result
}

fn distance(a: &[u8], b: &[u8]) -> f64 {
    a.iter()
        .zip(b)
        .map(|(a, b)| (*a as f64 - *b as f64).abs() / 255.0)
        .sum::<f64>()
        / a.len() as f64
}

pub fn directories(root: &Path) -> io::Result<Vec<PathBuf>> {
    if root.join("attacks.tsv").exists() {
        return Ok(vec![root.to_path_buf()]);
    }
    let mut result = fs::read_dir(root)?
        .map(|e| e.map(|e| e.path()))
        .collect::<io::Result<Vec<_>>>()?;
    result.retain(|p| p.is_dir() && p.join("attacks.tsv").exists());
    result.sort();
    Ok(result)
}

pub fn attack_paths(dir: &Path) -> io::Result<Vec<PathBuf>> {
    let mut paths = fs::read_dir(dir)?
        .map(|e| e.map(|e| e.path()))
        .collect::<io::Result<Vec<_>>>()?;
    paths.retain(|p| {
        p.file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .starts_with("attack-")
            && p.extension().is_some_and(|s| s == "json")
    });
    paths.sort();
    Ok(paths)
}

pub(crate) fn digits(image: &mut Image, text: &str, x: usize, y: usize) {
    const FONT: [[u8; 5]; 10] = [
        [7, 5, 5, 5, 7],
        [2, 6, 2, 2, 7],
        [7, 1, 7, 4, 7],
        [7, 1, 7, 1, 7],
        [5, 5, 7, 1, 1],
        [7, 4, 7, 1, 7],
        [7, 4, 7, 5, 7],
        [7, 1, 1, 1, 1],
        [7, 5, 7, 5, 7],
        [7, 5, 7, 1, 7],
    ];
    for (i, c) in text.chars().enumerate() {
        let Some(d) = c.to_digit(10) else { continue };
        for (row, bits) in FONT[d as usize].iter().enumerate() {
            for column in 0..3 {
                if bits & (1 << (2 - column)) != 0 {
                    for dy in 0..2 {
                        for dx in 0..2 {
                            let index =
                                ((y + row * 2 + dy) * image.w + x + i * 8 + column * 2 + dx) * 3;
                            if index + 3 <= image.data.len() {
                                image.data[index..index + 3].fill(255);
                            }
                        }
                    }
                }
            }
        }
    }
}

pub fn cluster(root: &Path) -> io::Result<()> {
    let work = Path::new("/tmp/vidmine-work/icons");
    fs::create_dir_all(work)?;
    let mut clusters: Vec<(Vec<u8>, PathBuf, usize)> = Vec::new();
    let mut manifest = String::from("path\tcluster\tdistance\n");
    for dir in directories(root)? {
        let slot_dir = dir.join("slots");
        if !slot_dir.exists() {
            continue;
        }
        let mut paths = fs::read_dir(slot_dir)?
            .map(|e| e.map(|e| e.path()))
            .collect::<io::Result<Vec<_>>>()?;
        paths.sort();
        for path in paths {
            if !path.extension().is_some_and(|s| s == "ppm") {
                continue;
            }
            let f = feature(&read(&path)?);
            let best = clusters
                .iter()
                .enumerate()
                .map(|(i, (v, _, _))| (i, distance(&f, v)))
                .min_by(|a, b| a.1.total_cmp(&b.1));
            let (id, score) = if let Some((id, score)) = best.filter(|(_, s)| *s < 0.105) {
                clusters[id].2 += 1;
                (id, score)
            } else {
                let id = clusters.len();
                clusters.push((f, path.clone(), 1));
                (id, 0.0)
            };
            manifest.push_str(&format!("{}\t{id}\t{score:.4}\n", path.display()));
        }
    }
    fs::write(root.join("icon-clusters.tsv"), manifest)?;
    let mut representatives = String::from("cluster\tcount\tpath\tname\n");
    for (page, chunk) in clusters.chunks(100).enumerate() {
        let mut sheet = Image::blank(1000, chunk.len().div_ceil(10) * 126);
        for (i, (_, path, count)) in chunk.iter().enumerate() {
            let icon = read(path)?;
            let mut thumb = Image::blank(72, 96);
            for y in 0..96 {
                for x in 0..72 {
                    let pixel = icon.pixel(x * icon.w / 72, y * icon.h / 96);
                    let j = (y * 72 + x) * 3;
                    thumb.data[j..j + 3].copy_from_slice(&pixel);
                }
            }
            sheet.paste(&thumb, i % 10 * 100, i / 10 * 126 + 18, 1);
            digits(
                &mut sheet,
                &(page * 100 + i).to_string(),
                i % 10 * 100,
                i / 10 * 126,
            );
            representatives.push_str(&format!(
                "{}\t{count}\t{}\t\n",
                page * 100 + i,
                path.display()
            ));
        }
        sheet.save(&work.join(format!("page-{page:02}.ppm")))?;
    }
    fs::write(root.join("icon-cluster-labels.tsv"), representatives)?;
    eprintln!("{} icon clusters; inspect /tmp/vidmine-work/icons/page-*.ppm and fill icon-cluster-labels.tsv",clusters.len());
    Ok(())
}

pub struct Library {
    templates: Vec<(String, Vec<u8>)>,
}

pub fn learn_cards(manifest: &Path, templates: &Path) -> io::Result<()> {
    let text = fs::read_to_string(manifest)?;
    for (i, line) in text.lines().skip(1).enumerate() {
        let c: Vec<_> = line.split('\t').collect();
        if c.len() != 6 || !c[5].bytes().all(|b| b.is_ascii_alphanumeric() || b == b' ') {
            return Err(io::Error::other(
                "card labels require path, x, y, w, h, name",
            ));
        }
        let n = c[1..5]
            .iter()
            .map(|s| s.parse::<usize>().map_err(io::Error::other))
            .collect::<io::Result<Vec<_>>>()?;
        let image = read(Path::new(c[0]))?;
        let r = Rect::new(n[0], n[1], n[2], n[3]);
        if r.x + r.w > image.w || r.y + r.h > image.h {
            return Err(io::Error::other("card label outside image"));
        }
        let f = feature(&image.crop(r));
        fs::write(
            templates.join(format!(
                "icons/{}--m3-reviewed-{i}.txt",
                c[5].replace(' ', "_")
            )),
            f.iter().map(u8::to_string).collect::<Vec<_>>().join(" ") + "\n",
        )?;
    }
    Ok(())
}
impl Library {
    pub fn identify_card(&self, image: &Image) -> (Option<String>, f64) {
        let portrait = feature(image);
        let chroma: usize = portrait
            .as_chunks::<3>()
            .0
            .iter()
            .map(|p| (*p.iter().max().unwrap() - *p.iter().min().unwrap()) as usize)
            .sum();
        if chroma < WIDTH * HEIGHT * 14 {
            return (None, 0.0);
        }
        // The original library includes right-anchored 61px windows as well as
        // complete portraits. Compare both geometries on a newly saved card.
        let mut candidates = Vec::new();
        for (left, width, height) in [
            (0.0, 1.0, 1.0),
            (0.15, 0.80, 0.88),
            (0.10, 0.85, 0.92),
            (0.0, 0.85, 0.92),
        ] {
            let crop = image.crop(Rect::new(
                (image.w as f64 * left) as usize,
                0,
                (image.w as f64 * width) as usize,
                (image.h as f64 * height) as usize,
            ));
            let (name, confidence) = self.identify(&crop);
            if let Some(name) = name {
                candidates.push((name, confidence));
            }
        }
        candidates.sort_by(|a, b| b.1.total_cmp(&a.1));
        let Some((name, confidence)) = candidates.first() else {
            return (None, 0.0);
        };
        if candidates
            .iter()
            .any(|(n, c)| n != name && confidence - c < 0.03)
        {
            return (None, *confidence);
        }
        if *confidence < 0.70 {
            return (None, *confidence);
        }
        (Some(name.clone()), *confidence)
    }

    pub fn load(root: &Path) -> io::Result<Self> {
        let mut templates = Vec::new();
        let dir = root.join("icons");
        if dir.exists() {
            for entry in fs::read_dir(dir)? {
                let path = entry?.path();
                if path.extension().is_some_and(|s| s == "txt") {
                    let data = fs::read_to_string(&path)?
                        .split_whitespace()
                        .map(|s| {
                            s.parse::<u8>()
                                .map_err(|_| io::Error::other("invalid icon template"))
                        })
                        .collect::<io::Result<Vec<_>>>()?;
                    if data.len() != WIDTH * HEIGHT * 3 {
                        return Err(io::Error::other("icon template length"));
                    }
                    let stem = path.file_stem().unwrap().to_string_lossy();
                    let name = stem.split("--").next().unwrap().replace('_', " ");
                    templates.push((name, data));
                }
            }
        }
        Ok(Self { templates })
    }
    pub fn identify(&self, image: &Image) -> (Option<String>, f64) {
        let f = feature(image);
        let mut scores = std::collections::BTreeMap::<&str, f64>::new();
        for (name, v) in &self.templates {
            let d = distance(&f, v);
            scores
                .entry(name)
                .and_modify(|s| *s = s.min(d))
                .or_insert(d);
        }
        let mut scores: Vec<_> = scores.into_iter().collect();
        scores.sort_by(|a, b| a.1.total_cmp(&b.1));
        let Some((name, score)) = scores.first() else {
            return (None, 0.0);
        };
        let margin = scores.get(1).map(|s| s.1 - score).unwrap_or(1.0);
        let accepted = *score <= 0.13 && margin >= 0.012;
        (
            accepted.then(|| name.to_string()),
            (1.0 - score / 0.25).clamp(0.0, 1.0),
        )
    }
}

pub fn learn(root: &Path, templates: &Path) -> io::Result<()> {
    let dir = templates.join("icons");
    fs::create_dir_all(&dir)?;
    let groups = fs::read_to_string(root.join("icon-reviewed-groups.tsv"))?;
    let mut labels = std::collections::BTreeMap::new();
    for line in groups.lines().skip(1) {
        let Some((name, ids)) = line.split_once('\t') else {
            continue;
        };
        for id in ids.split_whitespace() {
            if labels.insert(id.to_string(), name).is_some() {
                return Err(io::Error::other(format!("duplicate reviewed cluster {id}")));
            }
        }
    }
    let text = fs::read_to_string(root.join("icon-cluster-labels.tsv"))?;
    let mut planned = Vec::new();
    let mut reviewed = String::from("cluster\tcount\tpath\tname\n");
    for line in text.lines().skip(1) {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() < 4 {
            continue;
        }
        let name = labels.get(fields[0]).copied().unwrap_or("unknown");
        reviewed.push_str(&format!(
            "{}\t{}\t{}\t{name}\n",
            fields[0], fields[1], fields[2]
        ));
        if name == "unknown" {
            continue;
        }
        if !name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b' ' || c == b'_')
        {
            return Err(io::Error::other("invalid icon label"));
        }
        let f = feature(&read(Path::new(fields[2]))?);
        planned.push((
            format!("{}--{}.txt", name.replace(' ', "_"), fields[0]),
            f.iter().map(u8::to_string).collect::<Vec<_>>().join(" ") + "\n",
        ));
    }
    let extra = root.join("icon-extra-labels.tsv");
    if extra.exists() {
        for (i, line) in fs::read_to_string(extra)?.lines().skip(1).enumerate() {
            let Some((path, name)) = line.split_once('\t') else {
                continue;
            };
            if !name
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b' ' || c == b'_')
            {
                return Err(io::Error::other("invalid extra icon label"));
            }
            let f = feature(&read(Path::new(path))?);
            planned.push((
                format!("{}--extra-{i}.txt", name.replace(' ', "_")),
                f.iter().map(u8::to_string).collect::<Vec<_>>().join(" ") + "\n",
            ));
        }
    }
    // Validate and read every reviewed source before replacing an existing
    // library, so a missing crop cannot leave a partially retrained catalog.
    for entry in fs::read_dir(&dir)? {
        let path = entry?.path();
        if path.extension().is_some_and(|s| s == "txt") {
            fs::remove_file(path)?;
        }
    }
    for (name, data) in planned {
        fs::write(dir.join(name), data)?;
    }
    fs::write(root.join("icon-cluster-labels.tsv"), reviewed)?;
    update(root, templates)
}

pub fn update(root: &Path, templates: &Path) -> io::Result<()> {
    let library = Library::load(templates)?;
    let mut report = String::from("video\tattack\tslot\tname\tconfidence\n");
    for dir in directories(root)? {
        for path in attack_paths(&dir)? {
            let mut attack = Value::parse(&fs::read_to_string(&path)?)?;
            let attack_id = attack.get("attack").number().unwrap_or(0.0);
            let mut names = std::collections::BTreeMap::new();
            if let Some(slots) = attack.object_array_mut("slots") {
                for slot in slots {
                    let Some(icon) = slot.get("icon").string() else {
                        continue;
                    };
                    let (name, confidence) = library.identify(&read(&dir.join(icon))?);
                    let id = slot.get("slot").number().unwrap_or(0.0) as usize;
                    report.push_str(&format!(
                        "{}\t{attack_id}\t{id}\t{}\t{confidence:.4}\n",
                        dir.file_name().unwrap().to_string_lossy(),
                        name.as_deref().unwrap_or("unknown")
                    ));
                    names.insert(id, name.clone());
                    slot.set(
                        "name",
                        name.as_deref().map(Value::from).unwrap_or(Value::Null),
                    );
                    slot.set("name_confidence", Value::from(confidence));
                    slot.set("name_method",Value::from("manually labeled portrait templates v2; unknown on weak or ambiguous match"));
                }
            }
            if let Some(events) = attack.object_array_mut("deployments") {
                for event in events {
                    let name = event
                        .get("slot")
                        .number()
                        .and_then(|i| names.get(&(i as usize)))
                        .and_then(|n| n.as_deref());
                    event.set("name", name.map(Value::from).unwrap_or(Value::Null));
                }
            }
            attack.set("icon_library_version", Value::from("m2-v1"));
            let schema = attack
                .get("schema_version")
                .number()
                .unwrap_or(2.0)
                .max(2.0);
            attack.set("schema_version", Value::from(schema));
            fs::write(path, attack.encode() + "\n")?;
        }
    }
    fs::write(root.join("icon-identities.tsv"), report)
}
