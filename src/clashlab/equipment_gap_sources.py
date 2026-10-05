"""Pinned evidence used by the remaining equipment/pet domain components.

These components are not an admission shortcut into full_battle. The integration
owner must bind their events to paid identities, clocks and shared modifiers.
"""

from copy import deepcopy
from hashlib import sha256

from .common import InputError, integer, read_json
from .hero_extensions import require_fields


EXTRACTION_SHA256 = "ff2b72ec8a71b403d247b061c5d0edb0c59dfe0dbea8f199f3451de2ece26cb8"
EXTRACTION_URL = (
    "https://raw.githubusercontent.com/ClashKingInc/ClashKingAssets/"
    "b8f42a707fe92d5293d46088bf536450ae422e7b/assets/static_data.json"
)
MONOLITH_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/release-notes/"
    "the-anime-fury-update-is-here/"
)
ROCKET_BALANCE_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/news/state-of-gameplay-part-2/"
)


def selected_row(catalog, entity, level, town_hall):
    integer(level, "equipment/pet level", 1)
    integer(town_hall, "equipment/pet Town Hall", 1)
    if not catalog.available(entity, level, town_hall):
        raise InputError("Equipment/pet unavailable at the selected Town Hall")
    return deepcopy(catalog.level(entity, level))


def extracted_equipment(catalog, name, level):
    directory = getattr(catalog, "source_data_directory", None)
    if directory is None:
        raise InputError("Equipment requires the pinned existing extraction")
    path = directory / "clashking-static-data.json"
    if (
        sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        != EXTRACTION_SHA256
    ):
        raise InputError("Equipment extraction differs from pinned source bytes")
    matches = [item for item in read_json(path)["equipment"] if item["name"] == name]
    if len(matches) != 1:
        raise InputError("Equipment extraction identity is not unique")
    rows = [row for row in matches[0]["levels"] if row["level"] == level]
    if len(rows) != 1:
        raise InputError("Equipment extraction level is not unique")
    return deepcopy(rows[0])


def explicit_policy(parameters, policies, numeric_fields=()):
    """No omitted branch or automatic experimental opt-in."""
    from .common import identifier

    require_fields(parameters, {"source", *policies, *numeric_fields}, "Domain policy")
    identifier(parameters["source"], "domain behavior evidence")
    if any(parameters[key] != value for key, value in policies.items()):
        raise InputError("Equipment/pet policy requires explicit experimental opt-in")
