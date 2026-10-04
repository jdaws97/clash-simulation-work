"""Inspect versioned statistics and report gaps instead of inventing values."""

from copy import deepcopy

from .common import InputError, integer, read_json


class Catalog:
    def __init__(self, catalog, secondary):
        self.snapshot = catalog
        self.records = {entry["entity"]["id"]: entry for entry in catalog["entries"]}
        if len(self.records) != len(catalog["entries"]):
            raise InputError("Duplicate catalog entity identifiers")
        self.secondary = {
            item["name"].casefold(): item
            for item in secondary["RAW_UNITS"] + secondary["RAW_SUPER_UNITS"]
            if item.get("village") == "home"
        }
        self.maximum_town_hall = max(
            row["level"] for row in self.entity("town-hall")["levels"]
        )

    @classmethod
    def load(cls, data_directory):
        return cls(
            read_json(data_directory / "catalog.json"),
            read_json(data_directory / "secondary-raw.json"),
        )

    def entity(self, entity_id):
        if entity_id not in self.records:
            raise InputError(f"Unknown catalog entity: {entity_id}")
        return self.records[entity_id]["entity"]

    def level(self, entity_id, level, supercharge=False):
        integer(level, f"{entity_id} level", 1)
        matches = [
            item
            for item in self.entity(entity_id).get("levels", [])
            if item["level"] == level
            and bool(item.get("supercharge", False)) == supercharge
        ]
        if len(matches) != 1:
            raise InputError(f"No unique data for {entity_id} level {level}")
        return matches[0]

    def town_hall_requirement(self, entity_id, level):
        entity = self.entity(entity_id)
        row = self.level(entity_id, level)
        if entity_id == "town-hall":
            requirement = level
        elif "townHallRequired" in row:
            requirement = row["townHallRequired"]
        elif "heroHallLevelRequired" in row:
            hall = self.level("hero-hall", row["heroHallLevelRequired"])
            requirement = hall["townHallRequired"]
        elif "blacksmithLevelRequired" in row:
            blacksmith_level = row["blacksmithLevelRequired"]
            if blacksmith_level == 0 and entity.get("unlockRequirement") == [
                "Available by default"
            ]:
                requirement = self.town_hall_requirement(entity["hero"], 1)
            else:
                smith = self.level("blacksmith", blacksmith_level)
                requirement = smith["townHallRequired"]
        elif entity.get("troopType") == "super":
            parent = entity["parentTroop"]
            requirement = self.town_hall_requirement(parent, level)
        else:
            raise InputError(f"Missing level-unlock relation for {entity_id}")
        if entity.get("troopType") == "super":
            parent = entity["parentTroop"]
            parent_unlock = self.town_hall_requirement(
                parent, entity["regularLevelRequired"]
            )
            requirement = max(requirement, parent_unlock)
        if entity.get("category") == "hero-equipment":
            requirement = max(
                requirement, self.town_hall_requirement(entity["hero"], 1)
            )
        reference = self.secondary.get(entity["name"].casefold())
        if reference and reference.get("unlock", {}).get("hall"):
            requirement = max(requirement, reference["unlock"]["hall"])
        return requirement

    def coverage(self):
        from .adapters import partial_adapter_status

        output = []
        for entity_id, entry in self.records.items():
            entity = entry["entity"]
            if entity["category"] not in {
                "troop",
                "spell",
                "hero",
                "hero-equipment",
                "pet",
                "siege-machine",
                "defense",
                "crafted-defense",
                "guardian",
                "trap",
                "town-hall",
            }:
                continue
            output.append(
                {
                    "id": entity_id,
                    "category": entity["category"],
                    "levels_present": len(entity.get("levels", [])),
                    "source": entry["source"],
                    "statistics_verification": entry["verification"],
                    "full_battle_adapter": "REQUIRES_IMPLEMENTATION_AND_REPLAY_VALIDATION",
                    "conditional_sector_adapter": partial_adapter_status(entity),
                }
            )
        return output

    def available(self, entity_id, level, town_hall):
        integer(town_hall, "Town Hall", 1, self.maximum_town_hall)
        if self.town_hall_requirement(entity_id, level) > town_hall:
            return False
        reference = self.secondary.get(self.entity(entity_id)["name"].casefold())
        caps = reference.get("levels", []) if reference else []
        if len(caps) >= town_hall:
            return 0 < level <= caps[town_hall - 1]
        return True

    def audit(self, claims):
        counts = {}
        findings = []
        for entity_id, entry in self.records.items():
            entity = entry["entity"]
            category = entity["category"]
            counts[category] = counts.get(category, 0) + 1
            reference = self.secondary.get(entity["name"].casefold())
            if not reference and category in {
                "troop",
                "spell",
                "hero",
                "hero-equipment",
            }:
                findings.append({"entity": entity_id, "kind": "no_secondary_record"})
            for row in entity.get("levels", []):
                if row.get("supercharge") or not reference:
                    continue
                dps = reference.get("dps", [])
                index = row["level"] - 1
                primary = row.get("damagePerSecond")
                if primary is None:
                    primary = row.get("stats", {}).get("normal", {}).get("dps")
                if primary is not None and index < len(dps) and primary != dps[index]:
                    findings.append(
                        {
                            "entity": entity_id,
                            "level": row["level"],
                            "kind": "dps_disagreement",
                            "primary": primary,
                            "secondary": dps[index],
                        }
                    )
            if category == "hero":
                caps = reference.get("levels", []) if reference else []
                if caps and max(row["level"] for row in entity["levels"]) > max(caps):
                    findings.append(
                        {"entity": entity_id, "kind": "hero_cap_disagreement"}
                    )
        for claim in claims:
            if claim.get("value") is None:
                findings.append(
                    {
                        "entity": claim["entity"],
                        "kind": "balance_review_required",
                        "source": claim["source"],
                        "detail": claim["detail"],
                    }
                )
                continue
            value = self.level(claim["entity"], claim["level"])
            for field in claim["path"]:
                value = value.get(field) if isinstance(value, dict) else None
            if value != claim["value"]:
                findings.append(
                    {
                        "entity": claim["entity"],
                        "level": claim["level"],
                        "kind": "official_balance_conflict",
                        "snapshot_value": value,
                        "announced_value": claim["value"],
                        "source": claim["source"],
                    }
                )
        return {
            "snapshot_commit": self.snapshot["snapshotCommit"],
            "entity_count": len(self.records),
            "category_counts": counts,
            "findings": findings,
            "battle_ready": False,
            "reason": "Statistics, mechanics, current patch, and personal levels require validation",
        }

    def inspect(self, entity_id, level=None):
        result = deepcopy(self.records[entity_id])
        if level is not None:
            result["entity"]["levels"] = [self.level(entity_id, level)]
        return result
