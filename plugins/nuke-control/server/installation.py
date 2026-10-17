"""Consent-gated, user-level Nuke installation. No Nuke process is required.

Only owned, unmodified files are replaced. Existing startup bytes are preserved;
Startup backups are retained. All test installs use explicit scratch app dirs.
"""
import base64
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import tokenize

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.2"
OWNER = "bubble-nuke-control"
FILES = ("bridge.py", "bootstrap.py")
MANIFEST = "installation.json"
BEGIN = b"# BEGIN BUBBLE NUKE MANAGED STARTUP"
END = b"# END BUBBLE NUKE MANAGED STARTUP"


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _app_directory():
    override = os.environ.get("BUBBLE_NUKE_USER_DIR")
    return Path(os.path.expandvars(override)).expanduser() if override else Path.home() / ".nuke"


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


def _paths(nuke_version, nuke_app_dir):
    if str(nuke_version) != "15.1":
        raise ValueError("This release supports Nuke 15.1 installation only")
    app = Path(nuke_app_dir) if nuke_app_dir is not None else _app_directory()
    if "$" in str(app) or "%" in str(app):
        raise ValueError("Resolve environment variables in the profile directory before installation")
    if not app.is_absolute():
        raise ValueError("Nuke application directory must be absolute")
    scripts = _safe_path(app)
    target = _safe_path(scripts / "bubble_nuke_runtime")
    startup = _safe_path(scripts / "menu.py")
    for name in (*FILES, MANIFEST):
        _safe_path(target / name)
    return scripts, target, startup


def _runtime_files():
    return {"bridge.py": (ROOT / "nuke" / "bubble_nuke_bridge.py").read_bytes(),
            "bootstrap.py": (ROOT / "nuke" / "bootstrap.py").read_bytes()}


def _startup_block(target, original):
    # Python's encoding cookie / BOM stays at the start, and non-ASCII paths are
    # represented with ASCII escapes so existing source encodings remain valid.
    tokenize.detect_encoding(io.BytesIO(original).readline)
    compile(original, "menu.py", "exec")
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    code = "\n".join([
        BEGIN.decode(),
        "try:",
        "    exec(compile(open(%s, 'rb').read(), %s, 'exec'), {'__file__': %s})" % (ascii(str(target / "bootstrap.py")), ascii(str(target / "bootstrap.py")), ascii(str(target / "bootstrap.py"))),
        "except Exception as _bubble_error:",
        "    print('Bubble Nuke startup failed:', _bubble_error)",
        END.decode(), "",
    ]).encode("ascii").replace(b"\n", newline)
    return (newline if original and not original.endswith(b"\n") else b"") + code


def _read_state(target, startup):
    original = startup.read_bytes() if startup.exists() else b""
    manifest_path = target / MANIFEST
    if not manifest_path.exists():
        if any((target / name).exists() for name in FILES):
            raise ValueError("Installation directory is unowned or incomplete; inspect it before retrying: %s" % target)
        if BEGIN in original or END in original:
            raise ValueError("Existing Bubble Nuke startup block has no ownership manifest")
        return None, original, b""
    state = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("owner") != OWNER or not isinstance(state.get("files"), dict) or set(state["files"]) != set(FILES):
        raise ValueError("Invalid installation ownership manifest")
    block = base64.b64decode(state["startup_block"], validate=True)
    if BEGIN not in block or END not in block or original.count(block) != 1 or original.count(BEGIN) != 1 or original.count(END) != 1:
        raise ValueError("Managed menu.py block was changed; refusing to overwrite user edits")
    for name, digest in state["files"].items():
        file = target / name
        if not file.is_file() or _digest(file.read_bytes()) != digest:
            raise ValueError("Installed file was changed or removed; refusing to overwrite: %s" % file)
    return state, original, block


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


def _backup(startup, original):
    if not startup.exists():
        return None
    backup = _safe_path(startup.with_name("menu.py.bubble-nuke-%s.bak" % _digest(original)[:16]))
    if backup.exists():
        if backup.read_bytes() != original:
            raise ValueError("Startup backup conflicts with existing file: %s" % backup)
    else:
        _atomic_write(backup, original)
    return str(backup)


