import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import discovery


class SceneDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.metadata = [{"pid": 123, "maya_version": "2027", "token": "private-one"},
                         {"pid": 456, "maya_version": "2027", "token": "private-two"}]
        self.scenes = {123: {"ok": True, "data": {"path": "D:/characters/hero.ma", "maya_version": "2027", "modified": True}},
                       456: {"ok": True, "data": {"path": "D:/sets/room.mb", "maya_version": "2027", "modified": False}}}
        self.snapshot = patch.object(discovery, "sessions", return_value=self.metadata)
        self.request = patch.object(discovery, "request", side_effect=lambda operation, pid, timeout: self.scenes[pid])
        self.snapshot.start()
        self.calls = self.request.start()
        self.addCleanup(self.snapshot.stop)
        self.addCleanup(self.request.stop)

    def test_readable_rows_and_only_bounded_read_only_pid_requests(self):
        result = discovery.discover_sessions()
        self.assertEqual(result["selection"]["status"], "unspecified")
        self.assertIsNone(result["selection"]["selected_pid"])
        self.assertEqual([row["scene_name"] for row in result["data"]], ["hero.ma", "room.mb"])
        self.assertTrue(result["data"][0]["modified"])
        self.assertIn("已修改", result["data"][0]["display_label"])
        self.assertIn("D:/sets/room.mb", result["data"][1]["display_label"])
        self.assertEqual({call.kwargs["pid"] for call in self.calls.call_args_list}, {123, 456})
        for call in self.calls.call_args_list:
            self.assertEqual(call.args, ("scene_info",))
            self.assertEqual(call.kwargs["timeout"], 2)
        text = json.dumps(result)
        for metadata in self.metadata:
            self.assertNotIn(metadata["token"], text)

    def test_exact_filename_stem_and_fullpath_select_case_insensitively(self):
        for query in ("HERO.MA", "hero", "d:\\characters\\.\\HERO.ma"):
            with self.subTest(query=query):
                selection = discovery.discover_sessions(query)["selection"]
                self.assertEqual(selection["status"], "unique")
                self.assertEqual(selection["selected_pid"], 123)
        self.assertEqual(discovery.discover_sessions("ROOM")["selection"]["selected_pid"], 456)

    def test_full_path_never_falls_back_to_basename_and_partial_never_selects(self):
        for query in ("D:/other/hero.ma", "characters/hero.ma", "her", "*.ma"):
            selection = discovery.discover_sessions(query)["selection"]
            self.assertEqual(selection["status"], "not_found", query)
            self.assertIsNone(selection["selected_pid"])

    def test_duplicate_filename_requires_choice_but_exact_path_disambiguates(self):
        self.scenes[456]["data"]["path"] = "D:/archive/hero.ma"
        selection = discovery.discover_sessions("hero.ma")["selection"]
        self.assertEqual(selection["status"], "ambiguous")
        self.assertEqual(selection["matching_pids"], [123, 456])
        self.assertIsNone(selection["selected_pid"])
        self.assertEqual(discovery.discover_sessions("D:/archive/hero.ma")["selection"]["selected_pid"], 456)
        # Same scene open twice is still ambiguous, even with a full path.
        self.scenes[456]["data"]["path"] = "D:/characters/hero.ma"
        self.assertEqual(discovery.discover_sessions("D:/characters/hero.ma")["selection"]["status"], "ambiguous")

    def test_duplicate_stem_different_extensions_does_not_auto_select(self):
        self.scenes[456]["data"]["path"] = "D:/archive/hero.mb"
        self.assertEqual(discovery.discover_sessions("hero")["selection"]["status"], "ambiguous")
        self.assertEqual(discovery.discover_sessions("hero.mb")["selection"]["selected_pid"], 456)

    def test_dotted_stem_matches_but_filename_stem_collision_is_ambiguous(self):
        self.scenes[123]["data"]["path"] = "D:/characters/hero.v002.ma"
        self.assertEqual(discovery.discover_sessions("HERO.v002")["selection"]["selected_pid"], 123)
        self.scenes[456]["data"]["path"] = "D:/archive/hero.v002.ma.mb"
        result = discovery.discover_sessions("hero.v002.ma")
        self.assertEqual(result["selection"]["status"], "ambiguous")
        self.assertIsNone(result["selection"]["selected_pid"])

    def test_unsaved_scene_is_displayed_and_never_treated_as_filename(self):
        self.scenes[123]["data"]["path"] = ""
        self.scenes[456]["data"]["path"] = ""
        result = discovery.discover_sessions("未保存场景")
        self.assertEqual(result["selection"]["status"], "not_found")
        self.assertEqual([row["scene_name"] for row in result["data"]], ["未保存场景", "未保存场景"])
        self.assertNotEqual(result["data"][0]["display_label"], result["data"][1]["display_label"])

    def test_unavailable_or_invalid_scene_prevents_auto_selection(self):
        for unavailable in ({"ok": False, "error": {"code": "connection_error", "detail": "private-two"}},
                            {"ok": True, "data": {}}, {"ok": True, "data": {"path": None}}):
            self.scenes[456] = unavailable
            result = discovery.discover_sessions("hero.ma")
            self.assertEqual(result["selection"]["status"], "incomplete")
            self.assertEqual(result["selection"]["matching_pids"], [123])
            self.assertIsNone(result["selection"]["selected_pid"])
            self.assertEqual(result["data"][1]["status"], "unavailable")
            self.assertNotIn("private-two", json.dumps(result))

    def test_no_sessions_never_selects_and_makes_no_requests(self):
        self.metadata.clear()
        result = discovery.discover_sessions("hero.ma")
        self.assertEqual(result["data"], [])
        self.assertEqual(result["selection"]["status"], "not_found")
        self.calls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
