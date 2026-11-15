"""Bounded stdlib model-copy binding for the private PT-only experiment."""
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

MAX_BYTES=128*1024**2


def validate(binding):
    if (type(binding) is not dict or set(binding)!={'sha256','size_bytes'}
            or type(binding['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',binding['sha256'])
            or type(binding['size_bytes']) is not int or not 0<binding['size_bytes']<=MAX_BYTES):
        raise ValueError('model binding invalid')


def safe_path(path):
    path=Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('model path rejected')
    return path


def read_verified(path,binding):
    validate(binding);path=safe_path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size!=binding['size_bytes']:
            raise ValueError('model file rejected')
        raw=source.read(binding['size_bytes']+1);after=os.fstat(source.fileno())
    if (len(raw)!=binding['size_bytes'] or sha256(raw).hexdigest()!=binding['sha256']
            or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):
        raise ValueError('model fingerprint changed')
    return raw


def verify_file(path,binding):
    read_verified(path,binding);return True


def copy_verified(source,destination,binding):
    raw=read_verified(source,binding);destination=safe_path(destination)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:
        output.write(raw);output.flush();os.fsync(output.fileno())
    verify_file(destination,binding);verify_file(source,binding)
