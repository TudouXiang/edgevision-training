"""Verify and atomically publish both trained PT files after witnessed tree exit."""
import json
import os
import stat
from uuid import uuid4
from .config import data_root
from .database import transaction
from .dataset_storage import safe_directory
from .job_service import canonical, transition
from .run_files import fingerprint, read_json, relative_file, run_directory
from .security import timestamp
from .training_assets import digest_json
from .training_contract import TrainingEvidence, MAX_PT_BYTES
from .training_inputs import verify_input
from .training_service import provenance
from .schemas import TrainingRuntime, TrainingArtifactMetadata


def verify(job):
    directory = run_directory(job["id"], job["run_id"])
    frozen = verify_input(json.loads(job["input_snapshot_json"]))
    evidence = TrainingEvidence.model_validate(read_json(directory / "evidence.json"))
    if str(evidence.job_id) != job["id"] or str(evidence.run_id) != job["run_id"] or evidence.input_sha256 != digest_json(frozen) or evidence.completed_epochs != frozen["params"]["epochs"]: raise ValueError("training evidence binding invalid")
    expected = {"best.pt", "last.pt", "metadata.json"}
    bundle = directory / "bundle"
    actual = set()
    for item in bundle.rglob("*"):
        mode = item.lstat().st_mode
        if not stat.S_ISREG(mode): raise ValueError("unexpected output type")
        actual.add(item.relative_to(bundle).as_posix())
    if actual != expected or {e.path for e in evidence.outputs} != expected: raise ValueError("incomplete output bundle")
    entries = {}
    for entry in evidence.outputs:
        if entry.size_bytes <= 0 or entry.size_bytes > MAX_PT_BYTES or fingerprint(relative_file(bundle, entry.path)) != (entry.size_bytes, entry.sha256): raise ValueError("output fingerprint invalid")
        entries[entry.path] = entry.model_dump()
    metadata = read_json(bundle / "metadata.json", 65536)
    if set(metadata) != {"schema_version", "job_id", "run_id", "classes", "runtime", "input_sha256", "metrics_size_bytes", "metrics_sha256", "metric_count"} or metadata["schema_version"] != 1 or metadata["job_id"] != job["id"] or metadata["run_id"] != job["run_id"] or metadata["classes"] != frozen["classes"] or metadata["input_sha256"] != evidence.input_sha256 or metadata["metric_count"] != evidence.metric_count: raise ValueError("metadata binding invalid")
    if fingerprint(directory / "metrics.jsonl") != (metadata["metrics_size_bytes"], metadata["metrics_sha256"]): raise ValueError("metric journal changed")
    runtime = TrainingRuntime.model_validate(metadata["runtime"]).model_dump(mode="json")
    metadata["runtime"] = runtime
    if runtime["completed_epochs"] != evidence.completed_epochs or runtime["optimizer_steps"] != evidence.optimizer_steps or runtime["device"] != "cpu": raise ValueError("runtime evidence mismatch")
    with transaction() as connection:
        record = json.loads(connection.execute("SELECT process_identity_json FROM jobs WHERE id=? AND run_id=?", (job["id"], job["run_id"])).fetchone()[0])
        count = connection.execute("SELECT COUNT(*) FROM metrics WHERE job_id=?", (job["id"],)).fetchone()[0]
    if record.get("metric_sequence") != evidence.metric_count or record.get("metric_offset") != metadata["metrics_size_bytes"] or count != evidence.metric_count: raise ValueError("metrics not fully persisted")
    return frozen, metadata, entries


def publish(job):
    frozen, metadata, entries = verify(job)
    directory = run_directory(job["id"], job["run_id"])
    bundle_key = f"trained/{job['id']}/{job['run_id']}"
    intent = {"schema_version": 1, "run_id": job["run_id"], "bundle_key": bundle_key, "outputs": entries}
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        changed = connection.execute("UPDATE jobs SET publication_json=? WHERE id=? AND run_id=? AND status='running'", (canonical(intent), job["id"], job["run_id"])).rowcount
        if changed != 1: return False
    parent = safe_directory(data_root(), "trained", job["id"])
    destination = parent / job["run_id"]
    if destination.exists(): raise ValueError("immutable publication already exists")
    os.rename(directory / "bundle", destination)
    if os.name != "nt":
        descriptor = os.open(parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("SELECT status FROM jobs WHERE id=? AND run_id=?", (job["id"], job["run_id"])).fetchone()
        if not current or current["status"] != "running": return False
        now = timestamp()
        for name, kind in (("best.pt", "pt_best"), ("last.pt", "pt_last")):
            entry = entries[name]
            public = {"schema_version": 1, "task": "detection", "architecture": "yolo11n", "classes": frozen["classes"], "provenance": provenance(frozen), "runtime": metadata["runtime"], "validation_scope": "weights_only_detection_checkpoint"}
            public = TrainingArtifactMetadata.model_validate(public).model_dump(mode="json")
            connection.execute("INSERT INTO artifacts(id,project_id,job_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at,validated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), job["project_id"], job["id"], kind, "pt", bundle_key + "/" + name, entry["sha256"], entry["size_bytes"], "passed", canonical(public), now, now))
        connection.execute("UPDATE jobs SET environment_json=? WHERE id=?", (canonical(metadata["runtime"]), job["id"]))
        if not transition(connection, job["id"], "running", "succeeded", run_id=job["run_id"], process_exited=True, evidence_verified=True, fields={"launch_phase": "finished"}): raise RuntimeError("publication CAS failed")
    return True
