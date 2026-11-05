"""One trusted fixed runner per guardian; loss of the Worker control pipe aborts it."""
from __future__ import annotations
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time

from .job_service import MAX_LOG_BYTES, MAX_LOG_EVENTS, MAX_LOG_LINE_BYTES, canonical
from .process_identity import identity
from .run_files import atomic_json, run_directory


POLL_SECONDS = 0.05
GRACE_SECONDS = 1.0
WINDOWS_EXIT_SETTLE_SECONDS = 0.25
DRAIN_SECONDS = 15.0
MAX_RUN_SECONDS = 3600.0


def runner_command(job_id: str, run_id: str) -> list[str]:
    # No environment variable or uploaded field can choose an executable/adapter.
    return [sys.executable, "-m", "app.task_process", job_id, run_id]


def capture_output(source, path: Path, result: dict) -> None:
    """Bound retained bytes and lines while always draining the OS pipe to EOF."""
    pending = bytearray()
    retained = count = 0
    truncated = False
    try:
        sink = path.open("xb", buffering=0)
    except OSError:
        result["complete"] = False
        try:
            while os.read(source.fileno(), 4096):
                pass
        except OSError:
            pass
        return
    with sink as target:
        def emit(raw: bytes) -> None:
            nonlocal retained, count, truncated
            text = raw.decode("utf-8", errors="replace")
            # Never forward arbitrary child strings/tracebacks as user-facing logs.
            # Only the fixed adapter's exact compact structured messages are admitted.
            import json
            try:
                value = json.loads(text)
            except (ValueError, TypeError):
                value = None
            allowed = {"Validation started", "Archive fingerprint verified", "Dataset validation passed", "Dataset validation failed", "Validation report exceeds supported size", "Runner storage is unavailable", "Runner infrastructure failed"}
            if not isinstance(value, dict) or set(value) != {"level", "text"} or value.get("text") not in allowed or value.get("level") not in {"info", "warning", "error"}:
                value = {"level": "warning", "text": "Runner output omitted (unstructured or sensitive content)"}
            encoded = (canonical(value) + "\n").encode()
            if retained + len(encoded) > MAX_LOG_BYTES or count >= MAX_LOG_EVENTS:
                truncated = True
                return
            target.write(encoded)
            retained += len(encoded)
            count += 1
        try:
            while chunk := os.read(source.fileno(), 4096):
                pending.extend(chunk)
                while b"\n" in pending or len(pending) > MAX_LOG_LINE_BYTES:
                    newline = pending.find(b"\n")
                    length = min(newline if newline >= 0 else len(pending), MAX_LOG_LINE_BYTES)
                    emit(bytes(pending[:length]))
                    del pending[:length + (1 if newline == length else 0)]
            if pending:
                emit(bytes(pending))
            if truncated:
                target.write((canonical({"level": "warning", "text": "Log capture limit reached; remaining output was drained"}) + "\n").encode())
            os.fsync(target.fileno())
            result["complete"] = True
        except (OSError, ValueError):
            result["complete"] = False
            # A failed log sink must not leave a child blocked on its pipe.
            try:
                while os.read(source.fileno(), 4096):
                    pass
            except OSError:
                pass


def read_control(commands: queue.Queue) -> None:
    pending = b""
    try:
        while chunk := os.read(0, 64):
            pending += chunk
            if len(pending) > 128:
                break
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line not in {b"GO", b"STOP"}:
                    commands.put("STOP")
                    return
                commands.put(line.decode("ascii"))
    except OSError:
        pass
    commands.put("EOF")


def supervise(job_id: str, run_id: str) -> int:
    if os.name == "nt":
        from .process_windows import ProcessTree
    else:
        from .process_linux import ProcessTree
    directory = run_directory(job_id, run_id)
    guardian_identity = identity(os.getpid())
    commands: queue.Queue = queue.Queue()
    os.set_inheritable(0, False)
    if os.name != "nt":
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    threading.Thread(target=read_control, args=(commands,), daemon=True).start()
    stop_signal = False
    def signal_stop(*_):
        nonlocal stop_signal
        stop_signal = True
    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    tree = None
    capture = None
    log_result = {"complete": False}
    reason = "completed"
    started = False
    drain_at = None
    root_exit_at = None
    began = time.monotonic()
    try:
        tree = ProcessTree(runner_command(job_id, run_id))
        tree.start()
        capture = threading.Thread(target=capture_output, args=(tree.output, directory / "logs.jsonl", log_result), daemon=True)
        capture.start()
        atomic_json(directory / "identity.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id,
                    "guardian": guardian_identity, "runner": tree.record})
        while True:
            now = time.monotonic()
            if stop_signal:
                reason = "cancelled"
                drain_at = drain_at or now
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                if command in {"STOP", "EOF"}:
                    reason = "worker_lost" if command == "EOF" else "cancelled"
                    drain_at = drain_at or now
                elif command == "GO" and not started and drain_at is None:
                    tree.go()
                    started = True
            root_code = tree.poll()
            natural_exit = False
            if root_code is not None and drain_at is None:
                if os.name == "nt":
                    # Job accounting can retain exited processes while references
                    # are released. Keep handling STOP/EOF each poll while settling.
                    if root_exit_at is None:
                        root_exit_at = now
                    if tree.empty():
                        natural_exit = True
                    elif now - root_exit_at >= WINDOWS_EXIT_SETTLE_SECONDS:
                        reason = "remaining_job_members_after_settle"
                        drain_at = now
                else:
                    drain_at = now
                    if not tree.empty():
                        reason = "descendants_after_root_exit"
            if now - began > MAX_RUN_SECONDS or (not started and now - began > 30):
                reason = "timeout"
                drain_at = drain_at or now
            if natural_exit and drain_at is None:
                break  # Witnessed root exit + zero Job members; do not terminate.
            if drain_at is not None:
                tree.stop(force=now - drain_at > GRACE_SECONDS)
                if tree.empty():
                    break
                if now - drain_at > DRAIN_SECONDS:
                    return 4  # No receipt: never infer successful cleanup from timeout.
            time.sleep(POLL_SECONDS)
        if capture is not None:
            capture.join(timeout=5)
            if capture.is_alive():
                return 4
        atomic_json(directory / "drained.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id,
                    "guardian": guardian_identity, "tree_exited": True, "started": started,
                    "exit_code": tree.root_code, "reason": reason, "logs_complete": log_result["complete"]})
        return 0
    except Exception:
        # Startup failure may be after OS process creation. Drain the container,
        # not merely the recorded root. A failure to prove exit emits no receipt.
        if tree is not None:
            deadline = time.monotonic() + DRAIN_SECONDS
            try:
                while not tree.empty():
                    tree.stop(force=True)
                    if time.monotonic() > deadline:
                        return 4
                    time.sleep(POLL_SECONDS)
            except Exception:
                return 4
        if capture is not None:
            capture.join(timeout=5)
            if capture.is_alive():
                return 4
        atomic_json(directory / "drained.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id,
                    "guardian": guardian_identity, "tree_exited": True, "started": started,
                    "exit_code": None, "reason": "containment_or_startup_failed", "logs_complete": False})
        return 0
    finally:
        if tree is not None:
            tree.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(2)
    raise SystemExit(supervise(sys.argv[1], sys.argv[2]))
