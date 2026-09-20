import json
import unittest

from backend.app.building_register_inspector import _coerce_payload


class BuildingRegisterInspectorTest(unittest.TestCase):
    def test_detail_use_is_preserved(self):
        result = _coerce_payload(
            json.dumps({"violation_status": "absent", "main_use": "공동주택", "detail_use": "다세대주택"}),
            page_count=1,
        )

        self.assertEqual(result["main_use"], "공동주택")
        self.assertEqual(result["detail_use"], "다세대주택")


if __name__ == "__main__":
    unittest.main()
