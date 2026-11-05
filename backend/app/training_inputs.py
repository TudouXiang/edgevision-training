"""Verify frozen reports and independently copy run-local training data."""
from pathlib import Path
import shutil
from hashlib import sha256
from .dataset_storage import resolve_storage_file
from .run_files import fingerprint, read_json, relative_file
from .training_assets import verify_asset, digest_json
from .training_contract import FrozenTraining


def verify_input(value):
    frozen = FrozenTraining.model_validate(value).model_dump(mode="json")
    if frozen["base_manifest"] != verify_asset() or digest_json(frozen["base_manifest"]) != frozen["base_manifest_sha256"]:
        raise ValueError("base asset binding changed")
    report_path = resolve_storage_file(frozen["report_key"])
    if fingerprint(report_path) != (frozen["report_size_bytes"], frozen["report_sha256"]):
        raise ValueError("frozen report changed")
    report = read_json(report_path)
    if report.get("valid") is not True or report.get("dataset_id") != frozen["dataset_id"] or report.get("archive_sha256") != frozen["archive_sha256"] or report.get("snapshot_sha256") != frozen["snapshot_sha256"] or report.get("files") != frozen["files"] or report.get("classes") != frozen["classes"] or report.get("counts") != frozen["counts"]:
        raise ValueError("frozen report binding mismatch")
    digest = sha256()
    previous = None
    for item in frozen["files"]:
        if previous is not None and item["path"] <= previous: raise ValueError("noncanonical file manifest")
        previous = item["path"]
        source = resolve_storage_file(frozen["snapshot_key"] + "/" + item["path"])
        if fingerprint(source) != (item["size_bytes"], item["sha256"]): raise ValueError("snapshot changed")
        digest.update(item["path"].encode() + b"\0" + item["sha256"].encode() + b"\0" + str(item["size_bytes"]).encode() + b"\n")
    if digest.hexdigest() != frozen["snapshot_sha256"]: raise ValueError("snapshot manifest digest mismatch")
    return frozen


def copy_input(frozen, directory):
    frozen = verify_input(frozen)
    needed = sum(f["size_bytes"] for f in frozen["files"]) + 512 * 1024**2
    if shutil.disk_usage(directory).free < needed: raise OSError("insufficient training disk budget")
    destination = directory / "dataset"
    destination.mkdir(mode=0o700)
    for item in frozen["files"]:
        if item["path"] == "data.yaml": continue
        source = resolve_storage_file(frozen["snapshot_key"] + "/" + item["path"])
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as inp, target.open("xb") as out: shutil.copyfileobj(inp, out)
        if fingerprint(relative_file(destination, item["path"])) != (item["size_bytes"], item["sha256"]): raise ValueError("copy changed")
    import yaml
    content = {"path": str(destination), "train": "images/train", "val": "images/val", "names": frozen["classes"], "nc": len(frozen["classes"])}
    (destination / "data.yaml").write_text(yaml.safe_dump(content, allow_unicode=True))
    return destination
