"""Read-only, human-readable Unreal Engine scene discovery; never routes mutations."""
from concurrent.futures import ThreadPoolExecutor
import ntpath

from client import request, sessions


def _scene_row(metadata):
    pid = metadata["pid"]
    row = {"pid": pid, "unreal_version": metadata.get("unreal_version"),
           "scene_path": None, "scene_name": None, "modified": None,
           "display_label": "无法读取场景 · Unreal Engine %s · PID %s" % (metadata.get("unreal_version") or "?", pid),
           "status": "unavailable"}
    response = request("scene_info", pid=pid, timeout=2)
    data = response.get("data")
    if not response.get("ok") or not isinstance(data, dict) or not isinstance(data.get("path"), str):
        return row
    path = data["path"]
    name = ntpath.basename(path) if path else "未保存场景"
    version = data.get("unreal_version") or row["unreal_version"]
    modified = data.get("modified") if isinstance(data.get("modified"), bool) else None
    label = "%s%s · Unreal Engine %s · PID %s" % (name, "（已修改）" if modified else "", version or "?", pid)
    if path:
        label += " · " + path
    project = data.get("project") if isinstance(data.get("project"), str) else ""
    if project:
        label += " · 项目 " + project
    row.update(scene_path=path, scene_name=name, unreal_version=version,
               modified=modified, display_label=label, status="available",
               project_path=project, map_package=data.get("map_package", ""))
    return row


def _normalize_path(value):
    return ntpath.normcase(ntpath.normpath(value)).casefold()


def _matches(path, query):
    if not path:
        return False  # Unsaved scenes have no filename; user chooses a row.
    if "/" in query or "\\" in query or ntpath.splitdrive(query)[0]:
        return _normalize_path(path) == _normalize_path(query)
    filename = ntpath.basename(path)
    # Stems may contain dots (hero.v002.ma -> hero.v002). If a query matches
    # another scene's full filename as well, keep both and require user choice.
    return query.casefold() in (filename.casefold(), ntpath.splitext(filename)[0].casefold())


def discover_sessions(scene=None):
    """Snapshot connected bridges and match exact filename, stem or full path.

    A unique result is an observation, not a lasting scene identity: callers must
    retain its PID and recheck the scene before any authorized write operation.
    """
    snapshot = sessions()
    if snapshot:
        with ThreadPoolExecutor(max_workers=min(4, len(snapshot))) as executor:
            rows = list(executor.map(_scene_row, snapshot))
    else:
        rows = []
    query = scene.strip() if scene is not None else None
    matches = [row["pid"] for row in rows
               if query and row["status"] == "available" and
               any(_matches(value, query) for value in (row["scene_path"], row.get("project_path", ""), row.get("map_package", "")))]
    incomplete = any(row["status"] != "available" for row in rows)
    if not query:
        status = "unspecified"
    elif incomplete:
        status = "incomplete"
    elif len(matches) == 1:
        status = "unique"
    elif matches:
        status = "ambiguous"
    else:
        status = "not_found"
    return {"ok": True, "data": rows,
            "selection": {"status": status, "query": query,
                          "selected_pid": matches[0] if status == "unique" else None,
                          "matching_pids": matches},
            "note": "Only processes with discovered Bubble Unreal Engine bridges are listed. Paths and names are exact, case-insensitive matches; partial names are not selected. Ask the user to choose a displayed scene when ambiguous, unsaved, or incomplete. Keep the chosen PID and recheck its scene before writes; never switch to another instance automatically."}
