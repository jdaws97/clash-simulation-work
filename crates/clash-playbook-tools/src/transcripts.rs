use crate::{citations, io};
use clash_data::json::Json;
use clash_data::wire::{list, obj, put, string, text};
use std::fs;
use std::path::Path;
use std::process::Command;

fn compact(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn seconds(milliseconds: f64) -> f64 {
    // Formatting rounds ties to even, as round(milliseconds / 1000, 1) does.
    format!("{:.1}", milliseconds / 1000.0)
        .parse()
        .unwrap_or(0.0)
}

fn line(time: f64, text: String) -> Json {
    Json::Arr(vec![Json::Num(time), string(text)])
}

pub fn normalize(record: &Json, video: &str) -> Result<Json, String> {
    if record.get("lines").is_some() {
        citations::lines(record)?;
        return Ok(record.clone());
    }
    let Some(Json::Arr(events)) = record.get("events") else {
        return Err("expected stored transcript or yt-dlp json3 events".to_owned());
    };
    let mut lines = Vec::new();
    for event in events {
        let words = list(event, "segs")
            .iter()
            .map(|s| text(s, "utf8", ""))
            .collect::<String>();
        let words = compact(&words);
        if words.is_empty() {
            continue;
        }
        let milliseconds = io::optional_number(event.get("tStartMs"))?.unwrap_or(0.0);
        lines.push(line(seconds(milliseconds), words));
    }
    Ok(obj([
        ("id", string(video)),
        ("caption_kind", string("imported")),
        ("lines", Json::Arr(lines)),
    ]))
}

fn unescape(value: &str) -> Result<String, String> {
    let mut out = String::new();
    let mut rest = value;
    while let Some(i) = rest.find('&') {
        out.push_str(&rest[..i]);
        rest = &rest[i + 1..];
        let end = rest.find(';').ok_or("unterminated XML entity")?;
        let entity = &rest[..end];
        let character = match entity {
            "amp" => '&',
            "lt" => '<',
            "gt" => '>',
            "quot" => '"',
            "apos" => '\'',
            n if n.starts_with("#x") => u32::from_str_radix(&n[2..], 16)
                .ok()
                .and_then(char::from_u32)
                .ok_or("invalid XML entity")?,
            n if n.starts_with('#') => n[1..]
                .parse::<u32>()
                .ok()
                .and_then(char::from_u32)
                .ok_or("invalid XML entity")?,
            _ => return Err(format!("unsupported XML entity &{entity};")),
        };
        out.push(character);
        rest = &rest[end + 1..];
    }
    out.push_str(rest);
    Ok(out)
}

fn attribute(tag: &str, key: &str) -> Option<String> {
    let needle = format!("{key}=");
    let start = tag.find(&needle)? + needle.len();
    let quote = tag.as_bytes().get(start).copied()? as char;
    if !['\'', '"'].contains(&quote) {
        return None;
    }
    let value = &tag[start + 1..];
    Some(value[..value.find(quote)?].to_owned())
}

/// Format-3 timedtext only. Other XML is rejected rather than guessed at.
pub fn parse_timedtext(xml: &str, video: &str) -> Result<Json, String> {
    if !xml.contains("<timedtext") {
        return Err("expected format-3 timedtext XML".to_owned());
    }
    let mut lines = Vec::new();
    let mut rest = xml;
    while let Some(start) = rest.find("<p") {
        rest = &rest[start + 2..];
        if !rest.starts_with(|c: char| c.is_whitespace() || c == '>') {
            continue;
        }
        let header_end = rest.find('>').ok_or("unterminated caption tag")?;
        let time = attribute(&rest[..header_end], "t")
            .unwrap_or_else(|| "0".to_owned())
            .parse::<f64>()
            .map_err(|e| e.to_string())?;
        rest = &rest[header_end + 1..];
        let end = rest.find("</p>").ok_or("unterminated caption")?;
        let body = &rest[..end];
        let direct = body.split('<').next().unwrap_or("");
        let mut words = String::new();
        let mut spans = body;
        while let Some(start) = spans.find("<s") {
            spans = &spans[start + 2..];
            if !spans.starts_with(|c: char| c.is_whitespace() || c == '>') {
                continue;
            }
            let end = spans.find('>').ok_or("unterminated word tag")?;
            spans = &spans[end + 1..];
            words.push_str(spans.split('<').next().unwrap_or(""));
        }
        if words.is_empty() {
            words.push_str(direct);
        }
        let words = compact(&unescape(&words)?);
        if !words.is_empty() {
            lines.push(line(seconds(time), words));
        }
        rest = &rest[end + 4..];
    }
    Ok(obj([
        ("id", string(video)),
        ("caption_kind", string("imported")),
        ("lines", Json::Arr(lines)),
    ]))
}

pub fn import(path: &Path, video: &str) -> Result<Json, String> {
    io::safe_name(video)?;
    let source = fs::read_to_string(path).map_err(|e| e.to_string())?;
    if source.trim_start().starts_with('<') {
        parse_timedtext(&source, video)
    } else {
        normalize(&io::parse(&source)?, video)
    }
}

pub fn process_path(path: &Path, executable: &str) -> Result<String, String> {
    let absolute = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir()
            .map_err(|e| e.to_string())?
            .join(path)
    };
    if cfg!(target_os = "linux") && executable.ends_with(".exe") {
        let converted = Command::new("wslpath")
            .arg("-w")
            .arg(&absolute)
            .output()
            .map_err(|e| format!("wslpath: {e}"))?;
        if !converted.status.success() {
            return Err("wslpath failed for Windows provider output".to_owned());
        }
        return Ok(String::from_utf8_lossy(&converted.stdout).trim().to_owned());
    }
    Ok(absolute.to_string_lossy().into_owned())
}

