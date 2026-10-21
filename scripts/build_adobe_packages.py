"""Build the signed Premiere CEP release with publisher-owned signing credentials.

This replaces the old unsigned CCX ZIP builder. No Adobe host or user profile is
modified. Signing tools and certificates are release-time inputs, never runtime
requirements for plugin users. See the delegated helper --help for arguments.
"""
from pathlib import Path
import runpy

if __name__ == "__main__":
    helper = Path(__file__).resolve().parents[1] / "plugins/premiere-control/tools/build_signed_release.py"
    runpy.run_path(str(helper), run_name="__main__")
