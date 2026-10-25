"""Bounded read-only diagnostics. Never import or execute inspected packages."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
import time

APPS = ("maya", "nuke", "houdini", "max", "unreal", "unity", "blender")
ADOBE_APPS = ("premiere", "photoshop", "after-effects")
PLUGINS = tuple(a + "-control" for a in (*APPS, *ADOBE_APPS)) + (
    "deadline-control", "sequence-check", "asset-package", "plugin-doctor", "cinema4d-control", "resolve-control")
MAX_JSON = 256 * 1024
MAX_PACKAGES = 100


def fail(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def absolute(value):
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise ValueError("An absolute path is required")
    # Read-only, but do not traverse redirected package files or device nodes.
    p = Path(os.path.abspath(p))
    for item in (p, *p.parents):
        if os.path.lexists(item):
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Symlink/reparse paths are not inspected")
    return p


def read_bytes(path, limit=MAX_JSON):
    path = absolute(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Expected a regular file within the size limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("File grew beyond size limit")
    return data


def read_json(path):
    value = json.loads(read_bytes(path).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def children(path, limit):
    if not path.exists():
        return [], False
    absolute(path)
    result = []
    with os.scandir(path) as entries:
        for entry in entries:
            if len(result) >= limit:
                return result, True
            result.append(Path(entry.path))
    return sorted(result), False


def status():
    return {"ok": True, "data": {"version": "0.1.8", "mode": "read-only",
        "python_version": sys.version.split()[0], "uv_available": bool(shutil.which("uv")),
        "supported_plugins": list(PLUGINS)},
        "note": "Disk/cache observations do not prove Codex enabled state or tool loading. Use Codex's own tool discovery for that."}


def package_check(package_path):
    try:
        root = absolute(package_path)
        portable = read_json(root / "plugin.json")
        legacy = read_json(root / ".codex-plugin/plugin.json")
        name, version = portable.get("name"), portable.get("version")
        if name not in PLUGINS:
            raise ValueError("Not a supported Bubble package")
        issues = []
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("Invalid package version; launcher paths were not inspected")
        if legacy.get("name") != name or legacy.get("version") != version:
            issues.append("manifest_version_mismatch")
        if portable.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
            issues.append("portable_schema_missing")
        standard = read_json(root / "mcp.json").get("mcpServers")
        overlay = read_json(root / ".mcp.json").get("mcpServers")
        if not isinstance(standard, dict) or not standard or not isinstance(overlay, dict):
            raise ValueError("Missing MCP server mapping")
        if set(standard) != set(overlay):
            issues.append("mcp_server_mismatch")
        for key, config in standard.items():
            if not isinstance(config, dict):
                raise ValueError("Invalid server configuration")
            if {k: v for k, v in config.items() if k != "type"} != overlay.get(key):
                issues.append("mcp_config_mismatch")
            expected = ["run", "--no-project", "--no-config", "--directory", "/", "--locked", "--script", "${PLUGIN_ROOT}/launch-%s.py" % version]
            if name == "sequence-check":expected[1:1] = ["--python", "3.13"]
            if config.get("command") != "uv" or config.get("args") != expected:
                issues.append("nonstandard_launcher")
            if "cwd" in config or "cwd" in overlay.get(key, {}):
                issues.append("declared_cwd_may_prevent_loading")
        for relative in ("server/main.py", "launch-%s.py" % version, "launch-%s.py.lock" % version):
            if not absolute(root / relative).is_file():
                issues.append("missing_" + relative)
        if (root / ".venv").exists():
            issues.append("in_package_venv_may_block_uninstall")
        return {"ok": True, "data": {"name": name, "version": version,
            "path": str(root), "issues": sorted(set(issues)), "healthy": not issues},
            "note": "Static package checks only; no imports, installs, processes or Codex settings changed."}
    except (OSError, ValueError, TypeError) as exc:
        return fail("package_unreadable", str(exc))


def inventory(codex_home=None, source_root=None):
    try:
        home = absolute(codex_home or os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
        source = absolute(source_root) if source_root else None
        local = {}
        if source:
            for name in PLUGINS:
                path = source / "plugins" / name
                if path.exists():
                    local[name] = package_check(str(path))
        rows, issues = [], []
        markets, truncated = children(home / "plugins/cache", 100)
        for market in markets:
            if len(rows) >= MAX_PACKAGES:
                truncated = True
                break
            if not market.is_dir():
                continue
            for name in PLUGINS:
                if len(rows) >= MAX_PACKAGES:
                    truncated = True
                    break
                versions, cut = children(market / name, 30)
                truncated |= cut
                for folder in versions:
                    if len(rows) >= MAX_PACKAGES:
                        truncated = True
                        break
                    if not folder.is_dir():
                        continue
                    report = package_check(str(folder))
                    row = {"marketplace": market.name, "plugin": name,
                           "cached_directory": str(folder), "check": report}
                    if name in local and local[name].get("ok") and report.get("ok"):
                        row["source_version"] = local[name]["data"]["version"]
                        row["matches_source_version"] = row["source_version"] == report["data"]["version"]
                    rows.append(row)
        return {"ok": True, "data": {"cached_packages": rows, "source_packages": local,
            "truncated": truncated, "issues": issues}, "note":
            "All cached versions are shown; cache presence is not installed/enabled status. Source comparison is local, not a remote update check. No Codex auth/config contents read."}
    except (OSError, ValueError, TypeError) as exc:
        return fail("inventory_failed", str(exc))


def bridge_check(app, runtime_directory):
    try:
        if app not in APPS:
            raise ValueError("Choose a supported DCC application")
        root = absolute(runtime_directory)
        metadata = read_json(root / ("modules/bubble_blender_runtime/installation.json" if app == "blender" else ".bubble-installation.json" if app == "unity" else "installation.json"))
        if metadata.get("owner") != "bubble-%s-control" % app:
            raise ValueError("Ownership does not match the selected plugin")
        files = metadata.get("files")
        if not isinstance(files, dict) or not 0 < len(files) <= 32:
            raise ValueError("Invalid ownership file list")
        rows = []
        for name, expected in files.items():
            if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                    or Path(name).is_absolute() or ".." in Path(name).parts
                    or not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected)):
                raise ValueError("Invalid owned file entry")
            path = absolute(root / name)
            if not path.is_relative_to(root):
                raise ValueError("Owned file escapes runtime")
            if not path.exists():
                state = "missing"
            else:
                actual = hashlib.sha256(read_bytes(path, 8 * 1024 * 1024)).hexdigest()
                state = "matches_record" if actual == expected else "modified"
            rows.append({"file": name, "status": state})
        return {"ok": True, "data": {"app": app, "installed_version": metadata.get("version"),
            "files": rows, "intact": all(r["status"] == "matches_record" for r in rows)},
            "note": "Hashes are compared to the local ownership record, not a trusted remote release. Startup configuration and currently loaded version are not verified; use the owning plugin's installation_status for full validation."}
    except (OSError, ValueError, TypeError) as exc:
        return fail("bridge_inspection_failed", str(exc))


def _probe(row):
    # Metadata is untrusted: always loopback and only a fixed read-only operation.
    safe = {"pid": row["pid"], "port": row["port"], "status": "unreachable"}
    timeout = 2.0
    query = {"protocol": 1, "token": row["token"], "operation": "scene_info",
             "arguments": {}, "timeout": timeout, "expires_at": time.time() + timeout}
    try:
        deadline = time.monotonic() + 4
        with socket.create_connection(("127.0.0.1", row["port"]), timeout=1) as conn:
            conn.settimeout(1)
            conn.sendall(json.dumps(query).encode() + b"\n")
            result = bytearray()
            while b"\n" not in result and len(result) <= MAX_JSON:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                conn.settimeout(min(1, remaining))
                chunk = conn.recv(min(8192, MAX_JSON + 1 - len(result)))
                if not chunk:
                    break
                result.extend(chunk)
        if len(result) > MAX_JSON or not result.endswith(b"\n"):
            raise ValueError("Invalid response")
        response = json.loads(result)
        data = response.get("data") if isinstance(response, dict) else None
        if response.get("ok") is True and isinstance(data, dict):
            safe["status"] = "reachable"
            # Never echo arbitrary payloads/errors, including an echoed token.
            for field in ("path", "project_path", "maya_version", "nuke_version", "houdini_version", "max_version", "unreal_version", "unity_version", "blender_version"):
                value = data.get(field)
                if isinstance(value, str):
                    safe[field] = value.replace(row["token"], "[redacted]")[:2048]
            if isinstance(data.get("modified"), bool):
                safe["modified"] = data["modified"]
        else:
            safe["status"] = "bridge_error"
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return safe


def sessions(app, session_directory=None, probe=True):
    try:
        if app not in APPS:
            raise ValueError("Choose a supported DCC application")
        directory = absolute(session_directory or os.environ.get("BUBBLE_%s_SESSION_DIR" % app.upper()) or str(Path.home() / (".bubble-" + app) / "sessions"))
        paths, cut = children(directory, 64)
        candidates, invalid = [], 0
        for path in paths:
            if path.suffix != ".json":
                continue
            try:
                row = read_json(path)
                if (row.get("protocol") != 1 or row.get("host") != "127.0.0.1"
                        or type(row.get("pid")) is not int or row["pid"] <= 0 or path.stem != str(row["pid"])
                        or type(row.get("port")) is not int or not 0 < row["port"] < 65536
                        or not isinstance(row.get("token"), str) or not 32 <= len(row["token"]) <= 256):
                    raise ValueError("Invalid session metadata")
                candidates.append(row)
            except (OSError, ValueError, TypeError):
                invalid += 1
        cut |= len(candidates) > 16
        candidates = candidates[:16]
        if probe and candidates:
            with ThreadPoolExecutor(max_workers=8) as pool:
                rows = list(pool.map(_probe, candidates))
        else:
            rows = [{"pid": r["pid"], "port": r["port"], "status": "not_probed"} for r in candidates]
        return {"ok": True, "data": rows, "invalid_records": invalid, "truncated": cut,
            "note": "Only registered bridges appear; unreachable does not mean the application is closed. Choose an explicit PID/scene when multiple instances exist. No instance selected or changed."}
    except (OSError, ValueError, TypeError) as exc:
        return fail("session_inspection_failed", str(exc))


def log_check(log_path):
    try:
        path = absolute(log_path)
        if not path.is_file():
            raise ValueError("Expected a log file")
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - MAX_JSON))
            data = stream.read(MAX_JSON).decode("utf-8", errors="replace").lower()
        patterns = [
            ("maya_loader_file_context", "name '__file__' is not defined", "Update Maya plugin and software bridge to 0.2.6 or newer; save work and restart Maya."),
            ("windows_access_denied", "os error 5", "Check for an old in-package runtime or a matching process holding the cache; do not stop unrelated Python/Maya processes."),
            ("missing_dependency", "modulenotfounderror", "Check the versioned uv launcher and lock; inspect the exact missing dependency in the local log."),
            ("port_in_use", "address already in use", "Check the owning bridge and its instance registry; do not choose another instance silently."),
            ("runtime_spawn_failed", "failed to spawn", "Verify uv is available to the Codex process and the plugin launch file exists."),
        ]
        findings = [{"code": code, "suggestion": advice} for code, pattern, advice in patterns if pattern in data]
        return {"ok": True, "data": {"findings": findings, "bytes_examined": min(size, MAX_JSON), "tail_only": size > MAX_JSON},
            "note": "Signature matches are diagnostic clues, not proven causes. No raw log lines, credentials or tokens returned; unknown errors need local inspection."}
    except (OSError, ValueError) as exc:
        return fail("log_unreadable", str(exc))


def guidance(plugin_name, action):
    if plugin_name not in PLUGINS or action not in ("repair", "update", "uninstall"):
        return fail("invalid_request", "Choose a supported plugin and repair/update/uninstall")
    app = plugin_name.removesuffix("-control")
    steps = []
    if action in ("repair", "update"):
        steps = ["Inspect the exact package with doctor_check_package and use Codex tool discovery to verify runtime loading.",
            "Use the supported Codex marketplace refresh/install UI or CLI for the actual registered source; do not edit installed cache/config files."]
    if app == "cinema4d":
        steps.extend(["Use cinema4d_setup_status and cinema4d_list_sessions; this adapter uses Cinema 4D 2027 built-in MCP, not a Bubble socket bridge.",
            "Preview named registration with cinema4d_configure using the exact Maxon-exported MCP configuration; authorize registration explicitly. Never guess ports, edit vendor preferences or install a host plugin.",
            "Disconnect the exact session and remove its named registration through cinema4d_configure before Codex uninstall if full cleanup is requested. Preserve exported config and projects."])
    if app == "resolve":
        steps.extend(["Use resolve_setup_status and resolve_list_sessions for the native Resolve Studio 21+ scripting SDK. Do not scan Bubble socket registries or install a host bridge.",
            "The user must enable Local external scripting in Resolve preferences when required; never change preferences automatically. Select the exact session/project, and do not switch after disconnection.",
            "Codex package removal does not remove vendor SDK files, projects or preferences. No Bubble software-side installation is required."])
    if app == "blender":
        steps.append("Blender uses an owned Startup module in the exact user scripts directory; confirm actual installed profile (4.5 or5.2), save work and restart after authorized bridge installation. doctor_check_bridge expects the user scripts directory, not its nested runtime folder.")
    if app == "premiere":
        steps.extend([
            "Use premiere_installation_status to distinguish signed CEP release files, user-profile installation and an actually connected Premiere 26.x background extension.",
            "Use premiere_install_bridge or premiere_uninstall_bridge with a preview and explicit authorization. Preserve modified/unknown extensions. No Creative Cloud, UPIA or PlayerDebugMode is required; never edit Adobe private plugin stores or registry debug switches.",
            "Premiere 0.4.0 starts its signed background extension when Premiere activates. Use premiere_list_sessions for automatic discovery; select an explicit session and project by name/path when multiple instances match.",
            "First installation or software-side update may require restarting Premiere. No routine panel opening or pairing code is needed. Reconnection creates a new session; never replay a timed-out write or silently switch instances."])
    if app == "after-effects":
        steps.extend([
            "Use after_effects_installation_status and after_effects_list_sessions to inspect the selected AE 26.x installation and automatically discovered bridge sessions.",
            "Use after_effects_install_bridge or after_effects_uninstall_bridge with a concrete preview and user authorization. The managed Startup script starts on AE launch; installing into the application directory may require Windows administrator permission. Preserve modified and unknown files.",
            "Enable Allow Scripts To Write Files And Access Network once in AE preferences if needed, then restart after installation or update. Do not silently change this preference. No Creative Cloud, UPIA, developer tools, panel or pairing code is required.",
            "Multiple AE instances are listed by session and project path; select the exact session instead of the first match. Refresh project_state after edits. Never silently switch instances or automatically retry a timed-out write.",
            "For full removal, uninstall the managed AE bridge before the Codex package. Preserve user projects and preferences. Removing only the Codex package does not remove the AE Startup script."])
    if app == "photoshop":
        steps.extend([
            "Use photoshop_installation_status and photoshop_list_sessions to inspect native Windows COM registration, the exact installed version/path, and running instances.",
            "Photoshop 0.2.0+ needs only the Codex package: no Creative Cloud, UPIA, panel, pairing code, developer mode or software-side bridge files. Do not install Adobe components or edit its registry.",
            "If multiple processes share the same Photoshop executable, native COM cannot safely select a PID; request user resolution rather than choosing an instance.",
            "Updating/uninstalling the Codex package replaces/removes this integration; it does not stop Photoshop or alter documents. A separately installed legacy 0.1.0 UXP panel is outside this native integration."])
    if app in APPS:
        steps.append("Select the exact software profile/project, then call %s_installation_status." % app)
        steps.append("Structured scene/object tools require the matching software-side bridge. After a Codex package update, inspect the loaded bridge version and update/restart the selected application bridge if needed. Unsupported-operation errors must not silently fall back to arbitrary scripts or another instance.")
        tool = app + ("_uninstall_bridge" if action == "uninstall" else "_install_bridge")
        steps.extend(["Call %s with confirmed=false and the exact profile/project arguments to preview." % tool,
            "Only after user authorization for that concrete preview, call %s with confirmed=true. Preserve ownership conflicts." % tool,
            "Ask the user to save work and restart/refresh the application, then recheck instances; do not close applications automatically."])
    if action == "uninstall":
        steps.append("Use Codex's uninstall tool/UI for the exact plugin and marketplace after software-side cleanup, if applicable. Never delete whole caches or uv environments.")
    else:
        steps.append("Recheck tool discovery in the current/new conversation. Disk updates do not prove an existing MCP process reloaded.")
    return {"ok": True, "data": {"plugin": plugin_name, "action": action, "steps": steps,
        "executed": False}, "note": "This is a guided handoff to supported Codex/owning-plugin tools, not an automatic repair or uninstall."}
