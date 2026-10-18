"""Bounded, read-only sequence inspection. Suspects are not artistic judgments."""
import fnmatch
import hashlib
import os
from pathlib import Path
import re

import numpy as np
import OpenEXR
from PIL import Image

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.exr'}
MAX_ENTRIES = 10000
MAX_FILES = 1000
MAX_PIXELS = 16777216
MAX_DECODE_BYTES = 268435456
MAX_FILE_BYTES = 536870912
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def collect(directory, pattern='*'):
    root = Path(directory).expanduser()
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('directory must be an existing absolute directory')
    if not pattern or any(c in pattern for c in '/\\') or '**' in pattern:
        raise ValueError('pattern must be a non-recursive filename glob')
    paths = []
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_ENTRIES:
                raise ValueError('directory exceeds 10000 entries; choose a narrower directory')
            if entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in EXTENSIONS and fnmatch.fnmatchcase(entry.name, pattern):
                paths.append(Path(entry.path))
                if len(paths) > MAX_FILES:
                    raise ValueError('selection exceeds 1000 files; narrow pattern or split by directory')
    return sorted(paths)


def grouped(paths):
    groups = {}
    for path in paths:
        match = re.fullmatch(r'(.*?)(\d+)(\.[^.]+)', path.name)
        if match:
            prefix, digits, suffix = match.groups()
            key = prefix + '{frame}' + suffix
            frame = int(digits)
        else:
            key, frame = path.name, None
        groups.setdefault(key, []).append((frame, path))
    return groups


def discover(directory, pattern='*'):
    groups = grouped(collect(directory, pattern))
    return {'ok': True, 'data': [{'sequence': key, 'files': len(items), 'first': min((f for f, _ in items if f is not None), default=None), 'last': max((f for f, _ in items if f is not None), default=None)} for key, items in groups.items()], 'recursive': False}


def _stats(arrays, colour_names):
    digest = hashlib.sha256()
    nonfinite = 0
    black = bool(colour_names)
    for name, array in sorted(arrays.items()):
        digest.update(name.encode())
        digest.update(str((array.shape, array.dtype)).encode())
        # Row chunks bound temporary analysis allocations.
        for start in range(0, len(array), 64):
            chunk = np.ascontiguousarray(array[start:start + 64])
            digest.update(memoryview(chunk).cast('B'))
            finite = np.isfinite(chunk)
            nonfinite += int(chunk.size - np.count_nonzero(finite))
            if name in colour_names and (not finite.all() or np.any(np.abs(chunk.astype(np.float64)) > 1e-6)):
                black = False
    return {'pixel_sha256': digest.hexdigest(), 'nonfinite_samples': nonfinite, 'suspected_black': black, 'black_checked_channels': colour_names}


