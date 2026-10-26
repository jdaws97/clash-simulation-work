//! Typed source vocabulary, audited against engine Step::load/Trigger::parse,
//! direct Step::source reads, and clash-plans::compile. No executor is added.
use std::collections::BTreeMap;

use clash_data::json::Json;
use clash_data::wire::{self, obj, string};

/// Absence and explicit null have different canonical identities in source.
#[derive(Clone, Debug, Default, PartialEq)]
pub enum Field<T> {
    #[default]
    Absent,
    Null,
    Value(T),
}

impl<T> Field<T> {
    pub fn value(&self) -> Option<&T> {
        match self {
            Self::Value(value) => Some(value),
            _ => None,
        }
    }
}

trait Codec: Sized {
    fn decode(value: &Json) -> Result<Self, String>;
    fn encode(&self) -> Json;

    fn registry(&self) -> Json {
        self.encode()
    }
}

impl Codec for String {
    fn decode(value: &Json) -> Result<Self, String> {
        match value {
            Json::Str(value) => Ok(value.clone()),
            _ => Err("expected string".to_owned()),
        }
    }

    fn encode(&self) -> Json {
        string(self)
    }
}

impl Codec for f64 {
    fn decode(value: &Json) -> Result<Self, String> {
        match value {
            Json::Num(value) if value.is_finite() => Ok(*value),
            _ => Err("expected finite number".to_owned()),
        }
    }

    fn encode(&self) -> Json {
        wire::num(*self)
    }
}

impl Codec for bool {
    fn decode(value: &Json) -> Result<Self, String> {
        match value {
            Json::Bool(value) => Ok(*value),
            _ => Err("expected boolean".to_owned()),
        }
    }

    fn encode(&self) -> Json {
        Json::Bool(*self)
    }
}

impl<T: Codec> Codec for Vec<T> {
    fn decode(value: &Json) -> Result<Self, String> {
        match value {
            Json::Arr(values) => values.iter().map(T::decode).collect(),
            _ => Err("expected array".to_owned()),
        }
    }

    fn encode(&self) -> Json {
        Json::Arr(self.iter().map(T::encode).collect())
    }

    fn registry(&self) -> Json {
        Json::Arr(self.iter().map(T::registry).collect())
    }
}

fn take<T: Codec>(fields: &mut BTreeMap<String, Json>, key: &str) -> Result<Field<T>, String> {
    match fields.remove(key) {
        None => Ok(Field::Absent),
        Some(Json::Null) => Ok(Field::Null),
        Some(value) => T::decode(&value)
            .map(Field::Value)
            .map_err(|error| format!("{key}: {error}")),
    }
}

fn put<T: Codec>(fields: &mut BTreeMap<String, Json>, key: &str, value: &Field<T>) {
    match value {
        Field::Absent => {}
        Field::Null => {
            fields.insert(key.to_owned(), Json::Null);
        }
        Field::Value(value) => {
            fields.insert(key.to_owned(), value.encode());
        }
    }
}

fn put_registry<T: Codec>(fields: &mut BTreeMap<String, Json>, key: &str, value: &Field<T>) {
    if let Field::Value(value) = value {
        fields.insert(key.to_owned(), value.registry());
    } else {
        put(fields, key, value);
    }
}

fn fields(value: &Json) -> Result<BTreeMap<String, Json>, String> {
    match value {
        Json::Obj(values) => {
            let result: BTreeMap<_, _> = values.iter().cloned().collect();
            if result.len() != values.len() {
                return Err("duplicate parameter key".to_owned());
            }
            Ok(result)
        }
        _ => Err("expected parameter object".to_owned()),
    }
}

macro_rules! vocabulary {
    ($name:ident { $($field:ident: $kind:ty),* $(,)? }) => {
        #[derive(Clone, Debug, Default, PartialEq)]
        pub struct $name {
            $(pub $field: Field<$kind>,)*
        }

        impl $name {
            fn extract(fields: &mut BTreeMap<String, Json>) -> Result<Self, String> {
                Ok(Self { $($field: take(fields, stringify!($field))?,)* })
            }

            fn append(&self, fields: &mut BTreeMap<String, Json>) {
                $(put(fields, stringify!($field), &self.$field);)*
            }

            pub fn to_json(&self) -> Json {
                let mut fields = BTreeMap::new();
                $(put_registry(&mut fields, stringify!($field), &self.$field);)*
                obj(fields)
            }

            pub fn keys() -> &'static [&'static str] {
                &[$(stringify!($field)),*]
            }
        }
    };
}

