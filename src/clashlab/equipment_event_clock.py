"""Strict finite deadlines for the opt-in equipment/pet domain components."""

from .common import InputError, number


def advancing_deadline(start, duration, label):
    """Reject unrepresentable progress; never round a deadline to a nearby tick."""
    number(start, label + " start", 0)
    number(duration, label + " duration", 0)
    if duration == 0:
        raise InputError(label + " requires a strictly positive duration")
    deadline = number(start + duration, label + " deadline", 0)
    if deadline <= start:
        raise InputError(label + " deadline must strictly advance the finite clock")
    return deadline
