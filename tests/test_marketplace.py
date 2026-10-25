"""Distribution checks; no DCC application or user-profile writes required."""
import json
from pathlib import Path
import re
import struct
import tomllib
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NAMES = {f"{name}-control" for name in ("maya", "nuke", "houdini", "max", "unreal", "unity", "deadline", "premiere", "photoshop", "after-effects", "blender", "cinema4d", "resolve")} | {
    "sequence-check", "asset-package", "plugin-doctor"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class MarketplaceTests(unittest.TestCase):
    def test_catalog_contains_all_self_contained_packages(self):
        catalog = read_json(ROOT / ".agents/plugins/marketplace.json")
        names = [p["name"] for p in catalog["plugins"]]
        self.assertEqual(set(names), NAMES)
        self.assertEqual(len(names), len(NAMES))
        for entry in catalog["plugins"]:
            with self.subTest(plugin=entry["name"]):
                folder = ROOT / "plugins" / entry["name"]
                self.assertEqual(entry["source"], {"source": "local", "path": f"./plugins/{entry['name']}"})
                self.assertTrue((folder / "README.md").is_file())
                self.assertTrue((folder / "server/main.py").is_file())
                self.assertTrue((folder / "uv.lock").is_file())
                version = read_json(folder / "plugin.json")["version"]
                self.assertTrue((folder / f"launch-{version}.py").is_file())
                self.assertTrue((folder / f"launch-{version}.py.lock").is_file())

    def test_premiere_signed_release_matches_source(self):
        import hashlib
        folder = ROOT / 'plugins/premiere-control'
        source = folder / 'cep'
        signed = folder / 'adobe/signed'
        release = read_json(folder / 'adobe/release.json')
        # The signed Adobe bridge has its own release version; Python-only patches
        # must not force a host reinstall or invalidate existing receipts.
        self.assertRegex(release['version'], r'^\d+\.\d+\.\d+$')
        manifest = ET.fromstring((source / 'CSXS/manifest.xml').read_text(encoding='utf-8'))
        self.assertEqual(manifest.attrib['ExtensionBundleVersion'], release['version'])
        dispatch = manifest.find('./DispatchInfoList/Extension/DispatchInfo')
        self.assertEqual(dispatch.findtext('./UI/Type'), 'Custom')
        self.assertEqual(dispatch.findtext('./Lifecycle/AutoVisible'), 'false')
        self.assertEqual(dispatch.findtext('./Lifecycle/StartOn/Event'), 'com.adobe.csxs.events.ApplicationActivate')
        original = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        payload = {p.relative_to(signed).as_posix(): p.read_bytes() for p in signed.rglob('*') if p.is_file()}
        self.assertTrue(any(name.startswith('META-INF/') for name in payload))
        self.assertEqual({name:data for name,data in payload.items() if not name.startswith('META-INF/') and name != 'mimetype'},original)
        self.assertEqual({name:hashlib.sha256(data).hexdigest() for name,data in payload.items()},release['files'])
        with zipfile.ZipFile(folder / 'adobe/com.popostudio.bubble.premiere.zxp') as archive:
            files=[name for name in archive.namelist() if not name.endswith('/')]
            self.assertEqual(len(files),len(set(files)))
            self.assertEqual(set(files),set(payload))
            for name,data in payload.items():self.assertEqual(archive.read(name),data)

    def test_manifest_parity_and_local_references(self):
        for name in sorted(NAMES):
            with self.subTest(plugin=name):
                folder = ROOT / "plugins" / name
                portable = read_json(folder / "plugin.json")
                codex = read_json(folder / ".codex-plugin/plugin.json")
                pyproject = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))
                lock = tomllib.loads((folder / "uv.lock").read_text(encoding="utf-8"))
                self.assertEqual(portable["name"], name)
                self.assertEqual(codex["name"], name)
                self.assertRegex(portable["version"], r"^\d+\.\d+\.\d+$")
                self.assertEqual(portable["version"], codex["version"])
                self.assertEqual(portable["version"], pyproject["project"]["version"])
                package = next(p for p in lock["package"] if p["name"] == pyproject["project"]["name"])
                self.assertEqual(package["version"], portable["version"])
                extension = portable["extensions"]["com.openai"]
                interface = extension["interface"]
                self.assertEqual(interface, codex["interface"])
                self.assertLessEqual(len(interface["shortDescription"]), 30)
                self.assertTrue((folder / extension["onboardingSkill"]).is_file())
                self.assertFalse({"skills", "mcpServers", "apps", "interface"} & portable.keys())
                for field in ("logo", "composerIcon"):
                    icon = (folder / interface[field]).resolve()
                    self.assertTrue(icon.is_relative_to(folder.resolve()))
                    self.assertTrue(icon.is_file())
                    self.assertLessEqual(icon.stat().st_size, 5 * 1024 * 1024)
                    if icon.suffix == ".png":
                        data = icon.read_bytes()
                        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                        width, height = struct.unpack(">II", data[16:24])
                    elif icon.suffix == ".svg":
                        svg = ET.fromstring(icon.read_text(encoding="utf-8"))
                        width = float(svg.attrib["width"])
                        height = float(svg.attrib["height"])
                    else:
                        self.fail(f"Unexpected icon format {icon}")
                    self.assertEqual(width, height)
                    self.assertGreaterEqual(width, 48)
                    self.assertLessEqual(width, 4096)

    def test_stdio_configuration_and_skills(self):
        for name in sorted(NAMES):
            with self.subTest(plugin=name):
                folder = ROOT / "plugins" / name
                portable = read_json(folder / "mcp.json")["mcpServers"]
                overlay = read_json(folder / ".mcp.json")["mcpServers"]
                self.assertEqual(set(portable), set(overlay))
                for server_name, config in portable.items():
                    self.assertEqual(config["type"], "stdio")
                    self.assertEqual({k: v for k, v in config.items() if k != "type"}, overlay[server_name])
                    self.assertEqual(config["command"], "uv")
                    version = read_json(folder / "plugin.json")["version"]
                    self.assertEqual(config["args"], ["run"] + (["--python", "3.13"] if name == "sequence-check" else []) + [
                        "--no-project", "--no-config",
                        "--directory", "/", "--locked", "--script",
                        "${PLUGIN_ROOT}/launch-" + version + ".py",
                    ])
                    # Codex rejects a declared plugin cwd outside the package.
                    # uv itself changes directory before starting the server.
                    self.assertNotIn("cwd", config)
                    launch_lock = tomllib.loads((folder / f"launch-{version}.py.lock").read_text(encoding="utf-8"))
                    project = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))
                    launcher = (folder / f"launch-{version}.py").read_text(encoding="utf-8")
                    metadata = launcher.split("# /// script\n", 1)[1].split("# ///", 1)[0]
                    script = tomllib.loads("\n".join(line.removeprefix("# ") for line in metadata.splitlines()))
                    self.assertEqual(sorted(script["dependencies"]), sorted(project["project"]["dependencies"]))
                    self.assertEqual(script["requires-python"], project["project"]["requires-python"])
                    declared_names = {re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9_.-]+", item).group()).lower()
                                      for item in script["dependencies"]}
                    self.assertEqual({p["name"] for p in launch_lock["manifest"]["requirements"]}, declared_names)
                    self.assertEqual(
                        {p["name"]: p["version"] for p in launch_lock["package"]},
                        {p["name"]: p["version"] for p in tomllib.loads((folder / "uv.lock").read_text(encoding="utf-8"))["package"]
                         if not p["name"].startswith("bubble-")},
                    )
                skills = list((folder / "skills").glob("*/SKILL.md"))
                self.assertGreaterEqual(len(skills), 2)
                for skill in skills:
                    contents = skill.read_text(encoding="utf-8")
                    self.assertTrue(contents.startswith("---\n"))
                    frontmatter = contents.split("---", 2)[1]
                    self.assertRegex(frontmatter, rf"(?m)^name: {re.escape(skill.parent.name)}\s*$")
                    self.assertRegex(frontmatter, r"(?m)^description: .+")


if __name__ == "__main__":
    unittest.main()
