"""Bounded, explicit dependency collection. Never edits scene files or sources."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_FILES = 10000
MAX_BYTES = 100 * 1024**3
MAX_JSON = 8 * 1024**2
TOKEN = re.compile(r'<UDIM>|<udim>|%0([1-9][0-9]?)d|#+|\$F([1-9][0-9]?)?')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def safe(path, exists=True):
    p = Path(path)
    if not p.is_absolute() or '..' in p.parts:
        raise ValueError('Absolute paths without .. are required')
    for part in p.parts[1:]:
        if ':' in part or part.endswith((' ', '.')) or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)', part):
            raise ValueError('Unsupported Windows path component')
    for item in [p, *p.parents]:
        try:
            s = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlinks and reparse points are not supported: ' + str(item))
    if exists and not p.exists():
        raise FileNotFoundError(str(p))
    return p


def fingerprint(path):
    p = safe(path)
    before = p.stat()
    if not p.is_file() or before.st_size > MAX_BYTES:
        raise ValueError('Expected a regular file within the byte limit')
    h = hashlib.sha256()
    with p.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Source changed during open')
        read_bytes = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            read_bytes += len(chunk)
            if read_bytes > before.st_size:
                raise ValueError('Source grew while hashing')
            h.update(chunk)
    after = safe(p).stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Source changed while hashing')
    return {'size': before.st_size, 'mtime_ns': before.st_mtime_ns, 'sha256': h.hexdigest()}


def expand(path):
    p = Path(path)
    if not TOKEN.search(p.name):
        p = safe(p, False)
        return [p] if p.is_file() else []
    if '..' in p.parts or not p.is_absolute():
        raise ValueError('Absolute paths without .. are required')
    safe(p.parent)
    expression = ''
    end = 0
    for m in TOKEN.finditer(p.name):
        expression += re.escape(p.name[end:m.start()])
        token = m.group()
        expression += (r'1[0-9]{3}' if token.lower() == '<udim>' else r'[0-9]{' + str(int(m.group(1) or m.group(2) or len(token)) if token != '$F' else 1) + '}' if token != '$F' else r'[0-9]+')
        end = m.end()
    expression += re.escape(p.name[end:])
    matches = []
    with os.scandir(p.parent) as entries:
        for count, entry in enumerate(entries):
            if count >= MAX_FILES * 10:
                raise ValueError('Directory scan limit exceeded')
            if re.fullmatch(expression, entry.name):
                matches.append(safe(entry.path))
                if len(matches) > MAX_FILES:
                    raise ValueError('File count limit exceeded')
    return sorted(matches, key=lambda x: str(x).casefold())


def prepare(paths, destination, project_root=None, dependency_manifest=None):
    if len(paths) > MAX_FILES or not all(isinstance(p, str) for p in paths):
        raise ValueError('paths must be a bounded list of strings')
    inputs = list(paths)
    if dependency_manifest:
        manifest = safe(dependency_manifest)
        if manifest.stat().st_size > MAX_JSON:
            raise ValueError('Dependency manifest too large')
        data = json.loads(manifest.read_text(encoding='utf-8-sig'))
        entries = data.get('paths') if isinstance(data, dict) else None
        if not isinstance(entries, list) or len(entries) + len(inputs) > MAX_FILES or not all(isinstance(x, str) for x in entries):
            raise ValueError('Dependency manifest must contain paths: [absolute path strings]')
        inputs += entries
    if not inputs:
        raise ValueError('At least one explicit dependency is required')
    dest = safe(destination, False)
    if dest.exists():
        raise ValueError('Destination must be NEW; overwrites are never allowed')
    safe(dest.parent)
    root = safe(project_root) if project_root else None
    if root and (not root.is_dir() or dest.is_relative_to(root)):
        raise ValueError('Destination must be outside the project root')
    files, missing, duplicates, seen, targets = [], [], [], {}, set()
    total = 0
    for value in inputs:
        matches = expand(value)
        if not matches:
            missing.append(value)
        for src in matches:
            key = str(src).casefold()
            if key in seen:
                if not os.path.samefile(src, seen[key]):
                    raise ValueError('Distinct source paths collide ignoring case')
                duplicates.append(str(src))
                continue
            seen[key] = src
            if dest.is_relative_to(src.parent):
                raise ValueError('Destination cannot be inside a source directory')
            relative = Path('project') / src.relative_to(root) if root and src.is_relative_to(root) else Path('external') / hashlib.sha256(str(src.parent).encode()).hexdigest()[:16] / src.name
            target_key = relative.as_posix().casefold()
            if target_key in targets:
                raise ValueError('Case-insensitive destination collision')
            targets.add(target_key)
            meta = fingerprint(src)
            total += meta['size']
            if total > MAX_BYTES or len(files) >= MAX_FILES:
                raise ValueError('Package resource limit exceeded')
            files.append({'source': str(src), 'relative': relative.as_posix(), **meta})
    body = {'version': 1, 'paths': paths, 'dependency_manifest': dependency_manifest, 'destination': str(dest), 'project_root': str(root) if root else None,
            'files': sorted(files, key=lambda f: f['relative']), 'missing': sorted(set(missing)), 'duplicates': sorted(set(duplicates)), 'total_bytes': total,
            'coverage': 'Only supplied paths; token matches do not prove expected frame/UDIM completeness. No scene parsing or path rewriting.'}
    if len(json.dumps(body, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_JSON:
        raise ValueError('Preview manifest exceeds the 8 MiB limit')
    return {'ok': True, 'plan': body, 'plan_hash': digest(body), 'ready': not missing and bool(files)}


def execute(plan, plan_hash, confirmed=False):
    if not confirmed:
        return {'ok': False, 'error': 'Explicit confirmation of the displayed plan is required; no files written'}
    if digest(plan) != plan_hash:
        raise ValueError('Plan hash mismatch')
    fresh = prepare(plan['paths'], plan['destination'], plan['project_root'], plan['dependency_manifest'])
    if fresh['plan_hash'] != plan_hash or not fresh['ready']:
        raise ValueError('Plan changed or dependencies missing; preview again')
    dest = safe(plan['destination'], False)
    safe(dest.parent)
    dest.mkdir(exist_ok=False)
    completed = []
    try:
        for entry in plan['files']:
            src = safe(entry['source'])
            if fingerprint(src) != {k: entry[k] for k in ('size', 'mtime_ns', 'sha256')}:
                raise ValueError('Source changed after preview')
            out = safe(dest / entry['relative'], False)
            out.parent.mkdir(parents=True, exist_ok=True)
            safe(out.parent)
            h = hashlib.sha256()
            with src.open('rb') as source, out.open('xb') as target:
                copied = 0
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    copied += len(chunk)
                    if copied > entry['size']:
                        raise ValueError('Source grew during copy')
                    target.write(chunk)
                    h.update(chunk)
            if copied != entry['size'] or h.hexdigest() != entry['sha256']:
                raise ValueError('Source changed during copy')
            completed.append(entry['relative'])
        manifest = {'version': 1, 'plan_hash': plan_hash, 'coverage': plan['coverage'], 'files': plan['files']}
        safe(dest / 'package-manifest.json', False)
        with (dest / 'package-manifest.json').open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
        verification = verify(str(dest))
        return {'ok': verification['ok'], 'destination': str(dest), 'copied_files': len(completed), 'verification': verification}
    except Exception as exc:
        return {'ok': False, 'partial': True, 'destination': str(dest), 'completed': completed,
                'error': str(exc), 'recovery': 'Partial destination retained; inspect it and choose a NEW destination for retry. No source files deleted.'}


def manifest_entries(destination):
    dest = safe(destination)
    path = safe(dest / 'package-manifest.json')
    if path.stat().st_size > MAX_JSON:
        raise ValueError('Manifest too large')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict):
        raise ValueError('Invalid package manifest')
    entries = manifest.get('files')
    if manifest.get('version') != 1 or not isinstance(entries, list) or not entries or len(entries) > MAX_FILES:
        raise ValueError('Invalid package manifest')
    seen, total = set(), 0
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('relative'), str):
            raise ValueError('Invalid manifest entry')
        rel = Path(entry['relative'])
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] not in ('project', 'external') or str(rel).casefold() in seen:
            raise ValueError('Unsafe or duplicate manifest relative path')
        seen.add(str(rel).casefold())
        if type(entry.get('size')) is not int or entry['size'] < 0 or not isinstance(entry.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            raise ValueError('Invalid manifest size or SHA256')
        total += entry['size']
        if total > MAX_BYTES:
            raise ValueError('Manifest byte limit exceeded')
        safe(dest / rel, False)
    return dest, entries


def verify(destination, include_extras=False):
    if type(include_extras) is not bool:
        raise ValueError('include_extras must be a boolean')
    dest, entries = manifest_entries(destination)
    problems, total = [], 0
    for entry in entries:
        rel = Path(entry['relative'])
        p = safe(dest / rel, False)
        if not p.is_file():
            problems.append({'path': str(rel), 'issue': 'missing'})
            continue
        total += p.stat().st_size
        if total > MAX_BYTES:
            raise ValueError('Verification byte limit exceeded')
        actual = fingerprint(p)
        if actual['size'] != entry['size'] or actual['sha256'] != entry['sha256']:
            problems.append({'path': str(rel), 'issue': 'hash_or_size_mismatch'})
    extras = []
    if include_extras:
        expected = {Path(e['relative']).as_posix().casefold() for e in entries} | {'package-manifest.json'}
        pending, scanned = [dest], 0
        while pending:
            current = safe(pending.pop())
            with os.scandir(current) as contents:
                for item in contents:
                    scanned += 1
                    if scanned > MAX_FILES * 4:
                        raise ValueError('Strict verification directory entry limit exceeded')
                    path = safe(item.path)
                    if path.is_dir():
                        pending.append(path)
                    elif path.is_file():
                        relative = path.relative_to(dest).as_posix()
                        if relative.casefold() not in expected:
                            extras.append(relative)
                    else:
                        raise ValueError('Unsupported filesystem entry')
        problems.extend({'path': p, 'issue': 'unexpected_file'} for p in sorted(extras))
    return {'ok': not problems, 'checked_files': len(entries), 'problems': problems, 'extra_files': sorted(extras),
            'extras_checked': include_extras, 'coverage': ('Manifest entries hashed; additional files enumerated, not hashed. ' if include_extras else 'Manifest entries only; extra files not checked. ') + 'Hashes detect accidental changes, not malicious manifest replacement. Empty directories and scene portability are not verified.'}


def compare(reference, candidate):
    left_root, left_entries = manifest_entries(reference)
    right_root, right_entries = manifest_entries(candidate)
    def index(entries):
        return {Path(e['relative']).as_posix().casefold(): e for e in entries}
    left, right = index(left_entries), index(right_entries)
    added = [right[k]['relative'] for k in sorted(right.keys() - left.keys())]
    removed = [left[k]['relative'] for k in sorted(left.keys() - right.keys())]
    changed, unchanged = [], 0
    for key in sorted(left.keys() & right.keys()):
        a, b = left[key], right[key]
        if (a['size'], a['sha256']) != (b['size'], b['sha256']):
            changed.append({'path': b['relative'], 'before_size': a['size'], 'after_size': b['size'],
                            'before_sha256': a['sha256'], 'after_sha256': b['sha256']})
        else:
            unchanged += 1
    return {'ok': True, 'reference': str(left_root), 'candidate': str(right_root), 'added': added, 'removed': removed,
            'changed': changed, 'unchanged_count': unchanged, 'identical_manifests': not (added or removed or changed),
            'contents_verified': False, 'coverage': 'Compares declared relative paths, sizes and SHA256 only. Run package_verify on both deliveries to verify actual files. External parent mapping changes appear as added/removed paths. No files modified.'}
