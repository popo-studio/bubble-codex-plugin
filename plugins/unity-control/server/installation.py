"""Consent-gated embedded Editor package installation; project fixtures are testable."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
OWNER = "bubble-unity-control"
PACKAGE = "com.bubble.codex-control"
FILES = ("package.json", "Editor/BubbleUnityBridge.cs", "Editor/Bubble.UnityControl.Editor.asmdef")
MANIFEST = ".bubble-installation.json"


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _safe_path(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if os.path.lexists(item):
            info = item.lstat()
            tag = getattr(info, "st_reparse_tag", 0)
            cloud = tag & 0xFFFF0FFF == 0x9000001A
            if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400 and not cloud):
                raise ValueError("Refusing symlink/junction path: %s" % item)
    return path


def _paths(project_path):
    if os.name != "nt":
        raise ValueError("This release supports Windows Unity Editor only")
    if not isinstance(project_path, str) or not project_path or not Path(project_path).is_absolute():
        raise ValueError("An explicit absolute Unity project directory is required")
    project = _safe_path(project_path)
    version_file = _safe_path(project / "ProjectSettings/ProjectVersion.txt")
    manifest = _safe_path(project / "Packages/manifest.json")
    if not _safe_path(project / "Assets").is_dir() or not version_file.is_file() or not manifest.is_file():
        raise ValueError("Select an existing Unity project containing Assets, Packages/manifest.json and ProjectSettings/ProjectVersion.txt")
    match = re.search(r"^m_EditorVersion:\s*(\S+)", version_file.read_text(encoding="utf-8-sig"), re.M)
    if not match or not match[1].startswith("6000."):
        raise ValueError("This release supports Unity 6 (6000.x); validated against 6000.1.0f1")
    dependencies = json.loads(manifest.read_text(encoding="utf-8-sig")).get("dependencies", {})
    if not isinstance(dependencies, dict) or PACKAGE in dependencies:
        raise ValueError("Project manifest already declares this package, or is malformed. Refusing to shadow a dependency")
    target = _safe_path(project / "Packages" / PACKAGE)
    for name in (*FILES, MANIFEST):
        _safe_path(target / name)
    return project, target, match[1]


def _read_state(target):
    manifest = target / MANIFEST
    if not manifest.exists():
        if target.exists() and any(target.iterdir()):
            # Unity may leave .meta files after an uninstall. Nothing else may
            # occupy an unowned target, including another package with this name.
            for item in target.rglob("*"):
                _safe_path(item)
                if item.is_file() and not item.name.endswith(".meta"):
                    raise ValueError("Unowned/incomplete package directory: %s" % target)
        return None
    state = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("owner") != OWNER or not isinstance(state.get("files"), dict) or set(state["files"]) != set(FILES):
        raise ValueError("Invalid installation ownership manifest")
    for name, digest in state["files"].items():
        file = _safe_path(target / name)
        if not file.is_file() or _digest(file.read_bytes()) != digest:
            raise ValueError("Installed file was changed or removed; preserve and inspect user edits: %s" % file)
    return state


def _atomic_write(path, data):
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".bubble-write-", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _transaction(changes):
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
                _safe_path(path).unlink(missing_ok=True)
            else:
                _atomic_write(path, before[path])
        raise


def _operate(project_path, confirmed=False, uninstall=False):
    try:
        if type(confirmed) is not bool:
            raise ValueError("confirmed must be a boolean")
        project, target, version = _paths(project_path)
        state = _read_state(target)
        runtime = {name: (ROOT / "unity" / name).read_bytes() for name in FILES}
        if uninstall:
            changes = {target / name: None for name in (*FILES, MANIFEST)} if state else {}
        else:
            changes = {target / name: data for name, data in runtime.items()}
            metadata = {"owner": OWNER, "version": VERSION, "files": {name: _digest(data) for name, data in runtime.items()}}
            changes[target / MANIFEST] = (json.dumps(metadata, indent=2) + "\n").encode()
        changes = {path: data for path, data in changes.items() if data != (path.read_bytes() if path.exists() else None)}
        result = {"ok": True, "project_path": str(project), "unity_version": version, "installation_directory": str(target),
                  "installed": state is not None, "installed_version": state.get("version") if state else None, "available_version": VERSION,
                  "confirmed": confirmed, "applied": False, "requires_confirmation": bool(changes) and not confirmed,
                  "action": "uninstall" if uninstall else ("update" if state else "install"),
                  "changes": [{"path": str(path), "action": "remove" if data is None else ("replace" if path.exists() else "create")} for path, data in changes.items()],
                  "restart_recommended": bool(changes),
                  "no_restart_instructions": "Return to the selected Unity Editor in Edit Mode and wait for package refresh and compilation. If Auto Refresh is disabled, use Assets > Refresh. Then rediscover the same project; compilation reloads the bridge. If it does not connect, restart that Editor. Unity has no built-in Python Script Editor; do not paste Python code.",
                  "note": "Only this project's embedded Editor package is changed. Packages/manifest.json and scene files remain untouched. Restart the selected Editor after installation/removal; package refresh may apply it without a restart. Generated .meta files and unrelated files remain after removal. Existing C# errors can prevent the bridge from loading."}
        if confirmed:
            _transaction(changes)
            result.update(applied=True, installed=not uninstall, installed_version=None if uninstall else VERSION)
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return {"ok": False, "error": {"code": "installation_conflict", "message": str(error)}}


def installation_status(project_path):
    return _operate(project_path)


def install_bridge(project_path, confirmed=False):
    return _operate(project_path, confirmed)


def uninstall_bridge(project_path, confirmed=False):
    return _operate(project_path, confirmed, uninstall=True)
