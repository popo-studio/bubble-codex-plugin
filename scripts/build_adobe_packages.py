"""Build reproducible ZIP-based CCX candidates, not Adobe/UDT-certified packages.

Adobe UPIA/Creative Cloud must accept the candidate before installation is
verified. No host application, registry, or installed plugin files are touched.
"""
from pathlib import Path
import argparse
import importlib.util
import os
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ("premiere-control",)


def build_plugin(root):
    root = Path(root).resolve()
    spec = importlib.util.spec_from_file_location("adobe_package_validator", root / "server/installation.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    manifest = installer._manifest()
    source = root / "uxp"
    output = root / "adobe" / (manifest["id"] + ".ccx")
    for path in (source, output.parent, *source.rglob("*")):
        if path.is_symlink() or (path.exists() and getattr(path.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Refusing symlink/junction build path: " + str(path))
    files = sorted(path for path in source.rglob("*") if path.is_file())
    output.parent.mkdir(exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=".ccx", dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in files:
                entry = zipfile.ZipInfo(file.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, file.read_bytes())
        installer._validate_package(temporary, manifest)
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugins", nargs="*", help="photoshop-control and/or premiere-control (both by default)")
    args = parser.parse_args()
    if any(name not in PLUGINS for name in args.plugins):
        parser.error("Choose only " + ", ".join(PLUGINS))
    for name in args.plugins or PLUGINS:
        print(build_plugin(ROOT / "plugins" / name))
    print("CCX candidates built and payload-checked; Adobe installation/native loading remains unverified.")
