"""Transactional job state, idempotency, bounded event queries and ownership DTOs."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

from fastapi import HTTPException

from .contracts import JobState, TERMINAL_STATES, require_transition
from .security import Actor, timestamp
from .services import active_project, project_for_actor, project_for_resource

MAX_LOG_BYTES = 512 * 1024
MAX_LOG_LINE_BYTES = 2048
MAX_LOG_EVENTS = 2000
MAX_RESPONSE_BYTES = 64 * 1024


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def append_event(connection: sqlite3.Connection, job_id: str, kind: str, payload: dict) -> int:
    seq = connection.execute("SELECT COALESCE(MAX(seq),0)+1 FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0]
    connection.execute("INSERT INTO job_events(job_id,seq,kind,payload_json,created_at) VALUES(?,?,?,?,?)", (job_id, seq, kind, canonical(payload), timestamp()))
    return seq


def transition(connection: sqlite3.Connection, job_id: str, before: str, after: str, *, run_id: str | None = None,
               process_exited: bool = False, evidence_verified: bool = False, fields: dict | None = None) -> bool:
    """The only runtime status UPDATE: compare-and-set and its event share a transaction."""
    require_transition(JobState(before), JobState(after), process_exited=process_exited, evidence_verified=evidence_verified)
    values = dict(fields or {})
    allowed = {"started_at", "finished_at", "heartbeat_at", "worker_pid", "run_id", "worker_instance", "host_boot_id", "error_code", "error_message", "cancel_requested_at", "launch_phase"}
    if set(values) - allowed:
        raise ValueError("unsupported transition field")
    if JobState(after) in TERMINAL_STATES:
        values.update(finished_at=timestamp(), worker_pid=None)
    if after == "cancelling":
        values["cancel_requested_at"] = timestamp()
    assignment = ",".join(["status=?", *(f"{key}=?" for key in values)])
    query = f"UPDATE jobs SET {assignment} WHERE id=? AND status=?"
    parameters = [after, *values.values(), job_id, before]
    if run_id is not None:
        query += " AND run_id=?"
        parameters.append(run_id)
    changed = connection.execute(query, parameters).rowcount == 1
    if changed:
        append_event(connection, job_id, "status", {"status": after})
    return changed


def invalidate_dataset(connection: sqlite3.Connection, job_id: str) -> None:
    # Never touch a ready snapshot or a newer validation run. Preserve older reports.
    connection.execute("UPDATE datasets SET status='pending' WHERE validation_job_id=? AND status='validating'", (job_id,))


def job_public(row) -> dict:
    training = None
    export = None
    if row["kind"] == "export_onnx":
        from .export_contract import FrozenExport
        frozen = FrozenExport.model_validate_json(row["input_snapshot_json"]).model_dump(mode="json")
        export = {key: frozen[key] for key in ("source_artifact_id", "source_job_id", "source_sha256", "params", "runtime_binding", "code_version")}
    if row["kind"] == "train":
        from .training_service import provenance
        frozen = json.loads(row["input_snapshot_json"])
        if frozen.get("schema_version") == 1 and "runtime_binding" in frozen:
            training = provenance(frozen)
    return {"id": row["id"], "project_id": row["project_id"], "created_by": row["owner_id"], "kind": row["kind"],
            "state": row["status"], "params_schema_version": row["params_schema_version"], "created_at": row["created_at"],
            "started_at": row["started_at"], "finished_at": row["finished_at"], "error_code": row["error_code"], "source_job_id": row["retry_of_id"], "training": training, "export": export}


def artifact_public(row) -> dict:
    return {"id": row["id"], "project_id": row["project_id"], "job_id": row["job_id"], "kind": row["kind"], "format": row["format"],
            "sha256": row["sha256"], "size_bytes": row["size_bytes"], "metadata_schema_version": row["metadata_schema_version"],
            "validation_state": row["validation_status"], "metadata": json.loads(row["metadata_json"]), "created_at": row["created_at"]}


def submit_check(connection: sqlite3.Connection, actor: Actor, project_id: str, dataset_id: str, key: str, path: str) -> dict:
    project = project_for_actor(connection, project_id, actor)
    project_for_resource(connection, "datasets", dataset_id, actor)
    dataset = connection.execute("SELECT * FROM datasets WHERE id=? AND project_id=?", (dataset_id, project_id)).fetchone()
    if dataset is None:
        raise HTTPException(404, {"code": "RESOURCE_NOT_FOUND", "message": "Dataset was not found in this project"})
    body_hash = sha256(canonical({"kind": "dataset_check", "params": {"dataset_id": dataset_id}}).encode()).hexdigest()
    previous = connection.execute("SELECT * FROM idempotency_keys WHERE owner_id=? AND request_key=? AND method='POST' AND path=?", (actor.id, key, path)).fetchone()
    if previous:
        if previous["body_sha256"] != body_hash:
            raise HTTPException(409, {"code": "IDEMPOTENCY_CONFLICT", "message": "This key was already used with different parameters"})
        job = connection.execute("SELECT id,status FROM jobs WHERE id=?", (previous["job_id"],)).fetchone()
        return {"job_id": job["id"], "state": job["status"]}
    active_project(project)
    if dataset["status"] == "ready":
        raise HTTPException(409, {"code": "DATASET_ALREADY_READY", "message": "Validated snapshots are immutable; upload a new version"})
    previous_job = connection.execute("SELECT * FROM jobs WHERE id=?", (dataset["validation_job_id"],)).fetchone() if dataset["validation_job_id"] else None
    if previous_job and previous_job["status"] in {"queued", "running", "cancelling"}:
        job_id, state = previous_job["id"], previous_job["status"]
    else:
        job_id, state = str(uuid4()), "queued"
        frozen = {"schema_version": 1, "dataset_id": dataset_id, "archive_key": dataset["archive_key"], "sha256": dataset["sha256"], "size_bytes": dataset["size_bytes"]}
        connection.execute("""INSERT INTO jobs(id,project_id,owner_id,kind,status,payload_json,input_snapshot_json,retry_of_id,created_at)
                              VALUES(?,?,?,'dataset_check','queued',?,?,?,?)""",
                           (job_id, project_id, actor.id, canonical({"dataset_id": dataset_id}), canonical(frozen), previous_job["id"] if previous_job else None, timestamp()))
        connection.execute("UPDATE datasets SET status='validating',validation_job_id=?,report_key=NULL WHERE id=? AND status!='ready'", (job_id, dataset_id))
        append_event(connection, job_id, "status", {"status": "queued"})
    connection.execute("INSERT INTO idempotency_keys(owner_id,request_key,method,path,body_sha256,job_id,created_at) VALUES(?,?,'POST',?,?,?,?)", (actor.id, key, path, body_hash, job_id, timestamp()))
    return {"job_id": job_id, "state": state}


def cancel_job(connection: sqlite3.Connection, job_id: str) -> dict:
    row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row["status"] == "queued":
        if transition(connection, job_id, "queued", "cancelled", fields={"error_code": "CANCELLED", "error_message": "Cancelled before execution"}):
            invalidate_dataset(connection, job_id)
    elif row["status"] == "running":
        transition(connection, job_id, "running", "cancelling")
    return job_public(connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def incremental(connection: sqlite3.Connection, job_id: str, stream: str, cursor: str | None, limit: int) -> dict:
    row = connection.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
    high = connection.execute("SELECT COALESCE(MAX(seq),0) FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0]
    after = 0
    if cursor is not None:
        parts = cursor.split(":")
        if len(parts) != 4 or parts[:3] != ["v1", job_id, stream] or not parts[3].isascii() or not parts[3].isdigit() or len(parts[3]) > 16:
            raise HTTPException(422, {"code": "CURSOR_INVALID", "message": "Cursor does not belong to this job and stream"})
        after = int(parts[3])
        if str(after) != parts[3] or after > high:
            raise HTTPException(422, {"code": "CURSOR_INVALID", "message": "Cursor is not a valid event position"})
    events = connection.execute("SELECT * FROM job_events WHERE job_id=? AND kind=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?", (job_id, stream, after, high, limit + 1)).fetchall()
    items, size = [], 0
    for event in events[:limit]:
        payload = json.loads(event["payload_json"])
        item = {"seq": event["seq"], "at": event["created_at"], **payload}
        amount = len(canonical(item).encode())
        if items and size + amount > MAX_RESPONSE_BYTES:
            break
        items.append(item)
        size += amount
    position = items[-1]["seq"] if items else after
    has_more = connection.execute("SELECT 1 FROM job_events WHERE job_id=? AND kind=? AND seq>? AND seq<=? LIMIT 1", (job_id, stream, position, high)).fetchone() is not None
    if not has_more:
        position = high
    return {"items": items, "next_cursor": f"v1:{job_id}:{stream}:{position}", "eof": JobState(row["status"]) in TERMINAL_STATES and not has_more, "job_state": row["status"]}
