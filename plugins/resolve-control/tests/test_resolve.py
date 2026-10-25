"""Native SDK test doubles only: does not claim a real Resolve integration pass."""
from pathlib import Path
import sys
import time
import types
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import native
import operations as op
import worker


class Clip:
    def GetUniqueId(self): return "clip-1"
    def GetMediaId(self): return "media-1"
    def GetName(self): return "Clip"
    def GetClipProperty(self): return {"File Path": "D:/shot.mov", "FPS": "24"}
    def GetStart(self): return 0
    def GetEnd(self): return 24
    def GetDuration(self): return 24


class Folder:
    def __init__(self, key="root", name="Root"):
        self.key, self.name, self.children = key, name, []
    def GetUniqueId(self): return self.key
    def GetName(self): return self.name
    def GetClipList(self): return [Clip()]
    def GetSubFolderList(self): return self.children


class Timeline:
    def __init__(self): self.markers = {}
    def GetUniqueId(self): return "timeline-1"
    def GetName(self): return "Main"
    def GetTrackCount(self, kind): return 1 if kind == "video" else 0
    def GetTrackName(self, kind, index): return "Video 1"
    def GetItemListInTrack(self, kind, index): return [Clip()]
    def GetStartFrame(self): return 86400
    def GetEndFrame(self): return 86424
    def GetSetting(self): return {"timelineFrameRate": "24"}
    def GetMarkers(self): return self.markers
    def AddMarker(self, frame, color, name, note, duration):
        self.markers[frame] = {"color": color, "name": name, "note": note, "duration": duration}
        return True


class Project:
    def __init__(self):
        self.key, self.root, self.timeline, self.writes, self.rendering = "project-1", Folder(), Timeline(), [], False
    def GetUniqueId(self): return self.key
    def GetName(self): return "Example"
    def GetMediaPool(self): return self
    def GetRootFolder(self): return self.root
    def GetTimelineCount(self): return 1
    def GetTimelineByIndex(self, index): return self.timeline
    def GetCurrentTimeline(self): return self.timeline
    def GetSetting(self): return {"timelineFrameRate": "24"}
    def GetRenderJobList(self): return []
    def GetRenderPresetList(self): return [{"Name": "H264"}]
    def GetCurrentRenderFormatAndCodec(self): return {"format": "mp4", "codec": "H264"}
    def GetCurrentRenderMode(self): return 1
    def IsRenderingInProgress(self): return self.rendering
    def AddSubFolder(self, parent, name):
        item = Folder("new-1", name); parent.children.append(item); self.writes.append(name); return item
    def SetRenderSettings(self, settings): self.writes.append(settings); return True
    def SetCurrentTimeline(self, selected): self.writes.append("select"); return True
    def SetCurrentFolder(self, selected): self.writes.append("bin"); return True
    def ImportMedia(self, paths): self.writes.append(paths); return [Clip()]
    def CreateEmptyTimeline(self, name): self.writes.append(name); return self.timeline
    def CreateTimelineFromClips(self, name, clips): self.writes.append(name); return self.timeline
    def MoveClips(self, clips, destination): self.writes.append("move"); return True


class Resolve:
    def __init__(self): self.current = Project()
    def GetVersion(self): return [21, 0, 0, 1, ""]
    def GetVersionString(self): return "21.0.0.1"
    def GetProductName(self): return "DaVinci Resolve Studio"
    def GetProjectManager(self): return self
    def GetCurrentProject(self): return self.current
    def GetCurrentPage(self): return "edit"
    def GetProjectListInCurrentFolder(self): return ["Example"]
    def CreateProject(self, name): self.current = Project(); return self.current
    def LoadProject(self, name): self.current = Project(); return self.current
    def SaveProject(self): self.current.writes.append("save"); return True


