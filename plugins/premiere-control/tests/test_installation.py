import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import installation as m
import discovery

class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.target=Path(self.tmp.name)/"extensions"/m.PLUGIN_ID
        self.discovery_patch=patch.object(discovery,"runtime_directory",return_value=Path(self.tmp.name)/"discovery");self.discovery_patch.start()
        self.target_patch=patch.object(m,"_target",return_value=self.target);self.target_patch.start()
        self.apps=patch.object(m,"discover_applications",return_value=[{"version":"26.0","supported":True}]);self.apps.start()
    def tearDown(self):
        self.apps.stop();self.target_patch.stop();self.discovery_patch.stop();self.tmp.cleanup()
    def test_release_exact(self):
        release,source=m._release();self.assertEqual(m._hashes(source),release["files"])
    def test_preview_no_changes(self):
        self.assertTrue(m.install_bridge()["preview"]);self.assertFalse(self.target.exists())
    def test_install_update_uninstall(self):
        self.assertTrue(m.install_bridge(True)["ok"]);self.assertTrue(m.installation_status()["data"]["installed"])
        self.assertTrue(m.install_bridge(True)["ok"]);self.assertTrue(m.uninstall_bridge(True)["ok"])
        self.assertFalse(self.target.exists());self.assertFalse(m._receipt_path(self.target).exists())
    def test_managed_old_receipt_upgrades(self):
        self.assertTrue(m.install_bridge(True)['ok']);rp=m._receipt_path(self.target);r=json.loads(rp.read_text(encoding='utf-8'));r['version']='0.3.0';rp.write_text(json.dumps(r))
        self.assertTrue(m.install_bridge(True)['ok']);self.assertEqual(json.loads(rp.read_text(encoding='utf-8'))['version'],'0.4.0')
    def test_old_host_refused(self):
        with patch.object(m,"discover_applications",return_value=[{"supported":False,"version":"15.0"}]):
            self.assertEqual(m.install_bridge(True)["error"]["code"],"unsupported_version")
        self.assertFalse(self.target.exists())
    def test_unknown_extension_preserved(self):
        self.target.mkdir(parents=True);(self.target/"user.txt").write_text("keep")
        self.assertFalse(m.install_bridge(True)["ok"]);self.assertFalse(m.uninstall_bridge(True)["ok"])
        self.assertEqual((self.target/"user.txt").read_text(),"keep")
    def test_modified_owned_file_preserved(self):
        self.assertTrue(m.install_bridge(True)["ok"]);(self.target/"host.jsx").write_text("user edit")
        self.assertFalse(m.uninstall_bridge(True)["ok"]);self.assertFalse(m.install_bridge(True)["ok"])
        self.assertEqual((self.target/"host.jsx").read_text(),"user edit")
    def test_added_file_preserved(self):
        m.install_bridge(True);(self.target/"user.txt").write_text("keep")
        self.assertFalse(m.uninstall_bridge(True)["ok"])
    def test_receipt_commit_failure_rolls_back(self):
        self.assertTrue(m.install_bridge(True)["ok"]);before=m._hashes(self.target)
        with patch.object(m.os,"replace",side_effect=OSError("simulated receipt failure")):
            self.assertFalse(m.install_bridge(True)["ok"])
        self.assertEqual(m._hashes(self.target),before);self.assertTrue(m.installation_status()["data"]["installed"])
    def test_arbitrary_package_refused(self):
        self.assertFalse(m.install_bridge(True,"C:/other.zxp")["ok"])

if __name__=="__main__":unittest.main()
