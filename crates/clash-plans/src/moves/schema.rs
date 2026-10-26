use std::collections::BTreeMap;

use clash_data::json::Json;
use clash_data::wire::{self, obj, string};

pub const SCHEMA_VERSION: u32 = 2;

#[path = "parameters.rs"]
mod parameters;
pub use parameters::*;

#[derive(Clone, Debug, PartialEq)]
pub struct EvidenceScope {
    pub actor: String,
    pub purpose: String,
    pub order: String,
    pub geometry: String,
    pub timing: String,
    pub verification: String,
}

impl EvidenceScope {
    pub fn inherited() -> Self {
        Self {
            actor: "inferred".to_owned(),
            purpose: "inferred".to_owned(),
            order: "inferred".to_owned(),
            geometry: "inferred".to_owned(),
            timing: "unspecified".to_owned(),
            verification: "source_citations_not_reverified".to_owned(),
        }
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        Ok(Self {
            actor: required_text(value, "actor")?,
            purpose: required_text(value, "purpose")?,
            order: required_text(value, "order")?,
            geometry: required_text(value, "geometry")?,
            timing: required_text(value, "timing")?,
            verification: required_text(value, "verification")?,
        })
    }

    pub fn to_json(&self) -> Json {
        obj([
            ("actor", string(&self.actor)),
            ("purpose", string(&self.purpose)),
            ("order", string(&self.order)),
            ("geometry", string(&self.geometry)),
            ("timing", string(&self.timing)),
            ("verification", string(&self.verification)),
        ])
    }
}

/// Immutable identity/version pair. Supported fields and actor names constrain
/// the shared typed vocabulary to this definition's evidenced purpose.
#[derive(Clone, Debug)]
pub struct MoveDefinition {
    pub schema_version: u32,
    pub definition_version: u32,
    pub move_id: String,
    pub name: String,
    pub family: String,
    pub purpose: String,
    pub actor_bindings: Json,
    pub applicability: Json,
    pub resource_requirements: Json,
    pub static_preconditions: Vec<String>,
    pub live_preconditions: Vec<String>,
    pub parameters: Json,
    pub control: Json,
    pub completion: Json,
    /// Occurrence IDs, resolving to exact citations rather than copied summaries.
    pub evidence: Vec<String>,
    pub evidence_scope: EvidenceScope,
    pub human_costs: Json,
    pub mechanic_dependencies: Vec<String>,
    pub attribution: Json,
    pub lowering: String,
}

impl MoveDefinition {
    pub fn from_json(value: &Json) -> Result<Self, String> {
        Ok(Self {
            schema_version: version(value, "schema_version")?,
            definition_version: version(value, "definition_version")?,
            move_id: required_text(value, "move_id")?,
            name: required_text(value, "name")?,
            family: required_text(value, "family")?,
            purpose: required_text(value, "purpose")?,
            actor_bindings: object(value, "actor_bindings")?,
            applicability: object(value, "applicability")?,
            resource_requirements: object(value, "resource_requirements")?,
            static_preconditions: strings(value, "static_preconditions")?,
            live_preconditions: strings(value, "live_preconditions")?,
            parameters: object(value, "parameters")?,
            control: object(value, "control")?,
            completion: object(value, "completion")?,
            evidence: strings(value, "evidence")?,
            evidence_scope: EvidenceScope::from_json(required(value, "evidence_scope")?)?,
            human_costs: object(value, "human_costs")?,
            mechanic_dependencies: strings(value, "mechanic_dependencies")?,
            attribution: object(value, "attribution")?,
            lowering: required_text(value, "lowering")?,
        })
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MappingStatus {
    Mapped,
    Unresolved,
    Unsupported,
}

#[derive(Clone, Debug)]
pub struct Evidence {
    pub source_file: String,
    pub pointer: String,
    /// The entire original citation, including absent fields and non-video URLs.
    pub citation: Json,
}

#[derive(Clone, Debug)]
pub struct InstanceEvidence {
    pub citations: Vec<Evidence>,
    pub cite_present: bool,
    /// Prose, support counts and auxiliary citations retain exact source values.
    /// Some citations still influence the legacy compiler/aiming heuristics.
    pub annotations: BTreeMap<String, Json>,
}

#[derive(Clone, Debug)]
pub struct MoveInstance {
    pub schema_version: u32,
    pub instance_id: String,
    pub source_file: String,
    pub pointer: String,
    pub kind: String,
    pub source_hash: String,
    pub status: MappingStatus,
    pub reason: String,
    pub move_id: Option<String>,
    pub definition_version: Option<u32>,
    pub applicability: Json,
    pub parameters: MoveParameters,
    pub evidence: InstanceEvidence,
    /// Archival reconstruction tolerates these recorded evidence gaps. Strict
    /// admission for composition never treats this marker as an exemption.
    pub scope_unverified: Vec<String>,
    pub evidence_scope: EvidenceScope,
    pub human_costs: Json,
    pub mechanic_dependencies: Vec<String>,
    pub attribution: Json,
}

impl MoveInstance {
    pub fn from_json(value: &Json) -> Result<Self, String> {
        let status = match required_text(value, "status")?.as_str() {
            "mapped" => MappingStatus::Mapped,
            "unresolved" => MappingStatus::Unresolved,
            "unsupported" => MappingStatus::Unsupported,
            other => return Err(format!("invalid move status: {other}")),
        };
        let move_id = match required(value, "move_id")? {
            Json::Null => None,
            Json::Str(id) if !id.is_empty() => Some(id.clone()),
            _ => return Err("move_id needs a string or null".to_owned()),
        };
        let definition_version = match required(value, "definition_version")? {
            Json::Null => None,
            _ => Some(version(value, "definition_version")?),
        };
        let evidence_value = required(value, "evidence")?;
        let citations = array(evidence_value, "citations")?
            .iter()
            .map(|item| {
                Ok(Evidence {
                    source_file: required_text(item, "source_file")?,
                    pointer: required_text(item, "pointer")?,
                    citation: object(item, "citation")?,
                })
            })
            .collect::<Result<_, String>>()?;
        Ok(Self {
            schema_version: version(value, "schema_version")?,
            instance_id: required_text(value, "instance_id")?,
            source_file: required_text(value, "source_file")?,
            pointer: required_text(value, "pointer")?,
            kind: required_text(value, "kind")?,
            source_hash: required_text(value, "source_hash")?,
            status,
            reason: match required(value, "reason")? {
                Json::Str(reason) => reason.clone(),
                _ => return Err("reason needs a string".to_owned()),
            },
            move_id,
            definition_version,
            applicability: object(value, "applicability")?,
            parameters: MoveParameters::from_json(required(value, "parameters")?)?,
            evidence: InstanceEvidence {
                citations,
                cite_present: match required(evidence_value, "cite_present")? {
                    Json::Bool(value) => *value,
                    _ => return Err("cite_present needs a boolean".to_owned()),
                },
                annotations: object(evidence_value, "annotations")?
                    .obj()
                    .iter()
                    .cloned()
                    .collect(),
            },
            scope_unverified: strings(value, "scope_unverified")?,
            evidence_scope: EvidenceScope::from_json(required(value, "evidence_scope")?)?,
            human_costs: object(value, "human_costs")?,
            mechanic_dependencies: strings(value, "mechanic_dependencies")?,
            attribution: object(value, "attribution")?,
        })
    }
}

pub(crate) fn required<'a>(value: &'a Json, key: &str) -> Result<&'a Json, String> {
    value
        .get(key)
        .ok_or_else(|| format!("missing move field {key}"))
}

