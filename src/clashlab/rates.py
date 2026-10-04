"""Compose independently tracked movement and attack-rate effects."""


def attack_rate(actor):
    return (
        actor.get("_hazard_attack_rate", 1)
        * actor.get("_hit_status_attack_rate", 1)
        * actor.get("_hero_attack_rate", 1)
    )


def movement_speed(actor):
    return (
        (
            actor["speed"]
            + actor.get("_buff_movement_bonus", 0)
            + actor.get("_guardian_self_movement_bonus", 0)
            + actor.get("_guardian_field_movement_bonus", 0)
            + actor.get("_hero_movement_bonus", 0)
        )
        * actor.get("_hazard_movement_multiplier", 1)
        * actor.get("_hit_status_movement_multiplier", 1)
    )


def attack_resume_time(actor, time):
    """Attack work resumes after the union of Freeze and displacement pauses."""
    return max(
        time,
        actor["frozen_until"],
        actor.get("_displacement_pause_until", 0),
    )


def pause_attack_work(actor, time, pause_until):
    """Add only newly paused time; the caller updates its separate status clock."""
    extension = max(pause_until - attack_resume_time(actor, time), 0)
    for clock in ("next_attack", "_wall_next_attack"):
        if clock in actor:
            actor[clock] = max(actor[clock], time) + extension


def rescale_remaining_cooldown(actor, time, old_rate, new_rate):
    """Scale unfinished attack work without scaling any existing pause time."""
    resume_at = attack_resume_time(actor, time)
    for clock in ("next_attack", "_wall_next_attack"):
        if clock in actor:
            remaining = max(actor[clock] - resume_at, 0)
            actor[clock] = resume_at + remaining * old_rate / new_rate
