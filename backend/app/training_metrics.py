"""Bounded journal ingestion with atomic metric/event/offset commits."""
import json
import stat
from uuid import uuid4
from .database import transaction
from .job_service import append_event, canonical
from .run_files import run_directory
from .training_contract import TrainingMetric, METRIC_NAMES, MAX_METRIC_BYTES
from .security import timestamp


def ingest_metrics(job_id, run_id, *, final=False):
    path = run_directory(job_id, run_id) / "metrics.jsonl"
    if not path.exists(): return
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_METRIC_BYTES: raise ValueError("metric journal limit")
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM jobs WHERE id=? AND run_id=?", (job_id, run_id)).fetchone()
        if row is None or row["kind"] != "train": return
        record = json.loads(row["process_identity_json"])
        offset, sequence = record.get("metric_offset", 0), record.get("metric_sequence", 0)
        with path.open("rb") as source:
            source.seek(offset); content = source.read(MAX_METRIC_BYTES + 1)
        boundary = content.rfind(b"\n")
        if final and content and boundary != len(content) - 1: raise ValueError("incomplete metric journal")
        if boundary < 0: return
        total_epochs = json.loads(row["payload_json"])["epochs"]
        for line in content[:boundary].split(b"\n"):
            event = TrainingMetric.model_validate_json(line)
            if str(event.job_id) != job_id or str(event.run_id) != run_id or event.seq != sequence + 1 or event.name not in METRIC_NAMES or event.epoch > total_epochs or event.epoch < record.get("metric_epoch", 1): raise ValueError("metric binding/order invalid")
            existing = connection.execute("SELECT value FROM metrics WHERE job_id=? AND epoch=? AND name=?", (job_id, event.epoch, event.name)).fetchone()
            if existing:
                if existing["value"] != event.value: raise ValueError("conflicting duplicate metric")
            else:
                connection.execute("INSERT INTO metrics(id,job_id,epoch,name,value,created_at) VALUES(?,?,?,?,?,?)", (str(uuid4()), job_id, event.epoch, event.name, event.value, timestamp()))
                append_event(connection, job_id, "metric", {"epoch": event.epoch, "name": event.name, "value": event.value})
            sequence = event.seq
            record["metric_epoch"] = event.epoch
        record.update(metric_offset=offset + boundary + 1, metric_sequence=sequence)
        connection.execute("UPDATE jobs SET process_identity_json=? WHERE id=? AND run_id=?", (canonical(record), job_id, run_id))
