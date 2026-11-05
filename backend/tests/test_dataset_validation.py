"""T030 pure validator coverage using only generated synthetic fixtures."""

from io import BytesIO
from pathlib import Path
import stat
import struct
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from PIL import Image
import pytest

from app import dataset_validation as validation
from app.dataset_validation import DatasetValidationError, inspect_dataset_archive, validate_dataset_archive


def png(width: int = 8, height: int = 8) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), (40, 120, 80)).save(output, format="PNG")
    return output.getvalue()


def dataset_entries(*, wrapper: str = "", names: str = "[cat, dog]", train_label: bytes = b"0 0.5 0.5 0.5 0.5\n") -> list[tuple[str | ZipInfo, bytes]]:
    prefix = f"{wrapper}/" if wrapper else ""
    yaml = f"train: images/train\nval: images/val\nnc: 2\nnames: {names}\n".encode()
    return [
        (prefix + "data.yaml", yaml),
        (prefix + "images/train/a.png", png()),
        (prefix + "labels/train/a.txt", train_label),
        (prefix + "images/val/b.jpg", _jpeg()),
        (prefix + "labels/val/b.txt", b"1 0.5 0.5 0.25 0.25\n"),
    ]


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (9, 7), (80, 30, 100)).save(output, format="JPEG")
    return output.getvalue()


def write_zip(path: Path, entries: list[tuple[str | ZipInfo, bytes]]) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return path


def issue(path: Path, code: str, *, snapshot: Path | None = None) -> DatasetValidationError:
    with pytest.raises(DatasetValidationError) as caught:
        if snapshot is None:
            inspect_dataset_archive(path)
        else:
            validate_dataset_archive(path, snapshot)
    assert caught.value.issue.code == code
    assert caught.value.issue.path
    if snapshot is not None:
        assert not snapshot.exists()
    return caught.value


def test_valid_root_and_wrapper_are_deterministic_and_empty_label_is_explicit(tmp_path):
    first = write_zip(tmp_path / "first.zip", dataset_entries(train_label=b""))
    result = validate_dataset_archive(first, tmp_path / "snapshot-one")
    assert result.classes == ("cat", "dog")
    assert result.counts == {
        "train_images": 1, "val_images": 1, "test_images": 0,
        "images": 2, "annotations": 1, "background_images": 1,
    }
    assert [(item.code, item.path) for item in result.warnings] == [("LABEL_EMPTY", "labels/train/a.txt")]
    assert result.samples[0].annotations == ()
    assert result.manifest()["preview_samples"][1]["width"] == 9

    wrapped = write_zip(tmp_path / "wrapped.zip", dataset_entries(wrapper="bundle", names="{0: cat, 1: dog}"))
    wrapped_result = validate_dataset_archive(wrapped, tmp_path / "snapshot-two")
    assert wrapped_result.classes == result.classes
    assert wrapped_result.snapshot_sha256 != result.snapshot_sha256  # first fixture has an empty label
    assert (tmp_path / "snapshot-two" / "data.yaml").is_file()
    assert not (tmp_path / "snapshot-two" / "bundle").exists()


@pytest.mark.parametrize(
    ("replacement", "code"),
    [
        ({"labels/train/a.txt": None}, "LABEL_MISSING"),
        ({"labels/train/a.txt": b"2 0.5 0.5 0.2 0.2\n"}, "LABEL_CLASS_RANGE"),
        ({"labels/train/a.txt": b"0 nan 0.5 0.2 0.2\n"}, "LABEL_COORDINATE_NONFINITE"),
        ({"labels/train/a.txt": b"0 0.05 0.5 0.2 0.2\n"}, "LABEL_BOX_OUT_OF_BOUNDS"),
        ({"labels/train/a.txt": b"0 0.5 0.5 0 0.2\n"}, "LABEL_COORDINATE_RANGE"),
        ({"labels/train/a.txt": b"0 0.5 0.5 0.2\n"}, "LABEL_FIELD_COUNT"),
    ],
)
def test_label_failures_are_sample_local_and_clean_snapshot(tmp_path, replacement, code):
    entries = {str(name): content for name, content in dataset_entries()}
    for name, content in replacement.items():
        if content is None:
            entries.pop(name)
        else:
            entries[name] = content
    archive = write_zip(tmp_path / f"{code}.zip", list(entries.items()))
    caught = issue(archive, code, snapshot=tmp_path / f"snapshot-{code}")
    assert caught.issue.path.startswith("labels/")


