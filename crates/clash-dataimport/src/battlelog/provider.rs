//! Pluggable local and configured keyless HTTP sources. No authentication path.

use std::collections::BTreeSet;
use std::fmt;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use clash_data::json::{self, Json};

use super::{object, required_text};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ProviderError {
    Unsupported(String),
    Unavailable(String),
    RateLimited(String),
    InvalidData(String),
}

impl fmt::Display for ProviderError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let (kind, message) = match self {
            Self::Unsupported(message) => ("unsupported provider", message),
            Self::Unavailable(message) => ("provider unavailable", message),
            Self::RateLimited(message) => ("provider rate limited", message),
            Self::InvalidData(message) => ("invalid provider data", message),
        };
        write!(formatter, "{kind}: {message}")
    }
}

impl std::error::Error for ProviderError {}

pub struct Collection {
    pub battles: Vec<Json>,
    pub player: Option<Json>,
    /// Original response bodies retained privately, before runtime JSON normalization.
    pub raw_payloads: Vec<String>,
}

pub trait BattleLogSource {
    fn name(&self) -> &str;
    fn fetch(&mut self, tag: &str) -> Result<Collection, ProviderError>;
}

pub fn normalize_tag(tag: &str) -> Result<String, ProviderError> {
    let tag = tag.strip_prefix('#').unwrap_or(tag);
    if tag.is_empty() || !tag.bytes().all(|byte| byte.is_ascii_alphanumeric()) {
        return Err(ProviderError::InvalidData("invalid player tag".to_owned()));
    }
    Ok(format!("#{}", tag.to_ascii_uppercase()))
}

fn read(path: &Path) -> Result<String, ProviderError> {
    std::fs::read_to_string(path)
        .map_err(|error| ProviderError::Unavailable(format!("{}: {error}", path.display())))
}

fn parse(raw: &str) -> Result<Json, ProviderError> {
    json::parse(raw.trim_start_matches('\u{feff}'))
        .map_err(|error| ProviderError::InvalidData(error.to_string()))
}

fn rows(value: Json) -> Result<Vec<Json>, ProviderError> {
    let values = match value {
        Json::Arr(values) => values,
        Json::Obj(ref fields) => match value.get("items") {
            Some(Json::Arr(values)) => values.clone(),
            Some(_) => {
                return Err(ProviderError::InvalidData(
                    "items must be an array".to_owned(),
                ))
            }
            None if fields.iter().any(|(key, _)| key == "battleTimestamp") => vec![value],
            None => {
                return Err(ProviderError::InvalidData(
                    "missing battle items".to_owned(),
                ))
            }
        },
        _ => {
            return Err(ProviderError::InvalidData(
                "expected battle object or array".to_owned(),
            ))
        }
    };
    for value in &values {
        object(value).map_err(ProviderError::InvalidData)?;
    }
    Ok(values)
}

pub fn parse_battles(raw: &str, json_lines: bool) -> Result<Vec<Json>, ProviderError> {
    if !json_lines {
        return rows(parse(raw)?);
    }
    let mut values = Vec::new();
    for (index, line) in raw
        .lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
    {
        let value = parse(line)
            .map_err(|error| ProviderError::InvalidData(format!("line {}: {error}", index + 1)))?;
        object(&value).map_err(ProviderError::InvalidData)?;
        values.push(value);
    }
    Ok(values)
}

fn local_collection(
    raw: String,
    json_lines: bool,
    player_path: Option<&Path>,
    tag: &str,
) -> Result<Collection, ProviderError> {
    let battles = parse_battles(&raw, json_lines)?;
    let mut raw_payloads = vec![raw];
    let player = if let Some(path) = player_path {
        let raw = read(path)?;
        let player = parse(&raw)?;
        validate_player(&player, tag)?;
        raw_payloads.push(raw);
        Some(player)
    } else {
        None
    };
    Ok(Collection {
        battles,
        player,
        raw_payloads,
    })
}

pub fn validate_player(player: &Json, tag: &str) -> Result<(), ProviderError> {
    object(player).map_err(ProviderError::InvalidData)?;
    let player_tag = required_text(player, "tag").map_err(ProviderError::InvalidData)?;
    if normalize_tag(player_tag)? != normalize_tag(tag)? {
        return Err(ProviderError::InvalidData(
            "player snapshot tag mismatch".to_owned(),
        ));
    }
    Ok(())
}

pub struct LocalJson {
    pub path: PathBuf,
    pub player: Option<PathBuf>,
}

impl BattleLogSource for LocalJson {
    fn name(&self) -> &str {
        "local-json"
    }

