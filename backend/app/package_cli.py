"""Portable package integrity and CLI source, copied verbatim as run.py.

Standard library only at import. Native execution is deliberately lazy.
No platform API, database, framework or app imports belong in this file.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

PROTOCOL = 'edgevision-python-onnx-v1'
TARGET = 'linux-x86_64-cpython312-cpu'
MAX_MODEL = 128 * 1024**2
MAX_SMALL = 1024**2
MAX_TOTAL = 144 * 1024**2
MEMBERS = tuple(sorted(('model.onnx', 'run.py', 'delivery_infer.py', 'requirements.lock', 'README.md',
                        'example.png', 'LICENSE', 'LICENSE_SCOPE.md', 'THIRD_PARTY_NOTICES.md', 'MODEL_NOTICE.md')))


def fail():
    raise ValueError('PACKAGE_BUNDLE_INVALID')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _object(value, names):
    if type(value) is not dict or set(value) != set(names): fail()


def _sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None: fail()


def _integer(value, maximum):
    if type(value) is not int or not 0 < value <= maximum: fail()


def validate_manifest(value: object) -> dict:
    _object(value, ('schema_version', 'protocol', 'image_protocol', 'target', 'classes', 'source', 'template', 'members'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1: fail()
    if (value['protocol'], value['image_protocol'], value['target']) != (PROTOCOL, 'detection-image-v1', TARGET): fail()
    classes = value['classes']
    if type(classes) is not list or not 1 <= len(classes) <= 1000 or any(type(v) is not str or not 1 <= len(v) <= 128 for v in classes): fail()
    source = value['source']
    _object(source, ('onnx_artifact_id', 'export_job_id', 'parent_artifact_id', 'sha256', 'size_bytes', 'metadata_sha256'))
    for key in ('onnx_artifact_id', 'export_job_id', 'parent_artifact_id'):
        if type(source[key]) is not str: fail()
        try:
            if str(UUID(source[key])) != source[key]: fail()
        except (ValueError, AttributeError): fail()
    _sha(source['sha256']); _sha(source['metadata_sha256']); _integer(source['size_bytes'], MAX_MODEL)
    template = value['template']
    _object(template, ('template_sha256', 'core_sha256', 'lock_sha256'))
    for field in template.values(): _sha(field)
    members = value['members']
    if type(members) is not list or len(members) != len(MEMBERS): fail()
    for entry in members:
        _object(entry, ('path', 'size_bytes', 'sha256'))
        if type(entry['path']) is not str or entry['path'] not in MEMBERS: fail()
        _integer(entry['size_bytes'], MAX_MODEL if entry['path'] == 'model.onnx' else MAX_SMALL)
        _sha(entry['sha256'])
    if [v['path'] for v in members] != list(MEMBERS) or sum(v['size_bytes'] for v in members) > MAX_TOTAL: fail()
    by_name = {v['path']: v for v in members}
    if (source['sha256'], source['size_bytes']) != (by_name['model.onnx']['sha256'], by_name['model.onnx']['size_bytes']): fail()
    if template['core_sha256'] != by_name['delivery_infer.py']['sha256'] or template['lock_sha256'] != by_name['requirements.lock']['sha256']: fail()
    if template['template_sha256'] != digest([v for v in members if v['path'] != 'model.onnx']): fail()
    # No caller-owned nested references or unknown fields pass this boundary.
    return json.loads(canonical(value))


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result: fail()
        result[key] = value
    return result


def parse_manifest(raw: bytes) -> dict:
    if not 0 < len(raw) <= MAX_SMALL: fail()
    def invalid(_): fail()
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)
        return validate_manifest(value)
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        fail()


def verified_file(path: Path, limit: int, expected=None, destination=None, capture=False):
    """Read/hash and optional exclusive copy from one verified descriptor."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode): fail()
    _integer(before.st_size, limit)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    sink = None
    try:
        with os.fdopen(descriptor, 'rb') as source:
            opened = os.fstat(source.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size): fail()
            if expected is not None and opened.st_size != expected['size_bytes']: fail()
            if destination is not None: sink = destination.open('xb')
            remaining = opened.st_size; checksum = sha256(); chunks = []
            while remaining:
                block = source.read(min(1024**2, remaining))
                if not block: fail()
                remaining -= len(block); checksum.update(block)
                if sink is not None: sink.write(block)
                if capture: chunks.append(block)
            if source.read(1): fail()
            actual = checksum.hexdigest()
            if expected is not None and actual != expected['sha256']: fail()
            if sink is not None: sink.flush(); os.fsync(sink.fileno())
            return (opened.st_size, actual, b''.join(chunks) if capture else None)
    finally:
        if sink is not None: sink.close()


def verify_package(root: Path) -> dict:
    if not stat.S_ISDIR(root.lstat().st_mode): fail()
    names = set()
    for child in root.iterdir():
        names.add(child.name)
        if len(names) > 11: fail()
    if names != set(MEMBERS) | {'manifest.json'}: fail()
    _, _, raw = verified_file(root / 'manifest.json', MAX_SMALL, capture=True)
    value = parse_manifest(raw)
    for entry in value['members']:
        verified_file(root / entry['path'], MAX_MODEL if entry['path'] == 'model.onnx' else MAX_SMALL, entry)
    return value


