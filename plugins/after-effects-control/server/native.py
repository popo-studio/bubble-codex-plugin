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
