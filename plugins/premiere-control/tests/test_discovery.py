import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import discovery as d

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)/"discovery"
    def tearDown(self):self.temp.cleanup()
    def publisher(self,enabled=True):return d.Publisher(43210,"x"*44,self.folder,lambda:enabled)
    def test_disabled_never_writes_credentials(self):
        p=self.publisher(False);self.assertFalse(p.publish());self.assertFalse(self.folder.exists())
    def test_private_publish_replace_and_close(self):
        p=self.publisher();self.assertTrue(p.publish());first=json.loads(p.path.read_text());self.assertEqual(first["broker_id"],p.identifier);self.assertEqual(first["port"],43210)
        self.assertTrue(p.publish());p.close();self.assertFalse(p.path.exists())
    def test_protection_failure_never_writes(self):
        p=self.publisher()
        with patch.object(d,"protect_directory",side_effect=OSError("denied")):
            with self.assertRaises(OSError):p.publish()
        self.assertFalse(p.path.exists())
    def test_preexisting_temp_file_not_removed(self):
        p=self.publisher();self.folder.mkdir();temp=p.path.with_suffix(".tmp");temp.write_text("keep")
        with self.assertRaises(FileExistsError):p.publish()
        self.assertEqual(temp.read_text(),"keep")
    def test_uninstall_cleanup_preserves_unknown_files(self):
        p=self.publisher();p.publish();other=self.folder/"user.json";other.write_text("keep")
        with patch.object(d,"runtime_directory",return_value=self.folder):d.cleanup_records()
        self.assertFalse(p.path.exists());self.assertEqual(other.read_text(),"keep")
    def test_two_brokers_do_not_overwrite_each_other(self):
        a=self.publisher();b=self.publisher();a.publish();b.publish();self.assertNotEqual(a.path,b.path);a.close();self.assertTrue(b.path.exists());b.close()
    def test_receipt_revocation_removes_advertisement(self):
        p=self.publisher();p.publish();p.enabled=lambda:False;p.publish();self.assertFalse(p.path.exists())
if __name__=="__main__":unittest.main()
