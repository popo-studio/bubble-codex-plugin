"""Bounded, read-only sequence inspection. Suspects are not artistic judgments."""
import fnmatch
import hashlib
import csv
import io
import json
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


def grouped(paths, signed_frames=False):
    groups = {}
    for path in paths:
        match = re.fullmatch(r'(.*?)(-?\d+)(\.[^.]+)' if signed_frames else r'(.*?)(\d+)(\.[^.]+)', path.name)
        if match:
            prefix, digits, suffix = match.groups()
            key = prefix + '{frame}' + suffix
            frame = int(digits)
        else:
            key, frame = path.name, None
        groups.setdefault(key, []).append((frame, path))
    return groups


def discover(directory, pattern='*', signed_frames=False):
    if type(signed_frames) is not bool:
        raise ValueError('signed_frames must be a boolean')
    groups = grouped(collect(directory, pattern), signed_frames)
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


def inspect(directory, pattern='*', expected_start=None, expected_end=None, frame_step=1,
            signed_frames=False, expected_width=None, expected_height=None, required_channels=None):
    if (expected_start is None) != (expected_end is None):
        raise ValueError('provide both expected_start and expected_end')
    if type(frame_step) is not int or not 1 <= frame_step <= 10000 or type(signed_frames) is not bool:
        raise ValueError('frame_step must be an integer 1..10000 and signed_frames a boolean')
    if frame_step != 1 and expected_start is None:
        raise ValueError('Provide both expected endpoints when using a frame step')
    if expected_start is not None and (type(expected_start) is not int or type(expected_end) is not int
            or (expected_start < 0 and not signed_frames) or expected_end < expected_start
            or expected_end - expected_start > 10000 or (expected_end - expected_start) % frame_step):
        raise ValueError('Expected endpoints must be integers, ordered, span <=10000 and align to frame_step; negative numbers require signed_frames=true')
    if (expected_width is None) != (expected_height is None):
        raise ValueError('Provide both expected_width and expected_height')
    if expected_width is not None and (type(expected_width) is not int or type(expected_height) is not int
            or expected_width <= 0 or expected_height <= 0 or expected_width * expected_height > MAX_PIXELS):
        raise ValueError('Expected dimensions must be positive integers within the pixel limit')
    if required_channels is not None and (not isinstance(required_channels, list) or not required_channels
            or len(required_channels) > 128 or any(not isinstance(c, str) or not c or len(c) > 128 for c in required_channels)):
        raise ValueError('required_channels must be a nonempty bounded list of exact channel names')
    groups = grouped(collect(directory, pattern), signed_frames)
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
        missing = [n for n in range(start, end + 1, frame_step) if n not in numbered] if numbered else []
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
                    row['expected_layout_issues'] = []
                    for index, part in enumerate(row['parts']):
                        if expected_width is not None and (part['width'], part['height']) != (expected_width, expected_height):
                            row['expected_layout_issues'].append({'part': index, 'issue': 'dimensions', 'actual': [part['width'], part['height']]})
                    # Required channels apply to the union of EXR parts; per-part
                    # expectations are not inferred from a flat channel-name list.
                    present = {c for part in row['parts'] for c in part['channels']}
                    absent = sorted(set(required_channels or []) - present)
                    if absent:
                        row['expected_layout_issues'].append({'issue': 'missing_channels', 'channels': absent})
            except Exception as exc:
                row.update(status='error', reason=str(exc)[:500])
            records.append(row)
        output.append({'sequence': key, 'expected_range': [start, end] if numbered else None, 'frame_step': frame_step,
            'range_source': 'user' if expected_start is not None else 'observed (cannot detect missing ends)', 'missing_frames': missing,
            'off_step_frames': sorted(n for n in numbered if start <= n <= end and (n-start) % frame_step),
            'duplicate_numbers': {str(n): names for n, names in numbered.items() if len(names) > 1},
            'outside_expected_range': sorted(n for n in numbered if n < start or n > end), 'frames': records})
    return {'ok': True, 'data': output, 'matched_files': sum(len(x['frames']) for x in output), 'coverage': 'Full pixel decode within limits; EXR base level only; deep EXR and multi-page raster unverified. Black/repeated pixels are suspects, not failures. No colour-management or artistic judgment. No matched files is not a pass.'}


def write_report(directory, output_path, pattern='*', expected_start=None, expected_end=None,
                 frame_step=1, signed_frames=False, expected_width=None, expected_height=None,
                 required_channels=None, confirmed=False):
    target = Path(output_path)
    if not target.is_absolute() or '..' in target.parts or target.suffix.lower() not in {'.json', '.csv'}:
        raise ValueError('Choose an absolute NEW .json or .csv report path without parent traversal')
    for part in target.parts[1:]:
        if ':' in part or part.endswith((' ', '.')) or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)', part):
            raise ValueError('Unsupported report path component')
    for item in [target, *target.parents]:
        if os.path.lexists(item) and (item.is_symlink() or getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Report paths cannot contain symlinks/reparse points')
    if target.exists() or not target.parent.is_dir():
        raise ValueError('Report must be NEW with an existing parent directory')
    if type(confirmed) is not bool:
        raise ValueError('confirmed must be a boolean')
    report = inspect(directory, pattern, expected_start, expected_end, frame_step,
                     signed_frames, expected_width, expected_height, required_channels)
    if not report['matched_files']:
        raise ValueError('No matching images; a successful inspection report cannot be written')
    report['input'] = {'directory': str(Path(directory)), 'pattern': pattern, 'signed_frames': signed_frames,
                       'expected_width': expected_width, 'expected_height': expected_height, 'required_channels': required_channels}
    if target.suffix.lower() == '.json':
        text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    else:
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['sequence', 'file', 'frame', 'status', 'details'])
        def cell(value):
            text = str(value) if value is not None else ''
            return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text
        for group in report['data']:
            summary = {k: v for k, v in group.items() if k not in {'sequence', 'frames'}}
            writer.writerow([cell(group['sequence']), '', '', 'sequence_summary', cell(json.dumps(summary, ensure_ascii=False))])
            for row in group['frames']:
                details = {k: v for k, v in row.items() if k not in {'file', 'frame', 'status'}}
                writer.writerow([cell(group['sequence']), cell(row['file']), cell(row['frame']), row['status'], cell(json.dumps(details, ensure_ascii=False))])
        writer.writerow(['', '', '', 'coverage', report['coverage']])
        writer.writerow(['', '', '', 'input', json.dumps(report['input'], ensure_ascii=False)])
        text = stream.getvalue()
    encoded = text.encode('utf-8-sig' if target.suffix.lower() == '.csv' else 'utf-8')
    if len(encoded) > 8 * 1024 * 1024:
        raise ValueError('Report exceeds 8 MiB; narrow the inspected files')
    result = {'ok': True, 'written': False, 'output_path': str(target), 'bytes': len(encoded),
              'matched_files': report['matched_files'], 'sha256': hashlib.sha256(encoded).hexdigest(),
              'note': 'Report records inspection findings; written=true is not a QC pass. Source images are never modified.'}
    if confirmed:
        with target.open('xb') as output:
            output.write(encoded)
        result['written'] = True
    return result