def test_orphan_ambiguous_extension_and_corrupt_images_fail(tmp_path, monkeypatch):
    orphan = dataset_entries() + [("labels/train/orphan.txt", b"")]
    issue(write_zip(tmp_path / "orphan.zip", orphan), "LABEL_ORPHAN", snapshot=tmp_path / "orphan-out")

    ambiguous = dataset_entries() + [("images/train/a.jpg", _jpeg())]
    issue(write_zip(tmp_path / "ambiguous.zip", ambiguous), "IMAGE_STEM_AMBIGUOUS", snapshot=tmp_path / "ambiguous-out")

    corrupt = [(name, b"not-an-image" if str(name) == "images/train/a.png" else content) for name, content in dataset_entries()]
    issue(write_zip(tmp_path / "corrupt.zip", corrupt), "IMAGE_CORRUPT", snapshot=tmp_path / "corrupt-out")

    monkeypatch.setattr(validation, "MAX_IMAGE_PIXELS", 10)
    issue(write_zip(tmp_path / "pixels.zip", dataset_entries()), "IMAGE_PIXEL_LIMIT", snapshot=tmp_path / "pixels-out")


@pytest.mark.parametrize(
    ("yaml_text", "code"),
    [
        ("train: []\nval: images/val\nnames: [cat]\n", "YAML_SPLIT_INVALID"),
        ("train: images/train\nval: images/val\nnames: &n [cat]\n", "YAML_FEATURE_FORBIDDEN"),
        ("train: images/train\nval: images/val\nnames: [cat]\nnames: [dog]\n", "YAML_DUPLICATE_KEY"),
        ("train: images/train\nval: images/val\nnames: {0: cat, 2: dog}\n", "YAML_NAMES_INVALID"),
        ("train: images/train\nval: images/val\nnames: [cat]\nnc: 2\n", "YAML_NC_MISMATCH"),
        ("train: images/train\nval: images/val\nnames: [cat]\ndownload: echo bad\n", "YAML_FIELD_FORBIDDEN"),
        ("train: images/train\nval: images/val\nnames: [cat]\npath: /tmp\n", "YAML_PATH_FORBIDDEN"),
    ],
)
def test_yaml_is_restricted_and_failures_are_normalized(tmp_path, yaml_text, code):
    entries = [(name, yaml_text.encode() if str(name) == "data.yaml" else content) for name, content in dataset_entries(names="[cat]")]
    issue(write_zip(tmp_path / f"{code}.zip", entries), code, snapshot=tmp_path / f"out-{code}")


def test_yaml_complexity_and_huge_integer_do_not_escape_as_runtime_errors(tmp_path):
    nested = "[" * 40 + "cat" + "]" * 40
    for index, (extra, expected) in enumerate(((f"names: {nested}\n", "YAML_COMPLEXITY_LIMIT"), ("names: [cat]\nnc: " + "9" * 5000 + "\n", "YAML_INVALID"))):
        yaml_text = "train: images/train\nval: images/val\n" + extra
        entries = [(name, yaml_text.encode() if str(name) == "data.yaml" else content) for name, content in dataset_entries(names="[cat]")]
        issue(write_zip(tmp_path / f"complex-{index}.zip", entries), expected, snapshot=tmp_path / f"complex-out-{index}")


