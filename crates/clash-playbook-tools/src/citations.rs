//! Frozen check_playbook.py normalization, location and timing rules.
use crate::io;
use clash_data::json::Json;
use clash_data::wire::{self, list, obj, put, string, text};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

pub type Lines = Vec<(f64, String)>;
pub const EXTRACTED_LISTS: [&str; 5] = [
    "base_reading",
    "steps",
    "rules",
    "spell_policy",
    "ability_policy",
];

pub fn norm(value: &str) -> String {
    let mut result = String::new();
    let mut space = false;
    for c in value.chars().flat_map(char::to_lowercase) {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            if space && !result.is_empty() {
                result.push(' ');
            }
            result.push(c);
            space = false;
        } else {
            space = true;
        }
    }
    result
}

/// Intentionally counts braces inside strings too, matching the frozen parser.
/// A later opening brace is retried if the earlier candidate is invalid JSON.
pub fn parse_reply(reply: &str) -> Option<Json> {
    for (start, _) in reply.match_indices('{') {
        let mut depth = 0;
        for (offset, c) in reply[start..].char_indices() {
            if c == '{' {
                depth += 1;
            } else if c == '}' {
                depth -= 1;
                if depth == 0 {
                    if let Ok(value @ Json::Obj(_)) = io::parse(&reply[start..=start + offset]) {
                        return Some(value);
                    }
                    break;
                }
            }
        }
    }
    None
}

pub fn lines(record: &Json) -> Result<Lines, String> {
    let Some(Json::Arr(values)) = record.get("lines") else {
        return Err("transcript needs a lines array".to_owned());
    };
    values
        .iter()
        .map(|value| match value {
            Json::Arr(pair) if pair.len() == 2 => {
                let time = io::optional_number(pair.first())?.ok_or("caption needs a time")?;
                let Json::Str(text) = &pair[1] else {
                    return Err("caption needs text".to_owned());
                };
                Ok((time, text.clone()))
            }
            _ => Err("caption must be [seconds, text]".to_owned()),
        })
        .collect()
}

pub fn locate(lines: &Lines, quote: &str) -> Vec<f64> {
    let quote = norm(quote);
    if quote.len() < 6 {
        return Vec::new();
    }
    let texts: Vec<_> = lines.iter().map(|(_, text)| norm(text)).collect();
    let needle = format!(" {quote} ");
    texts
        .iter()
        .enumerate()
        .filter_map(|(i, first)| {
            if first.is_empty() {
                return None;
            }
            let window = texts[i..texts.len().min(i + 4)]
                .iter()
                .filter(|s| !s.is_empty())
                .cloned()
                .collect::<Vec<_>>()
                .join(" ");
            let position = format!(" {window} ").find(&needle)?;
            (position < first.len()).then_some(lines[i].0)
        })
        .collect()
}

pub fn verified_time(lines: &Lines, quote: &str, stated: Option<f64>) -> Option<f64> {
    let mut best = None;
    let mut distance = f64::INFINITY;
    for time in locate(lines, quote) {
        let delta = stated.map_or(0.0, |stated| (stated - time).abs());
        if delta <= 30.0 && delta < distance {
            best = Some(time);
            distance = delta;
        }
    }
    best
}

pub struct Transcripts {
    directory: PathBuf,
    cache: BTreeMap<String, Option<Lines>>,
}

impl Transcripts {
    pub fn new(directory: &Path) -> Self {
        Self {
            directory: directory.to_owned(),
            cache: BTreeMap::new(),
        }
    }

    pub fn get(&mut self, video: &str) -> Result<Option<&Lines>, String> {
        io::safe_name(video)?;
        if !self.cache.contains_key(video) {
            let path = self.directory.join(format!("{video}.json"));
            let record = if path.exists() {
                Some(lines(&io::read(&path)?)?)
            } else {
                None
            };
            self.cache.insert(video.to_owned(), record);
        }
        Ok(self.cache.get(video).and_then(Option::as_ref))
    }

    pub fn verify(&mut self, cite: &Json) -> Result<Option<f64>, String> {
        let video = text(cite, "video", "");
        if video.is_empty() {
            return Ok(None);
        }
        let stated = io::optional_number(cite.get("t"))?;
        Ok(self
            .get(video)?
            .and_then(|lines| verified_time(lines, text(cite, "quote", ""), stated)))
    }
}

pub fn check_extracted(reply: &str, video: &str, captions: &Lines) -> Result<Json, String> {
    let Some(mut playbook) = parse_reply(reply) else {
        return Ok(obj([
            ("video_id", string(video)),
            ("parse_error", Json::Bool(true)),
        ]));
    };
    let (mut kept, mut dropped) = (0, 0);
    for key in EXTRACTED_LISTS {
        let mut good = Vec::new();
        for item in list(&playbook, key) {
            let stated = io::optional_number(item.get("t"))?;
            if let Some(time) = verified_time(captions, text(item, "quote", ""), stated) {
                let mut item = item.clone();
                if !matches!(item, Json::Obj(_)) {
                    return Err("extracted items must be objects".to_owned());
                }
                put(&mut item, "verified_t", Json::Num(time));
                good.push(item);
                kept += 1;
            } else {
                dropped += 1;
            }
        }
        put(&mut playbook, key, Json::Arr(good));
    }
    put(
        &mut playbook,
        "check",
        obj([("kept", wire::num(kept)), ("dropped", wire::num(dropped))]),
    );
    Ok(playbook)
}
