"""Separate Titan aura and Druid healing/form lifecycles over v29 spells."""

from .attack_spell_rules import RULES as ATTACK_SPELL_RULES


RULESET = "spatial-troop-lifecycles-kernel-v30"
SCOPE = "troop_lifecycles_attack_spells_battle_exhaustion_sector"
RULES = {
    **ATTACK_SPELL_RULES,
    "electro_titan_aura": "independent_catalog_pulse_clock_live_layer_and_geometry_membership",
    "electro_titan_aura_policies": "explicit_source_freeze_visibility_buff_and_stacking_hypotheses",
    "druid_healing_chain": "live_selected_air_ground_hops_with_shared_recipient_stacking",
    "druid_healing_contact": "exact_relative_path_range_contact_for_moving_allies",
    "druid_transformation": "one_way_timeout_or_actual_hp_death_into_separately_owned_bear",
    "druid_bear_statistics": "complete_explicit_uncalibrated_inputs_required_no_saved_catalog_child",
    "druid_bear_emergence": "same_position_blocked_release_stays_pending_and_keeps_battle_alive",
    "druid_generated_resources": "bear_is_owned_generated_form_never_independent_army_inventory",
}
