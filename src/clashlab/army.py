"""Enumerate legal experimental armies under explicit account constraints."""

from itertools import product

from .common import InputError, integer, require, stable_id


def _owned_level(account, entity_id, level, catalog):
    level = integer(level, f"{entity_id} level", 1)
    owned = require(account, "levels").get(entity_id)
    if owned is None:
        raise InputError(f"Account level is unknown: {entity_id}")
    owned = integer(owned, f"owned {entity_id} level", 0)
    if level > owned or not catalog.available(entity_id, level, account["town_hall"]):
        raise InputError(f"Unavailable owned level: {entity_id} {level}")


def _housing(items, category, account, catalog, donated=False):
    total = 0
    seen = set()
    for item in items:
        entity_id = item["id"]
        if entity_id in seen:
            raise InputError(f"Duplicate army item: {entity_id}")
        seen.add(entity_id)
        entity = catalog.entity(entity_id)
        if entity["category"] != category:
            raise InputError(f"Wrong category for {entity_id}")
        count = integer(item["count"], f"{entity_id} count", 1)
        level = integer(item["level"], f"{entity_id} level", 1)
        catalog.level(entity_id, level)
        if donated:
            cap = require(account, "donation_levels").get(entity_id)
            if cap is None or level > cap:
                raise InputError(f"Donation availability is unconfirmed: {entity_id}")
            integer(cap, "donation level cap", 1)
        else:
            _owned_level(account, entity_id, level, catalog)
        total += count * integer(entity["housingSpace"], "housing space", 1)
    return total


def validate_army(army, account, catalog):
    town_hall = integer(
        require(account, "town_hall"), "Town Hall", 1, catalog.maximum_town_hall
    )
    capacities = require(account, "capacities")
    used = {
        "army_housing": _housing(army["troops"], "troop", account, catalog),
        "spell_housing": _housing(army["spells"], "spell", account, catalog),
        "clan_castle_troops": _housing(
            army["clan_castle"]["troops"], "troop", account, catalog, donated=True
        ),
        "clan_castle_spells": _housing(
            army["clan_castle"]["spells"], "spell", account, catalog, donated=True
        ),
    }
    for name, value in used.items():
        if value > integer(require(capacities, name), name, 0):
            raise InputError(f"{name} overflow: {value} > {capacities[name]}")
    heroes = army["heroes"]
    if len(heroes) > integer(require(capacities, "hero_slots"), "hero slots", 0):
        raise InputError("Too many deployed heroes")
    hero_ids = set()
    pet_ids = set()
    availability = require(account, "hero_availability")
    for hero in heroes:
        hero_id = hero["id"]
        if hero_id in hero_ids or catalog.entity(hero_id)["category"] != "hero":
            raise InputError(f"Invalid or duplicate hero: {hero_id}")
        hero_ids.add(hero_id)
        if availability.get(hero_id) is not True:
            raise InputError(f"Hero availability is unconfirmed: {hero_id}")
        _owned_level(account, hero_id, hero["level"], catalog)
        if require(hero, "mode") not in {"ground", "air"}:
            raise InputError("Hero mode must be ground or air")
        if (
            hero_id in {"barbarian-king", "archer-queen", "royal-champion"}
            and hero["mode"] != "ground"
        ):
            raise InputError(f"{hero_id} must use ground mode")
        if hero_id in {"minion-prince", "dragon-duke"} and hero["mode"] != "air":
            raise InputError(f"{hero_id} must use air mode")
        equipment = hero["equipment"]
        if len(equipment) != 2 or len({item["id"] for item in equipment}) != 2:
            raise InputError("Each selected hero needs two distinct equipment items")
        for item in equipment:
            definition = catalog.entity(item["id"])
            if (
                definition["category"] != "hero-equipment"
                or definition["hero"] != hero_id
            ):
                raise InputError(f"Equipment {item['id']} does not belong to {hero_id}")
            _owned_level(account, item["id"], item["level"], catalog)
        if "pet" not in hero:
            raise InputError("Each hero must explicitly select a pet or null")
        pet = hero["pet"]
        if pet:
            if pet["id"] in pet_ids or catalog.entity(pet["id"])["category"] != "pet":
                raise InputError("A pet cannot accompany two heroes")
            pet_ids.add(pet["id"])
            _owned_level(account, pet["id"], pet["level"], catalog)
    siege = army["siege"]
    if siege:
        integer(require(siege, "level"), "siege level", 1)
        if (
            integer(require(capacities, "siege_deployments"), "siege deployments", 0)
            < 1
        ):
            raise InputError("Siege deployment is unavailable")
        if catalog.entity(siege["id"])["category"] != "siege-machine":
            raise InputError("Selected siege is not a siege machine")
        if siege["origin"] == "own":
            _owned_level(account, siege["id"], siege["level"], catalog)
        elif siege["origin"] == "donated":
            cap = require(account, "donation_levels").get(siege["id"])
            if cap is None or siege["level"] > cap:
                raise InputError("Siege donation availability is unconfirmed")
            catalog.level(siege["id"], siege["level"])
        else:
            raise InputError("Siege origin must be own or donated")
    super_ids = {
        item["id"]
        for item in army["troops"]
        if catalog.entity(item["id"]).get("troopType") == "super"
    }
    if super_ids:
        if len(super_ids) > integer(
            require(capacities, "max_active_super_troops"), "super troop limit", 0
        ):
            raise InputError("Too many active super troop types")
        active = set(require(account, "active_super_troops"))
        if not super_ids <= active:
            raise InputError("Selected super troops have not been confirmed active")
    return {
        "town_hall": town_hall,
        "used": used,
        "id": stable_id(army),
        "status": "LEGAL_UNDER_ENTERED_ACCOUNT_AND_CATALOG_SNAPSHOT",
    }


