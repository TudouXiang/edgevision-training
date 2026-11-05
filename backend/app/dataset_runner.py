"""Production dataset adapter; no test mode and no ML dependency."""
from __future__ import annotations
from dataclasses import asdict

from .dataset_storage import resolve_storage_file
from .dataset_validation import DatasetValidationError, validate_dataset_archive
from .job_service import canonical
from .run_files import atomic_json, fingerprint, read_json, run_directory
from .runner_protocol import TaskInput


def log(text: str, level: str = "info") -> None:
    print(canonical({"level": level, "text": text}), flush=True)


def run(job_id: str, run_id: str) -> int:
    directory = run_directory(job_id, run_id)
    task = TaskInput.model_validate(read_json(directory / "input.json", 16384)).model_dump(mode="json")
    if set(task) != {"schema_version", "job_id", "run_id", "kind", "input"} or task["schema_version"] != 1 or task["job_id"] != job_id or task["run_id"] != run_id or task["kind"] != "dataset_check":
        return 65
    frozen = task["input"]
    source = resolve_storage_file(frozen["archive_key"])
    if fingerprint(source) != (frozen["size_bytes"], frozen["sha256"]):
        return 66
    log("Validation started")
    log("Archive fingerprint verified")
    bundle = directory / "bundle"
    bundle.mkdir(mode=0o700, exist_ok=False)
    try:
        result = validate_dataset_archive(source, bundle / "snapshot")
        report = {**result.report(), "job_id": job_id, "run_id": run_id, "dataset_id": frozen["dataset_id"], "archive_sha256": frozen["sha256"]}
        manifest = result.manifest()
        output = [{"path": f"snapshot/{item['path']}", "role": "snapshot", "size_bytes": item["size_bytes"], "sha256": item["sha256"]} for item in result.file_manifest]
        valid = True
        log("Dataset validation passed")
    except DatasetValidationError as exc:
        report = {"schema_version": 1, "job_id": job_id, "run_id": run_id, "dataset_id": frozen["dataset_id"],
                  "archive_sha256": frozen["sha256"], "valid": False, "errors": [asdict(exc.issue)], "warnings": [], "classes": [], "counts": {}}
        manifest, output, valid = {}, [], False
        log("Dataset validation failed", "error")
    atomic_json(bundle / "report.json", report)
    atomic_json(bundle / "manifest.json", manifest)
    for name, role in (("report.json", "report"), ("manifest.json", "manifest")):
        size, digest = fingerprint(bundle / name)
        output.append({"path": name, "role": role, "size_bytes": size, "sha256": digest})
    atomic_json(directory / "evidence.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id,
                "dataset_id": frozen["dataset_id"], "archive_sha256": frozen["sha256"], "valid": valid, "outputs": output})
    return 0 if valid else 2
