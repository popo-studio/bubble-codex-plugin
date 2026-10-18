import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('asset_package_core', Path(__file__).parents[1] / 'server/package.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class PackageTests(unittest.TestCase):
    def setUp(self):
        runtime = Path(__file__).parents[1] / '.test-runtime'
        runtime.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=runtime)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / '项目'
        self.project.mkdir()
        self.source = self.project / '场景.ma'
        self.source.write_bytes(b'fixture scene')
        self.dest = self.base / 'delivery'

    def preview(self, paths=None):
        return core.prepare(paths or [str(self.source)], str(self.dest), str(self.project))

    def execute(self, preview=None):
        p = preview or self.preview()
        return core.execute(p['plan'], p['plan_hash'], True)

    def test_real_copy_and_verify_preserves_source(self):
        p = self.preview()
        self.assertEqual(p, self.preview())
        result = self.execute(p)
        self.assertTrue(result['ok'])
        self.assertTrue(result['verification']['ok'])
        self.assertEqual(self.source.read_bytes(), b'fixture scene')
        self.assertEqual((self.dest / 'project/场景.ma').read_bytes(), b'fixture scene')

    def test_explicit_confirmation(self):
        p = self.preview()
        self.assertFalse(core.execute(p['plan'], p['plan_hash'])['ok'])
        self.assertFalse(self.dest.exists())

    def test_changed_source_rejects_before_writes(self):
        p = self.preview()
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.execute(p)
        self.assertFalse(self.dest.exists())

    def test_tampered_plan_rejected(self):
        p = self.preview()
        p['plan']['destination'] = str(self.base / 'other')
        with self.assertRaises(ValueError):
            self.execute(p)

    def test_missing_blocked(self):
        p = self.preview([str(self.source), str(self.project / 'missing.tx')])
        self.assertFalse(p['ready'])
        with self.assertRaises(ValueError):
            self.execute(p)

    def test_existing_destination_never_overwritten(self):
        self.dest.mkdir()
        sentinel = self.dest / 'sentinel'
        sentinel.write_text('keep')
        with self.assertRaises(ValueError):
            self.preview()
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_destination_in_source_rejected(self):
        with self.assertRaises(ValueError):
            core.prepare([str(self.source)], str(self.project / 'delivery'))

    def test_traversal_and_relative_and_ads_rejected(self):
        for p in ('relative.ma', str(self.project / '..' / 'other'), str(self.source) + ':stream'):
            with self.subTest(p=p), self.assertRaises(ValueError):
                core.prepare([p], str(self.dest))

    def test_duplicate_inputs_counted_once(self):
        p = self.preview([str(self.source), str(self.source)])
        self.assertEqual(len(p['plan']['files']), 1)
        self.assertEqual(len(p['plan']['duplicates']), 1)

    def test_tokens_and_external_mapping(self):
        ext = self.base / 'external'
        ext.mkdir()
        for name in ['a.1001.exr', 'a.1002.exr', 'a.0999.exr']:
            (ext / name).write_bytes(b'pixels')
        for token, count in [('<UDIM>', 2), ('####', 3), ('%04d', 3), ('$F4', 3), ('$F', 3)]:
            with self.subTest(token=token):
                p = self.preview([str(ext / ('a.' + token + '.exr'))])
                self.assertEqual(len(p['plan']['files']), count)
                self.assertTrue(all(x['relative'].startswith('external/') for x in p['plan']['files']))

    def test_json_manifest(self):
        m = self.base / 'deps.json'
        m.write_text(json.dumps({'paths': [str(self.source)]}), encoding='utf-8')
        p = core.prepare([], str(self.dest), str(self.project), str(m))
        self.assertTrue(self.execute(p)['ok'])

    def test_verify_tampered_and_missing(self):
        self.execute()
        target = self.dest / 'project/场景.ma'
        target.write_bytes(b'tampered')
        self.assertEqual(core.verify(self.dest)['problems'][0]['issue'], 'hash_or_size_mismatch')
        target.unlink()
        self.assertEqual(core.verify(self.dest)['problems'][0]['issue'], 'missing')

    def test_malicious_manifest_traversal(self):
        self.execute()
        m = self.dest / 'package-manifest.json'
        data = json.loads(m.read_text(encoding='utf-8'))
        data['files'][0]['relative'] = '../项目/场景.ma'
        m.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(ValueError):
            core.verify(self.dest)

    def test_partial_retained_source_untouched(self):
        p = self.preview()
        original = core.verify
        with patch.object(core, 'verify', side_effect=OSError('simulated verification interruption')):
            result = self.execute(p)
        self.assertFalse(result['ok'])
        self.assertTrue(result['partial'])
        self.assertTrue(self.source.exists())
        self.assertTrue(original(self.dest)['ok'])

    def test_file_limit(self):
        with patch.object(core, 'MAX_FILES', 0), self.assertRaises(ValueError):
            self.preview()

    def test_final_verification_failure_is_not_success(self):
        with patch.object(core, 'verify', return_value={'ok': False, 'problems': [{'issue': 'hash_or_size_mismatch'}]}):
            result = self.execute()
        self.assertFalse(result['ok'])
        self.assertFalse(result['verification']['ok'])

    def test_symlink_rejected(self):
        link = self.base / 'link.ma'
        try:
            link.symlink_to(self.source)
        except OSError:
            self.skipTest('Symlink creation not permitted')
        with self.assertRaises(ValueError):
            self.preview([str(link)])


if __name__ == '__main__':
    unittest.main()
