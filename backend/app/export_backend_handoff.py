"""Bounded private handoff for the fixed A/D numerical comparison.

Only fixed filenames are accepted. This module is stdlib-only and does not
load a model or any native runtime.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import stat
import struct
from uuid import UUID

from .export_contract import MAX_ONNX_BYTES
from .run_files import run_directory

SCHEMA_VERSION = 1
RAW_BYTES = 201_600  # little-endian FP32 (1, 6, 8400)
CURRENT_FILES = tuple(f'current-{name}.f32' for name in ('zeros', 'gradient', 'pattern'))
FIXED_FILES = ('model.onnx', *CURRENT_FILES)
PRECISION_KEYS = {'mkldnn_enabled', 'global', 'backend', 'conv', 'matmul'}
PRECISION_ENUMS = {'none', 'ieee', 'tf32', 'bf16'}
SHA_LENGTH = 64


def _canonical_uuid(value):
    return type(value) is str and str(UUID(value)) == value


def _field(value, name):
    if type(value) is dict:
        return value.get(name)
    return getattr(value, name, None)


def validate_precision(value, *, mkldnn_enabled=True):
    if type(value) is not dict or set(value) != PRECISION_KEYS:
        raise ValueError('precision schema invalid')
    if type(value['mkldnn_enabled']) is not bool or value['mkldnn_enabled'] is not mkldnn_enabled:
        raise ValueError('MKLDNN state invalid')
    if any(type(value[key]) is not str or value[key] not in PRECISION_ENUMS for key in ('global', 'backend', 'conv', 'matmul')):
        raise ValueError('precision enum invalid')
    return value


def _precision_value(owner, attribute, legacy_attribute=None):
    value = getattr(owner, attribute, None) if owner is not None else None
    if value is not None:
        if type(value) is not str or value not in PRECISION_ENUMS:
            raise ValueError('unsupported effective precision value')
        return value
    if legacy_attribute is not None and owner is not None and hasattr(owner, legacy_attribute):
        legacy = getattr(owner, legacy_attribute)
        if type(legacy) is not bool:
            raise ValueError('invalid legacy precision setting')
        return 'tf32' if legacy else 'ieee'
    return 'none'


def precision_snapshot(torch):
    """Read configured precision controls without changing runtime settings."""
    backends = torch.backends
    mkldnn = getattr(backends, 'mkldnn', None)
    mkldnn_conv = getattr(mkldnn, 'conv', None)
    mkldnn_matmul = getattr(mkldnn, 'matmul', None)
    if mkldnn_conv is None or mkldnn_matmul is None:
        raise ValueError('MKLDNN precision controls unavailable')
    global_value = _precision_value(backends, 'fp32_precision')
    backend_value = _precision_value(mkldnn, 'fp32_precision')
    result = {
        'mkldnn_enabled': getattr(mkldnn, 'enabled', None),
        'global': global_value,
        'backend': backend_value,
        'conv': _precision_value(mkldnn_conv, 'fp32_precision', 'allow_tf32'),
        'matmul': _precision_value(mkldnn_matmul, 'fp32_precision', 'allow_tf32'),
    }
    if type(result['mkldnn_enabled']) is not bool:
        raise ValueError('MKLDNN enable state unavailable')
    return validate_precision(result, mkldnn_enabled=result['mkldnn_enabled'])


def _check_parents(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('absolute path required')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError('symlink path rejected')
    return path


def _read_regular(path, limit, expected_size=None):
    path = _check_parents(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > limit:
            raise ValueError('handoff file type or size rejected')
        if expected_size is not None and before.st_size != expected_size:
            raise ValueError('handoff file size mismatch')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (len(raw) != before.st_size or len(raw) > limit or after.st_size != before.st_size
            or after.st_ino != before.st_ino or after.st_dev != before.st_dev
            or after.st_mtime_ns != before.st_mtime_ns):
        raise ValueError('handoff file changed while reading')
    return raw


def _check_raw(raw):
    if type(raw) is not bytes or len(raw) != RAW_BYTES or len(raw) % 4:
        raise ValueError('fixed tensor byte length invalid')
    if not all(math.isfinite(value[0]) for value in struct.iter_unpack('<f', raw)):
        raise ValueError('fixed tensor contains nonfinite values')


def _run_path(job_id, run_id):
    if not _canonical_uuid(job_id) or not _canonical_uuid(run_id):
        raise ValueError('noncanonical handoff identity')
    directory = _check_parents(run_directory(job_id, run_id))
    if not directory.is_dir():
        raise ValueError('handoff run directory unavailable')
    return directory


def _read_fixed_file(directory, name, expected_size=None):
    if name not in FIXED_FILES:
        raise ValueError('unknown handoff filename')
    bound = MAX_ONNX_BYTES if name == 'model.onnx' else RAW_BYTES
    size = expected_size if expected_size is not None else (None if name == 'model.onnx' else RAW_BYTES)
    raw = _read_regular(directory / name, bound, size)
    if name != 'model.onnx':
        _check_raw(raw)
    return raw


def _validate_manifest(manifest, frozen):
    if type(manifest) is not dict or set(manifest) != {'schema_version', 'job_id', 'run_id', 'source_sha256', 'runtime_binding', 'precision', 'files'}:
        raise ValueError('handoff manifest schema invalid')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != SCHEMA_VERSION:
        raise ValueError('handoff manifest version invalid')
    if not _canonical_uuid(manifest['job_id']) or not _canonical_uuid(manifest['run_id']):
        raise ValueError('handoff manifest identity invalid')
    for key in ('source_sha256', 'runtime_binding'):
        value = manifest[key]
        if type(value) is not str or len(value) != SHA_LENGTH or any(ch not in '0123456789abcdef' for ch in value):
            raise ValueError('handoff binding invalid')
        if value != _field(frozen, key):
            raise ValueError('handoff binding stale')
    validate_precision(manifest['precision'], mkldnn_enabled=True)
    files = manifest['files']
    if type(files) is not dict or set(files) != set(FIXED_FILES):
        raise ValueError('handoff files invalid')
    for name, entry in files.items():
        if type(entry) is not dict or set(entry) != {'size_bytes', 'sha256'}:
            raise ValueError('handoff file record invalid')
        size, digest = entry['size_bytes'], entry['sha256']
        if type(size) is not int or not 0 < size <= (MAX_ONNX_BYTES if name == 'model.onnx' else RAW_BYTES):
            raise ValueError('handoff file bound invalid')
        if name != 'model.onnx' and size != RAW_BYTES:
            raise ValueError('handoff tensor size invalid')
        if type(digest) is not str or len(digest) != SHA_LENGTH or any(ch not in '0123456789abcdef' for ch in digest):
            raise ValueError('handoff file digest invalid')
    return manifest


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _verify_files(directory, manifest):
    result = {}
    for name in FIXED_FILES:
        record = manifest['files'][name]
        raw = _read_fixed_file(directory, name, record['size_bytes'])
        if _digest(raw) != record['sha256']:
            raise ValueError('handoff file fingerprint changed')
        result[name] = raw
    return result


def capture(job_id, run_id, frozen, precision):
    """Capture A's fixed model and three finite PT outputs after its completed drain."""
    validate_precision(precision, mkldnn_enabled=True)
    directory = _run_path(job_id, run_id)
    files = {}
    for name in FIXED_FILES:
        raw = _read_fixed_file(directory, name)
        files[name] = {'size_bytes': len(raw), 'sha256': _digest(raw)}
    manifest = {'schema_version': SCHEMA_VERSION, 'job_id': job_id, 'run_id': run_id,
        'source_sha256': _field(frozen, 'source_sha256'),
        'runtime_binding': _field(frozen, 'runtime_binding'), 'precision': dict(precision), 'files': files}
    return _validate_manifest(manifest, frozen)


def verify(manifest, frozen):
    """Return the exact bounded, digest-verified A file bytes keyed by fixed basename."""
    _validate_manifest(manifest, frozen)
    directory = _run_path(manifest['job_id'], manifest['run_id'])
    return _verify_files(directory, manifest)


def _write_exclusive(path, raw):
    path = _check_parents(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def copy_to(manifest, frozen, destination):
    """Safely copy the verified A snapshot into D's own private run directory."""
    files = verify(manifest, frozen)
    destination = _check_parents(destination)
    if not destination.is_dir():
        raise ValueError('handoff destination unavailable')
    result = {}
    for name in FIXED_FILES:
        path = destination / name
        _write_exclusive(path, files[name])
        copied = _read_fixed_file(destination, name, len(files[name]))
        if _digest(copied) != manifest['files'][name]['sha256']:
            raise ValueError('copied handoff file mismatch')
        result[name] = path
    # Detect a mutation of A's retained snapshot during the copy window.
    _verify_files(_run_path(manifest['job_id'], manifest['run_id']), manifest)
    return result
