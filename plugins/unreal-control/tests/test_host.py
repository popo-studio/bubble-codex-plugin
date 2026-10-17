from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import bubble_unreal_bridge as bridge


class HostTests(unittest.TestCase):
    def test_commandlet_and_game_modes_are_not_interactive(self):
        for command in ("-run=pythonscript", "-RUN=Cook", "-game", "-server", "-unattended"):
            unreal = types.SimpleNamespace(is_editor=lambda: True,
                                           SystemLibrary=types.SimpleNamespace(get_command_line=lambda: command))
            with patch.dict(sys.modules, {"unreal": unreal}):
                self.assertFalse(bridge._host.is_interactive())

    def test_registry_scan_does_not_report_missing_packages_prematurely(self):
        registry = types.SimpleNamespace(is_loading_assets=lambda: True)
        unreal = types.SimpleNamespace(AssetRegistryHelpers=types.SimpleNamespace(get_asset_registry=lambda: registry))
        with patch.dict(sys.modules, {"unreal": unreal}), patch.object(bridge._host, "scene_info", return_value={"path": "map.umap", "map_package": "/Game/Map"}):
            report = bridge._host.inspect_scene()
            self.assertFalse(report["complete"])
            self.assertEqual(report["dependencies"], [])

    def test_direct_dependencies_distinguish_script_and_unresolved_packages(self):
        registry = types.SimpleNamespace(is_loading_assets=lambda: False,
                                         get_dependencies=lambda name, opts: ["/Script/Engine", "/Game/Present", "/Game/Missing"],
                                         get_assets_by_package_name=lambda name: [object()] if name in ("/Game/Present", "/Game/Map") else [])
        unreal = types.SimpleNamespace(AssetRegistryHelpers=types.SimpleNamespace(get_asset_registry=lambda: registry),
                                      AssetRegistryDependencyOptions=lambda **kwargs: kwargs)
        with patch.dict(sys.modules, {"unreal": unreal}), patch.object(bridge._host, "scene_info", return_value={"path": "map.umap", "map_package": "/Game/Map"}):
            report = bridge._host.inspect_scene()
            self.assertEqual(report["unresolved_packages"], ["/Game/Missing"])
            self.assertEqual(len(report["dependencies"]), 2)
            self.assertTrue(report["complete"])

    def test_unknown_root_package_cannot_report_complete(self):
        registry = types.SimpleNamespace(is_loading_assets=lambda: False, get_assets_by_package_name=lambda name: [])
        unreal = types.SimpleNamespace(AssetRegistryHelpers=types.SimpleNamespace(get_asset_registry=lambda: registry))
        with patch.dict(sys.modules, {"unreal": unreal}), patch.object(bridge._host, "scene_info", return_value={"path": "", "map_package": ""}):
            report = bridge._host.inspect_scene("/Game/DoesNotExist")
            self.assertFalse(report["complete"])
            self.assertIn("not registered", report["warning"])

    def test_unsaved_scene_requires_explicit_saved_package(self):
        with patch.dict(sys.modules, {"unreal": types.SimpleNamespace()}), patch.object(bridge._host, "scene_info", return_value={"path": "", "map_package": "/Temp/Untitled"}):
            with self.assertRaises(ValueError):
                bridge._host.inspect_scene()

    def test_python_output_and_error(self):
        unreal = types.SimpleNamespace(LevelEditorSubsystem=object(), get_editor_subsystem=lambda cls: types.SimpleNamespace(is_in_play_in_editor=lambda: False))
        with patch.dict(sys.modules, {"unreal": unreal}):
            self.assertEqual(bridge.dispatch("execute_python", {"code": "result = 42"})["result"], 42)
            self.assertFalse(bridge.dispatch("execute_python", {"code": "raise RuntimeError('oops')"})["ok"])

    def test_play_in_editor_rejects_script_before_execution(self):
        unreal = types.SimpleNamespace(LevelEditorSubsystem=object(), get_editor_subsystem=lambda cls: types.SimpleNamespace(is_in_play_in_editor=lambda: True))
        with patch.dict(sys.modules, {"unreal": unreal}):
            with self.assertRaisesRegex(RuntimeError, "Stop Play In Editor"):
                bridge.dispatch("execute_python", {"code": "raise AssertionError('must never run')"})
