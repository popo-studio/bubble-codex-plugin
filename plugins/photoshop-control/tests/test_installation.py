"""Lifecycle tests use temporary packages and mocked Adobe CLI, never Adobe profiles."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("adobe_installation", Path(__file__).resolve().parents[1] / "server/installation.py")
installation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installation)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "uxp").mkdir()
        self.manifest = {"id": installation.PLUGIN_ID, "name": "Bubble Test",
                         "version": "0.1.0", "host": {"app": "PS", "minVersion": "26.2.0"}}
        (self.root / "uxp/manifest.json").write_text(json.dumps(self.manifest), encoding="utf8")
        (self.root / "uxp/main.js").write_text("safe();", encoding="utf8")
        self.ccx = self.root / "fixture.ccx"
        self.package()
        self.patches = [
            patch.object(installation, "ROOT", self.root),
            patch.object(installation, "_upia", return_value=Path("C:/Adobe/UnifiedPluginInstallerAgent.exe")),
            patch.object(installation, "discover_applications", return_value=[{"supported": True}]),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def package(self, extra=None, changed=None):
        with zipfile.ZipFile(self.ccx, "w") as archive:
            for file in (self.root / "uxp").iterdir():
                archive.writestr(file.name, changed if file.name == "main.js" and changed else file.read_bytes())
            if extra:
                archive.writestr(extra, "unexpected")

    def test_preview_never_installs(self):
        with patch.object(installation, "_run", return_value="[]") as run:
            result = installation.install_bridge(package_path=str(self.ccx))
        self.assertFalse(result["applied"])
        self.assertTrue(result["package_ready"])
        self.assertEqual(run.call_args.args[1], ["/list", "all"])
        self.assertEqual(run.call_count, 1)

    def test_install_and_verify_exact_identity(self):
        with patch.object(installation, "_run", side_effect=["[]", "ok", json.dumps([self.manifest])]) as run:
            result = installation.install_bridge(True, str(self.ccx))
        self.assertTrue(result["installation_verified"])
        self.assertEqual(run.call_args_list[1].args[1], ["/install", str(self.ccx)])

    def test_unknown_listing_is_not_false_success(self):
        with patch.object(installation, "_run", return_value="unsupported localized output"):
            result = installation.install_bridge(True, str(self.ccx))
        self.assertTrue(result["applied"])
        self.assertIsNone(result["installed"])
        self.assertFalse(result["installation_verified"])

    def test_uninstall_verified_own_identity_only(self):
        with patch.object(installation, "_run", side_effect=[json.dumps([self.manifest]), "ok", "[]"]) as run:
            result = installation.uninstall_bridge(True)
        self.assertTrue(result["removal_verified"])
        self.assertEqual(run.call_args_list[1].args[1], ["/remove", "Bubble Test"])
        self.assertTrue((self.root / "uxp/main.js").exists())

    def test_unknown_listing_refuses_removal(self):
        with patch.object(installation, "_run", return_value="unrecognized") as run:
            with self.assertRaises(ValueError):
                installation.uninstall_bridge(True)
        self.assertEqual(run.call_count, 1)

    def test_foreign_identity_is_not_removed(self):
        foreign = dict(self.manifest, id="someone.else", name="Different plugin")
        with patch.object(installation, "_run", return_value=json.dumps([foreign])) as run:
            result = installation.uninstall_bridge(True)
        self.assertFalse(result["applied"])
        self.assertEqual(run.call_count, 1)

    def test_duplicate_display_name_blocks_removal(self):
        foreign = dict(self.manifest, id="someone.else")
        for rows in ([self.manifest, foreign], [self.manifest, self.manifest], [foreign]):
            with patch.object(installation, "_run", return_value=json.dumps(rows)) as run:
                with self.assertRaises(ValueError):
                    installation.uninstall_bridge(True)
            self.assertEqual(run.call_count, 1)

    def test_extra_package_payload_rejected(self):
        self.package(extra="../extra.js")
        with self.assertRaises(ValueError):
            installation._validate_package(str(self.ccx), self.manifest)

    def test_changed_payload_rejected(self):
        self.package(changed="evil();")
        with self.assertRaises(ValueError):
            installation._validate_package(str(self.ccx), self.manifest)

    def test_missing_package_blocks_install(self):
        with patch.object(installation, "_run", return_value="[]") as run:
            with self.assertRaises(ValueError):
                installation.install_bridge(True)
        self.assertEqual(run.call_count, 1)

    def test_unsupported_host_blocks_install_but_not_removal(self):
        with patch.object(installation, "discover_applications", return_value=[{"supported": False}]):
            with patch.object(installation, "_run", return_value="[]"):
                with self.assertRaises(ValueError):
                    installation.install_bridge(True, str(self.ccx))
            with patch.object(installation, "_run", side_effect=[json.dumps([self.manifest]), "ok", "[]"]):
                self.assertTrue(installation.uninstall_bridge(True)["removal_verified"])

    def test_absent_installer_is_unknown_not_uninstalled(self):
        with patch.object(installation, "_upia", return_value=None):
            self.assertIsNone(installation.installation_status()["installed"])

    def test_cli_failure_does_not_report_applied(self):
        with patch.object(installation, "_run", side_effect=["[]", RuntimeError("Adobe refused")]):
            with self.assertRaises(RuntimeError):
                installation.install_bridge(True, str(self.ccx))

    def test_confirmation_is_strict_boolean(self):
        for value in ("false", 1, None):
            with self.assertRaises(ValueError):
                installation.install_bridge(value, str(self.ccx))
            with self.assertRaises(ValueError):
                installation.uninstall_bridge(value)

    def test_candidate_build_is_reproducible_and_tracks_payload(self):
        source_root = Path(__file__).resolve().parents[1]
        (self.root / "server").mkdir()
        shutil.copyfile(source_root / "server/installation.py", self.root / "server/installation.py")
        build_spec = importlib.util.spec_from_file_location(
            "adobe_build", source_root.parents[1] / "scripts/build_adobe_packages.py")
        builder = importlib.util.module_from_spec(build_spec)
        build_spec.loader.exec_module(builder)
        output = builder.build_plugin(self.root)
        first = output.read_bytes()
        self.assertEqual(output, self.root / "adobe" / (installation.PLUGIN_ID + ".ccx"))
        self.assertEqual(builder.build_plugin(self.root).read_bytes(), first)
        (self.root / "uxp/main.js").write_text("updated();", encoding="utf8")
        self.assertNotEqual(builder.build_plugin(self.root).read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