def _runtime(root, manifest):
    import platform
    import sys
    from importlib import metadata
    if sys.version_info[:2] != (3, 12) or platform.system() != 'Linux' or platform.machine() != 'x86_64': fail()
    libc, version = platform.libc_ver()
    try:
        if libc != 'glibc' or tuple(int(v) for v in version.split('.')[:2]) < (2, 28): fail()
    except ValueError: fail()
    lock_entry = next(v for v in manifest['members'] if v['path'] == 'requirements.lock')
    _, _, lock = verified_file(root/'requirements.lock', MAX_SMALL, lock_entry, capture=True)
    lines = lock.decode('ascii').splitlines()
    if len(lines) != 9: fail()
    for line in lines:
        match = re.fullmatch(r'([A-Za-z0-9_]+)==([A-Za-z0-9.+]+) --hash=sha256:[0-9a-f]{64}', line)
        if match is None or metadata.version(match[1]) != match[2]: fail()


def _load_core(content):
    # Only bytes just fingerprinted against the manifest are compiled; neither
    # sys.path nor import-by-filename can substitute an unchecked sibling module.
    import types
    module = types.ModuleType('edgevision_portable_core')
    exec(compile(content, '<verified-delivery-infer>', 'exec'), module.__dict__)
    return module


def execute(root, image, declared_format, confidence=.25, iou=.45):
    """Return result, preview and full raw tensor for independent equivalence checks.

    Raw tensor is not written by the CLI and no platform integration is imported.
    One process owns one ORT initialization, following the shared core policy.
    """
    import math
    import tempfile
    if declared_format not in {'png', 'jpeg'} or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in (confidence, iou)): fail()
    manifest = verify_package(root)
    _runtime(root, manifest)
    entries = {v['path']: v for v in manifest['members']}
    _, _, core_bytes = verified_file(root/'delivery_infer.py', MAX_SMALL, entries['delivery_infer.py'], capture=True)
    with tempfile.TemporaryDirectory(prefix='edgevision-infer-') as temporary:
        private = Path(temporary)
        verified_file(root/'model.onnx', MAX_MODEL, entries['model.onnx'], destination=private/'model.onnx')
        image_size, image_sha, _ = verified_file(image, 50*1024**2, destination=private/'image')
        core = _load_core(core_bytes)
        rgb, decoded = core.decode_image(private/'image', declared_format)
        tensor, geometry = core.preprocess(rgb)
        infer, versions = core.load_onnx(private/'model.onnx', manifest['classes'])
        raw = infer(tensor)
        detections = core.postprocess(raw, manifest['classes'], geometry, confidence, iou)
        preview, preview_size = core.preview_png(rgb)
    result = {'schema_version': 1, 'protocol': 'detection-image-v1', 'backend': 'onnx',
              'model_sha256': manifest['source']['sha256'], 'template': manifest['template'], 'image_sha256': image_sha,
              'image_size_bytes': image_size, 'decoded': decoded, 'geometry': geometry,
              'confidence': confidence, 'iou': iou, 'detections': detections['detections'], 'counts': detections['counts'],
              'classes': manifest['classes'], 'provider': 'CPUExecutionProvider', 'runtime': versions,
              'raw_sha256': sha256(raw).hexdigest(), 'raw_elements': len(raw)//4,
              'preview': {'width': preview_size[0], 'height': preview_size[1], 'size_bytes': len(preview), 'sha256': sha256(preview).hexdigest()}}
    if len(canonical(result)) > MAX_SMALL: fail()
    return result, preview, raw


def write_outputs(output, result, preview):
    """Exclusive creation, with no destructive cleanup after a partial failure.

    Portable stat-then-unlink cannot atomically prove ownership under concurrent
    replacement. Retain a failed directory instead of risking another file.
    """
    output.mkdir()
    directory = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name, content in (('result.json', canonical(result)), ('preview.png', preview)):
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, 'wb') as sink:
                sink.write(content); sink.flush(); os.fsync(sink.fileno())
    finally:
        os.close(directory)


def main(argv=None):
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='Independent EdgeVision ONNX CPU image inference')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--format', choices=('png', 'jpeg'), required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing paths are never overwritten')
    parser.add_argument('--confidence', type=float, default=.25)
    parser.add_argument('--iou', type=float, default=.45)
    args = parser.parse_args(argv)
    try:
        if not sys.flags.isolated or args.output.exists() or args.output.is_symlink(): fail()
        result, preview, _ = execute(Path(__file__).resolve().parent, args.image, args.format, args.confidence, args.iou)
        write_outputs(args.output, result, preview)
    except Exception:
        print('PACKAGE_EXECUTION_FAILED', file=sys.stderr)
        return 1
    print('PACKAGE_EXECUTION_COMPLETE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