pub(crate) fn required_text(value: &Json, key: &str) -> Result<String, String> {
    match required(value, key)? {
        Json::Str(value) if !value.trim().is_empty() => Ok(value.clone()),
        _ => Err(format!("move field {key} needs a nonempty string")),
    }
}

pub(crate) fn object(value: &Json, key: &str) -> Result<Json, String> {
    match required(value, key)? {
        value @ Json::Obj(_) => Ok(value.clone()),
        _ => Err(format!("move field {key} needs an object")),
    }
}

pub(crate) fn array<'a>(value: &'a Json, key: &str) -> Result<&'a [Json], String> {
    match required(value, key)? {
        Json::Arr(values) => Ok(values),
        _ => Err(format!("move field {key} needs an array")),
    }
}

pub(crate) fn strings(value: &Json, key: &str) -> Result<Vec<String>, String> {
    array(value, key)?
        .iter()
        .map(|item| match item {
            Json::Str(item) if !item.is_empty() => Ok(item.clone()),
            _ => Err(format!("move field {key} needs nonempty strings")),
        })
        .collect()
}

pub(crate) fn version(value: &Json, key: &str) -> Result<u32, String> {
    match required(value, key)? {
        Json::Num(number)
            if number.is_finite()
                && *number >= 1.0
                && *number <= u32::MAX as f64
                && number.fract() == 0.0 =>
        {
            Ok(*number as u32)
        }
        _ => Err(format!("move field {key} needs a positive version integer")),
    }
}

pub fn canonical(value: &Json) -> String {
    // Parsed workspace numbers are f64 in both original and reconstructed books.
    wire::canonical(&wire::encode(value)).expect("valid in-memory JSON")
}

pub fn fingerprint(value: &Json) -> String {
    wire::sha256(canonical(value).as_bytes())
}

/// Readable registry files with compact short arrays/objects. Values still use
/// the workspace serializer, including its exact string and number encoding.
pub fn format_json(value: &Json) -> String {
    fn render(value: &Json, depth: usize) -> String {
        let compact = wire::encode(value);
        if compact.len() <= 100 {
            return compact;
        }
        let (open, close, children) = match value {
            Json::Obj(fields) => (
                '{',
                '}',
                fields
                    .iter()
                    .map(|(key, value)| {
                        format!(
                            "{}: {}",
                            wire::encode(&string(key)),
                            render(value, depth + 1)
                        )
                    })
                    .collect::<Vec<_>>(),
            ),
            Json::Arr(values) => (
                '[',
                ']',
                values
                    .iter()
                    .map(|value| render(value, depth + 1))
                    .collect(),
            ),
            _ => return compact,
        };
        let indentation = "  ".repeat(depth + 1);
        format!(
            "{open}\n{indentation}{}\n{}{close}",
            children.join(&format!(",\n{indentation}")),
            "  ".repeat(depth)
        )
    }
    format!("{}\n", render(value, 0))
}
