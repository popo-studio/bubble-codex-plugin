"""Read-only Windows process and PE-version discovery. Never launches AE."""
import json
import subprocess
import sys


def powershell(script):
    if sys.platform != 'win32':
        return []
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:])
    value = json.loads(result.stdout.strip() or '[]')
    return value if isinstance(value, list) else [value]


def installations():
    return powershell("@(Get-ChildItem -LiteralPath ($env:ProgramFiles+'\\Adobe') -Filter AfterFX.exe -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{executable=$_.FullName; version=$_.VersionInfo.ProductVersion; major=$_.VersionInfo.ProductMajorPart} }) | ConvertTo-Json -Compress")


def discover():
    rows = powershell("@(Get-Process -Name AfterFX -ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{pid=$_.Id; executable=$_.Path; started=$_.StartTime.ToUniversalTime().Ticks.ToString(); version=(Get-Item -LiteralPath $_.Path).VersionInfo.ProductVersion; major=(Get-Item -LiteralPath $_.Path).VersionInfo.ProductMajorPart} }) | ConvertTo-Json -Compress")
    for row in rows:
        row['session_id'] = str(row.get('pid')) + ':' + str(row.get('started'))
        row['status'] = 'available'
        if len(rows) != 1:
            row.update(status='unrouteable', reason='AfterFX -r has no PID selector. Close all other After Effects instances, including older versions.')
        elif not row.get('executable') or not row.get('started'):
            row.update(status='unrouteable', reason='Process executable/start time cannot be verified.')
        elif int(row.get('major') or 0) < 26:
            row.update(status='unsupported', reason='After Effects 26 or later is required; older versions are intentionally unsupported.')
    return rows


def select(session_id):
    rows = discover()
    if len(rows) != 1 or rows[0].get('session_id') != session_id or rows[0]['status'] != 'available':
        raise ValueError('Selected session is no longer uniquely routeable; list sessions again. AE 26+ and exactly one running instance are required.')
    return rows[0]