def _plan(nuke_version, nuke_app_dir, uninstall=False):
    scripts, target, startup = _paths(nuke_version, nuke_app_dir)
    state, original, old_block = _read_state(target, startup)
    runtime = _runtime_files()
    clean = original.replace(old_block, b"", 1) if old_block else original
    block = _startup_block(target, clean)
    new_startup = clean if uninstall else clean + block
    compile(new_startup, str(startup), "exec")
    changes = {}
    if uninstall:
        if state:
            changes.update({target / name: None for name in FILES})
            changes[startup] = new_startup if new_startup or state["startup_existed"] else None
            changes[target / MANIFEST] = None
    else:
        changes.update({target / name: data for name, data in runtime.items()})
        changes[startup] = new_startup
        metadata = {"owner": OWNER, "version": VERSION, "nuke_version": "15.1",
                    "files": {name: _digest(data) for name, data in runtime.items()},
                    "startup_block": base64.b64encode(block).decode("ascii"),
                    "startup_existed": state["startup_existed"] if state else startup.exists()}
        changes[target / MANIFEST] = (json.dumps(metadata, indent=2) + "\n").encode()
    changes = {path: data for path, data in changes.items()
               if data != (path.read_bytes() if path.exists() else None)}
    backup = None
    if changes and startup.exists():
        backup = _safe_path(startup.with_name("menu.py.bubble-nuke-%s.bak" % _digest(original)[:16]))
        if backup.exists() and backup.read_bytes() != original:
            raise ValueError("Startup backup conflicts with existing file: %s" % backup)
    manual_code = "exec(compile(open(%s, 'rb').read(), %s, 'exec'), {'__file__': %s})" % (ascii(str(target / "bootstrap.py")), ascii(str(target / "bootstrap.py")), ascii(str(target / "bootstrap.py")))
    result = {"ok": True, "installed": state is not None, "installed_version": state.get("version") if state else None,
              "available_version": VERSION, "nuke_version": "15.1", "nuke_app_dir": str(scripts),
              "installation_directory": str(target), "startup_file": str(startup),
              "startup_backup": str(backup) if backup else None,
              "action": "uninstall" if uninstall else ("update" if state else "install"),
              "changes": [{"path": str(path), "action": "remove" if data is None else ("replace" if path.exists() else "create")} for path, data in changes.items()],
              "restart_required": bool(changes), "no_restart_code": None if uninstall else manual_code,
              "note": ("Restart Nuke after removal to stop a currently running bridge. Only owned files and the exact startup block will be removed; backups and unrelated/generated files remain." if uninstall else "After installation, restart Nuke or run no_restart_code in its Python console. An already running bridge retains its code until restart.")}
    return result, changes, startup, original


def _operate(nuke_version, confirmed, nuke_app_dir, uninstall=False):
    try:
        if type(confirmed) is not bool:
            raise ValueError("confirmed must be a boolean")
        result, changes, startup, original = _plan(nuke_version, nuke_app_dir, uninstall)
        result["confirmed"] = bool(confirmed)
        result["applied"] = False
        if not confirmed:
            result["requires_confirmation"] = bool(changes)
            return result
        if changes:
            # Snapshot before editing startup, even when removing only our block.
            result["startup_backup"] = _backup(startup, original)
            _transaction(changes)
        result["applied"] = True
        result["installed"] = not uninstall
        result["installed_version"] = None if uninstall else VERSION
        if uninstall:
            result["no_restart_code"] = None
            result["note"] = "Restart Nuke to stop a currently running bridge. Only owned files and the exact startup block were removed; backups and any unrelated/generated files remain."
        return result
    except (OSError, ValueError, SyntaxError, KeyError, TypeError) as error:
        return {"ok": False, "error": {"code": "installation_conflict", "message": str(error)}}


def installation_status(nuke_version="15.1", nuke_app_dir=None):
    """Read-only preview, with conflicts reported instead of silently repaired."""
    return _operate(nuke_version, False, nuke_app_dir)


def install_bridge(nuke_version="15.1", confirmed=False, nuke_app_dir=None):
    return _operate(nuke_version, confirmed, nuke_app_dir)


def uninstall_bridge(nuke_version="15.1", confirmed=False, nuke_app_dir=None):
    return _operate(nuke_version, confirmed, nuke_app_dir, uninstall=True)
