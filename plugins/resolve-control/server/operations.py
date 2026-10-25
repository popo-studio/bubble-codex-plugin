"""Documented Resolve API operations. No implicit project switches or rendering."""
import contextlib
import io
import json
from pathlib import Path
import re

MAX_ROWS = 1000
MUTATIONS = {"create_project", "open_project", "save_project", "import_media", "create_timeline", "select_timeline", "move_media", "create_bin", "add_marker", "set_render_settings", "execute_python"}


def invoke(obj, method, *args):
    fn = getattr(obj, method, None)
    if not callable(fn):
        raise ValueError("Installed Resolve SDK does not expose " + method + "; update or consult its Help > Documentation > Developer > Scripting README")
    return fn(*args)


def identity(obj):
    value = invoke(obj, "GetUniqueId")
    if not isinstance(value, str) or not value:
        raise ValueError("SDK did not provide a stable unique ID")
    return value


def project(resolve, expected=None):
    current = invoke(invoke(resolve, "GetProjectManager"), "GetCurrentProject")
    if current is None:
        raise ValueError("Open the intended project in Resolve first; no project was loaded automatically")
    if expected is not None and identity(current) != expected:
        raise ValueError("Active project changed; inspect and select the project again before continuing")
    return current


def summary(item):
    return {"id": identity(item), "name": invoke(item, "GetName")}


def rows(value):
    if value is None:
        raise ValueError("SDK returned unavailable data; cannot report an empty complete result")
    if not isinstance(value, (list, tuple)):
        raise ValueError("Unexpected SDK list result")
    return list(value)


def bounded(value):
    value = rows(value)
    return {"items": value[:MAX_ROWS], "truncated": len(value) > MAX_ROWS}


def timelines(current):
    count = invoke(current, "GetTimelineCount")
    if type(count) is not int or not 0 <= count <= MAX_ROWS:
        raise ValueError("Timeline count exceeds supported bounded query; narrow the project")
    return [invoke(current, "GetTimelineByIndex", i) for i in range(1, count + 1)]


def timeline(current, selected):
    if not selected:
        raise ValueError("An explicit timeline_id from project_info is required")
    matches = [item for item in timelines(current) if identity(item) == selected]
    if len(matches) != 1:
        raise ValueError("Selected timeline no longer exists or is ambiguous")
    return matches[0]


def folder(current, selected):
    root = invoke(invoke(current, "GetMediaPool"), "GetRootFolder")
    if selected is None:
        return root
    queue, visited = [root], set()
    while queue:
        item = queue.pop(0)
        key = identity(item)
        if key in visited:
            continue
        visited.add(key)
        if len(visited) > MAX_ROWS:
            raise ValueError("Folder lookup exceeded 1000 folders; no mutation was performed")
        if key == selected:
            return item
        queue.extend(rows(invoke(item, "GetSubFolderList")))
    raise ValueError("Selected media folder no longer exists")


class Output(io.StringIO):
    def write(self, text):
        super().write(text[:max(0, 65536 - self.tell())])
        return len(text)


