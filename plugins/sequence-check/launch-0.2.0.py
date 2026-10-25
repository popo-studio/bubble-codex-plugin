# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.28,<2", "certifi>=2026.10.19", "Pillow==13.0.0", "OpenEXR==3.4.9", "numpy==2.2.6"]
# ///
"""Run with uv's locked script environment outside the installed plugin folder.

Do not use `uv run server/main.py` for a deployed plugin: it creates .venv
inside the package, whose Python/DLL handles prevent Windows uninstallation.
The versioned script filename selects a different cached environment for each
release, so updates cannot rewrite dependencies loaded by an older server.
Codex starts uv in the plugin directory; uv --directory / immediately leaves
that directory before starting Python. Both processes then use a filesystem
root, so neither holds the removable plugin directory open. Do not set a
manifest cwd outside the plugin: Codex may reject the entire server entry.
"""
import os
from pathlib import Path
import runpy
import sys

# Python source is loaded and closed at import time. Never populate package
# caches, and resolve the entrypoint before switching away from the package.
sys.dont_write_bytecode = True
entrypoint = Path(__file__).resolve().parent / "server" / "main.py"
os.chdir(Path(entrypoint.anchor))
sys.path.insert(0, str(entrypoint.parent))
runpy.run_path(str(entrypoint), run_name="__main__")
