"""Consent-gated installation of fixed owned files; no application configuration edits."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.2"
OWNER = "bubble-max-control"


def _digest(data):
    return hashlib.sha256(data).hexdigest()

def _safe_path(path):
    """Reject every existing symlink/junction ancestor, including dangling links."""
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if os.path.lexists(item):
            info = item.lstat()
            attributes = getattr(info, "st_file_attributes", 0)
            tag = getattr(info, "st_reparse_tag", 0)
            # Cloud/OneDrive placeholders do not redirect path names. Permit the
            # documented CLOUD and CLOUD_1..F tags, but fail closed for other
            # reparse types (including symlinks, junctions and unknown tags).
            cloud_placeholder = tag & 0xFFFF0FFF == 0x9000001A
            unsafe_reparse = attributes & 0x400 and not cloud_placeholder
            if stat.S_ISLNK(info.st_mode) or unsafe_reparse:
                raise ValueError("Refusing symlink or junction path: %s" % item)
    return path


def _atomic_write(path, data):
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".bubble-write-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _transaction(changes):
    """Roll back ordinary IO failures; hard interruption fails closed on next run."""
    before = {path: path.read_bytes() if path.exists() else None for path in changes}
    done = []
    try:
        for path, data in changes.items():
            if data == before[path]:
                continue
            if data is None:
                _safe_path(path).unlink()
            else:
                _atomic_write(path, data)
            done.append(path)
    except Exception:
        for path in reversed(done):
            if before[path] is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, before[path])
        raise




def profile_candidates():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    base = Path(local) / "Autodesk" / "3dsMax"
    return sorted(str(path) for path in base.glob("*/*/scripts/startup")
                  if path.is_dir() and path.parents[2].name.startswith(("2025", "2026")))


def _layout(location, uninstall=False):
    if location is None:
        candidates = profile_candidates()
        if len(candidates) != 1:
            raise ValueError("Select an absolute user startup scripts directory. Candidates: " + json.dumps(candidates) + "; custom path can be read in Max using getDir #userStartupScripts")
        location = candidates[0]
    target = Path(location).expanduser()
    if not target.is_absolute():
        raise ValueError("startup_directory must be absolute")
    boot = target / "bubble_max_runtime" / "bootstrap.py"
    # MAXScript verbatim quoted strings preserve Windows separators. Quotes cannot be a Windows filename.
    if '"' in str(boot) or "\n" in str(boot) or "\r" in str(boot):
        raise ValueError("Invalid startup path")
    startup = ('-- Bubble owned startup; safe to remove via max_uninstall_bridge.\ntry (python.ExecuteFile @"' + str(boot) + '") catch (format "Bubble Max startup: %\\n" (getCurrentException()))\n').encode("utf-8-sig")
    files = {"bubble_max_control.ms": startup}
    for name in ("bootstrap.py", "bubble_max_bridge.py", "host.py"):
        files["bubble_max_runtime/" + name] = (ROOT / "runtime" / name).read_bytes()
    code = "import runpy; runpy.run_path(%s, run_name='__bubble_max_startup__')" % ascii(str(boot))
    return target, "bubble_max_runtime/installation.json", files, code, {"startup_directory": str(target), "scope": "One 3ds Max user profile and language"}


def _operate(location, confirmed=False, uninstall=False):
    try:
        if type(confirmed) is not bool:
            raise ValueError("confirmed must be a boolean; no files changed")
        target, manifest, files, code, context = _layout(location, uninstall)
        target = _safe_path(target)
        manifest = _safe_path(target / manifest)
        paths = {name: _safe_path(target / name) for name in files}
        state = None
        if manifest.exists():
            state = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("owner") != OWNER or set(state.get("files", {})) != set(files):
                raise ValueError("Invalid ownership manifest; refusing changes")
            for name, digest in state["files"].items():
                if not paths[name].is_file() or _digest(paths[name].read_bytes()) != digest:
                    raise ValueError("Installed file changed or removed; preserve user edits: " + str(paths[name]))
        elif any(path.exists() for path in paths.values()):
            raise ValueError("Unowned files already occupy the installation path")
        changes = {}
        if uninstall:
            if state:
                changes.update({path: None for path in paths.values()})
                changes[manifest] = None
        else:
            changes.update({paths[name]: value for name, value in files.items()})
            metadata = {"owner": OWNER, "version": VERSION, "files": {name: _digest(value) for name, value in files.items()}}
            changes[manifest] = (json.dumps(metadata, indent=2) + "\n").encode()
        changes = {path: data for path, data in changes.items() if data != (path.read_bytes() if path.exists() else None)}
        result = {"ok": True, "installed": state is not None, "installed_version": state.get("version") if state else None,
                  "available_version": VERSION, "installation_directory": str(target), **context,
                  "action": "uninstall" if uninstall else "update" if state else "install",
                  "changes": [{"path": str(path), "action": "remove" if data is None else "replace" if path.exists() else "create"} for path, data in changes.items()],
                  "confirmed": bool(confirmed), "requires_confirmation": bool(changes) and not confirmed,
                  "applied": False, "restart_required": bool(changes), "no_restart_code": None if uninstall else code,
                  "note": "After consenting to installation, restart the application/project. Optional returned code loads the current session only if the host Python environment is already enabled. Updates require restart. Removal leaves unrelated/generated files; restart to stop an already running bridge."}
        if confirmed:
            _transaction(changes)
            result.update(applied=True, installed=not uninstall, installed_version=None if uninstall else VERSION)
        return result
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"ok": False, "error": {"code": "installation_conflict", "message": str(exc)}}


def installation_status(location=None):
    return _operate(location)


def install_bridge(location=None, confirmed=False):
    return _operate(location, confirmed)


def uninstall_bridge(location=None, confirmed=False):
    return _operate(location, confirmed, True)
