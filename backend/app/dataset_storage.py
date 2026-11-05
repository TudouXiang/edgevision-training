"""Bounded multipart staging and generated-key dataset storage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from typing import Callable
from uuid import UUID

from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from .config import MAX_DATASET_ZIP_BYTES, MAX_MULTIPART_OVERHEAD_BYTES, data_root


@dataclass(frozen=True)
class StagedUpload:
    path: Path
    filename: str
    sha256: str
    size_bytes: int


class UploadError(ValueError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _reject(code: str, message: str, status_code: int = 400) -> None:
    raise UploadError(status_code, code, message)


def safe_directory(root: Path, *parts: str) -> Path:
    """Create generated directories while refusing symlink/special ancestors."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = root
    for part in parts:
        if not part or "/" in part or "\\" in part or part in {".", ".."}:
            raise ValueError("storage path component is not generated-safe")
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        details = current.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise RuntimeError("storage directory is not a regular directory")
    return current


def _dataset_name(filename: str) -> str:
    if not filename or filename != filename.strip() or "/" in filename or "\\" in filename:
        _reject("UPLOAD_FILENAME_INVALID", "Upload filename must be a simple basename")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        _reject("UPLOAD_FILENAME_INVALID", "Upload filename cannot contain control characters")
    if not filename.lower().endswith(".zip"):
        _reject("UPLOAD_FILE_TYPE", "Dataset upload must use a .zip filename", 415)
    name = filename[:-4]
    if not 1 <= len(name) <= 160:
        _reject("DATASET_NAME_INVALID", "Dataset name derived from the filename must be 1 to 160 characters")
    return name


def dataset_name_from_filename(filename: str) -> str:
    return _dataset_name(filename)


