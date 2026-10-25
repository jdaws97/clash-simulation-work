use std::collections::{BTreeMap, BTreeSet};

use crate::stats::Level;

pub type Tile = (i32, i32);
pub type InstanceId = String;

/// Spell Tower aliases remain distinct on export; all three earthquake aliases
/// have the same unlock rule. Facing defaults are resolved by the engine.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Mode {
    Normal,
    Geared,
    Fast,
    Burst,
    Single,
    Multi,
    Ground,
    Air,
    Both,
    Rage,
    Poison,
    Invis,
    Eq,
    Quake,
    Earthquake,
    N,
    NE,
    E,
    SE,
    S,
    SW,
    W,
    NW,
    Long,
    Short,
    None,
    Cake,
    Candle,
    Hunter,
}

impl Mode {
    pub fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "normal" => Self::Normal,
            "geared" => Self::Geared,
            "fast" => Self::Fast,
            "burst" => Self::Burst,
            "single" => Self::Single,
            "multi" => Self::Multi,
            "ground" => Self::Ground,
            "air" => Self::Air,
            "both" => Self::Both,
            "rage" => Self::Rage,
            "poison" => Self::Poison,
            "invis" => Self::Invis,
            "eq" => Self::Eq,
            "quake" => Self::Quake,
            "earthquake" => Self::Earthquake,
            "N" => Self::N,
            "NE" => Self::NE,
            "E" => Self::E,
            "SE" => Self::SE,
            "S" => Self::S,
            "SW" => Self::SW,
            "W" => Self::W,
            "NW" => Self::NW,
            "long" => Self::Long,
            "short" => Self::Short,
            "none" => Self::None,
            "cake" => Self::Cake,
            "candle" => Self::Candle,
            "hunter" => Self::Hunter,
            _ => return None,
        })
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Normal => "normal",
            Self::Geared => "geared",
            Self::Fast => "fast",
            Self::Burst => "burst",
            Self::Single => "single",
            Self::Multi => "multi",
            Self::Ground => "ground",
            Self::Air => "air",
            Self::Both => "both",
            Self::Rage => "rage",
            Self::Poison => "poison",
            Self::Invis => "invis",
            Self::Eq => "eq",
            Self::Quake => "quake",
            Self::Earthquake => "earthquake",
            Self::N => "N",
            Self::NE => "NE",
            Self::E => "E",
            Self::SE => "SE",
            Self::S => "S",
            Self::SW => "SW",
            Self::W => "W",
            Self::NW => "NW",
            Self::Long => "long",
            Self::Short => "short",
            Self::None => "none",
            Self::Cake => "cake",
            Self::Candle => "candle",
            Self::Hunter => "hunter",
        }
    }

    pub fn geared(self) -> bool {
        matches!(self, Self::Geared | Self::Fast | Self::Burst)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct BuildingPlacement {
    pub id: InstanceId,
    pub key: String,
    pub position: Tile,
    pub mode: Option<Mode>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TrapPlacement {
    pub id: InstanceId,
    pub key: String,
    pub position: Tile,
    pub mode: Option<Mode>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct WallPiece {
    pub id: InstanceId,
    pub position: Tile,
    /// None inherits the fixed account-wide default. Overrides move with pieces.
    pub level: Option<Level>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CcEntry {
    pub name: String,
    pub source: Option<String>,
    pub level: Option<Level>,
    pub count: u32,
    pub object_form: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct HeroBinding {
    pub hero: String,
    pub banner: Option<InstanceId>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct DefenseSetup {
    pub levels: BTreeMap<String, Level>,
    pub hero_levels: BTreeMap<String, Level>,
    pub cc_troops: Vec<CcEntry>,
    pub heroes: Vec<HeroBinding>,
    pub guardian: Option<String>,
    pub wall_level: Option<Level>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Layout {
    pub name: String,
    pub notes: String,
    pub town_hall: i64,
    pub buildings: Vec<BuildingPlacement>,
    pub walls: Vec<WallPiece>,
    pub traps: Vec<TrapPlacement>,
    pub setup: DefenseSetup,
}

#[derive(Clone, Debug, PartialEq)]
pub enum HolePolicy {
    Allow,
    Forbid,
    Penalize { per_tile: f64 },
}

/// FullyMerged is a declared preset, never an assertion about a real account.
/// Owned snapshots use normalized building/trap keys and explicit level maps.
#[derive(Clone, Debug, PartialEq)]
pub enum InventoryPolicy {
    FullyMerged,
    Owned {
        snapshot_id: String,
        buildings: BTreeMap<String, usize>,
        traps: BTreeMap<String, usize>,
        walls: usize,
        levels: BTreeMap<String, Level>,
        hero_levels: BTreeMap<String, Level>,
        wall_level: Level,
        /// Empty means uniform wall_level; otherwise the complete owned multiset.
        wall_levels: Vec<Level>,
        geared: BTreeSet<String>,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct AdmissionPolicy {
    pub require_full: bool,
    pub require_all_walls: bool,
    pub inventory: InventoryPolicy,
    pub holes: HolePolicy,
}

impl Default for AdmissionPolicy {
    fn default() -> Self {
        Self {
            require_full: true,
            require_all_walls: false,
            inventory: InventoryPolicy::FullyMerged,
            holes: HolePolicy::Allow,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Objective {
    RankedV1,
    WarV1,
}

#[derive(Clone, Debug, PartialEq)]
pub enum BattleMode {
    Ranked,
    War,
    Multiplayer,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ScenarioManifest {
    pub id: String,
    pub content_identity: String,
    pub groups: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SearchBudgets {
    pub physical_battles: u64,
    pub proposals: u64,
    pub screen_groups: usize,
    pub confirm_groups: usize,
    pub finalist_groups: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ArchiveDefinition {
    pub version: String,
    pub descriptor_corpus_identity: String,
    /// TH offset, compartments, AD spread, core defense density, in that order.
    pub edges: [[f64; 2]; 4],
    pub attack_archive_identity: String,
}

/// M0 contract only: no search loop is implemented by M1.
#[derive(Clone, Debug, PartialEq)]
pub struct SearchConfig {
    pub schema_version: u32,
    pub objective: Objective,
    pub battle_mode: BattleMode,
    pub modifier: String,
    pub admission: AdmissionPolicy,
    pub development: ScenarioManifest,
    pub confirmation: ScenarioManifest,
    pub final_report: ScenarioManifest,
    pub budgets: SearchBudgets,
    pub operators: Vec<(String, f64)>,
    pub archive: ArchiveDefinition,
    pub proposal_seed: u64,
    pub battle_seed: u64,
    pub engine_identity: String,
    pub rules_identity: String,
    pub catalog_identity: String,
    pub compiler_identity: String,
    pub knowledge_policy_identity: String,
    pub execution_profile_identity: String,
}
