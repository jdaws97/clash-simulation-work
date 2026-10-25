//! Battle-local parameter registry. Game-data values do not establish AI semantics.

use std::collections::HashSet;

use crate::catalog::Catalog;
use crate::fast_hash::FastMap;
use crate::json::Json;

macro_rules! registry {
    ($($name:ident: $kind:ty = $default:expr, $provenance:literal, $unit:literal, $meaning:literal;)+) => {
        #[derive(Clone, Debug)]
        pub struct Params {
            $(pub $name: $kind,)+
            pub new_target_delays: FastMap<String, f64>,
        }

        impl Default for Params {
            fn default() -> Self {
                Self {
                    $($name: $default,)+
                    new_target_delays: FastMap::default(),
                }
            }
        }

        impl Params {
            fn set(&mut self, key: &str, value: &Json) -> Result<(), String> {
                match key {
                    $(stringify!($name) => self.$name = <$kind as ParameterValue>::read(value, key)?,)+
                    _ => return Err(format!("unknown engine parameter {key:?}")),
                }
                Ok(())
            }

            pub fn markdown() -> String {
                let mut out = String::from("| Name | Default | Provenance | Unit | Meaning |\n|---|---:|---|---|---|\n");
                $(out.push_str(&format!("| `{}` | {} | {} | {} | {} |\n", stringify!($name), $default, $provenance, $unit, $meaning));)+
                out
            }
        }
    };
}