def enumerate_counts(pool, capacity, catalog, category, exact_fill):
    integer(capacity, "capacity", 0)
    if len({item["id"] for item in pool}) != len(pool):
        raise InputError("Candidate pool has duplicate items")
    for item in pool:
        integer(item["minimum"], "minimum count", 0)
        integer(item["maximum"], "maximum count", item["minimum"])
        if catalog.entity(item["id"])["category"] != category:
            raise InputError("Candidate pool category mismatch")

    def visit(index, remaining, chosen):
        if index == len(pool):
            if remaining == 0 or not exact_fill:
                yield list(chosen)
            return
        item = pool[index]
        housing = catalog.entity(item["id"])["housingSpace"]
        maximum = min(item["maximum"], remaining // housing)
        for count in range(item["minimum"], maximum + 1):
            if count:
                chosen.append(
                    {"id": item["id"], "level": item["level"], "count": count}
                )
            yield from visit(index + 1, remaining - count * housing, chosen)
            if count:
                chosen.pop()

    yield from visit(0, capacity, [])


def generate_armies(specification, account, catalog):
    capacities = require(account, "capacities")
    limit = integer(require(specification, "maximum_candidates"), "candidate limit", 1)
    exact = require(specification, "exact_fill")
    if not isinstance(exact, bool):
        raise InputError("exact_fill must be explicit true or false")
    troop_options = enumerate_counts(
        require(specification, "troop_pool"),
        require(capacities, "army_housing"),
        catalog,
        "troop",
        exact,
    )
    spell_pool = require(specification, "spell_pool")
    loadout_options = require(specification, "loadout_options")
    castle_options = require(specification, "clan_castle_options")
    if not loadout_options or not castle_options:
        raise InputError("Loadout and Clan Castle options must be nonempty")
    generated = []
    rejected = []
    for troops in troop_options:
        spell_options = enumerate_counts(
            spell_pool, capacities["spell_housing"], catalog, "spell", exact
        )
        for spells in spell_options:
            for loadout, castle in product(loadout_options, castle_options):
                army = {
                    "troops": troops,
                    "spells": spells,
                    "heroes": loadout["heroes"],
                    "siege": loadout["siege"],
                    "clan_castle": castle,
                }
                try:
                    validation = validate_army(army, account, catalog)
                except InputError as error:
                    rejected.append({"id": stable_id(army), "reason": str(error)})
                else:
                    generated.append(
                        {"id": validation["id"], "army": army, "validation": validation}
                    )
                if len(generated) + len(rejected) >= limit:
                    return {
                        "candidates": generated,
                        "rejected": rejected,
                        "search_complete": False,
                        "ranked": False,
                    }
    return {
        "candidates": generated,
        "rejected": rejected,
        "search_complete": True,
        "ranked": False,
    }
