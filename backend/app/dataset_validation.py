"""Deterministic, side-effect-bounded validation for controlled YOLO datasets.

The service has no database or network dependency.  T040 may call
``validate_dataset_archive`` in a Worker and only publish its output after the
returned report has been durably written.  T030 HTTP upload only calls the
central-directory preflight; it never performs extraction in the request.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import unicodedata
import warnings
import zlib
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from PIL import Image, UnidentifiedImageError
import yaml
from yaml.tokens import (
    AliasToken, AnchorToken, BlockEndToken, BlockMappingStartToken,
    BlockSequenceStartToken, FlowMappingEndToken, FlowMappingStartToken,
    FlowSequenceEndToken, FlowSequenceStartToken, ScalarToken, TagToken,
)

from .config import (
    MAX_ARCHIVE_COMPRESSION_RATIO,
    MAX_ARCHIVE_CENTRAL_DIRECTORY_BYTES,
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_EXPANDED_BYTES,
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_DATASET_YAML_BYTES,
    MAX_DATASET_ZIP_BYTES,
    MAX_IMAGE_FILE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_LABEL_FILE_BYTES,
    MAX_LABEL_LINE_BYTES,
    MAX_LABELS_PER_FILE,
    MAX_PREVIEW_ANNOTATIONS,
    MAX_PREVIEW_SAMPLES,
)


_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul", "clock$",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_CLASS_ID = re.compile(r"[0-9]+\Z")
_IMAGE_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
_SPLITS = ("train", "val", "test")


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    path: str
    message: str
    line: int | None = None


class DatasetValidationError(ValueError):
    def __init__(self, issue: ValidationIssue):
        super().__init__(f"{issue.code}: {issue.path}: {issue.message}")
        self.issue = issue


def _fail(code: str, path: str, message: str, line: int | None = None) -> None:
    raise DatasetValidationError(ValidationIssue("error", code, path, message, line))


@dataclass(frozen=True)
class ArchiveEntry:
    source_name: str
    canonical_path: str
    size_bytes: int
    compressed_bytes: int
    is_directory: bool


@dataclass(frozen=True)
class ArchivePlan:
    wrapper: str | None
    entries: tuple[ArchiveEntry, ...]
    expanded_bytes: int


@dataclass(frozen=True)
class AnnotationPreview:
    class_id: int
    class_name: str
    xywh: tuple[float, float, float, float]


@dataclass(frozen=True)
class SamplePreview:
    id: str
    split: str
    image_path: str
    label_path: str
    width: int
    height: int
    annotations: tuple[AnnotationPreview, ...]
    annotations_truncated: bool


@dataclass(frozen=True)
class DatasetValidationResult:
    classes: tuple[str, ...]
    counts: dict[str, int]
    snapshot_sha256: str
    file_manifest: tuple[dict[str, object], ...]
    samples: tuple[SamplePreview, ...]
    preview_truncated: bool
    warnings: tuple[ValidationIssue, ...]

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "snapshot_sha256": self.snapshot_sha256,
            "sample_count": self.counts["images"],
            "preview_truncated": self.preview_truncated,
            "preview_samples": [asdict(sample) for sample in self.samples],
        }

    def report(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "valid": True,
            "classes": list(self.classes),
            "counts": self.counts,
            "snapshot_sha256": self.snapshot_sha256,
            "files": list(self.file_manifest),
            "warnings": [asdict(issue) for issue in self.warnings],
        }


def _portable_archive_path(info: ZipInfo) -> tuple[str, bool]:
    original = info.filename
    if getattr(info, "orig_filename", original) != original:
        _fail("ARCHIVE_PATH_INVALID", "<archive>", "Archive filename contains forbidden NUL or ambiguous bytes")
    if not original:
        _fail("ARCHIVE_PATH_INVALID", "<archive>", "Archive entry has an empty path")
    if "\\" in original:
        _fail("ARCHIVE_PATH_INVALID", original, "Backslashes are not accepted in portable ZIP paths")
    if original.startswith("/") or original.startswith("//"):
        _fail("ARCHIVE_PATH_ABSOLUTE", original, "Absolute archive paths are forbidden")
    if any(ord(character) < 32 or ord(character) == 127 for character in original):
        _fail("ARCHIVE_PATH_INVALID", "<archive>", "Archive paths cannot contain control characters")
    is_directory = info.is_dir()
    raw = original[:-1] if original.endswith("/") else original
    if not raw:
        _fail("ARCHIVE_PATH_INVALID", original, "Archive root is not a valid entry")
    if raw != unicodedata.normalize("NFC", raw):
        _fail("ARCHIVE_PATH_NOT_NORMALIZED", original, "Archive paths must use Unicode NFC")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        code = "ARCHIVE_PATH_TRAVERSAL" if ".." in parts else "ARCHIVE_PATH_INVALID"
        _fail(code, original, "Archive path contains a forbidden component")
    if len(raw.encode("utf-8")) > 1024:
        _fail("ARCHIVE_PATH_TOO_LONG", original, "Archive path exceeds 1024 UTF-8 bytes")
    for part in parts:
        if len(part.encode("utf-8")) > 255:
            _fail("ARCHIVE_PATH_TOO_LONG", original, "Archive path component exceeds 255 UTF-8 bytes")
        if any(character in part for character in '<>:"|?*') or part.endswith((".", " ")):
            _fail("ARCHIVE_PATH_INVALID", original, "Archive path is not portable across supported hosts")
        basename = part.split(".", 1)[0].casefold()
        if basename in _WINDOWS_RESERVED:
            _fail("ARCHIVE_PATH_INVALID", original, "Archive path uses a reserved portable filename")
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        _fail("ARCHIVE_LINK_OR_SPECIAL", original, "Links and special filesystem entries are forbidden")
    if file_type == stat.S_IFDIR and not is_directory:
        _fail("ARCHIVE_PATH_INVALID", original, "Directory metadata does not match the entry name")
    return raw, is_directory


def _check_layout(entries: list[tuple[ZipInfo, str, bool]]) -> tuple[str | None, list[ArchiveEntry]]:
    files = [path for _, path, is_directory in entries if not is_directory]
    yaml_candidates = [path for path in files if path == "data.yaml" or path.endswith("/data.yaml")]
    if len(yaml_candidates) != 1:
        _fail("DATA_YAML_REQUIRED", "data.yaml", "Archive must contain exactly one data.yaml")
    yaml_path = yaml_candidates[0]
    if yaml_path == "data.yaml":
        wrapper = None
    else:
        parts = yaml_path.split("/")
        if len(parts) != 2:
            _fail("WRAPPER_LAYOUT_INVALID", yaml_path, "Only one optional wrapper directory is accepted")
        wrapper = parts[0]
        prefix = wrapper + "/"
        for _, path, _ in entries:
            if path != wrapper and not path.startswith(prefix):
                _fail("WRAPPER_LAYOUT_INVALID", path, "All entries must be inside the single wrapper directory")

    prefix = "" if wrapper is None else wrapper + "/"
    planned: list[ArchiveEntry] = []
    for info, path, is_directory in entries:
        if wrapper is not None and path == wrapper:
            continue
        canonical = path[len(prefix):]
        if not canonical:
            continue
        if not is_directory:
            parts = canonical.split("/")
            valid_data_yaml = canonical == "data.yaml"
            valid_image = len(parts) >= 3 and parts[0] == "images" and parts[1] in _SPLITS and Path(parts[-1]).suffix in _IMAGE_FORMATS
            valid_label = len(parts) >= 3 and parts[0] == "labels" and parts[1] in _SPLITS and Path(parts[-1]).suffix == ".txt"
            if not (valid_data_yaml or valid_image or valid_label):
                _fail("ARCHIVE_FILE_NOT_ALLOWED", canonical, "Only data.yaml and controlled image/label paths are accepted")
            if valid_data_yaml and info.file_size > MAX_DATASET_YAML_BYTES:
                _fail("YAML_SIZE_LIMIT", canonical, f"data.yaml exceeds {MAX_DATASET_YAML_BYTES} bytes")
            if valid_image and info.file_size > MAX_IMAGE_FILE_BYTES:
                _fail("IMAGE_FILE_LIMIT", canonical, f"Image file exceeds {MAX_IMAGE_FILE_BYTES} bytes")
            if valid_label and info.file_size > MAX_LABEL_FILE_BYTES:
                _fail("LABEL_FILE_LIMIT", canonical, f"Label file exceeds {MAX_LABEL_FILE_BYTES} bytes")
        planned.append(ArchiveEntry(info.filename, canonical, info.file_size, info.compress_size, is_directory))
    return wrapper, planned


def _bounded_eocd(archive_path: Path) -> None:
    """Bound central-directory allocation before stdlib ZipFile constructs ZipInfo objects."""
    try:
        size = archive_path.stat().st_size
        if size > MAX_DATASET_ZIP_BYTES:
            _fail("ARCHIVE_FILE_LIMIT", "<archive>", f"ZIP exceeds {MAX_DATASET_ZIP_BYTES} bytes")
        if size < 22:
            _fail("ARCHIVE_INVALID", "<archive>", "ZIP is too short to contain an end record")
        with archive_path.open("rb") as source:
            if source.read(4) != b"PK\x03\x04":
                _fail("ARCHIVE_CONTAINER_UNSUPPORTED", "<archive>", "Self-extracting and nonstandard ZIP prefixes are forbidden")
            tail_size = min(size, 65_557)
            source.seek(size - tail_size)
            tail = source.read(tail_size)
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or len(tail) - offset < 22:
            _fail("ARCHIVE_INVALID", "<archive>", "ZIP end record is missing")
        signature, disk, central_disk, disk_entries, total_entries, central_size, central_offset, comment_size = struct.unpack_from("<4s4H2LH", tail, offset)
        absolute_offset = size - tail_size + offset
        if absolute_offset + 22 + comment_size != size:
            _fail("ARCHIVE_INVALID", "<archive>", "ZIP end record or trailing data is inconsistent")
        if disk or central_disk or disk_entries != total_entries:
            _fail("ARCHIVE_CONTAINER_UNSUPPORTED", "<archive>", "Multidisk ZIP archives are forbidden")
        if total_entries in {0xFFFF} or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
            _fail("ARCHIVE_CONTAINER_UNSUPPORTED", "<archive>", "ZIP64 archives are not accepted by the controlled dataset format")
        if total_entries > MAX_ARCHIVE_ENTRIES:
            _fail("ARCHIVE_ENTRY_LIMIT", "<archive>", f"Archive exceeds {MAX_ARCHIVE_ENTRIES} entries")
        if central_size > MAX_ARCHIVE_CENTRAL_DIRECTORY_BYTES:
            _fail("ARCHIVE_CENTRAL_DIRECTORY_LIMIT", "<archive>", f"ZIP central directory exceeds {MAX_ARCHIVE_CENTRAL_DIRECTORY_BYTES} bytes")
        if central_size < total_entries * 46 or central_offset + central_size != absolute_offset:
            _fail("ARCHIVE_INVALID", "<archive>", "ZIP central-directory bounds are inconsistent")
    except DatasetValidationError:
        raise
    except (OSError, struct.error, ValueError) as exc:
        _fail("ARCHIVE_INVALID", "<archive>", f"Cannot inspect ZIP end record: {type(exc).__name__}")


def inspect_dataset_archive(archive_path: Path) -> ArchivePlan:
    """Inspect ZIP metadata without extracting or decoding user content."""
    _bounded_eocd(archive_path)
    try:
        with ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if not infos:
                _fail("ARCHIVE_EMPTY", "<archive>", "Dataset archive is empty")
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                _fail("ARCHIVE_ENTRY_LIMIT", "<archive>", f"Archive exceeds {MAX_ARCHIVE_ENTRIES} entries")
            seen: dict[str, str] = {}
            file_paths: set[str] = set()
            directory_paths: set[str] = set()
            implicit_directories: set[str] = set()
            expanded = 0
            compressed = 0
            entries: list[tuple[ZipInfo, str, bool]] = []
            for info in infos:
                path, is_directory = _portable_archive_path(info)
                folded = path.casefold()
                previous = seen.get(folded)
                if previous is not None:
                    _fail("ARCHIVE_DUPLICATE_PATH", path, f"Path collides with {previous}")
                seen[folded] = path
                parts = path.split("/")
                ancestors = ["/".join(parts[:index]).casefold() for index in range(1, len(parts))]
                if any(ancestor in file_paths for ancestor in ancestors):
                    _fail("ARCHIVE_PATH_COLLISION", path, "Archive file is used as a parent directory")
                if is_directory:
                    if folded in file_paths:
                        _fail("ARCHIVE_PATH_COLLISION", path, "Archive path is both a file and directory")
                    directory_paths.add(folded)
                else:
                    if folded in directory_paths or folded in implicit_directories:
                        _fail("ARCHIVE_PATH_COLLISION", path, "Archive path is both a file and directory")
                    file_paths.add(folded)
                implicit_directories.update(ancestors)
                if info.flag_bits & 0x1:
                    _fail("ARCHIVE_ENCRYPTED", path, "Encrypted archive members are not accepted")
                if info.flag_bits & ~0x080E:
                    _fail("ARCHIVE_FLAG_UNSUPPORTED", path, "Archive member uses unsupported ZIP flags")
                if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                    _fail("ARCHIVE_COMPRESSION_UNSUPPORTED", path, "Only stored and deflated members are accepted")
                if info.file_size < 0 or info.compress_size < 0:
                    _fail("ARCHIVE_SIZE_INVALID", path, "Archive member has invalid size metadata")
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    _fail("ARCHIVE_MEMBER_LIMIT", path, f"Archive member exceeds {MAX_ARCHIVE_MEMBER_BYTES} bytes")
                expanded += info.file_size
                compressed += info.compress_size
                if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
                    _fail("ARCHIVE_EXPANDED_LIMIT", path, f"Archive expands beyond {MAX_ARCHIVE_EXPANDED_BYTES} bytes")
                if info.file_size and not info.compress_size:
                    _fail("ARCHIVE_COMPRESSION_RATIO", path, "Non-empty member declares zero compressed bytes")
                if info.file_size >= 1024 * 1024 and info.file_size / max(1, info.compress_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
                    _fail("ARCHIVE_COMPRESSION_RATIO", path, f"Compression ratio exceeds {MAX_ARCHIVE_COMPRESSION_RATIO}:1")
                entries.append((info, path, is_directory))
            if expanded >= 1024 * 1024 and expanded / max(1, compressed) > MAX_ARCHIVE_COMPRESSION_RATIO:
                _fail("ARCHIVE_COMPRESSION_RATIO", "<archive>", f"Aggregate compression ratio exceeds {MAX_ARCHIVE_COMPRESSION_RATIO}:1")
            wrapper, planned = _check_layout(entries)
            return ArchivePlan(wrapper, tuple(planned), expanded)
    except DatasetValidationError:
        raise
    except (BadZipFile, OSError, ValueError) as exc:
        _fail("ARCHIVE_INVALID", "<archive>", f"ZIP central directory is invalid: {type(exc).__name__}")


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node, deep: bool = False):
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            _fail("YAML_KEY_INVALID", "data.yaml", "YAML mapping keys must be scalar")
        if duplicate:
            _fail("YAML_DUPLICATE_KEY", "data.yaml", f"Duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _read_yaml(path: Path) -> tuple[dict[str, object], tuple[str, ...]]:
    if path.stat().st_size > MAX_DATASET_YAML_BYTES:
        _fail("YAML_SIZE_LIMIT", "data.yaml", f"data.yaml exceeds {MAX_DATASET_YAML_BYTES} bytes")
    raw = path.read_bytes()
    if len(raw) > MAX_DATASET_YAML_BYTES:
        _fail("YAML_SIZE_LIMIT", "data.yaml", f"data.yaml exceeds {MAX_DATASET_YAML_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("YAML_ENCODING", "data.yaml", "data.yaml must be UTF-8")
    try:
        depth = 0
        nodes = 0
        starts = (BlockMappingStartToken, BlockSequenceStartToken, FlowMappingStartToken, FlowSequenceStartToken)
        ends = (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken)
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("YAML_FEATURE_FORBIDDEN", "data.yaml", "Aliases, anchors and explicit tags are forbidden")
            if isinstance(token, starts):
                depth += 1
                nodes += 1
                if depth > 32:
                    _fail("YAML_COMPLEXITY_LIMIT", "data.yaml", "YAML nesting exceeds 32 levels")
            elif isinstance(token, ends):
                depth = max(0, depth - 1)
            elif isinstance(token, ScalarToken):
                nodes += 1
            if nodes > 10_000:
                _fail("YAML_COMPLEXITY_LIMIT", "data.yaml", "YAML contains too many nodes")
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except DatasetValidationError:
        raise
    except (yaml.YAMLError, RecursionError, ValueError, TypeError) as exc:
        _fail("YAML_INVALID", "data.yaml", f"Cannot parse controlled YAML: {type(exc).__name__}")
    if not isinstance(data, dict) or any(not isinstance(key, str) for key in data):
        _fail("YAML_SCHEMA", "data.yaml", "Top-level YAML must be a string-keyed mapping")
    allowed = {"path", "train", "val", "test", "names", "nc"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail("YAML_FIELD_FORBIDDEN", "data.yaml", f"Unsupported YAML field: {unknown[0]}")
    path_value = data.get("path", ".")
    if not isinstance(path_value, str) or path_value != ".":
        _fail("YAML_PATH_FORBIDDEN", "data.yaml", "path may only be omitted or '.'")
    for split in ("train", "val"):
        split_value = data.get(split)
        if not isinstance(split_value, str) or split_value not in {f"images/{split}", f"./images/{split}"}:
            _fail("YAML_SPLIT_INVALID", "data.yaml", f"{split} must point to images/{split}")
    if "test" in data:
        test_value = data["test"]
        if not isinstance(test_value, str) or test_value not in {"images/test", "./images/test"}:
            _fail("YAML_SPLIT_INVALID", "data.yaml", "test must point to images/test")
    names = data.get("names")
    ordered: list[object]
    if isinstance(names, list):
        ordered = names
    elif isinstance(names, dict):
        normalized: dict[int, object] = {}
        for key, value in names.items():
            if isinstance(key, bool) or not (
                isinstance(key, int)
                or isinstance(key, str) and len(key) <= 4 and _CLASS_ID.fullmatch(key)
            ):
                _fail("YAML_NAMES_INVALID", "data.yaml", "names mapping keys must be zero-based integers")
            index = int(key)
            if index in normalized:
                _fail("YAML_NAMES_INVALID", "data.yaml", "names contains duplicate numeric keys")
            normalized[index] = value
        if sorted(normalized) != list(range(len(normalized))):
            _fail("YAML_NAMES_INVALID", "data.yaml", "names mapping keys must be contiguous from zero")
        ordered = [normalized[index] for index in range(len(normalized))]
    else:
        _fail("YAML_NAMES_INVALID", "data.yaml", "names must be a list or contiguous integer mapping")
    if not ordered or len(ordered) > 1000:
        _fail("YAML_NAMES_INVALID", "data.yaml", "names must contain between 1 and 1000 classes")
    classes: list[str] = []
    for name in ordered:
        if not isinstance(name, str) or not name or name != name.strip() or len(name) > 128:
            _fail("YAML_CLASS_NAME_INVALID", "data.yaml", "Class names must be non-empty trimmed strings up to 128 characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in name):
            _fail("YAML_CLASS_NAME_INVALID", "data.yaml", "Class names cannot contain control characters")
        classes.append(name)
    if len({name.casefold() for name in classes}) != len(classes):
        _fail("YAML_CLASS_NAME_DUPLICATE", "data.yaml", "Class names must be unique ignoring case")
    nc = data.get("nc", len(classes))
    if isinstance(nc, bool) or not isinstance(nc, int) or nc != len(classes):
        _fail("YAML_NC_MISMATCH", "data.yaml", "nc must equal the number of class names")
    return data, tuple(classes)


def _extract(plan: ArchivePlan, archive_path: Path, snapshot_dir: Path) -> None:
    if snapshot_dir.exists() or snapshot_dir.is_symlink():
        _fail("SNAPSHOT_EXISTS", "<snapshot>", "Validation output directory must not already exist")
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    emitted = 0
    try:
        entries_by_source = {entry.source_name: entry for entry in plan.entries}
        with ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                entry = entries_by_source.get(info.filename)
                if entry is None or not entry.canonical_path:
                    continue
                destination = snapshot_dir.joinpath(*PurePosixPath(entry.canonical_path).parts)
                if entry.is_directory:
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                actual = 0
                try:
                    with archive.open(info, "r") as source, destination.open("xb") as target:
                        while chunk := source.read(1024 * 1024):
                            actual += len(chunk)
                            emitted += len(chunk)
                            if actual > entry.size_bytes or emitted > MAX_ARCHIVE_EXPANDED_BYTES:
                                _fail("ARCHIVE_EMITTED_LIMIT", entry.canonical_path, "Extracted bytes exceed declared or global limits")
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                except DatasetValidationError:
                    raise
                except (BadZipFile, OSError, EOFError, NotImplementedError, RuntimeError, zlib.error) as exc:
                    _fail("ARCHIVE_MEMBER_CORRUPT", entry.canonical_path, f"Cannot extract member: {type(exc).__name__}")
                if actual != entry.size_bytes:
                    _fail("ARCHIVE_SIZE_MISMATCH", entry.canonical_path, "Extracted size does not match central directory")
    except Exception:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def _validate_image(path: Path, relative: str) -> tuple[int, int]:
    size = path.stat().st_size
    if size > MAX_IMAGE_FILE_BYTES:
        _fail("IMAGE_FILE_LIMIT", relative, f"Image file exceeds {MAX_IMAGE_FILE_BYTES} bytes")
    expected = _IMAGE_FORMATS[path.suffix.lower()]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = image.size
                actual_format = image.format
                frames = getattr(image, "n_frames", 1)
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    _fail("IMAGE_PIXEL_LIMIT", relative, f"Image exceeds {MAX_IMAGE_PIXELS} pixels")
                if actual_format != expected:
                    _fail("IMAGE_FORMAT_MISMATCH", relative, "Image bytes do not match the filename extension")
                if frames != 1:
                    _fail("IMAGE_MULTIFRAME", relative, "Animated or multi-frame images are forbidden")
                image.verify()
            with Image.open(path) as decoded:
                decoded.load()
    except DatasetValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        _fail("IMAGE_CORRUPT", relative, f"Image cannot be safely decoded: {type(exc).__name__}")
    return width, height


def _parse_label(path: Path, relative: str, classes: tuple[str, ...]) -> tuple[list[AnnotationPreview], bool]:
    if path.stat().st_size > MAX_LABEL_FILE_BYTES:
        _fail("LABEL_FILE_LIMIT", relative, f"Label file exceeds {MAX_LABEL_FILE_BYTES} bytes")
    raw = path.read_bytes()
    if len(raw) > MAX_LABEL_FILE_BYTES:
        _fail("LABEL_FILE_LIMIT", relative, f"Label file exceeds {MAX_LABEL_FILE_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("LABEL_ENCODING", relative, "Label file must be UTF-8")
    if "\x00" in text:
        _fail("LABEL_ENCODING", relative, "Label file cannot contain NUL bytes")
    annotations: list[AnnotationPreview] = []
    annotation_count = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if len(line.encode("utf-8")) > MAX_LABEL_LINE_BYTES:
            _fail("LABEL_LINE_LIMIT", relative, f"Label line exceeds {MAX_LABEL_LINE_BYTES} bytes", line_number)
        if not line.strip():
            continue
        annotation_count += 1
        if annotation_count > MAX_LABELS_PER_FILE:
            _fail("LABEL_COUNT_LIMIT", relative, f"Label file exceeds {MAX_LABELS_PER_FILE} annotations", line_number)
        fields = line.split()
        if len(fields) != 5:
            _fail("LABEL_FIELD_COUNT", relative, "Detection labels require exactly five fields", line_number)
        class_text, *coordinate_text = fields
        if _CLASS_ID.fullmatch(class_text) is None:
            _fail("LABEL_CLASS_INVALID", relative, "Class ID must be a non-negative integer", line_number)
        class_id = int(class_text)
        if class_id >= len(classes):
            _fail("LABEL_CLASS_RANGE", relative, "Class ID is outside names/nc", line_number)
        try:
            x, y, width, height = (float(value) for value in coordinate_text)
        except ValueError:
            _fail("LABEL_COORDINATE_INVALID", relative, "Coordinates must be numeric", line_number)
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            _fail("LABEL_COORDINATE_NONFINITE", relative, "Coordinates must be finite", line_number)
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
            _fail("LABEL_COORDINATE_RANGE", relative, "Normalized center/size values are outside accepted ranges", line_number)
        if x - width / 2 < -1e-9 or x + width / 2 > 1 + 1e-9 or y - height / 2 < -1e-9 or y + height / 2 > 1 + 1e-9:
            _fail("LABEL_BOX_OUT_OF_BOUNDS", relative, "Bounding box extends beyond the normalized image", line_number)
        if len(annotations) < MAX_PREVIEW_ANNOTATIONS:
            annotations.append(AnnotationPreview(class_id, classes[class_id], (x, y, width, height)))
    return annotations, annotation_count > len(annotations)


def validate_dataset_archive(archive_path: Path, snapshot_dir: Path) -> DatasetValidationResult:
    """Extract and fully validate an archive into a new, caller-owned directory.

    The function never publishes database state. On failure its newly-created
    snapshot directory is removed and the error only contains archive-relative
    paths.
    """
    plan = inspect_dataset_archive(archive_path)
    _extract(plan, archive_path, snapshot_dir)
    try:
        yaml_data, classes = _read_yaml(snapshot_dir / "data.yaml")
        previews: list[SamplePreview] = []
        issues: list[ValidationIssue] = []
        file_manifest: list[dict[str, object]] = []
        digest = sha256()
        for file_path in sorted(path for path in snapshot_dir.rglob("*") if path.is_file()):
            relative = file_path.relative_to(snapshot_dir).as_posix()
            content_digest = sha256()
            with file_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    content_digest.update(chunk)
            content_hash = content_digest.hexdigest()
            size = file_path.stat().st_size
            file_manifest.append({"path": relative, "sha256": content_hash, "size_bytes": size})
            digest.update(relative.encode("utf-8") + b"\0" + content_hash.encode("ascii") + b"\0" + str(size).encode("ascii") + b"\n")

        counts = {"train_images": 0, "val_images": 0, "test_images": 0, "images": 0, "annotations": 0, "background_images": 0}
        for split in _SPLITS:
            image_root = snapshot_dir / "images" / split
            label_root = snapshot_dir / "labels" / split
            images = sorted(path for path in image_root.rglob("*") if path.is_file()) if image_root.is_dir() else []
            labels = sorted(path for path in label_root.rglob("*") if path.is_file()) if label_root.is_dir() else []
            if split in {"train", "val"} and not images:
                _fail("SPLIT_EMPTY", f"images/{split}", f"{split} must contain at least one image")
            yaml_has_split = split != "test" or "test" in yaml_data
            if split == "test" and bool(images or labels) != yaml_has_split:
                _fail("TEST_SPLIT_MISMATCH", "data.yaml", "test YAML entry and test files must either both exist or both be absent")
            image_by_stem: dict[str, Path] = {}
            for image_path in images:
                relative_stem = image_path.relative_to(image_root).with_suffix("").as_posix()
                if relative_stem in image_by_stem:
                    _fail("IMAGE_STEM_AMBIGUOUS", image_path.relative_to(snapshot_dir).as_posix(), "Multiple images would map to the same label")
                image_by_stem[relative_stem] = image_path
            label_by_stem = {path.relative_to(label_root).with_suffix("").as_posix(): path for path in labels}
            orphan = sorted(set(label_by_stem) - set(image_by_stem))
            if orphan:
                _fail("LABEL_ORPHAN", label_by_stem[orphan[0]].relative_to(snapshot_dir).as_posix(), "Label has no matching image")
            for stem, image_path in image_by_stem.items():
                image_relative = image_path.relative_to(snapshot_dir).as_posix()
                label_path = label_by_stem.get(stem)
                expected_label = f"labels/{split}/{stem}.txt"
                if label_path is None:
                    _fail("LABEL_MISSING", expected_label, f"Image {image_relative} requires an explicit label file")
                width, height = _validate_image(image_path, image_relative)
                annotations, truncated = _parse_label(label_path, expected_label, classes)
                label_text = label_path.read_text(encoding="utf-8")
                annotation_count = sum(1 for line in label_text.splitlines() if line.strip())
                counts[f"{split}_images"] += 1
                counts["images"] += 1
                counts["annotations"] += annotation_count
                if annotation_count == 0:
                    counts["background_images"] += 1
                    issues.append(ValidationIssue("warning", "LABEL_EMPTY", expected_label, "Empty label explicitly marks a background image"))
                if len(previews) < MAX_PREVIEW_SAMPLES:
                    sample_id = sha256(image_relative.encode("utf-8")).hexdigest()[:24]
                    previews.append(SamplePreview(sample_id, split, image_relative, expected_label, width, height, tuple(annotations), truncated))
        return DatasetValidationResult(
            classes,
            counts,
            digest.hexdigest(),
            tuple(file_manifest),
            tuple(previews),
            counts["images"] > len(previews),
            tuple(issues),
        )
    except Exception:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise
