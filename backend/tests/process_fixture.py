"""Isolated fault-injection entrypoint, never selectable by production startup.

Tests invoke this file explicitly in temporary data roots. It wraps the actual
Worker/guardian with local Python substitutions; production has no test env flag.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.process_identity import identity
from app.run_files import atomic_json, run_directory

HERE = str(Path(__file__).resolve())


def wait_file(path: Path, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("test barrier expired")
        time.sleep(0.01)


def marker(directory: Path, name: str) -> None:
    atomic_json(directory / name, identity(os.getpid()))


def descendant(directory: Path, grandchild: bool) -> None:
    if os.name != "nt":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.setsid()
    marker(directory, "grandchild.json" if grandchild else "child.json")
    if not grandchild:
        subprocess.Popen([sys.executable, HERE, "descendant", str(directory), "grandchild"], close_fds=True)
    wait_file(directory / "release-descendants", 60)


def runner(behavior: str, job_id: str, run_id: str) -> int:
    if sys.stdin.buffer.readline(16) != b"GO\n":
        return 125
    directory = run_directory(job_id, run_id)
    marker(directory, "started.json")
    print('{"level":"info","text":"Validation started"}', flush=True)
    if behavior in {"tree", "root_exits_first"}:
        subprocess.Popen([sys.executable, HERE, "descendant", str(directory), "child"], close_fds=True)
        wait_file(directory / "grandchild.json")
        if behavior == "root_exits_first":
            return 0
    if behavior in {"flood", "flood_wait"}:
        for _ in range(4096):
            os.write(1, b"x" * 4096)
        if behavior == "flood_wait":
            marker(directory, "flood-ready.json")
            wait_file(directory / "release-runner")
        return 0
    if behavior == "exit_zero":
        return 0
    if behavior == "storage_error":
        import errno
        from app import dataset_validation
        def no_space(_fd):
            raise OSError(errno.ENOSPC, "isolated storage fault")
        dataset_validation.os.fsync = no_space
        from app.task_process import execute
        return execute(job_id, run_id)
    if behavior == "output_capacity":
        from app import run_files
        run_files.MAX_DOCUMENT_BYTES = 100
        from app.task_process import execute
        return execute(job_id, run_id)
    if behavior in {"corrupt", "valid_then_wait"}:
        from app.dataset_runner import run
        code = run(job_id, run_id)
        if behavior == "corrupt":
            (directory / "bundle" / "report.json").write_bytes(b"broken")
        else:
            marker(directory, "evidence-ready.json")
            wait_file(directory / "release-runner")
        return code
    wait_file(directory / "release-runner")
    return 0


def guardian(behavior: str, job_id: str, run_id: str) -> int:
    from app import guardian as module
    module.runner_command = lambda job, run: [sys.executable, HERE, "runner", behavior, job, run]
    return module.supervise(job_id, run_id)


def worker(behavior: str) -> int:
    from app import worker as module
    if behavior.startswith("kill_") or behavior in {"pre_go", "go_commit_failure"}:
        runner_behavior = "valid_then_wait"
    else:
        runner_behavior = behavior
    module.guardian_command = lambda job, run: [sys.executable, HERE, "guardian", runner_behavior, job, run]
    if behavior == "flood_wait":
        module.ingest_logs = lambda *_: None
    if behavior == "go_commit_failure":
        from contextlib import contextmanager
        original_transaction = module.transaction
        @contextmanager
        def fail_go_commit(*args, **kwargs):
            with original_transaction(*args, **kwargs) as connection:
                yield connection
                row = connection.execute("SELECT id,run_id FROM jobs WHERE launch_phase='go_authorized' AND status='running'").fetchone()
                if row:
                    directory = run_directory(row["id"], row["run_id"])
                    wait_file(directory / "started.json")
                    marker(directory, "go-before-commit.json")
                    raise OSError("isolated commit failure after GO")
        module.transaction = fail_go_commit
    if behavior in {"pre_go", "kill_before_go"}:
        original = module.read_json
        def read_with_barrier(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path.name == "identity.json":
                marker(path.parent, "worker-before-go.json")
                wait_file(path.parent / "release-worker")
            return result
        module.read_json = read_with_barrier
    if behavior == "kill_after_rename":
        from app import publication
        rename = publication.os.rename
        def rename_and_wait(source, destination):
            rename(source, destination)
            marker(Path(source).parent, "worker-after-rename.json")
            wait_file(Path(source).parent / "release-worker")
        publication.os.rename = rename_and_wait
    if behavior == "kill_after_commit":
        from app import publication
        publish = publication.publish
        def commit_and_wait(job, exit_code):
            result = publish(job, exit_code)
            directory = run_directory(job["id"], job["run_id"])
            marker(directory, "worker-after-commit.json")
            wait_file(directory / "release-worker")
            return result
        publication.publish = commit_and_wait
    sys.argv = ["worker", "--once"]
    return module.main()


def nested_windows() -> int:
    from app import process_windows as win
    import ctypes
    job = win.checked(win.CreateJobObjectW(None, None))
    try:
        win.checked(win.AssignProcessToJobObject(job, win.GetCurrentProcess()))
        member = win.W.BOOL()
        win.checked(win.IsProcessInJob(win.GetCurrentProcess(), job, ctypes.byref(member)))
        assert member.value
        return worker("tree")
    finally:
        win.CloseHandle(job)


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "runner":
        raise SystemExit(runner(*args))
    if mode == "guardian":
        raise SystemExit(guardian(*args))
    if mode == "worker":
        raise SystemExit(worker(*args))
    if mode == "nested_windows":
        raise SystemExit(nested_windows())
    if mode == "descendant":
        descendant(Path(args[0]), args[1] == "grandchild")
