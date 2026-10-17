"""Distribution checks; no DCC application or user-profile writes required."""
import json
from pathlib import Path
import re
import struct
import tomllib
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NAMES = {f"{name}-control" for name in ("maya", "nuke", "houdini", "max", "unreal", "unity")}


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
                    self.assertIn("--locked", config["args"])
                    self.assertIn("${PLUGIN_ROOT}", config["args"])
                    self.assertEqual(config["cwd"], "${PLUGIN_ROOT}")
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
