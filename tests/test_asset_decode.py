"""Independent format and corruption fixtures for the asset decoder."""

import lzma
import unittest
import zlib

from clashlab.asset_decode import (
    AssetDecodeError,
    decode_inner,
    decode_zip_payload,
    inspect_asset,
    parse_logic_csv,
)


TABLE = (
    b'"Name","Hitpoints","DamagePerSecond","HousingSpace"\r\n'
    b'"string","int","int","int"\r\n'
    b'"FixtureTroop","100","20","5"\r\n'
    b'"","120","25","5"\r\n'
)


def compressed_table(unknown_size=False):
    standard = lzma.compress(TABLE, format=lzma.FORMAT_ALONE, preset=0)
    size = b"\xff" * 4 if unknown_size else len(TABLE).to_bytes(4, "little")
    return standard[:5] + size + standard[13:]


def metadata(payload, member, method):
    return {
        "Flags": 0,
        "CompressionMethod": method,
        "CompressedSize": len(payload),
        "UncompressedSize": len(member),
        "DeclaredCrc32": f"{zlib.crc32(member):08X}",
    }


class AssetDecodeTests(unittest.TestCase):
    def test_short_header_is_restored_after_byte_nine(self):
        encoded = compressed_table()
        decoded, consumed = decode_inner(encoded, "supercell-lzma")
        self.assertEqual(decoded, TABLE)
        self.assertEqual(consumed, len(encoded))

    def test_unknown_size_has_bounded_end_of_stream(self):
        decoded, _ = decode_inner(compressed_table(True), "supercell-lzma")
        self.assertEqual(decoded, TABLE)

    def test_standard_lzma_is_not_confused_with_short_header(self):
        encoded = lzma.compress(TABLE, format=lzma.FORMAT_ALONE, preset=0)
        self.assertEqual(decode_inner(encoded, "lzma-alone")[0], TABLE)

    def test_truncated_stream_is_rejected(self):
        with self.assertRaises(AssetDecodeError):
            decode_inner(compressed_table()[:-8], "supercell-lzma")

    def test_trailing_memory_is_only_allowed_explicitly(self):
        encoded = compressed_table()
        with self.assertRaises(AssetDecodeError):
            decode_inner(encoded + b"unrelated", "supercell-lzma")
        decoded, consumed = decode_inner(
            encoded + b"unrelated", "supercell-lzma", allow_trailing=True
        )
        self.assertEqual(decoded, TABLE)
        self.assertEqual(consumed, len(encoded))

    def test_dictionary_limit_precedes_allocation(self):
        encoded = compressed_table()
        oversized = encoded[:1] + (1 << 30).to_bytes(4, "little") + encoded[5:]
        with self.assertRaisesRegex(AssetDecodeError, "dictionary"):
            decode_inner(oversized, "supercell-lzma")

    def test_declared_output_limit(self):
        with self.assertRaisesRegex(AssetDecodeError, "Declared output"):
            decode_inner(compressed_table(), "supercell-lzma", maximum=10)

    def test_unknown_output_limit(self):
        with self.assertRaisesRegex(AssetDecodeError, "output limit"):
            decode_inner(compressed_table(True), "supercell-lzma", maximum=10)

    def test_zip_deflate_crc_is_over_uncompressed_member(self):
        member = compressed_table()
        encoder = zlib.compressobj(wbits=-15)
        payload = encoder.compress(member) + encoder.flush()
        report = inspect_asset(
            payload, "supercell-lzma", metadata(payload, member, method=8)
        )
        self.assertTrue(report["zip_crc_verified"])
        self.assertFalse(report["current_game_version_verified"])

    def test_stored_zip_member(self):
        self.assertEqual(decode_zip_payload(TABLE, metadata(TABLE, TABLE, 0)), TABLE)

    def test_bad_crc_does_not_become_a_decoded_asset(self):
        info = metadata(TABLE, TABLE, 0)
        info["DeclaredCrc32"] = "00000000"
        with self.assertRaisesRegex(AssetDecodeError, "CRC-32"):
            decode_zip_payload(TABLE, info)

    def test_zip_size_mismatch(self):
        info = metadata(TABLE, TABLE, 0)
        info["CompressedSize"] += 1
        with self.assertRaises(AssetDecodeError):
            decode_zip_payload(TABLE, info)

    def test_zip_encryption_is_not_silently_ignored(self):
        info = metadata(TABLE, TABLE, 0)
        info["Flags"] = 1
        with self.assertRaisesRegex(AssetDecodeError, "Encrypted"):
            decode_zip_payload(TABLE, info)

    def test_continuation_rows_preserve_raw_name_and_no_level_guess(self):
        table = parse_logic_csv(TABLE)
        continuation = table["rows"][1]
        self.assertEqual(continuation["entity_name"], "FixtureTroop")
        self.assertEqual(continuation["values"]["Name"], "")
        self.assertEqual(continuation["continuation_index"], 1)
        self.assertNotIn("level", continuation)

    def test_strings_and_field_names_alone_are_not_tables(self):
        for candidate in [
            b"Name,Hitpoints,DamagePerSecond\nFoo,100,20\n",
            b"prefix\0Name,Hitpoints,DamagePerSecond",
            TABLE.replace(b'"int"', b'"invalid"', 1),
            TABLE.replace(b'"FixtureTroop"', b'""'),
            TABLE.replace(b'"100","20","5"', b'"100","20"'),
        ]:
            with self.subTest(candidate=candidate):
                with self.assertRaises(AssetDecodeError):
                    parse_logic_csv(candidate)


if __name__ == "__main__":
    unittest.main()