def dispatch(resolve, request, recheck):
    operation = request["operation"]
    args = request.get("arguments", {})
    if operation in {"create_project", "open_project"}:
        manager = invoke(resolve, "GetProjectManager")
        if invoke(manager, "GetCurrentProject") is not None:
            raise ValueError("A project is already open. Save and close it yourself first; the API cannot safely infer unsaved state and this tool never closes projects.")
        name = args.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 255 or type(args.get("confirmed")) is not bool:
            raise ValueError("Provide a nonempty project name under 256 characters and boolean confirmed")
        existing = rows(invoke(manager, "GetProjectListInCurrentFolder"))
        if (operation == "open_project") != (name in existing):
            raise ValueError("Project is missing for open or already exists for create; names must match exactly in the current library folder")
        if not args["confirmed"]:
            return {"applied": False, "requires_confirmation": True, "operation": operation, "name": name}
        recheck()
        if invoke(manager, "GetCurrentProject") is not None:
            raise ValueError("A project was opened during preview; no switch was performed")
        result = invoke(manager, "CreateProject" if operation == "create_project" else "LoadProject", name)
        if result is None:
            raise RuntimeError("Resolve did not return the requested project; inspect state before retrying")
        return {"applied": True, "project": summary(result)}
    if operation == "project_info":
        manager = invoke(resolve, "GetProjectManager")
        current = invoke(manager, "GetCurrentProject")
        data = {"version": invoke(resolve, "GetVersionString"), "product": invoke(resolve, "GetProductName"), "page": invoke(resolve, "GetCurrentPage"), "project": None,
                "projects_in_current_library_folder": bounded(invoke(manager, "GetProjectListInCurrentFolder"))}
        if current is not None:
            active = invoke(current, "GetCurrentTimeline")
            data.update(project=summary(current), timelines=[summary(t) for t in timelines(current)], current_timeline=summary(active) if active else None,
                        settings=invoke(current, "GetSetting"))
        return data
    expected = args.get("project_id")
    if not isinstance(expected, str) or not expected:
        raise ValueError("An explicit project_id from project_info is required")
    current = project(resolve, expected)
    if operation in {"media_info", "missing_media"}:
        selected = folder(current, args.get("folder_id"))
        clips = rows(invoke(selected, "GetClipList"))
        children = rows(invoke(selected, "GetSubFolderList"))
        if operation == "missing_media":
            results = []
            for clip in clips[:MAX_ROWS]:
                properties = invoke(clip, "GetClipProperty")
                path = properties.get("File Path", "") if isinstance(properties, dict) else ""
                status = "unresolved"
                if isinstance(path, str) and path and Path(path).is_absolute() and not re.search(r"%|#|\[[0-9]+-[0-9]+\]|<[^>]+>", path):
                    status = "exists" if Path(path).is_file() else "missing"
                results.append({"id": invoke(clip, "GetMediaId"), "name": invoke(clip, "GetName"), "path": path, "status": status})
            return {"items": results, "truncated": len(clips) > MAX_ROWS, "coverage": "Only literal absolute media file paths in this bin. Image sequences, generated clips, empty/relative paths and placeholders remain unresolved; offline/proxy/remote media completeness is not inferred."}
        return {"project": summary(current), "folder": summary(selected), "folders": [summary(f) for f in children[:MAX_ROWS]],
                "clips": [{"id": invoke(c, "GetMediaId"), "name": invoke(c, "GetName"), "properties": invoke(c, "GetClipProperty")} for c in clips[:MAX_ROWS]],
                "truncated": len(clips) > MAX_ROWS or len(children) > MAX_ROWS,
                "coverage": "Only the selected bin; file paths/properties are reported by Resolve, not a complete missing-media or filesystem audit."}
    if operation == "timeline_info":
        selected = timeline(current, args.get("timeline_id"))
        tracks, remaining, truncated = [], MAX_ROWS, False
        for kind in ("video", "audio", "subtitle"):
            count = invoke(selected, "GetTrackCount", kind)
            if type(count) is not int or not 0 <= count <= MAX_ROWS:
                raise ValueError("Unsupported track count")
            for index in range(1, count + 1):
                clips = rows(invoke(selected, "GetItemListInTrack", kind, index))
                take = clips[:remaining]
                tracks.append({"type": kind, "index": index, "name": invoke(selected, "GetTrackName", kind, index),
                               "clips": [{**summary(c), "start": invoke(c, "GetStart"), "end": invoke(c, "GetEnd"), "duration": invoke(c, "GetDuration")} for c in take]})
                remaining -= len(take)
                truncated |= len(take) < len(clips)
                if remaining == 0:
                    truncated = True
                    break
            if remaining == 0:
                break
        return {"project": summary(current), "timeline": summary(selected), "start": invoke(selected, "GetStartFrame"), "end": invoke(selected, "GetEndFrame"),
                "settings": invoke(selected, "GetSetting"), "markers": invoke(selected, "GetMarkers"), "tracks": tracks, "truncated": truncated}
    if operation == "render_info":
        return {"project": summary(current), "jobs": bounded(invoke(current, "GetRenderJobList")), "presets": bounded(invoke(current, "GetRenderPresetList")),
                "rendering": invoke(current, "IsRenderingInProgress"), "format_codec": invoke(current, "GetCurrentRenderFormatAndCodec"), "mode": invoke(current, "GetCurrentRenderMode"),
                "note": "Read only. No undocumented GetRenderSettings call; full Deliver-panel settings are not exposed by this query."}
    if operation not in MUTATIONS:
        raise ValueError("Unknown operation")
    if type(args.get("confirmed")) is not bool:
        raise ValueError("confirmed must be a boolean")
    if operation == "save_project":
        action = lambda: invoke(invoke(resolve, "GetProjectManager"), "SaveProject")
    elif operation == "select_timeline":
        selected = timeline(current, args.get("timeline_id"))
        action = lambda: invoke(current, "SetCurrentTimeline", selected)
    elif operation in {"import_media", "create_timeline", "move_media"}:
        pool = invoke(current, "GetMediaPool")
        selected = folder(current, args.get("folder_id"))
        if operation == "import_media":
            paths = args.get("paths")
            if not isinstance(paths, list) or not 0 < len(paths) <= MAX_ROWS or any(not isinstance(p, str) or not Path(p).is_absolute() or not Path(p).is_file() for p in paths):
                raise ValueError("Provide 1..1000 explicit existing absolute media file paths; directories and patterns are not imported")
            def action():
                if not invoke(pool, "SetCurrentFolder", selected):
                    raise RuntimeError("Could not select destination bin")
                imported = rows(invoke(pool, "ImportMedia", paths))
                if not imported:
                    raise RuntimeError("No media was imported; inspect codec/file support before retrying")
                return {"clips": [{"id": invoke(c, "GetMediaId"), "name": invoke(c, "GetName")} for c in imported], "destination_folder": summary(selected), "note": "Destination bin is now selected. Resolve may group image frames; returned clip count can differ from input file count."}
        else:
            ids = args.get("media_ids") or []
            if not isinstance(ids, list) or len(ids) > MAX_ROWS or any(not isinstance(i, str) or not i for i in ids):
                raise ValueError("media_ids must be a list of up to 1000 exact media IDs")
            available = rows(invoke(selected, "GetClipList"))
            by_id = {invoke(c, "GetMediaId"): c for c in available}
            if any(i not in by_id for i in ids):
                raise ValueError("Selected media ID no longer exists in the specified bin")
            clips = [by_id[i] for i in ids]
            if operation == "move_media":
                if not clips:
                    raise ValueError("Select explicit media IDs to move")
                destination = folder(current, args.get("destination_folder_id"))
                if identity(destination) == identity(selected):
                    raise ValueError("Source and destination bins are identical")
                action = lambda: invoke(pool, "MoveClips", clips, destination)
            else:
                name = args.get("name")
                if not isinstance(name, str) or not name.strip() or len(name) > 255 or any(invoke(t, "GetName") == name for t in timelines(current)):
                    raise ValueError("Choose a nonempty unique timeline name under 256 characters")
                def action():
                    if not invoke(pool, "SetCurrentFolder", selected):
                        raise RuntimeError("Could not select timeline destination bin")
                    created = invoke(pool, "CreateTimelineFromClips", name, clips) if clips else invoke(pool, "CreateEmptyTimeline", name)
                    if created is None:
                        raise RuntimeError("Timeline creation failed; inspect state before retrying")
                    return {"timeline": summary(created), "note": "Resolve may activate the new timeline. Selected destination bin is left active."}
    elif operation == "create_bin":
        selected = folder(current, args.get("folder_id"))
        name = args.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError("A nonempty bin name under 256 characters is required")
        if any(invoke(f, "GetName") == name for f in rows(invoke(selected, "GetSubFolderList"))):
            raise ValueError("A bin with this name already exists; no duplicate was created")
        action = lambda: summary(invoke(invoke(current, "GetMediaPool"), "AddSubFolder", selected, name))
    elif operation == "add_marker":
        selected = timeline(current, args.get("timeline_id"))
        frame, duration = args.get("frame"), args.get("duration")
        if type(frame) is not int or frame < 0 or type(duration) is not int or duration <= 0:
            raise ValueError("Marker frame is a nonnegative timeline-relative integer; duration must be positive")
        markers = invoke(selected, "GetMarkers")
        if not isinstance(markers, dict):
            raise ValueError("Could not inspect existing markers")
        if frame in markers or str(frame) in markers:
            raise ValueError("A marker exists at this frame; no replacement was performed")
        action = lambda: invoke(selected, "AddMarker", frame, args["color"], args["name"], args["note"], duration)
    elif operation == "set_render_settings":
        settings = args.get("settings")
        allowed = {"TargetDir", "CustomName", "SelectAllFrames", "MarkIn", "MarkOut", "ExportVideo", "ExportAudio", "FormatWidth", "FormatHeight", "FrameRate"}
        if not isinstance(settings, dict) or not settings or set(settings) - allowed:
            raise ValueError("Use only documented supported render setting keys: " + ", ".join(sorted(allowed)))
        if any(not isinstance(v, (str, int, float, bool)) for v in settings.values()):
            raise ValueError("Render settings must contain scalar values")
        action = lambda: invoke(current, "SetRenderSettings", settings)
    else:
        code = args.get("code")
        if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > 131072:
            raise ValueError("Python code must be nonempty and at most 128 KiB")
        compiled = compile(code, "<bubble-resolve>", "exec")
        def action():
            output = Output()
            namespace = {"resolve": resolve, "project": current, "__name__": "__bubble_resolve__"}
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exec(compiled, namespace)
            value = namespace.get("result")
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError):
                value = repr(value)[:65536]
            return {"result": value, "output": output.getvalue()}
    if not args["confirmed"]:
        return {"applied": False, "requires_confirmation": True, "operation": operation, "project": summary(current), "arguments": {k:v for k,v in args.items() if k != "confirmed"},
                "note": "Preview only. Python runs externally with full user privileges and may change files/projects if authorized. No render/export is started by structured tools."}
    recheck()
    project(resolve, expected)
    if invoke(current, "IsRenderingInProgress"):
        raise ValueError("Wait for rendering to finish before applying edits")
    # Process and current project checked again immediately before mutation.
    recheck()
    project(resolve, expected)
    result = action()
    if result is False or result is None:
        raise RuntimeError("Resolve rejected the operation; inspect state before retrying")
    return {"applied": True, "result": result, "project_id": expected}