/// Explicit opt-in provider step. Tests never call this function.
pub fn fetch(video: &str, output: &Path, executable: &str) -> Result<Json, String> {
    io::safe_name(video)?;
    fs::create_dir_all(output).map_err(|e| e.to_string())?;
    let staging = output.join(format!(".fetch-{video}-{}", std::process::id()));
    fs::create_dir(&staging).map_err(|e| format!("{}: {e}", staging.display()))?;
    let result = (|| {
        let template = process_path(&staging.join(format!("{video}.%(ext)s")), executable)?;
        let response = Command::new(executable)
            .args([
                "--ignore-config",
                "--no-playlist",
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                "en.*",
                "--sub-format",
                "json3",
                "--write-info-json",
                "-o",
                &template,
                "--",
                &format!("https://www.youtube.com/watch?v={video}"),
            ])
            .output()
            .map_err(|e| format!("{executable}: {e}"))?;
        if !response.status.success() {
            return Err(format!(
                "subtitle provider exited {}: {}",
                response.status,
                String::from_utf8_lossy(&response.stderr)
            ));
        }
        let subtitles = io::files(&staging, "json3")?;
        let subtitle = subtitles
            .first()
            .ok_or("provider returned no English subtitles")?;
        let mut record = import(subtitle, video)?;
        let info_path = staging.join(format!("{video}.info.json"));
        if info_path.exists() {
            let info = io::read(&info_path)?;
            for (destination, source) in [
                ("title", "title"),
                ("channel", "channel"),
                ("description", "description"),
                ("length_s", "duration"),
                ("date", "upload_date"),
            ] {
                put(
                    &mut record,
                    destination,
                    info.get(source).cloned().unwrap_or(Json::Null),
                );
            }
        }
        put(&mut record, "caption_kind", string("yt-dlp"));
        put(&mut record, "status", string("OK"));
        io::write(&output.join(format!("{video}.json")), &record)?;
        Ok(record)
    })();
    let _ = fs::remove_dir_all(&staging);
    result
}
