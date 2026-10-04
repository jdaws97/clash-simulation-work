"""Bounded, read-only decoding of extracted Clash logic-asset candidates.

This module does not identify the active game version or modify a catalog.
ZIP's checksum covers the ZIP-uncompressed member, before inner asset decoding.
Supercell's short LZMA header stores five property bytes and a four-byte size;
the standard LZMA-alone header uses an eight-byte size instead.
"""

import argparse
import csv
import hashlib
import io
import json
import lzma
import zlib
from pathlib import Path


MAX_OUTPUT = 16 * 1024 * 1024
MAX_DICTIONARY = 8 * 1024 * 1024
MEMORY_LIMIT = 32 * 1024 * 1024
STAT_FIELDS = {"Hitpoints", "HitPoints", "DamagePerSecond", "HousingSpace", "Speed"}
KNOWN_TYPES = {"string", "int", "bool", "float"}


class AssetDecodeError(ValueError):
    """The candidate cannot be accepted within the declared format and limits."""


def _bounded_lzma(data, maximum):
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=MEMORY_LIMIT)
    try:
        output = decoder.decompress(data, max_length=maximum + 1)
    except lzma.LZMAError as error:
        raise AssetDecodeError(f"Invalid LZMA stream: {error}") from error
    if len(output) > maximum:
        raise AssetDecodeError("Decoded asset exceeds the output limit")
    if not decoder.eof:
        raise AssetDecodeError(
            "Incomplete LZMA stream; do not treat a prefix as a table"
        )
    return output, len(data) - len(decoder.unused_data)


def decode_inner(data, encoding, maximum=MAX_OUTPUT, allow_trailing=False):
    """Return decoded bytes and the exact number of encoded bytes consumed."""
    if not 0 < maximum <= MAX_OUTPUT:
        raise AssetDecodeError("Output limit is outside the supported bound")
    if encoding == "plain-csv":
        if len(data) > maximum:
            raise AssetDecodeError("Plain CSV exceeds the output limit")
        return data, len(data)
    if encoding not in {"supercell-lzma", "lzma-alone"}:
        raise AssetDecodeError("Unknown encoding; signatures do not prove a codec")
    minimum = 9 if encoding == "supercell-lzma" else 13
    if len(data) < minimum:
        raise AssetDecodeError("Truncated LZMA header")
    dictionary_size = int.from_bytes(data[1:5], "little")
    if dictionary_size > MAX_DICTIONARY:
        raise AssetDecodeError("LZMA dictionary exceeds the memory bound")
    if data[0] >= 225:
        raise AssetDecodeError("Invalid LZMA property byte")
    size_width = 4 if encoding == "supercell-lzma" else 8
    declared_size = int.from_bytes(data[5 : 5 + size_width], "little")
    unknown_size = declared_size == (1 << (8 * size_width)) - 1
    if not unknown_size and declared_size > maximum:
        raise AssetDecodeError("Declared output exceeds the output limit")
    wrapped = data
    if encoding == "supercell-lzma":
        extension = b"\xff" * 4 if unknown_size else b"\0" * 4
        wrapped = data[:9] + extension + data[9:]
    try:
        output, consumed = _bounded_lzma(wrapped, maximum)
    except AssetDecodeError:
        if unknown_size:
            raise
        # Some producers emit an end marker as well as a declared length.
        # Decode that variant with an unknown-size header, then independently
        # enforce the original length below. A complete end marker is required.
        end_marked = wrapped[:5] + b"\xff" * 8 + wrapped[13:]
        output, consumed = _bounded_lzma(end_marked, maximum)
    if encoding == "supercell-lzma":
        consumed -= 4
    if not unknown_size and len(output) != declared_size:
        raise AssetDecodeError("Decoded length disagrees with the header")
    if not allow_trailing and consumed != len(data):
        raise AssetDecodeError("Unexpected bytes after the complete LZMA stream")
    return output, consumed