registry! {
    target_list: bool = false, "assumed", "flag", "Opt-in target-list hypothesis";
    warden_spatial: bool = false, "assumed", "flag", "Opt-in spatial grouping hypothesis";
    defender_separation: bool = false, "assumed", "flag", "Separate defenders using the same collision rule";
    hidden_information: bool = false, "assumed", "flag", "Hide unrevealed structures from attacker planning and navigation";
    wall_cost: f64 = 12.0, "assumed", "tiles", "Legacy normal wall cost, divided by grid resolution per cell";
    ground_radius: f64 = 0.35, "assumed", "tiles", "Ground separation base radius";
    ground_radius_per_housing: f64 = 0.015, "assumed", "tiles/housing", "Ground separation housing contribution";
    separation_housing_cap: f64 = 30.0, "assumed", "housing", "Cap on ground radius housing contribution";
    air_radius: f64 = 0.35, "measured", "tiles", "Dragon spacing estimate; output/dragon-spacing/measure.md";
    separation_push: f64 = 0.25, "assumed", "overlap/tick", "Each member receives this fraction of overlap";
    separation_angle: f64 = 2.399, "assumed", "radians/id", "Deterministic direction for coincident units";
    stuck_timeout: f64 = 2.0, "assumed", "seconds", "Legacy no-waypoint timeout";
    dragon_arrival_windup: f64 = 0.75, "assumed", "seconds", "Fallback Dragon arrival wind-up";
    melee_arrival_windup: f64 = 0.33, "assumed", "seconds", "Fallback melee arrival wind-up cap";
    mite_attack_windup: f64 = 0.5, "assumed", "seconds", "Frostmite/Firemite first attack gate";
    defender_retarget_delay: f64 = 0.5, "assumed", "seconds", "Defender periodic target selection";
    attacker_engage_delay: f64 = 0.5, "assumed", "seconds", "Attacker retaliation checks";
    siege_blocker_delay: f64 = 0.5, "assumed", "seconds", "Ground siege blocker checks";
    retaliation_radius: f64 = 7.0, "game-data", "tiles", "CHAR_VS_CHAR_RADIUS_FOR_ATTACKER; ally alert search";
    ally_hit_memory: f64 = 1.0, "assumed", "seconds", "Recent ally damage counts for retaliation";
    castle_radius: f64 = 13.0, "game-data", "tiles", "CLAN_CASTLE_RADIUS";
    castle_exit_delay: f64 = 0.3, "assumed", "seconds", "Spacing between defending CC releases";
    th_activation_delay: f64 = 0.5, "assumed", "seconds", "Town Hall weapon wake delay";
    guardian_activation_delay: f64 = 0.5, "assumed", "seconds", "Guardian rooftop wake delay";
    scout_time: f64 = 30.0, "assumed", "seconds", "Pre-attack scouting budget";
    hero_jitter: f64 = 0.5, "assumed", "tiles", "Generic hero deployment jitter per axis";
    cleanup_jitter: f64 = 0.3, "assumed", "tiles", "Generic cleanup deployment jitter per axis";
    reaction_delay: f64 = 0.5, "assumed", "seconds", "Generic plan and fallback decision interval";
    pace: f64 = 1.0, "assumed", "multiplier", "Human input time scale";
    pace_tap: f64 = 0.133, "measured", "seconds", "Held deployment cadence; docs/VIDEO_MEASUREMENTS.md";
    pace_switch: f64 = 0.6, "assumed", "seconds", "Slot/spot switch time";
    pace_ability: f64 = 0.3, "assumed", "seconds", "Ability action time";
    aim_wait: f64 = 10.0, "assumed", "seconds", "Ready ability/spell aim timeout";
    late_deployment: f64 = 150.0, "assumed", "seconds", "Spend remaining camp by this time";
    opening_hold: f64 = 30.0, "assumed", "seconds", "Maximum generic opening hold";
    revive_delay: f64 = 1.5, "assumed", "seconds", "Default revive reaction delay (explicit plans still override)";
    healer_group_radius: f64 = 1.5, "game-data", "tiles", "Healer splash/group radius";
    healer_group_min_housing: f64 = 2.0, "assumed", "housing", "Group must exceed this housing";
    healer_hero_weight: f64 = 25.0, "assumed", "housing", "Hero weight in Healer group test";
    healer_projectile_speed: f64 = 12.0, "assumed", "tiles/second", "Healer beam travel speed";
    warden_radius: f64 = 13.0, "game-data", "tiles", "Legacy Warden vision radius";
    warden_min_weight: f64 = 20.0, "game-data", "weight", "Legacy Grand Warden vote threshold";
    apprentice_radius: f64 = 13.0, "game-data", "tiles", "Apprentice TargetGroupsRange / 100";
    apprentice_min_weight: f64 = 10.0, "assumed", "weight", "Legacy Apprentice vote threshold";
    spell_landing_delay: f64 = 0.5, "assumed", "seconds", "Bottle landing delay except instant Revive";
    poison_ramp: f64 = 4.0, "assumed", "seconds", "Poison time to full DPS";
    trap_frame_seconds: f64 = 1.5 / 35.0, "assumed", "seconds/frame", "Bomb-derived ActionFrame conversion";
    spring_delay: f64 = 0.3, "assumed", "seconds", "Spring fuse retained over conflicting frame inference";
    spring_stun: f64 = 1.0, "assumed", "seconds", "Spring stun on survivors";
    tornado_force_scale: f64 = 1.0, "assumed", "multiplier", "Interpret table force as pull velocity";
    internal_units_per_tile: f64 = 100.0, "game-data", "units/tile", "TargetGroupsRange evidence; path/noise scale transfer is a hypothesis";
    target_list_size: f64 = 3.0, "game-data", "candidates", "TARGET_LIST_SIZE; nearest primary candidates (hypothesis)";
    max_target_list_size: f64 = 6.0, "game-data", "candidates", "MAX_TARGET_LIST_SIZE; unreachable/forced expansion cap (hypothesis)";
    extra_target_path_cost_penalty: f64 = 5.0, "game-data", "tiles/rank", "EXTRA_TARGET_PATH_COST_PENALTY; extra candidate penalty (hypothesis)";
    wall_cost_base: f64 = 1000.0, "game-data", "internal units", "WALL_COST_BASE; path wall cost (hypothesis)";
    forget_target_time: f64 = 6000.0, "game-data", "milliseconds", "FORGET_TARGET_TIME; no-progress forgetting (hypothesis)";
    remember_original_target: bool = true, "game-data", "bool", "REMEMBER_ORIGINAL_TARGET; resume after retaliation/detour (hypothesis)";
    force_new_target_default_max_noise: f64 = 800.0, "game-data", "internal units", "FORCE_NEW_TARGET_DEFAULT_MAX_NOISE; forced score noise bound (hypothesis)";
    force_new_target_jump_max_noise: f64 = 100.0, "game-data", "internal units", "FORCE_NEW_TARGET_JUMP_MAX_NOISE; Jump forced score noise bound (hypothesis)";
    force_new_target_tesla_max_noise: f64 = 400.0, "game-data", "internal units", "FORCE_NEW_TARGET_TESLA_MAX_NOISE; Tesla forced score noise bound (hypothesis)";
    retarget_after_destroying_wall: bool = false, "game-data", "bool", "RETARGET_AFTER_DESTROYING_WALL; reselect building when wall falls (hypothesis)";
    selected_wall_time: f64 = 4000.0, "game-data", "milliseconds", "SELECTED_WALL_TIME; hold a selected live wall (hypothesis)";
    stick_to_targeted_building_when_forcing_retarget: bool = true, "game-data", "bool", "STICK_TO_TARGETED_BUILDING_WHEN_FORCING_RETARGET; preserve eligible original (hypothesis)";
    target_groups_radius: f64 = 500.0, "game-data", "internal units", "TargetGroupsRadius; seed-centred spatial cluster radius (hypothesis)";
    target_groups_min_weight: f64 = 2000.0, "game-data", "centi-weight", "TargetGroupsMinWeight; divide by 100 (hypothesis)";
    apprentice_target_groups_min_weight: f64 = 1000.0, "game-data", "centi-weight", "Apprentice TargetGroupsMinWeight (hypothesis)";
    group_weight_units_per_weight: f64 = 100.0, "assumed", "units/weight", "Conversion of TargetGroupsMinWeight to wiki Warden weights (hypothesis)";
    warden_waits_for_group_retargeting: bool = true, "game-data", "bool", "WARDEN_WAITS_FOR_GROUP_RETARGETING; wait while selected group has no target (hypothesis)";
}

