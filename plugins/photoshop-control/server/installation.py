"""Official UXP deployment: Adobe UPIA owns installed files; CCX candidates are payload-checked.

No registry edits, private Adobe directory writes, or development-mode toggles.
An installed application, a prepared CCX, and an installed plugin are separate facts.
"""
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP = "photoshop"
APP_PREFIX = "Adobe Photoshop"
EXE = "Photoshop.exe"
PLUGIN_ID = "com.popostudio.bubble.photoshop"
MIN_VERSION = "26.2.0"
GUIDE = "https://developer.adobe.com/uxp/guides/how-to/distribution/install/"
PACKAGE_GUIDE = "https://developer.adobe.com/uxp/guides/how-to/distribution/package/"


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
                              "supported": parsed is not None and parsed >= _version(MIN_VERSION)})
    return found


def _upia():
    override = os.environ.get("BUBBLE_ADOBE_UPIA")
    if override:
        path = Path(override)
        if not path.is_absolute() or path.name.lower() != "unifiedplugininstalleragent.exe":
            raise ValueError("BUBBLE_ADOBE_UPIA must be the absolute Adobe UnifiedPluginInstallerAgent.exe path")
        return path if path.is_file() else None
    for variable, fallback in (("CommonProgramFiles", "C:/Program Files/Common Files"),
                               ("CommonProgramFiles(x86)", "C:/Program Files (x86)/Common Files")):
        path = Path(os.environ.get(variable, fallback)) / "Adobe/Adobe Desktop Common/RemoteComponents/UPI/UnifiedPluginInstallerAgent/UnifiedPluginInstallerAgent.exe"
        if path.is_file():
            return path
    return None


