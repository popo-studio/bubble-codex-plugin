"""Worker snapshots remain executable after an isolated package copy is removed."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class LifecycleTests(unittest.TestCase):
    def test_source_removal_preserves_worker_and_status(self):
        root = Path(__file__).resolve().parents[1]
        scratch = root / ".test-runtime"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            source = Path(directory) / "package"
            shutil.copytree(root / "server", source, ignore=shutil.ignore_patterns("__pycache__"))
            code = r'''
import importlib.util, json, pathlib, shutil, sys
from unittest.mock import patch
source = pathlib.Path(sys.argv[1]).resolve()
assert source.parent == pathlib.Path(sys.argv[2]).resolve()
sys.path.insert(0,str(source))
import main
shutil.rmtree(source)
assert not source.exists()
assert main.resolve_setup_status()['ok']
assert main.resolve_uninstall_bridge()['data']['removed_files']==[]
row={'session_id':'-1:nonexistent','pid':-1,'status':'available'}
with patch.object(main,'discover',return_value=[row]):
    result=main.call('project_info',row['session_id'])
# The separate real worker runs after source deletion, rejects the fake target,
# and never loads the SDK or connects to an actual Resolve instance.
assert result['error']['code']=='operation_failed',result
print(json.dumps({'ok':True,'source_removed':True,'worker_result':result['error']['code']}))
'''
            result = subprocess.run([sys.executable, "-B", "-c", code, str(source), directory], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"source_removed": true', result.stdout)


if __name__ == "__main__": unittest.main()