    fn fetch(&mut self, tag: &str) -> Result<Collection, ProviderError> {
        local_collection(read(&self.path)?, false, self.player.as_deref(), tag)
    }
}

pub struct LocalJsonLines {
    pub path: PathBuf,
    pub player: Option<PathBuf>,
}

impl BattleLogSource for LocalJsonLines {
    fn name(&self) -> &str {
        "local-jsonl"
    }

    fn fetch(&mut self, tag: &str) -> Result<Collection, ProviderError> {
        local_collection(read(&self.path)?, true, self.player.as_deref(), tag)
    }
}

pub struct Stdin {
    pub json_lines: bool,
    pub player: Option<PathBuf>,
}

impl BattleLogSource for Stdin {
    fn name(&self) -> &str {
        "stdin"
    }

    fn fetch(&mut self, tag: &str) -> Result<Collection, ProviderError> {
        let mut raw = String::new();
        std::io::stdin()
            .read_to_string(&mut raw)
            .map_err(|error| ProviderError::Unavailable(error.to_string()))?;
        local_collection(raw, self.json_lines, self.player.as_deref(), tag)
    }
}

pub struct HttpResponse {
    pub status: u16,
    pub body: String,
    pub retry_after: Option<Duration>,
}

/// Injection boundary used by offline tests and alternative native transports.
pub trait HttpTransport {
    fn get(&mut self, url: &str) -> Result<HttpResponse, ProviderError>;

    fn wait(&mut self, duration: Duration) {
        std::thread::sleep(duration);
    }
}

/// Uses installed curl for HTTPS/TLS; no shell, curlrc, credentials or redirects.
pub struct CurlTransport;

impl HttpTransport for CurlTransport {
    fn get(&mut self, url: &str) -> Result<HttpResponse, ProviderError> {
        let output = Command::new("curl")
            .args([
                "--disable",
                "--silent",
                "--show-error",
                "--include",
                "--connect-timeout",
                "10",
                "--max-time",
                "30",
                "--proto",
                "=https",
                "--user-agent",
                "clash-lab native snapshot",
                "--url",
                url,
            ])
            .output()
            .map_err(|error| ProviderError::Unavailable(format!("curl: {error}")))?;
        if !output.status.success() {
            return Err(ProviderError::Unavailable(format!(
                "HTTPS transport exited {}",
                output.status
            )));
        }
        let raw = String::from_utf8(output.stdout)
            .map_err(|error| ProviderError::InvalidData(error.to_string()))?;
        parse_http_response(&raw)
    }
}

fn parse_http_response(mut raw: &str) -> Result<HttpResponse, ProviderError> {
    loop {
        let (headers, body) = raw
            .split_once("\r\n\r\n")
            .ok_or_else(|| ProviderError::InvalidData("missing HTTP headers".to_owned()))?;
        let status = headers
            .lines()
            .next()
            .and_then(|line| line.split_whitespace().nth(1))
            .and_then(|status| status.parse::<u16>().ok())
            .ok_or_else(|| ProviderError::InvalidData("invalid HTTP status".to_owned()))?;
        if (status == 100 || status == 200) && body.starts_with("HTTP/") {
            raw = body;
            continue;
        }
        let retry_after = headers
            .lines()
            .filter_map(|line| line.split_once(':'))
            .find(|(key, _)| key.eq_ignore_ascii_case("retry-after"))
            .and_then(|(_, value)| value.trim().parse::<u64>().ok())
            .map(Duration::from_secs);
        return Ok(HttpResponse {
            status,
            body: body.to_owned(),
            retry_after,
        });
    }
}

pub struct ConfiguredKeylessHttpProvider<T> {
    pub name: String,
    /// HTTPS URL containing `{tag}`; the tag is percent-encoded, including `#`.
    pub endpoint: String,
    pub player_endpoint: Option<String>,
    /// When configured, follow `paging.cursors.after` using this query parameter.
    pub cursor_parameter: Option<String>,
    pub transport: T,
}

fn endpoint(template: &str, tag: &str) -> Result<String, ProviderError> {
    let authority = template
        .strip_prefix("https://")
        .and_then(|rest| rest.split('/').next());
    if authority.is_none_or(|host| host.is_empty() || host.contains('@'))
        || !template.contains("{tag}")
        || template.contains(['?', '#'])
    {
        return Err(ProviderError::Unsupported(
            "configure a keyless HTTPS endpoint containing {tag}, without credentials or query parameters".to_owned(),
        ));
    }
    Ok(template.replace("{tag}", &percent_encode(tag)))
}

