"""Existing-process discovery and official SDK loading. Never launches Resolve."""
import importlib.util
import os
from pathlib import Path
import sys
import psutil


def failure(code, message, **details):
    return {"ok": False, "error": {"code": code, "message": str(message), **details}}


def sdk_path():
    base = os.environ.get("RESOLVE_SCRIPT_API") or str(Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting")
    path = Path(base) / "Modules/DaVinciResolveScript.py"
    if not path.is_absolute():
        raise ValueError("RESOLVE_SCRIPT_API must be an absolute SDK directory")
    return path


def discover():
    if sys.platform != "win32":
        return []
    rows = []
    # psutil caches Process objects; discard cached creation times between calls.
    psutil.process_iter.cache_clear()
    for process in psutil.process_iter(["pid", "name"]):
        if str(process.info.get("name", "")).casefold() != "resolve.exe":
            continue
        row = {"pid": process.pid, "status": "unavailable"}
        try:
            row.update(executable=process.exe(), started=process.create_time())
            row["session_id"] = "%s:%.6f" % (process.pid, row["started"])
            row["status"] = "available"
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            row["reason"] = "Resolve process identity cannot be read; close stale instances or fix process access."
        rows.append(row)
    if len(rows) > 1:
        for row in rows:
            row.update(status="unrouteable", reason="The official external API has no documented PID selector. Multiple Resolve processes cannot be safely routed; keep only the intended instance open.")
    return rows


def select(rows, session_id=None):
    if len(rows) != 1:
        raise ValueError("Exactly one running Resolve process is required; list sessions and resolve multiple instances first")
    row = rows[0]
    if row.get("status") != "available" or (session_id is not None and row.get("session_id") != session_id):
        raise ValueError("Selected Resolve session is unavailable, closed or restarted; no fallback was attempted")
    return row


def connect(selected):
    select(discover(), selected["session_id"])
    module_path = sdk_path()
    library = Path(selected["executable"]).parent / "fusionscript.dll"
    if not module_path.is_file() or not library.is_file():
        raise RuntimeError("Official Resolve scripting SDK/module or fusionscript.dll is missing. Install Resolve Studio normally; no files were installed by Bubble.")
    # Worker-local environment only. Never load an unrelated RESOLVE_SCRIPT_LIB.
    os.environ["RESOLVE_SCRIPT_LIB"] = str(library)
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("DaVinciResolveScript", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module = sys.modules[spec.name]  # SDK may replace itself with native fusionscript.
    resolve = module.scriptapp("Resolve")
    select(discover(), selected["session_id"])
    if resolve is None:
        raise RuntimeError("Resolve API unavailable. Open Resolve Studio, enable Preferences > System > General > External scripting using: Local, and restart if requested. Free edition external scripting is unsupported.")
    return resolve
