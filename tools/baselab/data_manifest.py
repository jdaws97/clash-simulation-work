"""Fingerprint local simulator/scorer inputs without importing the battle engine.

Usage: python3 -B tools/baselab/data_manifest.py build|check

Build records a deterministic snapshot, not proof of regeneration. After actually
regenerating an artifact, use build --record-derived PATH (repeatable) to bind it
to its current inputs. Unchanged artifacts keep their previous input bindings.
Calibration writers may instead record provenance.input_hash using this module's
calibration_input_hash; result writers should record manifest_hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
PATTERNS = {
    "gamecsv": ("data/gamecsv/*/*.csv",),
    "clashking": (
        "data/clashking-static-data.json",
        "data/clashking-static-source.json",
    ),
    "balance_overrides": ("data/balance-overrides.json",),
    "registry": ("data/registry.json",),
    "wiki": ("data/wiki/text/*.txt", "data/wiki/tables/*.json"),
    "wiki_pages": ("data/wiki/pages/*.json",),
    "playbooks": ("data/playbooks/*.json",),
    "meta_armies": ("data/meta-armies-*.json", "data/custom-armies*.json"),
    # evaluate.py:26-37 also reads the undated and baselab calibration files.
    "calibration": ("data/meta-calibration*.json", "data/baselab-calibration*.json"),
    "runtime_data": (
        "data/attacker-policy*.json",
        "data/warden-weights.json",
        "data/mode-rules.json",
        "data/your-levels.json",
        "data/live/battles.jsonl",
        "data/reference-bases/*.json",
    ),
    "rust_catalog": ("rust/data/catalog.json",),
    "engine_code": (
        "src/baselab/engine/*.py",
        "src/baselab/pathing.py",
        "rust/src/*.rs",
    ),
    "scoring_code": ("src/baselab/*.py",),
    "builder_code": (
        "tools/baselab/wiki_tables.py",
        "tools/baselab/rust_export.py",
        "tools/baselab/calibrate.py",
        "tools/baselab/calibrate_meta.py",
    ),
}
REQUIRED = (
    "data/clashking-static-data.json",
    "data/balance-overrides.json",
    "data/registry.json",
    "rust/data/catalog.json",
    "src/baselab/pathing.py",
)


def digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_hash(manifest: dict) -> str:
    return digest({k: v for k, v in manifest.items() if k != "manifest_hash"})


def load_manifest(path: Path) -> dict:
    manifest = read_json(path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported manifest schema: {path}")
    if manifest.get("manifest_hash") != manifest_hash(manifest):
        raise ValueError(f"manifest hash does not match its contents: {path}")
    return manifest


def snapshot(root: Path, previous: dict | None = None, record_derived=()) -> dict:
    files = {}
    groups = {}
    sources = {}
    for group, patterns in PATTERNS.items():
        members = {}
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                if not path.is_file():
                    continue
                name = path.relative_to(root).as_posix()
                if group == "scoring_code" and name == "src/baselab/pathing.py":
                    continue
                entry = {"sha256": file_hash(path), "source_version": None}
                if group == "gamecsv":
                    entry["source_version"] = path.parent.name
                elif group in ("wiki", "wiki_pages"):
                    metadata_path = path
                    if path.suffix == ".txt":
                        metadata_path = (
                            root / "data/wiki/tables" / (path.stem + ".json")
                        )
                    metadata = (
                        read_json(metadata_path) if metadata_path.exists() else {}
                    )
                    entry["source_version"] = metadata.get("revid")
                elif group in ("meta_armies", "playbooks"):
                    metadata = read_json(path)
                    entry["source_version"] = metadata.get(
                        "version", metadata.get("date")
                    )
                    sources[name] = {
                        key: metadata[key]
                        for key in ("source", "sources")
                        if key in metadata
                    }
                elif group == "balance_overrides":
                    metadata = read_json(path)
                    entry["source_version"] = metadata["effective_date"]
                    sources[name] = {
                        key: metadata[key]
                        for key in ("description", "research", "effective_date")
                    }
                members[name] = entry
                files[name] = entry
        groups[group] = {"sha256": digest(members), "files": sorted(members)}

    source_path = root / "data/clashking-static-source.json"
    if source_path.exists():
        metadata = read_json(source_path)
        sources["clashking"] = {
            key: metadata[key]
            for key in (
                "repository",
                "commit",
                "committed_at_utc",
                "path",
                "url",
                "sha256",
            )
            if key in metadata
        }
        if "data/clashking-static-data.json" in files:
            files["data/clashking-static-data.json"]["source_version"] = metadata.get(
                "commit"
            )
        groups["clashking"]["sha256"] = digest(
            {name: files[name] for name in groups["clashking"]["files"]}
        )
    sources["csv_versions"] = sorted(
        {files[name]["source_version"] for name in groups["gamecsv"]["files"]}
    )

    def inputs(group_names=(), names=()):
        return digest(
            {
                "groups": {name: groups[name]["sha256"] for name in group_names},
                "files": {name: files.get(name) for name in names},
            }
        )

    registry_input = inputs(
        ("clashking", "wiki", "wiki_pages"),
        (
            "src/baselab/registry.py",
            "src/baselab/gamedata.py",
            "tools/baselab/wiki_tables.py",
        ),
    )
    catalog_input = inputs(
        ("registry", "balance_overrides", "engine_code", "gamecsv", "runtime_data"),
        (
            "src/baselab/mechanics.py",
            "src/baselab/gamedata.py",
            "tools/baselab/rust_export.py",
        ),
    )
    calibration_input = inputs(
        (
            "gamecsv",
            "clashking",
            "balance_overrides",
            "registry",
            "wiki",
            "engine_code",
            "scoring_code",
            "playbooks",
            "meta_armies",
            "runtime_data",
            "builder_code",
        )
    )
    derived_inputs = {
        "data/registry.json": registry_input,
        "rust/data/catalog.json": catalog_input,
    }
    for name in groups["calibration"]["files"]:
        derived_inputs[name] = calibration_input
    recorded = set(record_derived)
    unknown = recorded - derived_inputs.keys()
    if unknown:
        raise ValueError("not a derived artifact: " + ", ".join(sorted(unknown)))
    absent = recorded - files.keys()
    if absent:
        raise ValueError("cannot record missing artifact: " + ", ".join(sorted(absent)))
    derivations = {}
    for name, input_hash in sorted(derived_inputs.items()):
        if name not in files:
            continue
        old = (previous or {}).get("derivations", {}).get(name)
        provenance = read_json(root / name).get("provenance", {})
        embedded_input = (
            provenance.get("input_hash") if isinstance(provenance, dict) else None
        )
        # docs/GAP_ANALYSIS.md:152: a snapshot must not bless stale derived data.
        if name in recorded:
            binding = "recorded-regeneration"
        elif name in groups["calibration"]["files"] and embedded_input == input_hash:
            binding = "embedded-input-hash"
        elif old:
            derivations[name] = old
            continue
        else:
            binding = "unverified-snapshot"
        derivations[name] = {
            "sha256": files[name]["sha256"],
            "input_hash": input_hash,
            "binding": binding,
        }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "sha256",
        "files": dict(sorted(files.items())),
        "groups": groups,
        "sources": sources,
        "code_hash": groups["engine_code"]["sha256"],
        "registry_input_hash": registry_input,
        "rust_catalog_input_hash": catalog_input,
        "calibration_input_hash": calibration_input,
        "derivations": derivations,
    }
    manifest["manifest_hash"] = manifest_hash(manifest)
    return manifest


def recorded_manifest_hashes(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("manifest_hash", "data_manifest_hash") and isinstance(item, str):
                yield item
            elif key in ("manifest", "data_manifest") and isinstance(item, dict):
                for field in ("sha256", "hash"):
                    if isinstance(item.get(field), str):
                        yield item[field]
                yield from recorded_manifest_hashes(item)
            elif isinstance(item, (dict, list)):
                yield from recorded_manifest_hashes(item)
    elif isinstance(value, list):
        for item in value:
            yield from recorded_manifest_hashes(item)


def check(root: Path, saved: dict, current: dict) -> tuple[list[str], bool]:
    lines = [f"Manifest: {saved['manifest_hash']}"]
    bad = False
    old_files, files = saved["files"], current["files"]
    for name in sorted(old_files.keys() | files.keys()):
        if old_files.get(name) == files.get(name):
            continue
        if name not in old_files:
            state = "ADDED"
        elif name not in files:
            state = "REMOVED"
        else:
            state = "CHANGED"
        lines.append(f"{state}: {name}")
        bad = True
    if not bad:
        lines.append("No input content or source-version changes since the manifest.")
    missing = [name for name in REQUIRED if name not in files]
    for group in ("gamecsv", "wiki", "playbooks", "meta_armies", "engine_code"):
        if not current["groups"][group]["files"]:
            missing.append(f"{group} (no files)")
    for name in missing:
        lines.append(f"MISSING: {name}")
        bad = True

    source_hash = current["sources"].get("clashking", {}).get("sha256")
    if source_hash and source_hash != files.get(
        "data/clashking-static-data.json", {}
    ).get("sha256"):
        source_path = root / "data/clashking-static-data.json"
        normalized_hash = None
        if source_path.exists():
            normalized_hash = hashlib.sha256(
                source_path.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
        if normalized_hash == source_hash:
            lines.append(
                "SOURCE NOTE: ClashKing source hash matches after CRLF-to-LF "
                "normalization; the manifest retains its raw content hash"
            )
        else:
            lines.append(
                "SOURCE MISMATCH: ClashKing content differs from its source sidecar's sha256"
            )
            bad = True
    wiki_mismatches = []
    for name in current["groups"]["wiki_pages"]["files"]:
        revision = files[name]["source_version"]
        if revision is None:
            continue
        stem = Path(name).stem
        table = files.get(f"data/wiki/tables/{stem}.json")
        text = files.get(f"data/wiki/text/{stem}.txt")
        if not table or not text or table["source_version"] != revision:
            wiki_mismatches.append(stem)
    if wiki_mismatches:
        lines.append(
            f"STALE WIKI: {len(wiki_mismatches)} pages need wiki_tables.py: "
            + ", ".join(wiki_mismatches)
        )
        bad = True

    registry = (
        read_json(root / "data/registry.json") if "data/registry.json" in files else {}
    )
    catalog = (
        read_json(root / "rust/data/catalog.json")
        if "rust/data/catalog.json" in files
        else {}
    )
    revisions = {}
    for name in current["groups"]["wiki"]["files"]:
        if name.startswith("data/wiki/tables/"):
            page = read_json(root / name)
            revisions[page.get("source")] = page.get("revid")
    registry_mismatches = []
    for name, record in registry.items():
        source = record.get("source", {})
        url = source.get("wiki")
        if url and (url not in revisions or source.get("wiki_rev") != revisions[url]):
            registry_mismatches.append(name)

    registry_binding = current["derivations"].get("data/registry.json", {})
    registry_stale = bool(
        registry_mismatches
        or wiki_mismatches
        or registry_binding.get("input_hash") != current["registry_input_hash"]
        or registry_binding.get("sha256")
        != files.get("data/registry.json", {}).get("sha256")
    )

    for name, derivation in current["derivations"].items():
        if name == "data/registry.json":
            input_hash = current["registry_input_hash"]
        elif name == "rust/data/catalog.json":
            input_hash = current["rust_catalog_input_hash"]
        else:
            input_hash = current["calibration_input_hash"]
        reasons = []
        if input_hash != derivation["input_hash"]:
            reasons.append("upstream inputs changed since its recorded binding")
        if files[name]["sha256"] != derivation["sha256"]:
            reasons.append("artifact changed without a recorded regeneration")
        if name == "data/registry.json" and registry_mismatches:
            reasons.append(
                f"wiki revisions differ for {len(registry_mismatches)} entities"
            )
        if name == "rust/data/catalog.json":
            source_hashes = catalog.get("resolved", {}).get("source_hashes")
            if source_hashes is not None:
                # rust_export.py embeds the registry after applying overrides.
                expected = {
                    "registry": files.get("data/registry.json", {}).get("sha256"),
                    "balance_overrides": files.get(
                        "data/balance-overrides.json", {}
                    ).get("sha256"),
                }
                if source_hashes != expected:
                    reasons.append("embedded registry/balance source hashes differ")
            elif catalog.get("registry") != registry:
                reasons.append("embedded registry differs from data/registry.json")
        if name == "data/registry.json" and wiki_mismatches:
            reasons.append("parsed wiki text/tables lag mirrored revisions")
        if name != "data/registry.json" and registry_stale:
            reasons.append("registry or its sources are stale")
        provenance = read_json(root / name).get("provenance", {})
        embedded_input = (
            provenance.get("input_hash") if isinstance(provenance, dict) else None
        )
        if embedded_input and embedded_input != input_hash:
            reasons.append("embedded provenance.input_hash differs from current inputs")
        if reasons:
            lines.append(f"STALE: {name}: " + "; ".join(reasons))
            bad = True
        elif (
            derivation["binding"] == "recorded-regeneration"
            or embedded_input == input_hash
        ):
            lines.append(f"CURRENT: {name}: recorded input binding matches")
        else:
            lines.append(
                f"UNVERIFIED: {name}: legacy artifact has no regeneration/input-hash record"
            )

    references = unversioned = 0
    output = root / "output"
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.suffix not in (".json", ".jsonl"):
            continue
        try:
            with path.open(encoding="utf-8") as handle:
                raw = handle.read()
                has_reference = any(
                    key in raw
                    for key in (
                        "manifest_hash",
                        "data_manifest_hash",
                        '"manifest"',
                        '"data_manifest"',
                    )
                )
                if not has_reference:
                    if any(word in path.stem.lower() for word in ("winner", "best")):
                        unversioned += 1
                    continue
                values = (
                    (json.loads(line) for line in raw.splitlines() if line.strip())
                    if path.suffix == ".jsonl"
                    else (json.loads(raw),)
                )
                hashes = set()
                for value in values:
                    hashes.update(recorded_manifest_hashes(value))
        except (OSError, ValueError) as error:
            lines.append(f"UNREADABLE: {path.relative_to(root)}: {error}")
            bad = True
            continue
        if hashes:
            references += 1
            if hashes != {current["manifest_hash"]}:
                lines.append(
                    f"STALE RESULT: {path.relative_to(root)}: recorded manifest differs from current inputs"
                )
                bad = True
        elif any(word in path.stem.lower() for word in ("winner", "best")):
            unversioned += 1
    lines.append(
        f"Saved results: {references} with manifest hashes; {unversioned} winner/best files without provenance."
    )
    return lines, bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument(
        "--manifest", type=Path, help="default: <root>/data/manifest.json"
    )
    parser.add_argument(
        "--record-derived",
        action="append",
        default=[],
        metavar="PATH",
        help="build only: record an artifact just regenerated with current inputs",
    )
    args = parser.parse_args()
    if args.command == "check" and args.record_derived:
        parser.error("--record-derived is only valid with build")
    root = args.root.resolve()
    path = args.manifest or root / "data/manifest.json"
    try:
        previous = load_manifest(path) if path.exists() else None
        if args.command == "check" and previous is None:
            raise ValueError(f"missing manifest: {path}; run build first")
        recorded = []
        for name in args.record_derived:
            recorded.append((root / name).resolve().relative_to(root).as_posix())
        current = snapshot(root, previous, recorded)
        if args.command == "build":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(current, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(
                f"Wrote {path}: {current['manifest_hash']} ({len(current['files'])} inputs)"
            )
            return 0
        lines, bad = check(root, previous, current)
        print("\n".join(lines))
        return int(bad)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Manifest error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
