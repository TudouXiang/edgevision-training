"""Bounded same-descriptor image/model IO. No decoder or native imports."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
import stat
from .dataset_storage import resolve_storage_file


@contextmanager
def verified_file(path, size, digest, limit):
    if type(size) is not int or not 0 < size <= limit: raise ValueError('file size invalid')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode): raise ValueError('regular file required')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as source:
        current = os.fstat(source.fileno())
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino, current.st_size) != (before.st_dev, before.st_ino, size):
            raise ValueError('opened file identity changed')
        remaining = size; actual = sha256()
        while remaining:
            chunk = source.read(min(1024**2, remaining))
            if not chunk: raise ValueError('file truncated')
            actual.update(chunk); remaining -= len(chunk)
        if source.read(1) or actual.hexdigest() != digest: raise ValueError('file fingerprint changed')
        source.seek(0)
        yield source


def check_stored(key, size, digest, limit):
    with verified_file(resolve_storage_file(key), size, digest, limit): pass


def read_document(key, entry, limit):
    with verified_file(resolve_storage_file(key), entry['size_bytes'], entry['sha256'], limit) as source:
        raw = source.read(entry['size_bytes'] + 1)
    if len(raw) != entry['size_bytes'] or sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('document changed while reading')
    value = json.loads(raw)
    if not isinstance(value, dict): raise ValueError('document object required')
    return value


def copy_stored(key, size, digest, limit, destination):
    actual = sha256(); total = 0
    with verified_file(resolve_storage_file(key), size, digest, limit) as source, destination.open('xb') as sink:
        while total < size:
            chunk = source.read(min(1024**2, size-total))
            if not chunk: raise ValueError('copy source truncated')
            actual.update(chunk); sink.write(chunk); total += len(chunk)
        if source.read(1) or actual.hexdigest() != digest: raise ValueError('copy source changed')
        sink.flush(); os.fsync(sink.fileno())
    return destination


def write_bytes(path, content, limit):
    if not 0 < len(content) <= limit: raise ValueError('output size invalid')
    with path.open('xb') as sink:
        sink.write(content); sink.flush(); os.fsync(sink.fileno())