async def stage_multipart_zip(request: Request, destination: Path) -> StagedUpload:
    """Consume raw ASGI bytes into exactly one bounded ``file`` part.

    This intentionally does not use ``request.form()``/``UploadFile`` because
    Starlette's field-size option does not cap file parts before spooling.
    """
    content_type = request.headers.get("content-type")
    media_type, options = parse_options_header(content_type)
    if media_type != b"multipart/form-data" or b"boundary" not in options:
        _reject("MULTIPART_REQUIRED", "Content-Type must be multipart/form-data with a boundary", 415)
    boundary = options[b"boundary"]
    if not boundary or len(boundary) > 200:
        _reject("MULTIPART_BOUNDARY_INVALID", "Multipart boundary is invalid")
    content_length = request.headers.get("content-length")
    body_limit = MAX_DATASET_ZIP_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
    if content_length is not None:
        if len(content_length) > 20 or not content_length.isdecimal():
            _reject("CONTENT_LENGTH_INVALID", "Content-Length must be a non-negative integer")
        if int(content_length) > body_limit:
            _reject("DATASET_TOO_LARGE", f"Multipart body exceeds {body_limit} bytes", 413)

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    hasher = sha256()
    file_handle = None
    filename: str | None = None
    file_bytes = 0
    body_bytes = 0
    part_seen = False
    part_finished = False
    parser_finished = False
    header_name = bytearray()
    header_value = bytearray()
    headers: list[tuple[bytes, bytes]] = []
    accepting_data = False
    succeeded = False

    def on_part_begin() -> None:
        nonlocal part_seen, accepting_data
        if part_seen:
            _reject("MULTIPART_PART_COUNT", "Upload must contain exactly one file part")
        part_seen = True
        accepting_data = False

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_name.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        headers.append((bytes(header_name).lower(), bytes(header_value)))
        header_name.clear()
        header_value.clear()

    def one_header(name: bytes) -> bytes | None:
        values = [value for key, value in headers if key == name]
        if len(values) > 1:
            _reject("MULTIPART_HEADER_INVALID", "Multipart part contains duplicate headers")
        return values[0] if values else None

    def on_headers_finished() -> None:
        nonlocal filename, accepting_data, file_handle
        disposition, params = parse_options_header(one_header(b"content-disposition"))
        if disposition != b"form-data" or params.get(b"name") != b"file" or b"filename" not in params:
            _reject("MULTIPART_FILE_REQUIRED", "Upload must contain one file field named 'file'")
        try:
            filename = params[b"filename"].decode("utf-8")
        except UnicodeDecodeError:
            _reject("UPLOAD_FILENAME_INVALID", "Upload filename must be UTF-8")
        _dataset_name(filename)
        part_type, _ = parse_options_header(one_header(b"content-type"))
        if part_type not in {b"application/zip", b"application/x-zip-compressed", b"application/octet-stream"}:
            _reject("UPLOAD_FILE_TYPE", "Dataset file part must be a ZIP media type", 415)
        try:
            file_handle = destination.open("xb")
        except FileExistsError:
            raise RuntimeError("generated staging path already exists")
        accepting_data = True

    def on_part_data(data: bytes, start: int, end: int) -> None:
        nonlocal file_bytes
        if not accepting_data or file_handle is None:
            _reject("MULTIPART_INVALID", "Multipart file data appeared before valid headers")
        chunk = data[start:end]
        file_bytes += len(chunk)
        if file_bytes > MAX_DATASET_ZIP_BYTES:
            _reject("DATASET_TOO_LARGE", f"Dataset ZIP exceeds {MAX_DATASET_ZIP_BYTES} bytes", 413)
        file_handle.write(chunk)
        hasher.update(chunk)

    def on_part_end() -> None:
        nonlocal part_finished, accepting_data
        part_finished = True
        accepting_data = False

    def on_end() -> None:
        nonlocal parser_finished
        parser_finished = True

    callbacks: dict[str, Callable[..., None]] = {
        "on_part_begin": on_part_begin,
        "on_header_field": on_header_field,
        "on_header_value": on_header_value,
        "on_header_end": on_header_end,
        "on_headers_finished": on_headers_finished,
        "on_part_data": on_part_data,
        "on_part_end": on_part_end,
        "on_end": on_end,
    }
    parser = MultipartParser(boundary, callbacks, max_size=body_limit, max_header_count=8, max_header_size=4096)
    try:
        async for chunk in request.stream():
            body_bytes += len(chunk)
            if body_bytes > body_limit:
                _reject("DATASET_TOO_LARGE", f"Multipart body exceeds {body_limit} bytes", 413)
            parser.write(chunk)
        parser.finalize()
        if not (part_seen and part_finished and parser_finished and filename is not None and file_handle is not None):
            _reject("MULTIPART_INCOMPLETE", "Multipart upload ended before the file part completed")
        if file_bytes == 0:
            _reject("UPLOAD_EMPTY", "Dataset ZIP cannot be empty")
        file_handle.flush()
        os.fsync(file_handle.fileno())
        file_handle.close()
        file_handle = None
        result = StagedUpload(destination, filename, hasher.hexdigest(), file_bytes)
        succeeded = True
        return result
    except UploadError:
        raise
    except MultipartParseError as exc:
        _reject("MULTIPART_INVALID", f"Multipart body is malformed: {type(exc).__name__}")
    finally:
        if file_handle is not None:
            file_handle.close()
        if not succeeded:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass


def publish_dataset_source(staged: Path, dataset_id: str) -> tuple[str, str]:
    root = data_root()
    try:
        if str(UUID(dataset_id)) != dataset_id:
            raise ValueError
    except ValueError as exc:
        raise ValueError("dataset ID is not a canonical UUID") from exc
    datasets = safe_directory(root, "datasets")
    directory = datasets / dataset_id
    directory.mkdir(mode=0o700, exist_ok=False)
    if stat.S_ISLNK(directory.lstat().st_mode):
        directory.rmdir()
        raise RuntimeError("dataset directory cannot be a symlink")
    source = directory / "source.zip"
    try:
        os.replace(staged, source)
        if os.name != "nt":
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return f"datasets/{dataset_id}/source.zip", f"datasets/{dataset_id}/snapshot"


def remove_dataset_storage(dataset_id: str) -> None:
    try:
        if str(UUID(dataset_id)) != dataset_id:
            raise ValueError
    except ValueError as exc:
        raise ValueError("dataset ID is not a canonical UUID") from exc
    shutil.rmtree(data_root() / "datasets" / dataset_id, ignore_errors=True)


def resolve_storage_file(storage_key: str) -> Path:
    pure = PurePosixPath(storage_key)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError("stored key is invalid")
    root = data_root()
    current = root
    for part in pure.parts:
        current = current / part
        details = current.lstat()
        if stat.S_ISLNK(details.st_mode):
            raise RuntimeError("stored path crosses a symlink")
    if not current.is_file():
        raise RuntimeError("stored path is not a regular file")
    try:
        current.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("stored path escapes storage root") from exc
    return current