macro_rules! names {
    ($name:ident { $($variant:ident => $text:literal),* $(,)? }) => {
        #[derive(Clone, Debug, PartialEq, Eq)]
        pub enum $name { $($variant),* }

        impl Codec for $name {
            fn decode(value: &Json) -> Result<Self, String> {
                match String::decode(value)?.as_str() {
                    $($text => Ok(Self::$variant),)*
                    other => Err(format!("unknown {} {other}", stringify!($name))),
                }
            }

            fn encode(&self) -> Json {
                string(match self { $(Self::$variant => $text,)* })
            }
        }
    };
}

names!(MoveAction {
    Deploy => "deploy",
    Spell => "spell",
    Ability => "ability",
    Recall => "recall",
    Redeploy => "redeploy",
    ReleaseSiege => "release_siege",
});

names!(SelectorKind {
    Edge => "edge",
    Unit => "unit",
    UnitAhead => "unit_ahead",
    Group => "group",
    Cohort => "cohort",
    TownHall => "th",
    Threat => "threat",
    Defenders => "defenders",
    Defender => "defender",
    Building => "building",
});

names!(EdgeSide {
    Main => "main",
    Left => "left",
    Right => "right",
    Charge => "charge",
    Funnel => "funnel",
});

names!(StockOrigin {
    Home => "home",
    Donated => "donated",
});

/// The side is `argument` for an Edge selector. Other arguments name an actor,
/// cohort, group, building key or `defender:group`. These are symbolic selectors,
/// not recovered coordinates. `spread` scales the executor's fixed formation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Selector {
    pub kind: SelectorKind,
    pub argument: Option<String>,
}

impl Selector {
    pub fn edge(side: EdgeSide) -> Self {
        Self {
            kind: SelectorKind::Edge,
            argument: Some(side.encode().str().to_owned()),
        }
    }

    pub fn side(&self) -> Option<EdgeSide> {
        if self.kind != SelectorKind::Edge {
            return None;
        }
        self.argument
            .as_ref()
            .and_then(|side| EdgeSide::decode(&string(side)).ok())
    }
}

impl Codec for Selector {
    fn decode(value: &Json) -> Result<Self, String> {
        let text = String::decode(value)?;
        let (kind, argument) = text
            .split_once(':')
            .map_or((text.as_str(), None), |(k, a)| (k, Some(a.to_owned())));
        Ok(Self {
            kind: SelectorKind::decode(&string(kind))?,
            argument,
        })
    }