def decode_zip_payload(payload, metadata):
    """Validate one extracted ZIP member, including its uncompressed CRC-32."""
    flags = metadata["Flags"]
    method = metadata["CompressionMethod"]
    compressed_size = metadata["CompressedSize"]
    uncompressed_size = metadata["UncompressedSize"]
    if flags & (1 | 64):
        raise AssetDecodeError("Encrypted ZIP members are not supported")
    if not 0 <= compressed_size <= MAX_OUTPUT:
        raise AssetDecodeError("ZIP input size exceeds the bound")
    if not 0 <= uncompressed_size <= MAX_OUTPUT:
        raise AssetDecodeError("ZIP output size exceeds the bound")
    if len(payload) != compressed_size:
        raise AssetDecodeError("ZIP payload length disagrees with metadata")
    if method == 0:
        member = payload
    elif method == 8:
        decoder = zlib.decompressobj(-15)
        try:
            member = decoder.decompress(payload, uncompressed_size + 1)
        except zlib.error as error:
            raise AssetDecodeError(f"Invalid raw DEFLATE stream: {error}") from error
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise AssetDecodeError("Incomplete, oversized, or trailing ZIP data")
    else:
        raise AssetDecodeError(f"Unsupported ZIP compression method: {method}")
    if len(member) != uncompressed_size:
        raise AssetDecodeError("ZIP member length disagrees with metadata")
    expected_crc = int(metadata["DeclaredCrc32"], 16)
    if zlib.crc32(member) != expected_crc:
        raise AssetDecodeError("ZIP-uncompressed member CRC-32 mismatch")
    return member


def parse_logic_csv(data):
    """Preserve column types, blank continuation names, and unparsed raw values.

    A continuation row is associated with its preceding name for inspection,
    but is never automatically relabeled as a numeric in-game troop level.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AssetDecodeError("Logic table is not UTF-8") from error
    if "\0" in text:
        raise AssetDecodeError("Binary NUL in a purported CSV table")
    try:
        parsed = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        raise AssetDecodeError(f"Invalid CSV structure: {error}") from error
    parsed = [row for row in parsed if row]
    if len(parsed) < 3:
        raise AssetDecodeError("Need a header, a type row, and data")
    fields, types = parsed[:2]
    if len(fields) != len(set(fields)) or "Name" not in fields:
        raise AssetDecodeError("Expected unique field names and a Name column")
    if len(STAT_FIELDS.intersection(fields)) < 2:
        raise AssetDecodeError("Insufficient stat columns to identify a logic table")
    if len(types) != len(fields) or not all(item in KNOWN_TYPES for item in types):
        raise AssetDecodeError("Missing or invalid typed CSV schema")
    name_index = fields.index("Name")
    if types[name_index] != "string":
        raise AssetDecodeError("Name must have the string type")
    current_name = None
    continuation_index = 0
    rows = []
    for row_number, values in enumerate(parsed[2:], start=3):
        if len(values) != len(fields):
            raise AssetDecodeError(f"CSV row {row_number} has the wrong column count")
        raw_name = values[name_index]
        if raw_name:
            current_name = raw_name
            continuation_index = 0
        else:
            continuation_index += 1
        if current_name is None:
            raise AssetDecodeError("Continuation row has no preceding named entity")
        rows.append(
            {
                "csv_row": row_number,
                "entity_name": current_name,
                "continuation_index": continuation_index,
                "values": dict(zip(fields, values)),
            }
        )
    return {"fields": fields, "types": dict(zip(fields, types)), "rows": rows}


def inspect_asset(payload, encoding, zip_metadata=None, allow_trailing=False):
    member = decode_zip_payload(payload, zip_metadata) if zip_metadata else payload
    decoded, consumed = decode_inner(member, encoding, allow_trailing=allow_trailing)
    table = parse_logic_csv(decoded)
    return {
        "status": "DECODED_TABLE_REQUIRES_VERSION_AND_SEMANTIC_VALIDATION",
        "encoding": encoding,
        "zip_crc_verified": zip_metadata is not None,
        "encoded_bytes_consumed": consumed,
        "decoded_bytes": len(decoded),
        "encoded_sha256": hashlib.sha256(member[:consumed]).hexdigest(),
        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
        "current_game_version_verified": False,
        "live_battle_state_verified": False,
        "catalog_modified": False,
        "table": table,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--encoding",
        required=True,
        choices=["plain-csv", "supercell-lzma", "lzma-alone"],
    )
    parser.add_argument("--zip-metadata", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path to preserve evidence")
    if args.payload.stat().st_size > MAX_OUTPUT:
        parser.error("Input file exceeds the bounded asset size")
    metadata = None
    if args.zip_metadata:
        metadata = json.loads(args.zip_metadata.read_text(encoding="utf-8-sig"))
    try:
        report = inspect_asset(args.payload.read_bytes(), args.encoding, metadata)
    except AssetDecodeError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(
        f"Decoded {len(report['table']['rows'])} rows; game version remains unverified."
    )


if __name__ == "__main__":
    main()
