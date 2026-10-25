import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import installation as m

class InstallTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'scripts'
 def tearDown(self):self.tmp.cleanup()
 def test_preview_no_writes(self):self.assertTrue(m.install_bridge(str(self.path))['ok']);self.assertFalse(self.path.exists())
 def test_install_update_uninstall_preserves_unknown(self):
  self.assertTrue(m.install_bridge(str(self.path),True)['ok']);extra=self.path/'keep.py';extra.write_text('keep');self.assertTrue(m.install_bridge(str(self.path),True)['ok']);self.assertTrue(m.uninstall_bridge(str(self.path),True)['ok']);self.assertEqual(extra.read_text(),'keep')
 def test_modified_owned_preserved(self):
  m.install_bridge(str(self.path),True);p=self.path/'startup/bubble_blender.py';p.write_text('custom');self.assertFalse(m.install_bridge(str(self.path),True)['ok']);self.assertFalse(m.uninstall_bridge(str(self.path),True)['ok']);self.assertEqual(p.read_text(),'custom')
 def test_unknown_collision(self):
  p=self.path/'startup/bubble_blender.py';p.parent.mkdir(parents=True);p.write_text('foreign');self.assertFalse(m.install_bridge(str(self.path),True)['ok']);self.assertEqual(p.read_text(),'foreign')
 def test_receipt_failure_rolls_back(self):
  real=m._atomic_write
  def write(p,data):
   if p.name=='installation.json':raise OSError('fixture failure')
   real(p,data)
  with patch.object(m,'_atomic_write',side_effect=write):self.assertFalse(m.install_bridge(str(self.path),True)['ok'])
  self.assertFalse((self.path/'startup/bubble_blender.py').exists())
 def test_lock_blocks(self):
  self.path.mkdir();(self.path/'.bubble-blender-install.lock').write_text('lock');self.assertFalse(m.install_bridge(str(self.path),True)['ok']);self.assertFalse((self.path/'startup').exists())
 def test_versions(self):self.assertTrue(m.supported_profile('4.5'));self.assertTrue(m.supported_profile('5.2'));self.assertFalse(m.supported_profile('4.4'));self.assertFalse(m.supported_profile('../5.2'))

 def test_installer_payload_survives_source_removal(self):
  with patch.object(m,'ROOT',Path(self.tmp.name)/'deleted-package'):
   self.assertTrue(m.install_bridge(str(self.path),True)['ok'])
