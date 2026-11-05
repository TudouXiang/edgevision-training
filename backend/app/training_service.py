"""Authorized immutable train submission and sanitized provenance."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4
from fastapi import HTTPException
from .services import project_for_actor, project_for_resource, active_project
from .job_service import canonical, append_event
from .run_files import read_json, fingerprint
from .dataset_storage import resolve_storage_file
from .security import timestamp
from .training_assets import capability, verify_asset, digest_json, runtime_identity
from .training_contract import FrozenTraining


def provenance(frozen):
    return {"base_model_sha256": frozen["base_manifest"]["sha256"], **{key: frozen[key] for key in ("schema_version", "dataset_id", "dataset_version", "archive_sha256", "snapshot_sha256", "report_artifact_id", "report_sha256", "classes", "counts", "params", "base_manifest_sha256", "runtime_binding", "code_version")}}


def submit_train(connection, actor, project_id, params, source_job_id, key, path):
    project = project_for_actor(connection, project_id, actor)
    values = params.model_dump(mode="json")
    values["learning_rate"] = values["learning_rate"] if values["learning_rate"] is not None else .01
    body_hash = digest_json({"kind": "train", "params": values, "source_job_id": source_job_id})
    previous = connection.execute("SELECT * FROM idempotency_keys WHERE owner_id=? AND request_key=? AND method='POST' AND path=?", (actor.id, key, path)).fetchone()
    if previous:
        if previous["body_sha256"] != body_hash: raise HTTPException(409, {"code": "IDEMPOTENCY_CONFLICT", "message": "This key was used with different parameters"})
        old = connection.execute("SELECT id,status FROM jobs WHERE id=?", (previous["job_id"],)).fetchone()
        return {"job_id": old["id"], "state": old["status"]}
    active_project(project)
    project_for_resource(connection, "datasets", values["dataset_id"], actor)
    dataset = connection.execute("SELECT * FROM datasets WHERE id=? AND project_id=?", (values["dataset_id"], project_id)).fetchone()
    if not dataset: raise HTTPException(404, {"code": "RESOURCE_NOT_FOUND", "message": "Dataset was not found in this project"})
    if dataset["status"] != "ready": raise HTTPException(409, {"code": "DATASET_NOT_READY", "message": "Training requires a validated immutable dataset"})
    if source_job_id:
        project_for_resource(connection, "jobs", source_job_id, actor)
        source = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='train'", (source_job_id, project_id)).fetchone()
        if not source: raise HTTPException(404, {"code": "RESOURCE_NOT_FOUND", "message": "Source training job was not found"})
        if source["status"] in {"queued", "running", "cancelling"}: raise HTTPException(409, {"code": "SOURCE_JOB_ACTIVE", "message": "Retry requires a terminal source job"})
    if values["device"] != "cpu": raise HTTPException(409, {"code": "DEVICE_UNAVAILABLE", "message": "Only the verified CPU device is available"})
    if not capability()["available"]: raise HTTPException(409, {"code": "TRAINING_SETUP_REQUIRED", "message": "Operator CPU runtime and trusted asset verification is required"})
    try:
        report_artifact = connection.execute("SELECT * FROM artifacts WHERE storage_key=? AND project_id=? AND kind='dataset_report' AND validation_status='passed'", (dataset["report_key"], project_id)).fetchone()
        if not report_artifact: raise ValueError("missing report")
        report_path = resolve_storage_file(dataset["report_key"])
        if fingerprint(report_path) != (report_artifact["size_bytes"], report_artifact["sha256"]): raise ValueError("report changed")
        report = read_json(report_path)
        manifest = verify_asset()
        # Source fingerprint is available without executing Git in the API process.
        code_version = digest_json(runtime_identity()["adapter"])
        frozen = FrozenTraining.model_validate({"schema_version": 1, "dataset_id": dataset["id"], "dataset_version": dataset["version"],
            "archive_sha256": dataset["sha256"], "snapshot_key": dataset["snapshot_key"], "snapshot_sha256": report["snapshot_sha256"],
            "report_artifact_id": report_artifact["id"], "report_key": dataset["report_key"], "report_size_bytes": report_artifact["size_bytes"], "report_sha256": report_artifact["sha256"],
            "files": report["files"], "classes": json.loads(dataset["classes_json"]), "counts": json.loads(dataset["counts_json"]), "params": values,
            "base_manifest": manifest, "base_manifest_sha256": digest_json(manifest), "runtime_binding": digest_json(runtime_identity()), "code_version": code_version}).model_dump(mode="json")
        if report.get("valid") is not True or report.get("classes") != frozen["classes"] or report.get("counts") != frozen["counts"] or report.get("dataset_id") != frozen["dataset_id"]: raise ValueError("report binding")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(409, {"code": "TRAINING_INPUT_UNAVAILABLE", "message": "Validated training inputs are missing or changed"}) from exc
    job_id = str(uuid4())
    connection.execute("INSERT INTO jobs(id,project_id,owner_id,kind,status,payload_json,input_snapshot_json,retry_of_id,code_version,created_at) VALUES(?,?,?,'train','queued',?,?,?,?,?)",
        (job_id, project_id, actor.id, canonical(values), canonical(frozen), source_job_id, code_version, timestamp()))
    append_event(connection, job_id, "status", {"status": "queued"})
    connection.execute("INSERT INTO idempotency_keys(owner_id,request_key,method,path,body_sha256,job_id,created_at) VALUES(?,?,'POST',?,?,?,?)", (actor.id, key, path, body_hash, job_id, timestamp()))
    return {"job_id": job_id, "state": "queued"}
