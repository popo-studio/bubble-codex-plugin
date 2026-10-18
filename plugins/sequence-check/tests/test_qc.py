import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'server'))
import qc
import numpy as np
import OpenEXR
from PIL import Image


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def png(self, name, size=(5, 4), colour='red', mode='RGB'):
        Image.new(mode, size, colour).save(self.root / name)

    def exr(self, name, value=1., channels=('R', 'G', 'B')):
        OpenEXR.File({}, {c: np.full((4, 5), value, dtype=np.float32) for c in channels}).write(str(self.root / name))

    def test_gaps_padding_duplicates_expected_ends(self):
        for name in ('shot.001.png', 'shot.1.png', 'shot.003.png'):
            self.png(name)
        result = qc.inspect(str(self.root), 'shot.*', 0, 4)['data'][0]
        self.assertEqual(result['missing_frames'], [0, 2, 4])
        self.assertEqual(len(result['duplicate_numbers']['1']), 2)
        self.assertEqual(result['frames'][1]['same_pixels_as'], 'shot.001.png')

    def test_black_layout_and_corruption(self):
        self.png('x.1.png', colour='black')
        self.png('x.2.png', size=(6, 4))
        (self.root / 'x.3.png').write_bytes(b'corrupt')
        rows = qc.inspect(str(self.root))['data'][0]['frames']
        self.assertTrue(rows[0]['suspected_black'])
        self.assertTrue(rows[1]['layout_mismatch'])
        self.assertEqual(rows[2]['status'], 'error')

    def test_exr_real_decode_channels_nonfinite(self):
        self.exr('x.1.exr', 0.)
        self.exr('x.2.exr', float('nan'), ('R', 'Z'))
        rows = qc.inspect(str(self.root))['data'][0]['frames']
        self.assertEqual(rows[0]['status'], 'decoded')
        self.assertTrue(rows[0]['suspected_black'])
        self.assertTrue(rows[1]['layout_mismatch'])
        self.assertEqual(rows[1]['nonfinite_samples'], 40)

    def test_truncated_exr(self):
        self.exr('x.1.exr')
        p = self.root / 'x.1.exr'
        p.write_bytes(p.read_bytes()[:-20])
        self.assertEqual(qc.inspect(str(self.root))['data'][0]['frames'][0]['status'], 'error')

    def test_multipart_exr(self):
        parts = [OpenEXR.Part({}, {'R': np.ones((3, 4), dtype=np.float32)}, 'beauty'), OpenEXR.Part({}, {'Z': np.ones((3, 4), dtype=np.float32)}, 'depth')]
        OpenEXR.File(parts).write(str(self.root / 'multi.1.exr'))
        row = qc.inspect(str(self.root))['data'][0]['frames'][0]
        self.assertEqual(row['status'], 'decoded')
        self.assertEqual(len(row['parts']), 2)

    def test_no_match_and_invalid_bounds(self):
        self.assertEqual(qc.inspect(str(self.root))['matched_files'], 0)
        for args in [('relative', '*'), (str(self.root), '**/*.exr')]:
            with self.assertRaises(ValueError): qc.collect(*args)
        with self.assertRaises(ValueError): qc.inspect(str(self.root), '*', 1, None)
        with self.assertRaises(ValueError): qc.inspect(str(self.root), '*', 1, 10003)

    def test_budget_and_multipage_unverified(self):
        self.png('x.1.png')
        old = qc.MAX_PIXELS
        try:
            qc.MAX_PIXELS = 1
            self.assertEqual(qc.decode(self.root / 'x.1.png')['status'], 'unverified')
        finally: qc.MAX_PIXELS = old
        a = Image.new('RGB', (4, 4))
        a.save(self.root / 'a.1.tif', save_all=True, append_images=[a])
        self.assertEqual(qc.decode(self.root / 'a.1.tif')['status'], 'unverified')

    def test_nonrecursive_and_symlink_skipped(self):
        (self.root / 'nested').mkdir()
        Image.new('RGB', (2, 2)).save(self.root / 'nested' / 'x.1.png')
        self.assertEqual(qc.collect(str(self.root)), [])

if __name__ == '__main__': unittest.main()