def _run(upia, args):
    result = subprocess.run([str(upia), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Adobe UPIA failed (%s): %s" %
                           (result.returncode, (result.stderr or result.stdout)[-3000:]))
    return result.stdout


def _manifest():
    manifest = json.loads((ROOT / "uxp/manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("id") != PLUGIN_ID or not isinstance(manifest.get("name"), str):
        raise ValueError("Unexpected packaged UXP identity")
    return manifest


def _listing(text, manifest):
    """Only structured exact identities constitute evidence.

    UPIA versions/locales have different display output. Unknown text is not an
    empty plugin list, and is never permission to uninstall a guessed name.
    """
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    rows = value if isinstance(value, list) else value.get("plugins") if isinstance(value, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return None
    same_name = [row for row in rows if row.get("name") == manifest["name"]]
    if len(same_name) > 1 or (same_name and same_name[0].get("id") != PLUGIN_ID):
        return None  # Adobe removal uses display name; never remove an ambiguous label.
    for row in rows:
        if row.get("id") == PLUGIN_ID and row.get("name") == manifest["name"]:
            return {"id": PLUGIN_ID, "name": manifest["name"], "version": row.get("version")}
    # Only a schema with identity-bearing entries can establish absence.
    if not rows or all(isinstance(row.get("id"), str) and isinstance(row.get("name"), str) for row in rows):
        return False
    return None


def _validate_package(package_path, manifest):
    path = Path(package_path)
    if not path.is_absolute() or path.suffix.lower() != ".ccx" or not path.is_file():
        raise ValueError("Provide an existing absolute .ccx path for this plugin release")
    source = ROOT / "uxp"
    expected = {file.relative_to(source).as_posix(): file.read_bytes()
                for file in source.rglob("*") if file.is_file()}
    with zipfile.ZipFile(path) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("CCX has duplicate file names")
        if set(names) != set(expected):
            raise ValueError("CCX contents do not match this plugin release; package its uxp directory with UDT")
        for name, content in expected.items():
            item = archive.getinfo(name)
            if item.file_size > 8 * 1024 * 1024:
                raise ValueError("Unexpected oversized CCX entry")
            data = archive.read(name)
            # UDT may normalize JSON whitespace while packaging.
            matches = json.loads(data) == manifest if name == "manifest.json" else data == content
            if not matches:
                raise ValueError("CCX differs from this plugin release: " + name)
    return path


def installation_status(package_path=None):
    manifest = _manifest()
    upia = _upia()
    evidence = None
    listing_error = None
    if upia:
        try:
            evidence = _listing(_run(upia, ["/list", "all"]), manifest)
            if evidence is None:
                listing_error = "UPIA listing format is not recognized; verify in Creative Cloud Manage Plugins"
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            listing_error = str(exc)
    else:
        listing_error = "Adobe Unified Plugin Installer Agent is not installed; install/update Creative Cloud Desktop"
    package = Path(package_path) if package_path else ROOT / "adobe" / (PLUGIN_ID + ".ccx")
    package_error = None
    try:
        _validate_package(str(package), manifest)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        package_error = str(exc)
    applications = discover_applications()
    return {
        "application": APP, "minimum_version": MIN_VERSION,
        "applications": applications, "compatible_application_found": any(app["supported"] for app in applications),
        "plugin_id": PLUGIN_ID, "plugin_name": manifest["name"], "available_version": manifest["version"],
        "installed": True if evidence else False if evidence is False else None,
        "installed_version": evidence.get("version") if evidence else None,
        "installation_evidence": "Adobe UPIA exact plugin identity" if evidence else None,
        "upia_path": str(upia) if upia else None, "listing_error": listing_error,
        "package_path": str(package), "package_ready": package_error is None, "package_error": package_error,
        "package_validation": "Source payload matched; this does not prove Adobe installer acceptance or native loading",
        "source_path": str(ROOT / "uxp"), "packaging_guide": PACKAGE_GUIDE, "installation_guide": GUIDE,
        "applied": False,
    }


def install_bridge(confirmed=False, package_path=None):
    if not isinstance(confirmed, bool):
        raise ValueError('confirmed must be a boolean')
    status = installation_status(package_path)
    status["action"] = "install_or_update"
    status["changes"] = ["Adobe UPIA installs the validated CCX for " + PLUGIN_ID]
    status["blocked_reasons"] = []
    if not status["compatible_application_found"]:
        status["blocked_reasons"].append("No supported application version detected")
    if not status["upia_path"]:
        status["blocked_reasons"].append(status["listing_error"])
    if not status["package_ready"]:
        status["blocked_reasons"].append("Package the uxp source with Adobe UXP Developer Tool and pass package_path")
    if not confirmed:
        return status
    if status["blocked_reasons"]:
        raise ValueError("; ".join(status["blocked_reasons"]))
    upia = Path(status["upia_path"])
    # Re-read source/package immediately before handing it to Adobe.
    path = _validate_package(status["package_path"], _manifest())
    _run(upia, ["/install", str(path)])
    result = installation_status(str(path))
    result.update(action="install_or_update", applied=True,
                  installation_verified=result["installed"] is True,
                  next_step="Open the Bubble panel in the host application; verify its connected session in Codex")
    return result


def uninstall_bridge(confirmed=False):
    if not isinstance(confirmed, bool):
        raise ValueError('confirmed must be a boolean')
    status = installation_status()
    status["action"] = "uninstall"
    status["changes"] = ["Adobe UPIA removes only " + status["plugin_name"]]
    if not confirmed:
        return status
    if status["installed"] is False:
        return status
    if status["installed"] is not True or not status["upia_path"]:
        raise ValueError("Cannot verify this plugin's installed identity. Use Creative Cloud > Manage Plugins to uninstall " + status["plugin_name"])
    _run(Path(status["upia_path"]), ["/remove", status["plugin_name"]])
    result = installation_status()
    result.update(action="uninstall", applied=True, removal_verified=result["installed"] is False,
                  next_step="Close the Bubble panel or restart the host to end an already loaded bridge")
    return result


