"""Compose acquisition-only concealment without changing actor collision."""


def untargetable_until(actor):
    return max(
        actor.get("_untargetable_until", 0),
        actor.get("_spell_tower_untargetable_until", 0),
        actor.get("_attack_spell_untargetable_until", 0),
    )