class OperationTests(unittest.TestCase):
    def setUp(self): self.resolve, self.check = Resolve(), Mock()
    def run_op(self, operation, **arguments):
        return op.dispatch(self.resolve, {"operation": operation, "arguments": {"project_id": "project-1", **arguments}}, self.check)
    def test_project_and_media_read_does_not_write(self):
        self.assertEqual(self.run_op("project_info")["project"]["id"], "project-1")
        self.assertEqual(self.run_op("media_info")["clips"][0]["properties"]["File Path"], "D:/shot.mov")
        self.assertEqual(self.resolve.current.writes, [])
    def test_no_current_project_can_be_reported_without_opening_one(self):
        self.resolve.current = None
        self.assertIsNone(self.run_op("project_info")["project"])
        with self.assertRaisesRegex(ValueError, "Open the intended"):
            self.run_op("media_info")
    def test_stale_project_refused_before_write(self):
        self.resolve.current.key = "another"
        with self.assertRaisesRegex(ValueError, "changed"):
            self.run_op("create_bin", folder_id="root", name="New", confirmed=True)
        self.assertEqual(self.resolve.current.writes, [])
    def test_timeline_read_and_deleted_timeline_rejected(self):
        self.assertEqual(self.run_op("timeline_info", timeline_id="timeline-1")["tracks"][0]["clips"][0]["duration"], 24)
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.run_op("timeline_info", timeline_id="missing")
    def test_query_limit_marks_incomplete(self):
        self.resolve.current.timeline.GetItemListInTrack = lambda *a: [Clip()] * 1001
        report = self.run_op("timeline_info", timeline_id="timeline-1")
        self.assertTrue(report["truncated"])
        self.assertEqual(len(report["tracks"][0]["clips"]), 1000)
    def test_bin_preview_then_create_and_no_duplicate(self):
        self.assertFalse(self.run_op("create_bin", folder_id="root", name="New", confirmed=False)["applied"])
        self.assertEqual(self.resolve.current.writes, [])
        self.assertTrue(self.run_op("create_bin", folder_id="root", name="New", confirmed=True)["applied"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_op("create_bin", folder_id="root", name="New", confirmed=True)
    def test_confirmation_not_truthy_string(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.run_op("create_bin", folder_id="root", name="New", confirmed="true")
    def test_closed_session_at_last_guard_never_writes(self):
        self.check.side_effect = ValueError("closed target")
        with self.assertRaisesRegex(ValueError, "closed target"):
            self.run_op("create_bin", folder_id="root", name="New", confirmed=True)
        self.assertEqual(self.resolve.current.writes, [])
    def test_project_changed_during_preflight_never_writes(self):
        self.check.side_effect = lambda: setattr(self.resolve.current, "key", "changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.run_op("create_bin", folder_id="root", name="New", confirmed=True)
        self.assertEqual(self.resolve.current.writes, [])
    def test_render_busy_rejects_write(self):
        self.resolve.current.rendering = True
        with self.assertRaisesRegex(ValueError, "rendering"):
            self.run_op("create_bin", folder_id="root", name="New", confirmed=True)
        self.assertEqual(self.resolve.current.writes, [])
    def test_markers_relative_frame_and_no_overwrite(self):
        args = dict(timeline_id="timeline-1", frame=12, duration=1, name="Check", note="Review", color="Blue", confirmed=True)
        self.assertTrue(self.run_op("add_marker", **args)["applied"])
        self.assertIn(12, self.resolve.current.timeline.markers)
        with self.assertRaisesRegex(ValueError, "exists"):
            self.run_op("add_marker", **args)
    def test_render_query_never_renders_and_settings_only(self):
        self.assertFalse(self.run_op("render_info")["rendering"])
        self.assertTrue(self.run_op("set_render_settings", settings={"CustomName": "shot"}, confirmed=True)["applied"])
        with self.assertRaisesRegex(ValueError, "documented"):
            self.run_op("set_render_settings", settings={"StartRendering": True}, confirmed=True)
    def test_python_preview_does_not_execute(self):
        self.assertFalse(self.run_op("execute_python", code="raise AssertionError('executed')", confirmed=False)["applied"])
        data = self.run_op("execute_python", code="print('hello'); result = project.GetName()", confirmed=True)
        self.assertEqual(data["result"]["result"], "Example")
        self.assertEqual(data["result"]["output"], "hello\n")
    def test_missing_sdk_method_explicitly_errors(self):
        self.resolve.current.GetSetting = None
        with self.assertRaisesRegex(ValueError, "does not expose"):
            self.run_op("project_info")
    def test_none_list_is_not_reported_as_complete_empty(self):
        self.resolve.current.root.GetClipList = lambda: None
        with self.assertRaisesRegex(ValueError, "unavailable data"):
            self.run_op("media_info")
    def test_project_create_open_never_closes_existing_project(self):
        for operation, name in (("create_project", "New"), ("open_project", "Example")):
            with self.assertRaisesRegex(ValueError, "already open"):
                self.run_op(operation, name=name, confirmed=True)
        self.assertEqual(self.resolve.current.writes, [])
    def test_project_creation_preview_and_no_implicit_save(self):
        self.resolve.current = None
        self.assertFalse(self.run_op("create_project", name="New", confirmed=False)["applied"])
        self.assertIsNone(self.resolve.current)
        self.assertTrue(self.run_op("create_project", name="New", confirmed=True)["applied"])
        self.assertEqual(self.resolve.current.writes, [])
    def test_project_open_only_exact_existing_name(self):
        self.resolve.current = None
        with self.assertRaisesRegex(ValueError, "missing"):
            self.run_op("open_project", name="Examp", confirmed=True)
        self.assertTrue(self.run_op("open_project", name="Example", confirmed=True)["applied"])
    def test_project_open_race_rejected(self):
        self.resolve.current = None
        self.check.side_effect = lambda: setattr(self.resolve, "current", Project())
        with self.assertRaisesRegex(ValueError, "opened during"):
            self.run_op("open_project", name="Example", confirmed=True)
    def test_save_and_activate_explicit_project_timeline(self):
        self.assertFalse(self.run_op("save_project", confirmed=False)["applied"])
        self.assertTrue(self.run_op("save_project", confirmed=True)["applied"])
        self.assertTrue(self.run_op("select_timeline", timeline_id="timeline-1", confirmed=True)["applied"])
        self.assertEqual(self.resolve.current.writes, ["save", "select"])
    def test_media_import_preview_and_destination(self):
        scratch = Path(__file__).resolve().parents[1] / ".test-runtime"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            media = Path(temp) / "clip.mov"; media.write_bytes(b"test")
            args = {"paths": [str(media)], "folder_id": "root"}
            self.assertFalse(self.run_op("import_media", confirmed=False, **args)["applied"])
            self.assertEqual(self.resolve.current.writes, [])
            self.assertTrue(self.run_op("import_media", confirmed=True, **args)["applied"])
            self.assertEqual(media.read_bytes(), b"test")
        with self.assertRaisesRegex(ValueError, "explicit"):
            self.run_op("import_media", folder_id="root", paths=["relative.mov"], confirmed=True)
    def test_timeline_create_empty_or_from_ordered_clips(self):
        for ids in ([], ["media-1"]):
            self.assertTrue(self.run_op("create_timeline", folder_id="root", name="New", media_ids=ids, confirmed=True)["applied"])
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.run_op("create_timeline", folder_id="root", name="Other", media_ids=["deleted"], confirmed=True)
    def test_move_media_does_not_move_disk_files(self):
        self.resolve.current.root.children.append(Folder("destination", "Destination"))
        self.assertTrue(self.run_op("move_media", folder_id="root", destination_folder_id="destination", media_ids=["media-1"], confirmed=True)["applied"])
        self.assertEqual(self.resolve.current.writes, ["move"])
    def test_missing_media_distinguishes_pattern_from_literal(self):
        clip = Clip(); clip.GetClipProperty=lambda:{"File Path":"D:/shot.%04d.exr"}
        self.resolve.current.root.GetClipList=lambda:[clip]
        self.assertEqual(self.run_op("missing_media")["items"][0]["status"], "unresolved")


class RoutingTests(unittest.TestCase):
    def setUp(self): self.row = {"pid": 22, "started": 123.0, "session_id": "22:123.000000", "status": "available", "executable": "C:/Resolve/Resolve.exe"}
    def test_zero_or_multiple_instances_never_choose(self):
        for rows in ([], [self.row, {**self.row, "pid": 23}]):
            with self.assertRaises(ValueError): native.select(rows, self.row["session_id"])
    def test_restarted_same_pid_is_not_selected(self):
        with self.assertRaises(ValueError): native.select([self.row], "22:122.000000")
    def test_unreadable_process_is_not_omitted(self):
        proc = Mock(pid=22, info={"name":"Resolve.exe"})
        proc.exe.side_effect = native.psutil.AccessDenied(22)
        with patch.object(native.sys, "platform", "win32"), patch.object(native.psutil, "process_iter", return_value=[proc]):
            self.assertEqual(native.discover()[0]["status"], "unavailable")
    def test_multiple_processes_marked_unrouteable(self):
        one = Mock(pid=22, info={"name":"Resolve.exe"}); one.exe.return_value="C:/Resolve/Resolve.exe"; one.create_time.return_value=123
        two = Mock(pid=23, info={"name":"Resolve.exe"}); two.exe.return_value="C:/Resolve/Resolve.exe"; two.create_time.return_value=124
        with patch.object(native.sys, "platform", "win32"), patch.object(native.psutil, "process_iter", return_value=[one, two]):
            self.assertEqual([r["status"] for r in native.discover()], ["unrouteable", "unrouteable"])
    def test_worker_rechecks_after_sdk_connection(self):
        request = {"operation":"project_info", "session_id":self.row["session_id"], "expires_at":time.time()+10}
        with patch.object(worker, "discover", side_effect=[[self.row], []]), patch.object(worker, "connect", return_value=Resolve()):
            self.assertFalse(worker.run(request)["ok"])
    def test_expired_worker_never_connects(self):
        with patch.object(worker, "connect") as connect:
            result=worker.run({"operation":"project_info", "session_id":self.row["session_id"], "expires_at":0})
            self.assertFalse(result["ok"]); connect.assert_not_called()
    def test_unsupported_version_never_dispatches(self):
        resolve=Resolve(); resolve.GetVersion=lambda:[20,3]
        with patch.object(worker,"discover",return_value=[self.row]), patch.object(worker,"connect",return_value=resolve), patch.object(worker,"dispatch") as dispatch:
            self.assertFalse(worker.run({"operation":"project_info","session_id":self.row["session_id"],"expires_at":time.time()+10})["ok"])
            dispatch.assert_not_called()


if __name__ == "__main__": unittest.main()
