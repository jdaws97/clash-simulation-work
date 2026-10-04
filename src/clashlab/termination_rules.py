"""Opt-in whole-battle force exhaustion with explicit inventory hypotheses."""

from .hero_roster_rules import RULES as HERO_ROSTER_RULES


RULESET = "spatial-battle-exhaustion-kernel-v28"
SCOPE = "battle_exhaustion_extended_hero_roster_defenses_pets_siege_sector"
RULES = {
    **HERO_ROSTER_RULES,
    "battle_termination_boundary": "observe_after_complete_same_time_health_and_lifecycle_settlement",
    "battle_termination_priority": "all_counted_destruction_then_selected_force_exhaustion_then_time_limit",
    "battle_force_exhaustion": "opt_in_source_declared_inventory_and_runtime_continuation_hypothesis",
    "battle_generated_reserves": "controlled_generated_actors_require_their_own_lifecycle_provider",
    "battle_spell_reserves": "explicit_per_origin_entity_level_classification_never_inferred_from_name",
    "battle_resource_receipts": "historical_deployment_and_cast_receipts_clipped_to_actual_terminal_boundary",
}
