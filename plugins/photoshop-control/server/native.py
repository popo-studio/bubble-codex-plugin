"""Windows Photoshop discovery; no application launch or registry writes."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def failure(code, message):
    return {"ok": False, "error": {"code": code, "message": str(message)}}


def installations():
    if sys.platform != "win32":
        return []
    import winreg
    found = {}
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not re.fullmatch(r"Photoshop\.Application\.\d+", name, re.I):
                continue
            try:
                with winreg.OpenKey(root, name + r"\CLSID") as key:
                    clsid = winreg.QueryValue(key, "")
                with winreg.OpenKey(root, "CLSID\\" + clsid + r"\LocalServer32") as key:
                    command = winreg.QueryValue(key, "")
                match = re.match(r'^\s*"([^"]+\.exe)"|^\s*(.+?\.exe)(?:\s|$)', command, re.I)
                if not match:
                    continue
                exe = str(Path(os.path.expandvars(match.group(1) or match.group(2))).resolve())
                if Path(exe).is_file():
                    found[exe.lower()] = {"prog_id": name, "executable": exe}
            except OSError:
                continue
    return list(found.values())


def running_processes():
    script = "@(Get-Process -Name Photoshop -ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{pid=$_.Id; executable=$_.Path; version=(Get-Item -LiteralPath $_.Path).VersionInfo.ProductVersion; started=$_.StartTime.ToUniversalTime().Ticks.ToString()} }) | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Cannot inspect Photoshop processes")
    value = json.loads(result.stdout.strip() or "[]")
    return value if isinstance(value, list) else [value]


def discover():
    apps = installations()
    if sys.platform != "win32":
        return []
    processes = running_processes()
    sessions = []
    incomplete = any(not p.get("executable") or not p.get("started") for p in processes)
    for process in processes:
        path = process.get("executable")
        app = next((item for item in apps if path and os.path.normcase(item["executable"]) == os.path.normcase(path)), None)
        matches = [p for p in processes if path and str(p.get("executable", "")).lower() == path.lower()]
        version_match = re.match(r"(\d+)\.(\d+)", str(process.get("version", "")))
        supported = bool(version_match and tuple(map(int, version_match.groups())) >= (26, 2))
        row = {**process, "status": "available" if not incomplete and app and supported and len(matches) == 1 and process.get("started") else "unrouteable"}
        if app:
            row.update({"prog_id":app["prog_id"], "executable":app["executable"]})
            row["session_id"] = f'{process["pid"]}:{process.get("started", "")}:{app["prog_id"]}'
        if incomplete:
            row["reason"] = "Some Photoshop process paths or start times cannot be read; exact COM routing cannot be verified. Resolve process access before connecting."
        elif len(matches) > 1:
            row["reason"] = "Multiple processes share this executable; COM cannot safely address an arbitrary PID. Close extra instances before connecting."
        elif app and not supported:
            row["reason"] = "Native mode requires Photoshop 26.2 or later; this executable is older or its version cannot be verified."
        elif not app:
            row["reason"] = "No exact versioned COM registration matches this process executable."
        sessions.append(row)
    return sessions


def select(sessions, session_id):
    if session_id is None:
        if len(sessions) != 1:
            raise ValueError("Choose an explicit session_id from photoshop_list_sessions; no unique running Photoshop")
        selected = sessions[0]
    else:
        selected = next((row for row in sessions if row.get("session_id") == session_id), None)
        if selected is None:
            raise ValueError("The selected Photoshop session no longer exists; list sessions again")
    if selected["status"] != "available":
        raise ValueError(selected.get("reason", "Session cannot be safely addressed"))
    return selected

