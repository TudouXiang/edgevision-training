"""Single-instance Worker skeleton. No business adapter is installed yet."""
import argparse
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .config import data_root
from .contracts import JobState, require_transition
from .database import connect, database_ready


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def event(connection, job_id: str, status: str) -> None:
    sequence = connection.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0]
    connection.execute("INSERT INTO job_events (job_id,seq,kind,payload_json,created_at) VALUES (?,?,?,?,?)", (job_id, sequence, "status", json.dumps({"status": status}), now()))


def orphaned_jobs() -> list[str]:
    """Fail closed: T040 must prove old child identity and exit before recovery."""
    with connect() as connection:
        rows = connection.execute("SELECT id FROM jobs WHERE status IN ('running','cancelling')").fetchall()
        return [row["id"] for row in rows]


@contextmanager
def worker_lock(root: Path):
    """Hold one byte exclusively until the Worker exits, on either host OS."""
    with (root / "worker.lock").open("a+b") as lock:
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


def host_boot_marker() -> str:
    if os.name == "nt":
        # No trustworthy Windows boot identity is available in the T010 skeleton.
        # Startup always refuses to claim work while any old job is nonterminal.
        return "windows-unverified"
    with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as source:
        return source.read().strip()


def stop_child(child: subprocess.Popen, force: bool = False) -> None:
    if child.poll() is not None:
        return
    try:
        if os.name == "nt":
            # The T010 task_process is a single process with no descendants.
            # T040 must add verified tree cleanup before a real task adapter.
            if force:
                child.kill()
            else:
                child.terminate()
        else:
            os.killpg(child.pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def claim(worker_instance: str, boot_id: str) -> tuple[str, str] | None:
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancelling') LIMIT 1").fetchone():
            return None
        row = connection.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
        if not row:
            return None
        job_id = row["id"]
        UUID(job_id)  # Older manual/test rows are not valid production task IDs.
        require_transition(JobState.QUEUED, JobState.RUNNING)
        run_id = str(uuid4())
        result = connection.execute(
            "UPDATE jobs SET status='running',started_at=?,heartbeat_at=?,worker_pid=?,run_id=?,worker_instance=?,host_boot_id=? WHERE id=? AND status='queued'",
            (now(), now(), os.getpid(), run_id, worker_instance, boot_id, job_id),
        )
        if result.rowcount != 1:
            raise RuntimeError("Queued task changed while claiming")
        event(connection, job_id, "running")
        return job_id, run_id


def process(job_id: str, run_id: str) -> None:
    # T010 has no production runner. DEVNULL prevents a pipe deadlock while
    # the unsupported child returns a failure code; T040 adds bounded logs.
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    child = subprocess.Popen([sys.executable, "-m", "app.task_process", job_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
    try:
        with connect() as connection:
            connection.execute("UPDATE jobs SET child_pid=?,child_pgid=? WHERE id=? AND run_id=? AND status='running'", (child.pid, child.pid, job_id, run_id))
    except Exception:
        if child.poll() is None:
            stop_child(child)
        child.wait(timeout=5)
        raise
    cancellation_at = None
    while child.poll() is None:
        with connect() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row and row["status"] == "cancelling" and cancellation_at is None:
                stop_child(child)
                cancellation_at = time.monotonic()
            if cancellation_at is not None and time.monotonic() - cancellation_at > 5:
                stop_child(child, force=True)
            connection.execute("UPDATE jobs SET heartbeat_at=? WHERE id=? AND status IN ('running','cancelling')", (now(), job_id))
        time.sleep(0.25)
    child.wait()
    with connect() as connection:
        row = connection.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        cancelled = bool(row and row["status"] == "cancelling")
        # A zero exit is not sufficient for success: adapters must register validated evidence first.
        status = "cancelled" if cancelled else "failed"
        reason = "CANCELLED" if cancelled else "UNSUPPORTED_JOB"
        if row and row["status"] in ("running", "cancelling"):
            require_transition(JobState(row["status"]), JobState(status), process_exited=True)
            result = connection.execute(
                "UPDATE jobs SET status=?,error_code=?,error_message=?,finished_at=?,worker_pid=NULL,child_pid=NULL,child_pgid=NULL WHERE id=? AND run_id=? AND status=?",
                (status, reason, "No production runner is installed", now(), job_id, run_id, row["status"]),
            )
            if result.rowcount != 1:
                raise RuntimeError("Task state changed during terminal update")
            event(connection, job_id, status)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one queued job; useful for smoke checks")
    args = parser.parse_args()
    if not database_ready():
        print("Database is not migrated; run alembic upgrade head", file=sys.stderr)
        return 2
    try:
        boot_id = host_boot_marker()
    except OSError:
        print("Host boot identity unavailable; refusing to claim tasks", file=sys.stderr)
        return 2
    worker_instance = str(uuid4())
    root = data_root()
    try:
        with worker_lock(root):
            leftovers = orphaned_jobs()
            if leftovers:
                print(f"{len(leftovers)} previous tasks need process ownership review; refusing to claim new work", file=sys.stderr)
                return 4
            while True:
                claimed = claim(worker_instance, boot_id)
                if claimed:
                    job_id, run_id = claimed
                    try:
                        process(job_id, run_id)
                    except Exception as exc:
                        # A crash may leave a live child. Never claim it stopped or
                        # free the execution slot until ownership is verified.
                        print(f"Worker cannot confirm exit for job {job_id}: {type(exc).__name__}", file=sys.stderr)
                        return 4
                if args.once:
                    return 0
                if not claimed:
                    time.sleep(1)
    except BlockingIOError:
        print("Another Worker owns the queue", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
