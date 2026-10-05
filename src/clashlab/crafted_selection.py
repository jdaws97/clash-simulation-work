"""One explicit seasonal Station; permanent unlock data remains unchanged."""

from copy import deepcopy
from datetime import date

from .common import InputError, integer, require


SEASON_SOURCE = (
    "https://supercell.com/en/games/clashofclans/blog/news/the-awesome-quest-is-here/"
)
SEASON_POLICY = "official_august_2026_phase4_th11_plus_not_current_date_certified"
VARIANTS = {"cake-a-pult", "hero-hunter", "hot-candle"}
ROTATION_POLICY = "explicit_phase4_selection_not_current_date_certified"
SELECTION_FIELDS = (
    "variant",
    "phase",
    "as_of_date",
    "rotation_policy",
    "module_levels",
    "availability_policy",
)


def selection_projection(parameters):
    return {
        key: deepcopy(parameters[key]) for key in SELECTION_FIELDS if key in parameters
    }


def validate_availability(selection, town_hall):
    """The official season exception proves TH access, not October rotation."""
    integer(town_hall, "crafted Town Hall", 11, 18)
    if not isinstance(selection, dict):
        raise InputError("Crafted selection must be explicit")
    if (
        selection.get("variant") not in VARIANTS
        or selection.get("phase") != 4
        or selection.get("rotation_policy") != ROTATION_POLICY
    ):
        raise InputError("Historical or unknown crafted rotation is unavailable")
    policy = selection.get("availability_policy")
    if policy is None and town_hall == 18:
        return None  # Historical reviewed inputs already had permanent access.
    if policy != SEASON_POLICY:
        raise InputError(
            "Seasonal Station requires the explicit TH11+ availability policy"
        )
    try:
        observed = date.fromisoformat(require(selection, "as_of_date"))
    except (TypeError, ValueError) as error:
        raise InputError("Crafted observation date must be an ISO date") from error
    if observed < date(2026, 8, 1):
        raise InputError("Crafted season selection predates its August 1 opening")
    return {
        "policy": policy,
        "source": SEASON_SOURCE,
        "source_publication_date": "2026-07-31",
        "season_start_date": "2026-08-01",
        "minimum_town_hall": 11,
        "selected_town_hall": town_hall,
        "current_date_rotation_verified": False,
    }


def selected_modules(selection, town_hall, catalog, secondary_station=None):
    validate_availability(selection, town_hall)
    entity = catalog.entity(selection["variant"])
    if entity["craftingPhase"] != 4 or entity["category"] != "crafted-defense":
        raise InputError("Selected source is not phase-4 crafted content")
    secondary_station = (
        catalog.crafting_station_source()
        if secondary_station is None
        else secondary_station
    )
    if secondary_station.get("_id") != catalog.entity("crafting-station")["dataId"]:
        raise InputError("Crafting secondary source identity mismatch")
    secondary = [
        item
        for item in require(secondary_station, "seasonal_defenses")
        if item["_id"] == entity["dataId"]
    ]
    if len(secondary) != 1:
        raise InputError("Secondary extraction lacks a unique selected crafted variant")
    levels = require(selection, "module_levels")
    if not isinstance(levels, dict) or set(levels) != {
        m["name"] for m in entity["modules"]
    }:
        raise InputError(
            "Independent crafted module levels require their complete explicit contract"
        )
    values, rows = {}, []
    for module in entity["modules"]:
        level = integer(levels[module["name"]], "crafted module level", 1, 10)
        selected = [r for r in module["upgrades"] if r["level"] == level]
        raw_modules = [
            m for m in secondary[0]["modules"] if m["_id"] == module["dataId"]
        ]
        if len(selected) != 1 or len(raw_modules) != 1:
            raise InputError("Crafted module source mapping is not unique")
        raw_rows = [r for r in raw_modules[0]["levels"] if r["level"] == level]
        if len(raw_rows) != 1 or raw_rows[0]["required_townhall"] > town_hall:
            raise InputError(
                "Selected crafted module is unavailable at declared Town Hall"
            )
        values[module["name"]] = selected[0]["stat"]
        rows.append(deepcopy(raw_rows[0]))
    return entity, values, rows


def layout_selection(building, town_hall, catalog):
    """Validate the selected physical Station before geometry/inventory checks."""
    settings = building.get("settings", {})
    selected = settings.get("crafted") if isinstance(settings, dict) else None
    if selected is None:
        if building.get("mode") == "normal":
            raise InputError(
                "Normal-mode Station requires an explicit crafted selection"
            )
        return None
    if (
        set(settings) != {"crafted"}
        or not isinstance(selected, dict)
        or set(selected)
        not in (set(SELECTION_FIELDS), set(SELECTION_FIELDS) - {"availability_policy"})
        or building.get("level") != 1
        or building.get("mode") != "normal"
        or building.get("counts_for_destruction") is not True
    ):
        raise InputError("Crafted layout requires one counted level-1 normal Station")
    entity, _, _ = selected_modules(selected, town_hall, catalog)
    if entity["size"] != catalog.entity("crafting-station")["size"]:
        raise InputError("Crafted weapon and physical Station footprints disagree")
    return validate_availability(selected, town_hall)
