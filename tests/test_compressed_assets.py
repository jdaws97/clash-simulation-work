"""Exercise scanner boundaries and rejection paths without opening processes."""

import lzma
import unittest

from clashlab.compressed_assets import CHUNK_BYTES, plausible_headers, scan


TABLE = b"Name,Hitpoints,HousingSpace\nstring,int,int\nBarbarian,100,1\nArcher,90,1\n"


def encoded_table():
    stream = lzma.compress(TABLE, format=lzma.FORMAT_ALONE, preset=0)
    return stream[:5] + len(TABLE).to_bytes(4, "little") + stream[13:]


class FakeMemoryReader:
    def __init__(self, content, unstable=False):
        self.content = content
        self.unstable = unstable
        self.reads = {}

    def regions(self):
        return [(4096, len(self.content))]

    def read(self, address, size):
        key = (address, size)
        self.reads[key] = self.reads.get(key, 0) + 1
        start = address - 4096
        result = self.content[start : start + size]
        if self.unstable and self.reads[key] > 1:
            result = result[:-1] + bytes([result[-1] ^ 0xFF])
        return result


class CompressedAssetScanTests(unittest.TestCase):
    def test_candidate_header_split_across_chunks_is_found(self):
        content = b"\0" * (CHUNK_BYTES - 4) + encoded_table()
        result = scan(FakeMemoryReader(content), CHUNK_BYTES * 3, 20)
        self.assertEqual(len(result["tables"]), 1)
        self.assertEqual(
            result["tables"][0]["table"]["rows"][0]["entity_name"], "Barbarian"
        )
        self.assertFalse(result["raw_memory_saved"])

    def test_total_read_budget_includes_candidate_probes(self):
        content = b"\0" * (CHUNK_BYTES - 4) + encoded_table()
        limit = CHUNK_BYTES + 16
        result = scan(FakeMemoryReader(content), limit, 20)
        total = result["bytes_attempted"] + result["probe_bytes_attempted"]
        self.assertLessEqual(total, limit)
        self.assertTrue(result["budget_reached"])

    def test_false_signatures_do_not_become_tables(self):
        content = bytes.fromhex("5d0000040000100000") + b"invalid" * 100
        result = scan(FakeMemoryReader(content), CHUNK_BYTES, 20)
        self.assertEqual(result["tables"], [])
        self.assertEqual(result["candidate_headers"], 1)

    def test_partial_last_chunk_is_not_reported_as_a_completed_region(self):
        content = b"\0" * (CHUNK_BYTES + 100)
        result = scan(FakeMemoryReader(content), CHUNK_BYTES + 16, 20)
        self.assertTrue(result["budget_reached"])
        self.assertEqual(result["regions_completed"], 0)

    def test_invalid_size_or_dictionary_is_rejected_before_probe(self):
        content = bytes.fromhex("5d0000004000100000")
        self.assertEqual(list(plausible_headers(content)), [])

    def test_identical_decoded_tables_are_deduplicated(self):
        content = encoded_table() + b"\0" * 100 + encoded_table()
        result = scan(FakeMemoryReader(content), CHUNK_BYTES, 20)
        self.assertEqual(len(result["tables"]), 1)
        self.assertEqual(result["candidate_headers"], 2)

    def test_changed_asset_is_rejected(self):
        content = b"\0" * 20 + encoded_table()
        result = scan(FakeMemoryReader(content, unstable=True), CHUNK_BYTES, 20)
        self.assertEqual(result["tables"], [])
        self.assertEqual(result["rejection_counts"]["asset_changed_between_reads"], 1)


if __name__ == "__main__":
    unittest.main()