@pytest.mark.parametrize(
    ("bad_name", "code"),
    [
        ("../data.yaml", "ARCHIVE_PATH_TRAVERSAL"),
        ("/data.yaml", "ARCHIVE_PATH_ABSOLUTE"),
        ("bundle\\data.yaml", "ARCHIVE_PATH_INVALID"),
        ("images/train/a?.png", "ARCHIVE_PATH_INVALID"),
    ],
)
def test_archive_paths_are_portable(tmp_path, bad_name, code):
    issue(write_zip(tmp_path / f"bad-{code}.zip", [(bad_name, b"x")]), code)


def test_archive_rejects_link_duplicates_case_and_file_directory_collisions(tmp_path):
    link = ZipInfo("data.yaml")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    issue(write_zip(tmp_path / "link.zip", [(link, b"target")]), "ARCHIVE_LINK_OR_SPECIAL")

    duplicate = dataset_entries() + [("data.yaml", b"train: x")]
    issue(write_zip(tmp_path / "duplicate.zip", duplicate), "ARCHIVE_DUPLICATE_PATH")

    case = dataset_entries() + [("images/train/A.png", png())]
    issue(write_zip(tmp_path / "case.zip", case), "ARCHIVE_DUPLICATE_PATH")

    collision = dataset_entries() + [("images/train/tree", b"file"), ("images/train/tree/a.png", png())]
    issue(write_zip(tmp_path / "collision.zip", collision), "ARCHIVE_PATH_COLLISION")


def test_archive_declared_limits_and_ratio_are_enforced_without_extracting(tmp_path, monkeypatch):
    archive = write_zip(tmp_path / "limits.zip", dataset_entries())
    monkeypatch.setattr(validation, "MAX_ARCHIVE_ENTRIES", 2)
    issue(archive, "ARCHIVE_ENTRY_LIMIT")
    monkeypatch.setattr(validation, "MAX_ARCHIVE_ENTRIES", 20_000)
    monkeypatch.setattr(validation, "MAX_ARCHIVE_EXPANDED_BYTES", 100)
    issue(archive, "ARCHIVE_EXPANDED_LIMIT")

    ratio_entries = dataset_entries() + [("labels/train/repeated.txt", b"0" * (1024 * 1024))]
    ratio = write_zip(tmp_path / "ratio.zip", ratio_entries)
    monkeypatch.setattr(validation, "MAX_ARCHIVE_EXPANDED_BYTES", 2 * 1024 * 1024 * 1024)
    monkeypatch.setattr(validation, "MAX_ARCHIVE_COMPRESSION_RATIO", 2)
    issue(ratio, "ARCHIVE_COMPRESSION_RATIO")


def test_aggregate_ratio_and_raw_central_directory_bounds_precede_zipinfo_allocation(tmp_path):
    aggregate_entries = dataset_entries() + [
        ("labels/train/repeated-one.txt", b"0" * 700_000),
        ("labels/train/repeated-two.txt", b"0" * 700_000),
    ]
    issue(write_zip(tmp_path / "aggregate.zip", aggregate_entries), "ARCHIVE_COMPRESSION_RATIO")

    valid = bytearray(write_zip(tmp_path / "valid.zip", dataset_entries()).read_bytes())
    eocd = valid.rfind(b"PK\x05\x06")
    assert eocd > 0
    struct.pack_into("<H", valid, eocd + 8, validation.MAX_ARCHIVE_ENTRIES + 1)
    struct.pack_into("<H", valid, eocd + 10, validation.MAX_ARCHIVE_ENTRIES + 1)
    too_many = tmp_path / "declared-entries.zip"
    too_many.write_bytes(valid)
    issue(too_many, "ARCHIVE_ENTRY_LIMIT")

    sfx = tmp_path / "sfx.zip"
    sfx.write_bytes(b"executable-prefix" + write_zip(tmp_path / "plain.zip", dataset_entries()).read_bytes())
    issue(sfx, "ARCHIVE_CONTAINER_UNSUPPORTED")
