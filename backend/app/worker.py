"""Single-instance FIFO worker with witnessed process-tree exit and atomic publish."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from uuid import UUID, uuid4

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .config import data_root
from .database import database_ready, transaction
from .dataset_storage import resolve_storage_file
from .job_service import append_event, canonical, invalidate_dataset, transition
from .process_identity import boot_id, exited, identity, valid_identity, valid_boot_id
from .python_launch import python_child
from .run_files import atomic_json, fingerprint, read_json, run_directory
from .security import timestamp


def now() -> str:
    return timestamp()


@contextmanager
def worker_lock(root: Path):
    with (root / "worker.lock").open("a+b") as lock:
        os.set_inheritable(lock.fileno(), False)
        if os.name == "nt":
            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EDEADLK) or getattr(exc, "winerror", None) in (32, 33):
                    raise BlockingIOError("Another Worker owns the queue") from exc
                raise
        else:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def host_boot_marker() -> str | None:
    return boot_id()


def claim(worker_instance: str, boot_marker: str | None) -> tuple[str, str] | None:
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancelling') LIMIT 1").fetchone():
            return None
        row = connection.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
        if row is None:
            return None
        job_id = row["id"]
        UUID(job_id)
        run_id = str(uuid4())
        if not transition(connection, job_id, "queued", "running", fields={"started_at": now(), "heartbeat_at": now(),
                          "worker_pid": os.getpid(), "run_id": run_id, "worker_instance": worker_instance,
                          "host_boot_id": boot_marker, "launch_phase": "claimed"}):
            raise RuntimeError("claim compare-and-set failed")
        connection.execute("UPDATE jobs SET environment_json=? WHERE id=?", (canonical({"schema_version": 1, "python": platform.python_version(), "platform": sys.platform, "process_protocol": 1}), job_id))
        return job_id, run_id


def get_job(job_id: str) -> dict:
    with transaction() as connection:
        return dict(connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def finish(job_id: str, run_id: str, code: str, *, interrupted: bool = False) -> None:
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT status FROM jobs WHERE id=? AND run_id=?", (job_id, run_id)).fetchone()
        if row is None or row["status"] not in {"running", "cancelling"}:
            return
        after = "interrupted" if interrupted else ("cancelled" if row["status"] == "cancelling" else "failed")
        if transition(connection, job_id, row["status"], after, run_id=run_id, process_exited=True,
                      fields={"error_code": "CANCELLED" if after == "cancelled" else code,
                              "error_message": "Task did not complete; inspect its status and validation report", "launch_phase": "finished"}):
            invalidate_dataset(connection, job_id)


def ingest_logs(job_id: str, run_id: str) -> None:
    path = run_directory(job_id, run_id) / "logs.jsonl"
    if not path.exists():
        return
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT process_identity_json FROM jobs WHERE id=? AND run_id=?", (job_id, run_id)).fetchone()
        if row is None:
            return
        record = json.loads(row[0])
        offset = record.get("log_offset", 0)
        with path.open("rb") as source:
            source.seek(offset)
            content = source.read(64 * 1024)
        boundary = content.rfind(b"\n")
        if boundary < 0:
            return
        for line in content[:boundary].split(b"\n"):
            value = json.loads(line)
            if set(value) != {"level", "text"} or value["level"] not in {"info", "warning", "error"} or not isinstance(value["text"], str) or len(value["text"].encode()) > 2048:
                raise ValueError("invalid bounded guardian log")
            append_event(connection, job_id, "log", value)
        record["log_offset"] = offset + boundary + 1
        connection.execute("UPDATE jobs SET process_identity_json=? WHERE id=? AND run_id=?", (canonical(record), job_id, run_id))


def ingest_all_logs(job_id: str, run_id: str) -> None:
    for _ in range(16):  # More than the hard 512 KiB retained log bound.
        ingest_logs(job_id, run_id)


def drain_receipt(job: dict, *, wait_seconds: float = 0) -> dict | None:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            record = read_json(run_directory(job["id"], job["run_id"]) / "drained.json", 16384)
            expected = {"schema_version", "job_id", "run_id", "guardian", "tree_exited", "started", "exit_code", "reason", "logs_complete"}
            if set(record) != expected or type(record["schema_version"]) is not int or record["schema_version"] != 1 or record["job_id"] != job["id"] or record["run_id"] != job["run_id"] or record["tree_exited"] is not True:
                return None
            reasons = {"completed", "worker_lost", "cancelled", "descendants_after_root_exit", "remaining_job_members_after_settle", "timeout", "containment_or_startup_failed"}
            code = record["exit_code"]
            if not valid_identity(record["guardian"]) or type(record["started"]) is not bool or type(record["logs_complete"]) is not bool or record["reason"] not in reasons or (code is not None and (type(code) is not int or not -128 <= code < 2**32)):
                return None
            known = json.loads(job["process_identity_json"])
            if not isinstance(known, dict):
                return None
            if known.get("guardian") is not None and known["guardian"] != record["guardian"]:
                return None
            if exited(record["guardian"]):
                return record
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def recover() -> list[tuple[str, str]]:
    with transaction() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM jobs WHERE status IN ('running','cancelling')")]
    blocked = []
    current_boot = boot_id()
    for row in rows:
        phase = row["launch_phase"]
        if phase == "claimed" and row["run_id"] and row["worker_instance"]:
            finish(row["id"], row["run_id"], "WORKER_INTERRUPTED_BEFORE_LAUNCH", interrupted=True)
        elif current_boot and row["run_id"] and valid_boot_id(row["host_boot_id"]) and row["host_boot_id"] != current_boot:
            finish(row["id"], row["run_id"], "HOST_RESTARTED", interrupted=True)
        elif row["run_id"] and row["worker_instance"] and drain_receipt(row, wait_seconds=20):
            ingest_all_logs(row["id"], row["run_id"])
            finish(row["id"], row["run_id"], "WORKER_INTERRUPTED", interrupted=True)
        else:
            code = "RECOVERY_BLOCKED_IDENTITY_UNVERIFIED" if phase == "unverified" else "RECOVERY_BLOCKED_DRAIN_UNCONFIRMED"
            blocked.append((row["id"], code))
    return blocked


def orphaned_jobs() -> list[str]:
    with transaction() as connection:
        return [row[0] for row in connection.execute("SELECT id FROM jobs WHERE status IN ('running','cancelling')")]


def guardian_command(job_id: str, run_id: str) -> list[str]:
    return [sys.executable, "-m", "app.guardian", job_id, run_id]


def send_control(stream, command: bytes) -> bool:
    try:
        stream.write(command)
        stream.flush()
        return True
    except BrokenPipeError:
        # The guardian may have just exited. Its receipt, not the pipe error,
        # decides whether this run can terminalize. Missing proof still blocks.
        return False


def process(job_id: str, run_id: str) -> None:
    job = get_job(job_id)
    if job["kind"] not in {"dataset_check", "train"}:
        finish(job_id, run_id, "UNSUPPORTED_JOB")
        return
    # A claimed-only task cannot have launched a guardian. Prelaunch input errors
    # may safely terminalize; any attempted launch below requires a receipt.
    try:
        frozen = json.loads(job["input_snapshot_json"])
        if job["kind"] == "dataset_check":
            if fingerprint(resolve_storage_file(frozen["archive_key"])) != (frozen["size_bytes"], frozen["sha256"]):
                raise ValueError("archive fingerprint changed")
        else:
            from .training_inputs import verify_input
            verify_input(frozen)
        directory = run_directory(job_id, run_id, create=True)
        atomic_json(directory / "input.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id, "kind": job["kind"], "input": frozen})
    except Exception:
        finish(job_id, run_id, "INPUT_UNAVAILABLE")
        return
    with transaction() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "cancelling":
            do_launch = False
        else:
            do_launch = connection.execute("UPDATE jobs SET launch_phase='spawning' WHERE id=? AND run_id=? AND status='running' AND launch_phase='claimed'", (job_id, run_id)).rowcount == 1
    if not do_launch:
        finish(job_id, run_id, "CANCELLED")
        return
    child = None
    try:
        command, environment = python_child(guardian_command(job_id, run_id))
        child = subprocess.Popen(command, env=environment, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True, start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        guardian_identity = identity(child.pid)
        with transaction() as connection:
            connection.execute("UPDATE jobs SET process_identity_json=? WHERE id=? AND run_id=?", (canonical({"schema_version": 1, "guardian": guardian_identity, "log_offset": 0}), job_id, run_id))
        prepared, stopping = False, False
        metric_error = False
        began = time.monotonic()
        while child.poll() is None:
            current = get_job(job_id)
            if current["status"] == "cancelling" and not stopping:
                send_control(child.stdin, b"STOP\n")
                stopping = True
            if not prepared and (directory / "identity.json").exists():
                ready = read_json(directory / "identity.json", 16384)
                if set(ready) != {"schema_version", "job_id", "run_id", "guardian", "runner"} or ready["schema_version"] != 1 or ready["job_id"] != job_id or ready["run_id"] != run_id or ready["guardian"] != guardian_identity:
                    raise ValueError("guardian identity mismatch")
                with transaction() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    old = json.loads(connection.execute("SELECT process_identity_json FROM jobs WHERE id=?", (job_id,)).fetchone()[0])
                    ready["log_offset"] = old.get("log_offset", 0)
                    connection.execute("UPDATE jobs SET process_identity_json=?,child_pid=?,launch_phase='prepared' WHERE id=? AND run_id=?", (canonical(ready), ready["runner"]["pid"], job_id, run_id))
                with transaction() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    authorized = connection.execute("UPDATE jobs SET launch_phase='go_authorized' WHERE id=? AND run_id=? AND status='running' AND launch_phase='prepared'", (job_id, run_id)).rowcount == 1
                    # Send under the same reserved-writer transaction: cancellation
                    # cannot win between the status check and GO. Identity was
                    # already committed in the preceding transaction.
                    if authorized and not stopping:
                        send_control(child.stdin, b"GO\n")
                prepared = True
            ingest_logs(job_id, run_id)
            if job["kind"] == "train":
                from .training_metrics import ingest_metrics
                if not metric_error:
                    try:
                        ingest_metrics(job_id, run_id)
                    except Exception:
                        metric_error = True
                        send_control(child.stdin, b"STOP\n")
                        stopping = True
            with transaction() as connection:
                connection.execute("UPDATE jobs SET heartbeat_at=? WHERE id=? AND run_id=? AND status IN ('running','cancelling')", (now(), job_id, run_id))
            if time.monotonic() - began > 3630:
                raise TimeoutError("guardian did not finish within its run/drain bound")
            time.sleep(0.05)
        child.wait()
    finally:
        if child is not None and child.stdin and not child.stdin.closed:
            try:
                child.stdin.close()  # Also on Worker errors: guardian sees EOF and drains.
            except BrokenPipeError:
                pass
    job = get_job(job_id)
    receipt = drain_receipt(job, wait_seconds=2)
    if receipt is None:
        raise RuntimeError("RECOVERY_BLOCKED_DRAIN_UNCONFIRMED")
    # Drain bounded persisted logs fully before the terminal event.
    ingest_all_logs(job_id, run_id)
    if job["kind"] == "train":
        from .training_metrics import ingest_metrics
        try:
            ingest_metrics(job_id, run_id, final=True)
        except Exception:
            finish(job_id, run_id, "METRICS_INVALID")
            return
    if job["status"] == "cancelling":
        finish(job_id, run_id, "CANCELLED")
    elif metric_error:
        finish(job_id, run_id, "METRICS_INVALID")
    elif receipt["reason"] != "completed" or not receipt["logs_complete"]:
        finish(job_id, run_id, "RUNNER_FAILED")
    elif receipt["exit_code"] not in ({0, 2} if job["kind"] == "dataset_check" else {0}):
        reason = {65: "INPUT_INVALID", 66: "INPUT_CHANGED", 70: "STORAGE_UNAVAILABLE", 71: "OUTPUT_CAPACITY_LIMIT", 67: "RUNTIME_CHANGED", 68: "TRAINING_POLICY_FAILED"}.get(receipt["exit_code"], "RUNNER_FAILED")
        finish(job_id, run_id, reason)
    else:
        from .publication import publish
        try:
            if job["kind"] == "train":
                from .training_publication import publish as publish_train
                published = publish_train(job)
            else:
                published = publish(job, receipt["exit_code"])
            if not published:
                finish(job_id, run_id, "CANCELLED")
        except Exception:
            finish(job_id, run_id, "OUTPUT_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Recover, then process at most one queued task")
    args = parser.parse_args()
    if not database_ready():
        print("Database is not migrated; run alembic upgrade head", file=sys.stderr)
        return 2
    try:
        marker = boot_id()
        with worker_lock(data_root()):
            from .training_probe import recover_probe
            if not recover_probe():
                print("RECOVERY_BLOCKED_PROBE_DRAIN_UNCONFIRMED", file=sys.stderr)
                return 4
            blocked = recover()
            if blocked:
                for job_id, code in blocked:
                    print(f"{code}: job {job_id}; old task exit is unconfirmed, new work is blocked", file=sys.stderr)
                return 4
            instance = str(uuid4())
            while True:
                claimed = claim(instance, marker)
                if claimed:
                    try:
                        process(*claimed)
                    except Exception:
                        print(f"RECOVERY_BLOCKED_DRAIN_UNCONFIRMED: job {claimed[0]}; refusing new work", file=sys.stderr)
                        return 4
                if args.once:
                    return 0
                if not claimed:
                    time.sleep(0.5)
    except BlockingIOError:
        print("Another Worker owns the queue", file=sys.stderr)
        return 3
    except (OSError, ValueError):
        print("Worker storage or host identity is unavailable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
