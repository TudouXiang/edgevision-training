"""Verify completed run evidence, then publish one immutable dataset/report bundle."""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from uuid import uuid4


from .config import data_root
from .database import transaction
from .dataset_storage import resolve_storage_file, safe_directory
from .job_service import canonical, transition
from .run_files import fingerprint, read_json, relative_file, run_directory
from .schemas import DatasetSamplePublic
from .runner_protocol import ValidationEvidence
from .security import timestamp


def verify(job: dict, exit_code: int) -> tuple[dict, dict, dict]:
    directory = run_directory(job["id"], job["run_id"])
    evidence = ValidationEvidence.model_validate(read_json(directory / "evidence.json"))
    frozen = json.loads(job["input_snapshot_json"])
    if (str(evidence.job_id), str(evidence.run_id), str(evidence.dataset_id), evidence.archive_sha256) != (job["id"], job["run_id"], frozen["dataset_id"], frozen["sha256"]):
        raise ValueError("evidence does not bind this run and input")
    if exit_code != (0 if evidence.valid else 2):
        raise ValueError("adapter exit does not match evidence")
    if fingerprint(resolve_storage_file(frozen["archive_key"])) != (frozen["size_bytes"], frozen["sha256"]):
        raise ValueError("frozen archive fingerprint changed")
    bundle = directory / "bundle"
    names = set()
    snapshot = []
    report_entry = None
    for output in evidence.outputs:
        if output.path in names:
            raise ValueError("duplicate output path")
        names.add(output.path)
        if output.role == "snapshot":
            if not output.path.startswith("snapshot/"):
                raise ValueError("snapshot path invalid")
            snapshot.append({"path": output.path[len("snapshot/"):], "sha256": output.sha256, "size_bytes": output.size_bytes})
        elif output.path != f"{output.role}.json":
            raise ValueError("output role mismatch")
        if output.role == "report":
            report_entry = output.model_dump()
        if fingerprint(relative_file(bundle, output.path)) != (output.size_bytes, output.sha256):
            raise ValueError("output missing or corrupt")
    actual = set()
    for item in bundle.rglob("*"):
        mode = item.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError("special output rejected")
        if stat.S_ISREG(mode):
            actual.add(item.relative_to(bundle).as_posix())
    if actual != names or report_entry is None or "manifest.json" not in names:
        raise ValueError("unlisted or missing output")
    report, manifest = read_json(bundle / "report.json"), read_json(bundle / "manifest.json")
    if report.get("schema_version") != 1 or report.get("valid") is not evidence.valid or report.get("job_id") != job["id"] or report.get("run_id") != job["run_id"] or report.get("dataset_id") != frozen["dataset_id"] or report.get("archive_sha256") != frozen["sha256"]:
        raise ValueError("report binding invalid")
    classes, counts = report.get("classes"), report.get("counts")
    if not isinstance(classes, list) or not all(isinstance(value, str) and value for value in classes) or not isinstance(counts, dict) or any(not isinstance(key, str) or type(value) is not int or value < 0 for key, value in counts.items()):
        raise ValueError("report metadata invalid")
    if evidence.valid:
        if not snapshot or not classes or counts.get("images", 0) < 2 or report.get("files") != sorted(snapshot, key=lambda item: item["path"]):
            raise ValueError("snapshot manifest mismatch")
        digest = sha256()
        for item in sorted(snapshot, key=lambda item: item["path"]):
            digest.update(item["path"].encode() + b"\0" + item["sha256"].encode() + b"\0" + str(item["size_bytes"]).encode() + b"\n")
        if report.get("snapshot_sha256") != digest.hexdigest() or manifest.get("snapshot_sha256") != digest.hexdigest() or manifest.get("schema_version") != 1:
            raise ValueError("snapshot digest mismatch")
        for sample in manifest["preview_samples"]:
            DatasetSamplePublic.model_validate({**sample, "image_url": "/verified"})
    elif snapshot or manifest or not report.get("errors"):
        raise ValueError("invalid dataset report is incomplete")
    return report, manifest, report_entry


def publish(job: dict, exit_code: int) -> bool:
    report, manifest, report_entry = verify(job, exit_code)
    valid = report["valid"]
    directory = run_directory(job["id"], job["run_id"])
    dataset_id = json.loads(job["input_snapshot_json"])["dataset_id"]
    bundle_key = f"datasets/{dataset_id}/validations/{job['run_id']}"
    intent = {"schema_version": 1, "run_id": job["run_id"], "bundle_key": bundle_key, "report_sha256": report_entry["sha256"]}
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("SELECT status FROM jobs WHERE id=? AND run_id=?", (job["id"], job["run_id"])).fetchone()
        if current is None or current["status"] != "running":
            return False
        if not connection.execute("SELECT 1 FROM datasets WHERE id=? AND validation_job_id=? AND status='validating'", (dataset_id, job["id"])).fetchone():
            raise ValueError("stale validation job")
        connection.execute("UPDATE jobs SET publication_json=? WHERE id=? AND run_id=? AND status='running'", (canonical(intent), job["id"], job["run_id"]))
    parent = safe_directory(data_root(), "datasets", dataset_id, "validations")
    destination = parent / job["run_id"]
    if destination.exists():
        raise ValueError("immutable publication target exists")
    os.rename(directory / "bundle", destination)
    if os.name != "nt":
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    # A process crash above intentionally leaves an unreferenced bundle. Recovery
    # never reconstructs success from its existence.
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("SELECT status FROM jobs WHERE id=? AND run_id=?", (job["id"], job["run_id"])).fetchone()
        if current is None or current["status"] != "running":
            return False
        dataset = connection.execute("SELECT status,validation_job_id FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if dataset is None or dataset["status"] != "validating" or dataset["validation_job_id"] != job["id"]:
            raise ValueError("stale publication")
        artifact_id = str(uuid4())
        now = timestamp()
        report_key = f"{bundle_key}/report.json"
        connection.execute("""INSERT INTO artifacts(id,project_id,job_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at,validated_at)
                            VALUES(?,?,?,'dataset_report','json',?,?,?,'passed',?,?,?)""",
                           (artifact_id, job["project_id"], job["id"], report_key, report_entry["sha256"], report_entry["size_bytes"], canonical({"schema_version": 1, "dataset_id": dataset_id, "valid": valid}), now, now))
        connection.execute("""UPDATE datasets SET status=?,snapshot_key=?,report_key=?,classes_json=?,counts_json=?,manifest_json=?
                            WHERE id=? AND validation_job_id=? AND status='validating'""",
                           ("ready" if valid else "invalid", f"{bundle_key}/snapshot" if valid else "", report_key, canonical(report["classes"]), canonical(report["counts"]), canonical(manifest), dataset_id, job["id"]))
        changed = transition(connection, job["id"], "running", "succeeded" if valid else "failed", run_id=job["run_id"],
                             process_exited=True, evidence_verified=True,
                             fields={"error_code": None if valid else "DATASET_INVALID", "error_message": None if valid else "Dataset content validation failed; see report", "launch_phase": "finished"})
        if not changed:
            raise RuntimeError("publication lost terminal compare-and-set")
    return True