def decode(path):
    if path.stat().st_size > MAX_FILE_BYTES:
        return {'status': 'unverified', 'reason': 'file exceeds 512 MiB'}
    if path.suffix.lower() == '.exr':
        with OpenEXR.File(str(path), header_only=True, separate_channels=True) as header_file:
            parts = []
            estimated = 0
            if not header_file.parts:
                raise ValueError('decoder returned no EXR headers; refusing unchecked allocation')
            for part in header_file.parts:
                h = part.header
                lo, hi = h['dataWindow']
                width, height = int(hi[0]) - int(lo[0]) + 1, int(hi[1]) - int(lo[1]) + 1
                channels = sorted(c.name for c in h['channels'])
                parts.append({'width': width, 'height': height, 'channels': channels, 'data_window': [list(map(int, lo)), list(map(int, hi))]})
                if h.get('type') in (OpenEXR.deepscanline, OpenEXR.deeptile):
                    return {'status': 'unverified', 'reason': 'deep EXR pixel decode is unsupported', 'parts': parts}
                if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                    return {'status': 'unverified', 'reason': 'EXR exceeds pixel limit', 'parts': parts}
                estimated += width * height * len(channels) * 4
            if estimated > MAX_DECODE_BYTES or len(parts) > 32:
                return {'status': 'unverified', 'reason': 'EXR exceeds decoded channel budget', 'parts': parts}
        with OpenEXR.File(str(path), separate_channels=True) as image:
            arrays = {f'{i}:{name}': ch.pixels for i, part in enumerate(image.parts) for name, ch in part.channels.items()}
            colours = [name for name in arrays if name.split(':', 1)[1] in ('R', 'G', 'B', 'Y')]
            return {'status': 'decoded', 'parts': parts, **_stats(arrays, colours)}
    with Image.open(path) as image:
        width, height = image.size
        if width * height > MAX_PIXELS or width * height * max(len(image.getbands()), 4) * 4 > MAX_DECODE_BYTES:
            return {'status': 'unverified', 'reason': 'raster exceeds decoded pixel budget'}
        if getattr(image, 'n_frames', 1) != 1:
            return {'status': 'unverified', 'reason': 'multi-page/animated raster unsupported'}
        image.verify()
    with Image.open(path) as image:
        image.load()
        mode = image.mode
        if mode == 'P':
            image = image.convert('RGBA')
        array = np.asarray(image)
        bands = list(image.getbands())
        arrays = {band: array[..., i] for i, band in enumerate(bands)} if array.ndim == 3 else {bands[0]: array}
        return {'status': 'decoded', 'parts': [{'width': width, 'height': height, 'channels': bands, 'mode': mode}], **_stats(arrays, [b for b in bands if b in ('R', 'G', 'B', 'L', 'I', 'F') or b.startswith('I;')])}


def inspect(directory, pattern='*', expected_start=None, expected_end=None):
    if (expected_start is None) != (expected_end is None):
        raise ValueError('provide both expected_start and expected_end')
    if expected_start is not None and (expected_start < 0 or expected_end < expected_start or expected_end - expected_start > 10000):
        raise ValueError('expected range must be nonnegative, ordered, and at most 10001 frames')
    groups = grouped(collect(directory, pattern))
    output = []
    for key, items in groups.items():
        numbered = {}
        for frame, path in items:
            if frame is not None:
                numbered.setdefault(frame, []).append(path.name)
        start = expected_start if expected_start is not None else min(numbered, default=0)
        end = expected_end if expected_end is not None else max(numbered, default=-1)
        if end - start > 10000:
            raise ValueError('inferred span exceeds 10001 frames; specify a bounded expected range')
        missing = [n for n in range(start, end + 1) if n not in numbered] if numbered else []
        records, hashes, baseline = [], {}, None
        for frame, path in sorted(items, key=lambda item: (item[0] if item[0] is not None else -1, item[1].name)):
            row = {'file': path.name, 'frame': frame}
            try:
                row.update(decode(path))
                if row['status'] == 'decoded':
                    signature = row['parts']
                    row['layout_mismatch'] = baseline is not None and signature != baseline
                    if baseline is None:
                        baseline = signature
                    digest = row['pixel_sha256']
                    row['same_pixels_as'] = hashes.get(digest)
                    hashes.setdefault(digest, path.name)
            except Exception as exc:
                row.update(status='error', reason=str(exc)[:500])
            records.append(row)
        output.append({'sequence': key, 'expected_range': [start, end] if numbered else None, 'range_source': 'user' if expected_start is not None else 'observed (cannot detect missing ends)', 'missing_frames': missing, 'duplicate_numbers': {str(n): names for n, names in numbered.items() if len(names) > 1}, 'outside_expected_range': sorted(n for n in numbered if n < start or n > end), 'frames': records})
    return {'ok': True, 'data': output, 'matched_files': sum(len(x['frames']) for x in output), 'coverage': 'Full pixel decode within limits; EXR base level only; deep EXR and multi-page raster unverified. Black/repeated pixels are suspects, not failures. No colour-management or artistic judgment. No matched files is not a pass.'}