fn percent_encode(value: &str) -> String {
    value
        .bytes()
        .map(|byte| {
            if byte.is_ascii_alphanumeric() || b"-._~".contains(&byte) {
                (byte as char).to_string()
            } else {
                format!("%{byte:02X}")
            }
        })
        .collect()
}

impl<T: HttpTransport> ConfiguredKeylessHttpProvider<T> {
    fn request(&mut self, url: &str) -> Result<(Json, String), ProviderError> {
        for attempt in 0..3 {
            let response = self.transport.get(url);
            let (error, delay) = match response {
                Ok(response) if (200..300).contains(&response.status) => {
                    return Ok((parse(&response.body)?, response.body))
                }
                Ok(response) => {
                    let delay = response
                        .retry_after
                        .unwrap_or(Duration::from_secs(1 << attempt));
                    let message = format!("{} returned HTTP {}", self.name, response.status);
                    match response.status {
                        401 | 403 => {
                            return Err(ProviderError::Unsupported(format!(
                                "{message}; credentials are not supported"
                            )))
                        }
                        404 | 410 => {
                            return Err(ProviderError::Unsupported(format!(
                                "{message}; player history may be untracked"
                            )))
                        }
                        429 => (ProviderError::RateLimited(message), delay),
                        500..=599 => (ProviderError::Unavailable(message), delay),
                        _ => return Err(ProviderError::Unsupported(message)),
                    }
                }
                Err(error @ ProviderError::Unavailable(_)) => {
                    (error, Duration::from_secs(1 << attempt))
                }
                Err(error) => return Err(error),
            };
            if attempt == 2 || delay > Duration::from_secs(60) {
                return Err(error);
            }
            self.transport.wait(delay);
        }
        unreachable!("bounded retries return a response or error")
    }
}

impl<T: HttpTransport> BattleLogSource for ConfiguredKeylessHttpProvider<T> {
    fn name(&self) -> &str {
        &self.name
    }

    fn fetch(&mut self, tag: &str) -> Result<Collection, ProviderError> {
        let tag = normalize_tag(tag)?;
        let url = endpoint(&self.endpoint, &tag)?;
        let player_url = self
            .player_endpoint
            .as_deref()
            .map(|value| endpoint(value, &tag))
            .transpose()?;
        if self.cursor_parameter.as_ref().is_some_and(|key| {
            key.is_empty()
                || !key
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
        }) {
            return Err(ProviderError::Unsupported(
                "invalid cursor query parameter".to_owned(),
            ));
        }
        let mut next = url.clone();
        let mut seen = BTreeSet::new();
        let mut battles = Vec::new();
        let mut raw_payloads = Vec::new();
        loop {
            let (page, raw) = self.request(&next)?;
            raw_payloads.push(raw);
            let cursor = match page
                .get("paging")
                .and_then(|value| value.get("cursors"))
                .and_then(|value| value.get("after"))
            {
                None | Some(Json::Null) => None,
                Some(Json::Str(value)) if value.is_empty() => None,
                Some(Json::Str(value)) => Some(value.clone()),
                _ => {
                    return Err(ProviderError::InvalidData(
                        "invalid pagination cursor".to_owned(),
                    ))
                }
            };
            battles.extend(rows(page)?);
            let Some(cursor) = cursor else {
                break;
            };
            let Some(parameter) = &self.cursor_parameter else {
                return Err(ProviderError::Unsupported(
                    "provider has more pages; configure its cursor parameter".to_owned(),
                ));
            };
            if !seen.insert(cursor.clone()) || seen.len() >= 1000 {
                return Err(ProviderError::InvalidData(
                    "pagination did not terminate".to_owned(),
                ));
            }
            next = format!("{url}?{parameter}={}", percent_encode(&cursor));
        }
        let player = player_url
            .map(|url| self.request(&url))
            .transpose()?
            .map(|(player, raw)| {
                raw_payloads.push(raw);
                player
            });
        if let Some(player) = &player {
            validate_player(player, &tag)?;
        }
        Ok(Collection {
            battles,
            player,
            raw_payloads,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn curl_headers_and_connect_tunnel_are_decoded_without_a_network() {
        let response = parse_http_response("HTTP/1.1 200 Connection established\r\n\r\nHTTP/2 429\r\nRetry-After: 7\r\n\r\n{\"error\":\"limit\"}").unwrap();
        assert_eq!(response.status, 429);
        assert_eq!(response.retry_after, Some(Duration::from_secs(7)));
        assert!(parse_http_response("bad response").is_err());
    }
}