    fn encode(&self) -> Json {
        let kind = self.kind.encode();
        string(match &self.argument {
            Some(argument) => format!("{}:{argument}", kind.str()),
            None => kind.str().to_owned(),
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Count {
    All,
    Exact(u32),
    /// Legacy numeric strings retain their source spelling.
    Text(String),
}

impl Codec for Count {
    fn decode(value: &Json) -> Result<Self, String> {
        match value {
            Json::Str(value) if value == "all" => Ok(Self::All),
            Json::Str(value) if value.parse::<u32>().is_ok() => Ok(Self::Text(value.clone())),
            Json::Num(value)
                if value.is_finite()
                    && *value >= 0.0
                    && *value <= u32::MAX as f64
                    && value.fract() == 0.0 =>
            {
                Ok(Self::Exact(*value as u32))
            }
            _ => Err("count needs a nonnegative integer or all".to_owned()),
        }
    }

    fn encode(&self) -> Json {
        match self {
            Self::All => string("all"),
            Self::Exact(value) => wire::num(*value),
            Self::Text(value) => string(value),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum EquipmentSelection {
    One(String),
    AnyOf(Vec<String>),
}

impl Codec for EquipmentSelection {
    fn decode(value: &Json) -> Result<Self, String> {
        match value {
            Json::Str(_) => String::decode(value).map(Self::One),
            Json::Arr(_) => Vec::decode(value).map(Self::AnyOf),
            _ => Err("equipment needs a name or any-of list".to_owned()),
        }
    }

    fn encode(&self) -> Json {
        match self {
            Self::One(value) => value.encode(),
            Self::AnyOf(value) => value.encode(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Aim {
    Arrow,
    Dash,
    At(Selector),
}

impl Codec for Aim {
    fn decode(value: &Json) -> Result<Self, String> {
        match value.opt_str() {
            Some("arrow") => Ok(Self::Arrow),
            Some("dash") => Ok(Self::Dash),
            _ => Selector::decode(value).map(Self::At),
        }
    }

    fn encode(&self) -> Json {
        match self {
            Self::Arrow => string("arrow"),
            Self::Dash => string("dash"),
            Self::At(value) => value.encode(),
        }
    }
}

vocabulary!(ActorParameters {
    what: String,
    count: Count,
    level: f64,
    origin: StockOrigin,
    recall_from: String,
    allocated_count: f64,
    siege_role: String,
});

vocabulary!(ObjectiveParameters {
    at: Selector,
    objective: String,
    objective_at: Selector,
    mask_for: String,
    mask_hero: String,
    bind_before: String,
    target_keys: Vec<String>,
    target_mode: String,
    route_hero: String,
    per_target: bool,
    snipe: bool,
});

vocabulary!(PlacementParameters {
    spread: f64,
    ahead_of: String,
    at_cite: bool,
});

vocabulary!(ControlParameters {
    id: String,
    group: String,
    packet: String,
    primary: bool,
    primary_cohort: bool,
    when: Condition,
    until: Condition,
    every: f64,
    timeout: f64,
    after_success: String,
    recheck_when: bool,
    post_recall: bool,
    repeat_effect_remaining: f64,
    repeat_units_absent: String,
});

vocabulary!(ActivationParameters {
    ability: String,
    equipment: EquipmentSelection,
    aim: Aim,
    aim_count: f64,
    required: bool,
});

vocabulary!(SupportParameters {
    optional: bool,
    reserved: bool,
    spell_budget: String,
    uncited: bool,
    variant: String,
});

vocabulary!(CompletionParameters {
    completion: bool,
    skip_if_impossible: bool,
});

vocabulary!(PredicateFields {
    all: Vec<Condition>,
    any: Vec<Condition>,
    t: f64,
    after: String,
    inside: String,
    group_inside: String,
    near_th: String,
    heavy_fire: String,
    hp_below: String,
    spells_left: String,
    dead: String,
    defenders_near: String,
    destruction: f64,
    effect_active: String,
    effect_expired: String,
    objective: String,
    defender: String,
    cohort_absent: String,
    succeeded: String,
    delay: f64,
    r: f64,
    frac: f64,
    n: f64,
    state: String,
    group: String,
});

#[derive(Clone, Debug, PartialEq)]
pub enum Condition {
    Disabled,
    Predicate(Box<Predicate>),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Predicate {
    pub fields: PredicateFields,
    pub residual: BTreeMap<String, ResidualParameter>,
}

impl Codec for Condition {
    fn decode(value: &Json) -> Result<Self, String> {
        if value == &Json::Bool(false) {
            return Ok(Self::Disabled);
        }
        let mut source = fields(value)?;
        let stored_residual = source.remove("residual");
        let fields = PredicateFields::extract(&mut source)?;
        if fields
            .to_json()
            .obj()
            .iter()
            .any(|(_, value)| value.is_null())
        {
            return Err("predicate fields cannot be null".to_owned());
        }
        let predicates = fields
            .to_json()
            .obj()
            .iter()
            .filter(|(key, _)| {
                !["delay", "r", "frac", "n", "state", "group"].contains(&key.as_str())
            })
            .count();
        if predicates > 1 {
            return Err("trigger needs one predicate; combine with all/any".to_owned());
        }
        let mut residual = residual(source);
        if let Some(value) = stored_residual {
            residual.extend(read_residual(&value, PredicateFields::keys())?);
        }
        if predicates == 0 && !fields.to_json().obj().is_empty() && residual.is_empty() {
            return Err("trigger modifiers need a predicate".to_owned());
        }
        Ok(Self::Predicate(Box::new(Predicate { fields, residual })))
    }

    fn encode(&self) -> Json {
        match self {
            Self::Disabled => Json::Bool(false),
            Self::Predicate(value) => {
                let mut fields = BTreeMap::new();
                value.fields.append(&mut fields);
                fields.extend(
                    value
                        .residual
                        .iter()
                        .map(|(key, value)| (key.clone(), value.value.clone())),
                );
                obj(fields)
            }
        }
    }

    fn registry(&self) -> Json {
        match self {
            Self::Disabled => Json::Bool(false),
            Self::Predicate(value) => {
                let mut record = value.fields.to_json();
                if !value.residual.is_empty() {
                    wire::put(&mut record, "residual", residual_json(&value.residual));
                }
                record
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ResidualParameter {
    pub value: Json,
    pub reason: String,
}

fn residual_json(values: &BTreeMap<String, ResidualParameter>) -> Json {
    obj(values.iter().map(|(key, value)| {
        (
            key,
            obj([
                ("value", value.value.clone()),
                ("reason", string(&value.reason)),
            ]),
        )
    }))
}

fn read_residual(
    value: &Json,
    known: &[&str],
) -> Result<BTreeMap<String, ResidualParameter>, String> {
    let mut result = BTreeMap::new();
    for (key, value) in fields(value)? {
        if known.contains(&key.as_str())
            || annotation_key(&key)
            || ["cite", "source_record", "residual"].contains(&key.as_str())
        {
            return Err(format!("typed/evidence field in residual: {key}"));
        }
        result.insert(
            key,
            ResidualParameter {
                value: super::required(&value, "value")?.clone(),
                reason: super::required_text(&value, "reason")?,
            },
        );
    }
    Ok(result)
}

fn residual(fields: BTreeMap<String, Json>) -> BTreeMap<String, ResidualParameter> {
    fields
        .into_iter()
        .map(|(key, value)| {
            (
                key,
                ResidualParameter {
                    value,
                    reason: "unknown vocabulary; preserve and require review before composition"
                        .to_owned(),
                },
            )
        })
        .collect()
}

pub fn annotation_key(key: &str) -> bool {
    [
        "support",
        "rule",
        "note",
        "target_note",
        "timing_note",
        "aim_cite",
        "origin_cite",
    ]
    .contains(&key)
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct MoveParameters {
    pub action: Field<MoveAction>,
    pub actor: ActorParameters,
    pub objective: ObjectiveParameters,
    pub placement: PlacementParameters,
    pub control: ControlParameters,
    pub activation: ActivationParameters,
    pub support: SupportParameters,
    pub completion: CompletionParameters,
    pub residual: BTreeMap<String, ResidualParameter>,
}

impl MoveParameters {
    pub fn from_record(record: &Json) -> Result<Self, String> {
        let mut fields = fields(record)?;
        fields.retain(|key, _| key != "cite" && !annotation_key(key));
        Ok(Self {
            action: take(&mut fields, "action")?,
            actor: ActorParameters::extract(&mut fields)?,
            objective: ObjectiveParameters::extract(&mut fields)?,
            placement: PlacementParameters::extract(&mut fields)?,
            control: ControlParameters::extract(&mut fields)?,
            activation: ActivationParameters::extract(&mut fields)?,
            support: SupportParameters::extract(&mut fields)?,
            completion: CompletionParameters::extract(&mut fields)?,
            residual: residual(fields),
        })
    }

    pub fn executable(&self) -> Json {
        let mut fields = BTreeMap::new();
        put(&mut fields, "action", &self.action);
        self.actor.append(&mut fields);
        self.objective.append(&mut fields);
        self.placement.append(&mut fields);
        self.control.append(&mut fields);
        self.activation.append(&mut fields);
        self.support.append(&mut fields);
        self.completion.append(&mut fields);
        fields.extend(
            self.residual
                .iter()
                .map(|(key, value)| (key.clone(), value.value.clone())),
        );
        obj(fields)
    }

    pub fn to_json(&self) -> Json {
        let mut value = obj([
            ("actor", self.actor.to_json()),
            ("objective", self.objective.to_json()),
            ("placement", self.placement.to_json()),
            ("control", self.control.to_json()),
            ("activation", self.activation.to_json()),
            ("support", self.support.to_json()),
            ("completion", self.completion.to_json()),
            ("residual", residual_json(&self.residual)),
        ]);
        match &self.action {
            Field::Absent => {}
            Field::Null => wire::put(&mut value, "action", Json::Null),
            Field::Value(action) => wire::put(&mut value, "action", action.encode()),
        }
        value
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        let mut source = fields(value)?;
        let action = take(&mut source, "action")?;
        let mut executable = obj([] as [(&str, Json); 0]);
        for key in [
            "actor",
            "objective",
            "placement",
            "control",
            "activation",
            "support",
            "completion",
        ] {
            let group = source
                .remove(key)
                .ok_or_else(|| format!("missing parameter group {key}"))?;
            for (field, value) in fields(&group)? {
                let allowed = match key {
                    "actor" => ActorParameters::keys(),
                    "objective" => ObjectiveParameters::keys(),
                    "placement" => PlacementParameters::keys(),
                    "control" => ControlParameters::keys(),
                    "activation" => ActivationParameters::keys(),
                    "support" => SupportParameters::keys(),
                    _ => CompletionParameters::keys(),
                };
                if !allowed.contains(&field.as_str()) {
                    return Err(format!("unknown typed field {key}.{field}"));
                }
                wire::put(&mut executable, &field, value);
            }
        }
        let residual_value = source.remove("residual").ok_or("missing residual map")?;
        if !source.is_empty() {
            return Err("unknown parameter group (source_record is forbidden)".to_owned());
        }
        let mut result = Self::from_record(&executable)?;
        result.action = action;
        result.residual = read_residual(&residual_value, &Self::known_keys())?;
        Ok(result)
    }

    pub fn known_keys() -> Vec<&'static str> {
        [
            vec!["action"],
            ActorParameters::keys().to_vec(),
            ObjectiveParameters::keys().to_vec(),
            PlacementParameters::keys().to_vec(),
            ControlParameters::keys().to_vec(),
            ActivationParameters::keys().to_vec(),
            SupportParameters::keys().to_vec(),
            CompletionParameters::keys().to_vec(),
        ]
        .concat()
    }
}
