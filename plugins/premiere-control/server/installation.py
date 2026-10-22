"""Managed signed CEP deployment; no Adobe installer, debug mode, or registry writes."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP_PREFIX = "Adobe Premiere"
EXE = "Adobe Premiere Pro.exe"
PLUGIN_ID = "com.popostudio.bubble.premiere"
MIN_VERSION = "26.0.0"

def _version(value):
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", str(value))
    return tuple(int(x or 0) for x in match.groups()) if match else None


def _file_version(path):
    """Read Windows PE version resources without starting the application."""
    if os.name != "nt":
        return None
    try:
        api = ctypes.windll.version
        size = api.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not api.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        words = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
        return "%d.%d.%d.%d" % (words[2] >> 16, words[2] & 65535, words[3] >> 16, words[3] & 65535)
    except (OSError, ValueError):
        return None


def discover_applications():
    roots = {Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Adobe"}
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(root.glob(APP_PREFIX + "*")):
            exe = folder / EXE
            if exe.is_file():
                version = _file_version(exe)
                parsed = _version(version)
                found.append({"path": str(exe), "version": version,
                              "supported": parsed is not None and 26 <= parsed[0] < 27})
    return found



def _target():
    if os.name != "nt":
        raise ValueError("Windows is required")
    base = os.environ.get("APPDATA")
    if not base or not Path(base).is_absolute():
        raise ValueError("A valid per-user APPDATA directory is required")
    return Path(base) / "Adobe/CEP/extensions" / PLUGIN_ID


def _safe(path):
    path = Path(path).absolute()
    for node in [path, *path.parents]:
        if node.exists() and (node.is_symlink() or getattr(node.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Refusing a symbolic link or reparse-point installation path")
    return path


def _receipt_path(target):
    return target.parent / (PLUGIN_ID + ".bubble-install.json")


def _hashes(folder):
    values = {}
    for path in sorted(folder.rglob("*")):
        _safe(path)
        if path.is_file():
            values[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def _release():
    release = json.loads((ROOT / "adobe/release.json").read_text(encoding="utf-8"))
    source = ROOT / "adobe/signed"
    actual = _hashes(source)
    if release.get("plugin_id") != PLUGIN_ID or release.get("version") != "0.4.0" or not actual or actual != release.get("files"):
        raise ValueError("Signed CEP release contents failed integrity validation")
    if "META-INF/signatures.xml" not in actual or "CSXS/manifest.xml" not in actual:
        raise ValueError("Release is missing its Adobe signature or manifest")
    # No silent drift between editable sources and packaged signed files.
    source_files = _hashes(ROOT / "cep")
    if set(actual) != set(source_files) | {"META-INF/signatures.xml", "mimetype"}:
        raise ValueError("Signed CEP package contains missing or unexpected files")
    for key, digest in source_files.items():
        if actual.get(key) != digest:
            raise ValueError("CEP source changed after signing; rebuild the release first")
    return release, source


def _owned(target):
    receipt = _safe(_receipt_path(target))
    if not target.exists():
        if receipt.exists():
            raise ValueError("Installation receipt exists but extension is missing; inspect before repair")
        return None
    if not target.is_dir() or not receipt.is_file():
        raise ValueError("Existing extension is not managed by Bubble; will not overwrite or delete it")
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if data.get("plugin_id") != PLUGIN_ID or data.get("target") != str(target) or data.get("files") != _hashes(target):
        raise ValueError("Installed extension changed or contains unknown files; refusing destructive cleanup")
    return data


def _remove_owned_tree(path, hashes):
    # Never recursive-delete an arbitrary path. Remove only exact validated files.
    _safe(path)
    if _hashes(path) != hashes:
        raise ValueError("Files changed before cleanup")
    for relative in hashes:
        candidate = path / relative
        if candidate.resolve().is_relative_to(path.resolve()):
            candidate.unlink()
        else:
            raise ValueError("Unsafe owned file path")
    for child in sorted((x for x in path.rglob("*") if x.is_dir()), key=lambda x:len(x.parts), reverse=True):
        child.rmdir()
    path.rmdir()


def installation_status(package_path=None):
    try:
        if package_path is not None:
            raise ValueError("Only the bundled signed CEP release is supported")
        target = _safe(_target())
        release, source = _release()
        owned = _owned(target)
        applications = discover_applications()
        return {"ok": True, "data": {"application": "premiere", "minimum_version": MIN_VERSION,
            "supported_major": 26, "applications": applications, "supported_application": any(x["supported"] for x in applications),
            "installed": owned is not None, "installed_version": owned.get("version") if owned else None,
            "version": release["version"], "target": str(target), "transport": "signed CEP 12 background bridge",
            "requires_creative_cloud": False, "requires_developer_mode": False,
            "native_tested": False, "note": "Premiere 26 native acceptance is pending. Installation authorizes automatic same-user local Codex connections after Premiere restarts. No panel or pairing code needed."}}
    except (ValueError, OSError, KeyError) as error:
        return {"ok": False, "error": {"code": "installation", "message": str(error)}}


def install_bridge(confirmed=False, package_path=None):
    status = installation_status(package_path)
    if not status["ok"]: return status
    if not confirmed: return {**status, "preview": True}
    if confirmed is not True:
        return {"ok": False, "error": {"code": "authorization", "message": "confirmed must be true after user authorization"}}
    if not status["data"]["supported_application"]:
        return {"ok": False, "error": {"code": "unsupported_version", "message": "Install Premiere 26 first. No old-version fallback or Adobe configuration changes were made."}}
    stage = backup = None
    target = None
    committed = False
    swapped = False
    previous = None
    receipt_before = None
    try:
        target = _safe(_target()); release, source = _release(); previous = _owned(target)
        receipt_before = _receipt_path(target).read_bytes() if previous else None
        target.parent.mkdir(parents=True, exist_ok=True)
        _safe(target.parent)
        stage = Path(tempfile.mkdtemp(prefix=".bubble-premiere-stage-",dir=target.parent))
        shutil.copytree(source, stage, dirs_exist_ok=True)
        if _hashes(stage) != release["files"]: raise ValueError("Staged release mismatch")
        if previous:
            _owned(target)
            backup = target.with_name(".bubble-premiere-backup-" + next(tempfile._get_candidate_names()))
            target.rename(backup)
        stage.rename(target); stage = None; swapped = True
        receipt = {"plugin_id": PLUGIN_ID, "version": release["version"], "target": str(target), "files": release["files"]}
        receipt_stage = stage_receipt = target.parent / (".bubble-receipt-" + next(tempfile._get_candidate_names()))
        try:
            receipt_stage.write_text(json.dumps(receipt,indent=2), encoding="utf-8")
            os.replace(receipt_stage, _receipt_path(target))
        finally:
            if stage_receipt.exists(): stage_receipt.unlink()
        committed = True
        if backup: _remove_owned_tree(backup,previous["files"]); backup = None
        return {"ok": True, "data": {"installed": True, "version": release["version"], "target": str(target), "host_loaded": False,
            "next_step": "Restart Premiere once after install/update; the background bridge connects automatically. List sessions and select the intended project."}}
    except (ValueError, OSError) as error:
        # Roll back only trees whose exact owned hashes still match. Never discard unknown files.
        if not committed and target is not None and (swapped or backup):
            try:
                if target.exists() and _hashes(target) == release["files"]:
                    _remove_owned_tree(target, release["files"])
                if backup and backup.exists() and not target.exists():
                    backup.rename(target); backup = None
                if receipt_before is not None:
                    _receipt_path(target).write_bytes(receipt_before)
                elif _receipt_path(target).exists():
                    _receipt_path(target).unlink()
            except (ValueError, OSError): pass
        return {"ok": False, "error": {"code": "installation", "message": str(error), "backup": str(backup) if backup else None,
            "note": "Restart Premiere after update. Inspect any reported backup; no automatic destructive retry."}}
    finally:
        if stage and stage.exists():
            try: _remove_owned_tree(stage, _hashes(stage))
            except (ValueError, OSError): pass


def uninstall_bridge(confirmed=False):
    try:
        target = _safe(_target()); owned = _owned(target)
        if not confirmed: return {"ok": True, "preview": True, "data": {"target":str(target),"installed":owned is not None}}
        if confirmed is not True: raise ValueError("confirmed must be true after user authorization")
        if not owned: return {"ok":True,"data":{"removed":False,"note":"No managed CEP extension installed"}}
        _remove_owned_tree(target,owned["files"])
        _receipt_path(target).unlink()
        from discovery import cleanup_records
        cleanup_records()
        return {"ok":True,"data":{"removed":True,"note":"The background bridge checks its receipt and disconnects automatically within a few seconds. Restart Premiere to unload cached code. Projects and Adobe settings were not changed."}}
    except (ValueError,OSError) as error:
        return {"ok":False,"error":{"code":"uninstall","message":str(error)}}
