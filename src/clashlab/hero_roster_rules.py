"""Declared extended-hero mechanics on the advanced defense and pet kernel."""

from .advanced_defense_rules import RULES as ADVANCED_DEFENSE_RULES


RULESET = "spatial-extended-hero-roster-kernel-v27"
SCOPE = "extended_hero_roster_advanced_defenses_pets_siege_sector"
RULES = {
    **ADVANCED_DEFENSE_RULES,
    "extended_hero_activation": "one_common_manual_charge_and_recovery_per_hero",
    "hero_damage_attribution": "resolver_receipts_clipped_to_actual_hp_in_packet_order",
    "duke_isolation": "explicit_friendly_air_membership_exact_relative_motion_boundaries",
    "duke_revenge": "positive_actual_loss_from_live_hostile_source_shared_counter_clock",
    "duke_fire_heart": "deployed_self_healing_and_actual_death_after_lethal_interception",
    "king_spiky_ball": "finite_locked_bounces_with_explicit_geometry_and_release_policy",
    "king_gauntlet": "source_centered_instant_area_swing_and_incoming_damage_reduction",
    "king_stick_horse": "deployment_duration_then_complete_existing_wall_crossing",
    "prince_noble_iron": "finite_opening_main_weapon_launches_with_captured_boosts",
    "prince_metal_pants": "explicit_numeric_percentage_mapping_and_timed_protection",
    "prince_dark_orb": "moving_circle_first_contacts_and_independent_strongest_slow",
    "extended_hero_validation": "conditional_source_statistics_with_uncalibrated_behavior_parameters",
}