trait ParameterValue: Sized {
    fn read(value: &Json, key: &str) -> Result<Self, String>;
}

impl ParameterValue for f64 {
    fn read(value: &Json, key: &str) -> Result<Self, String> {
        match value {
            Json::Num(number) if number.is_finite() && *number >= 0.0 => Ok(*number),
            _ => Err(format!(
                "parameter {key} requires a finite nonnegative number"
            )),
        }
    }
}

impl ParameterValue for bool {
    fn read(value: &Json, key: &str) -> Result<Self, String> {
        match value {
            Json::Bool(value) => Ok(*value),
            _ => Err(format!("parameter {key} requires a boolean")),
        }
    }
}

impl Params {
    /// Precedence: registry < catalog env < process file < job env < job params.
    pub fn resolve(catalog: &Catalog, env: &Json, job: &Json) -> Result<Self, String> {
        let mut params = Self::default();
        params.new_target_delays = catalog.new_target_delays.clone();
        params.poison_ramp = catalog.poison_ramp;
        params.warden_radius = catalog.warden_weights.at("vision_radius").f64();
        params.warden_min_weight = catalog.warden_weights.at("threshold").f64();
        params.healer_group_radius = catalog.unit("Healer").spec.splash;
        for key in ["pace", "pace_tap", "pace_switch", "pace_ability"] {
            if let Some(value) = env.get(key) {
                params.set(key, value)?;
            }
        }
        if let Some(value) = env.get("params") {
            params.apply(value)?;
        }
        if let Some(path) = std::env::var_os("BASELAB_PARAMS_FILE") {
            let text = std::fs::read_to_string(&path)
                .map_err(|error| format!("params file {path:?}: {error}"))?;
            params.apply(&crate::json::parse(&text).map_err(|error| error.to_string())?)?;
        }
        if let Some(env) = job.get("env") {
            for key in ["pace", "pace_tap", "pace_switch", "pace_ability"] {
                if let Some(value) = env.get(key) {
                    params.set(key, value)?;
                }
            }
            if let Some(value) = env.get("params") {
                params.apply(value)?;
            }
        }
        if let Some(value) = job.get("params") {
            params.apply(value)?;
        }
        Ok(params)
    }

    pub fn apply(&mut self, value: &Json) -> Result<(), String> {
        let Json::Obj(entries) = value else {
            return Err("params must be a JSON object".to_owned());
        };
        let mut candidate = self.clone();
        let mut seen = HashSet::new();
        for (key, value) in entries {
            if !seen.insert(key) {
                return Err(format!("duplicate engine parameter {key:?}"));
            }
            if let Some(name) = key.strip_prefix("new_target_delay.") {
                if !candidate.new_target_delays.contains_key(name) {
                    return Err(format!("unknown new-target delay unit {name:?}"));
                }
                candidate
                    .new_target_delays
                    .insert(name.to_owned(), f64::read(value, key)?);
            } else {
                candidate.set(key, value)?;
            }
        }
        for (key, value) in [
            ("internal_units_per_tile", candidate.internal_units_per_tile),
            ("poison_ramp", candidate.poison_ramp),
            ("healer_projectile_speed", candidate.healer_projectile_speed),
            (
                "group_weight_units_per_weight",
                candidate.group_weight_units_per_weight,
            ),
        ] {
            if value <= 0.0 {
                return Err(format!("parameter {key} must be positive"));
            }
        }
        if candidate.target_list_size < 1.0
            || candidate.target_list_size.fract() != 0.0
            || candidate.max_target_list_size < candidate.target_list_size
            || candidate.max_target_list_size.fract() != 0.0
            || candidate.max_target_list_size > 1024.0
        {
            return Err("target list sizes must be integers: 1 <= size <= max <= 1024".to_owned());
        }
        *self = candidate;
        Ok(())
    }
}
