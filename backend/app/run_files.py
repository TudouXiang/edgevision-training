"""Generated run paths and bounded, atomically replaced protocol documents."""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
from uuid import UUID

from .config import data_root
from .dataset_storage import safe_directory

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024


class OutputLimitError(ValueError):
    """A supported output bound was exceeded, not a dataset-content verdict."""


def run_directory(job_id: str, run_id: str, *, create: bool = False) -> Path:
    for value in (job_id, run_id):
        if str(UUID(value)) != value:
            raise ValueError("noncanonical run identity")
    if create:
        parent = safe_directory(data_root(), "jobs", job_id, "runs")
        result = parent / run_id
        result.mkdir(mode=0o700, exist_ok=False)
        return result
    return data_root() / "jobs" / job_id / "runs" / run_id


def atomic_json(path: Path, value: dict) -> None:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    if len(content) > MAX_DOCUMENT_BYTES:
        raise OutputLimitError("protocol document exceeds its bound")
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def read_json(path: Path, limit: int = MAX_DOCUMENT_BYTES) -> dict:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_size > limit:
        raise ValueError("protocol file invalid")
    with path.open("rb") as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError("protocol file exceeds its bound")
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("protocol object required")
    return value


def fingerprint(path: Path) -> tuple[int, str]:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("regular file required")
    digest, size = sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def relative_file(root: Path, key: str) -> Path:
    pure = PurePosixPath(key)
    if not key or ":" in key or "\\" in key or pure.is_absolute() or key != pure.as_posix() or any(part in {".", ".."} for part in pure.parts):
        raise ValueError("output key invalid")
    current = root
    for part in pure.parts:
        current /= part
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ValueError("output symlink rejected")
    current.resolve().relative_to(root.resolve())
    if not stat.S_ISREG(current.lstat().st_mode):
        raise ValueError("output regular file required")
    return current
