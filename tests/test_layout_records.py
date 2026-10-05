import json
import unittest

from clashlab.layout_records import (
    decode_object_prefix,
    find_layout_objects,
    inspect_layout_value,
)


class LayoutRecordTests(unittest.TestCase):
    def test_torn_numeric_value_is_not_accepted(self):
        self.assertEqual(decode_object_prefix('{"x":1,"y":2'), {"x": 1})
        self.assertEqual(decode_object_prefix('{"x":1,"y":2,'), {"x": 1, "y": 2})

    def test_objects_need_whitelisted_identity_and_mark_partial_fields(self):
        source = b'{"data":1000001,"id":500000000,"lvl":15,"x":3,"y":43,"l4x":['
        found = find_layout_objects(source, {1000001})
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0]["object_complete"])
        self.assertNotIn("l4x", found[0]["fields"])
        self.assertEqual(find_layout_objects(source, {1000008}), [])

    def test_exports_only_whitelisted_numeric_fields(self):
        data = b'"buildings":[{"data":1000001,"x":2,"y":3,"lvl":15,"token":"secret","name":"private"}],"secret":"hidden"'
        result = inspect_layout_value(data, "buildings")
        self.assertEqual(
            result["retained_entries"], [{"data": 1000001, "x": 2, "y": 3, "lvl": 15}]
        )
        self.assertNotIn("secret", json.dumps(result))
        self.assertFalse(result["level_encoding_verified"])

    def test_rejects_stale_and_non_json_anchors(self):
        self.assertEqual(
            inspect_layout_value(b'"traps":[]', "buildings")["status"], "STALE_ANCHOR"
        )
        self.assertEqual(
            inspect_layout_value(b'"buildings"\x00', "buildings")["status"],
            "IDENTIFIER_WITHOUT_JSON_VALUE",
        )

    def test_does_not_export_incomplete_or_unrelated_records(self):
        self.assertEqual(
            inspect_layout_value(b'"buildings":[{"x":1', "buildings")["status"],
            "NO_COMPLETE_JSON_VALUE",
        )
        result = inspect_layout_value(
            b'"buildings":[{"x":true,"y":2,"id":1},{"token":"sensitive"}]', "buildings"
        )
        self.assertEqual(result["retained_entries"], [])
        self.assertEqual(result["status"], "NO_LAYOUT_RECORDS")

    def test_unknown_keys_cannot_be_used_as_arbitrary_memory_export(self):
        with self.assertRaises(ValueError):
            inspect_layout_value(b'"account":[]', "account")

    def test_partial_array_keeps_complete_objects_without_claiming_completeness(self):
        result = inspect_layout_value(
            b'"buildings":[{"data":1000001,"x":1,"y":2},{"data":',
            "buildings",
        )
        self.assertFalse(result["array_complete"])
        self.assertEqual(
            result["retained_entries"], [{"data": 1000001, "x": 1, "y": 2}]
        )


if __name__ == "__main__":
    unittest.main()
