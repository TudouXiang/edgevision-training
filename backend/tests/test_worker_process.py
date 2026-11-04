"""Real process fault matrix; host-specific mechanisms execute, not skipped greens."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_dataset_api import data_root, setup_admin, upload, headers, BACKEND
from test_worker_api import submit, work
from app.database import transaction
from app.main import app
from app.process_identity import identity, exited
from app.python_launch import python_child
from app.run_files import run_directory, read_json
from app.worker import claim, recover

FIXTURE = str(Path(__file__).with_name("process_fixture.py"))


def wait_until(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("deterministic process barrier did not arrive")


def record(job_id):
    with transaction() as connection:
        return dict(connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def start(behavior):
    args = [sys.executable, FIXTURE, "nested_windows"] if behavior == "nested_windows" else [sys.executable, FIXTURE, "worker", behavior]
    args, environment = python_child(args, os.environ.copy())
    return subprocess.Popen(args, cwd=BACKEND, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_path(job_id):
    row = wait_until(lambda: record(job_id) if record(job_id)["run_id"] else None)
    return run_directory(job_id, row["run_id"])


def wait_marker(directory, name):
    return wait_until(lambda: read_json(directory / name) if (directory / name).exists() else None)


def stop_and_reap(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)
    for stream in (process.stdout, process.stderr):
        if stream:
            stream.close()


def safely_kill(record):
    if exited(record):
        return
    if os.name == "nt":
        from app import process_windows as win
        handle = win.checked(win.OpenProcess(0x1000 | 1 | 0x100000, False, record["pid"]))
        try:
            if win.creation_time(handle) == record["creation_time"]:
                win.checked(win.TerminateProcess(handle, 125))
        finally:
            win.CloseHandle(handle)
    else:
        fd = os.pidfd_open(record["pid"])
        try:
            if identity(record["pid"])["start_ticks"] == record["start_ticks"]:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
        finally:
            os.close(fd)


def test_atomic_fifo_claim_and_real_second_worker_lock(data_root):
    client, project = setup_admin(data_root)
    first = submit(client, upload(client, project, "first.zip").json()["id"])
    second = submit(client, upload(client, project, "second.zip").json()["id"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        claimed = list(pool.map(lambda _: claim(str(uuid4()), None), range(6)))
    assert [value[0] for value in claimed if value] == [first]
    assert record(second)["status"] == "queued"
    assert recover() == []
    assert record(first)["status"] == "interrupted"
    process = start("tree")
    directory = run_path(second)
    try:
        wait_marker(directory, "grandchild.json")
        args, environment = python_child([sys.executable, "-m", "app.worker", "--once"])
        other = subprocess.run(args, env=environment, cwd=BACKEND, capture_output=True, timeout=10)
        assert other.returncode == 3
        client.post(f"/api/v1/jobs/{second}/cancel", headers=headers(client))
        assert process.wait(timeout=10) == 0
        assert record(second)["status"] == "cancelled"
    finally:
        stop_and_reap(process)


@pytest.mark.parametrize("behavior", ["tree", "root_exits_first"] + (["nested_windows"] if os.name == "nt" else []))
def test_real_descendants_root_exit_and_cancel_drain(data_root, behavior):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start(behavior)
    directory = run_path(task)
    try:
        identities = [wait_marker(directory, name) for name in ("started.json", "child.json", "grandchild.json")]
        if behavior != "root_exits_first":
            assert client.post(f"/api/v1/jobs/{task}/cancel", headers=headers(client)).json()["state"] == "cancelling"
        assert process.wait(timeout=15) == 0, process.stderr.read().decode()
        assert all(exited(item) for item in identities)
        assert record(task)["status"] == ("failed" if behavior == "root_exits_first" else "cancelled")
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
        assert read_json(directory / "drained.json")["tree_exited"] is True
    finally:
        stop_and_reap(process)


def test_pre_go_cancel_and_incremental_logs_survive_api_lifecycle(data_root):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start("pre_go")
    directory = run_path(task)
    try:
        wait_marker(directory, "worker-before-go.json")
        assert not (directory / "started.json").exists()
        assert client.post(f"/api/v1/jobs/{task}/cancel", headers=headers(client)).json()["state"] == "cancelling"
        (directory / "release-worker").touch()
        assert process.wait(timeout=10) == 0
        assert record(task)["status"] == "cancelled"
        assert not (directory / "started.json").exists()
        assert read_json(directory / "drained.json")["started"] is False
    finally:
        stop_and_reap(process)
    retry = submit(client, dataset["id"], "retry")
    process = start("tree")
    directory = run_path(retry)
    try:
        wait_marker(directory, "grandchild.json")
        with TestClient(app) as restarted:
            restarted.cookies.update(client.cookies)
            assert restarted.get(f"/api/v1/jobs/{retry}").json()["state"] == "running"
            wait_until(lambda: restarted.get(f"/api/v1/jobs/{retry}/logs").json()["items"])
        assert process.poll() is None
        client.post(f"/api/v1/jobs/{retry}/cancel", headers=headers(client))
        assert process.wait(timeout=15) == 0
    finally:
        stop_and_reap(process)


@pytest.mark.parametrize("behavior", ["kill_before_go", "tree"])
def test_worker_kill_eof_drains_and_restart_interrupts_without_rerun(data_root, behavior):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start(behavior)
    directory = run_path(task)
    try:
        wait_marker(directory, "worker-before-go.json" if behavior == "kill_before_go" else "grandchild.json")
        process.kill()
        process.wait(timeout=10)
        receipt = wait_marker(directory, "drained.json")
        assert receipt["tree_exited"] is True
        wait_until(lambda: exited(receipt["guardian"]))
        work()
        assert record(task)["status"] == "interrupted"
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
        assert len(list(directory.parent.iterdir())) == 1
        for name in ("started.json", "child.json", "grandchild.json"):
            if (directory / name).exists():
                assert exited(read_json(directory / name))
    finally:
        stop_and_reap(process)


@pytest.mark.parametrize("behavior", ["exit_zero", "corrupt", "flood"])
def test_zero_missing_corrupt_and_output_flood_never_publish(data_root, behavior):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start(behavior)
    try:
        assert process.wait(timeout=20) == 0, process.stderr.read().decode()
        assert record(task)["status"] == "failed" and record(task)["error_code"] == "OUTPUT_INVALID"
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
        assert client.get(f"/api/v1/projects/{project}/artifacts").json()["total"] == 0
        with transaction() as connection:
            count, amount = connection.execute("SELECT COUNT(*),COALESCE(SUM(LENGTH(payload_json)),0) FROM job_events WHERE job_id=? AND kind='log'", (task,)).fetchone()
        assert count <= 2001 and amount < 520 * 1024
        if behavior == "flood":
            assert count == 2001
    finally:
        stop_and_reap(process)


@pytest.mark.parametrize("phase", ["rename", "commit"])
def test_worker_crash_publication_boundaries_do_not_reconstruct_success(data_root, phase):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start(f"kill_after_{phase}")
    directory = run_path(task)
    try:
        wait_marker(directory, "evidence-ready.json")
        (directory / "release-runner").touch()
        wait_marker(directory, f"worker-after-{phase}.json")
        process.kill()
        process.wait(timeout=10)
        work()
        assert record(task)["status"] == ("interrupted" if phase == "rename" else "succeeded")
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == ("pending" if phase == "rename" else "ready")
        assert client.get(f"/api/v1/projects/{project}/artifacts").json()["total"] == (0 if phase == "rename" else 1)
        assert len(list((data_root / "datasets" / dataset["id"] / "validations").iterdir())) == 1
    finally:
        stop_and_reap(process)


def test_cancel_wins_completion_and_terminal_event_is_unique(data_root):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start("valid_then_wait")
    directory = run_path(task)
    try:
        wait_marker(directory, "evidence-ready.json")
        assert client.post(f"/api/v1/jobs/{task}/cancel", headers=headers(client)).json()["state"] == "cancelling"
        (directory / "release-runner").touch()
        assert process.wait(timeout=15) == 0
        assert record(task)["status"] == "cancelled"
        assert client.get(f"/api/v1/projects/{project}/artifacts").json()["total"] == 0
        with transaction() as connection:
            statuses = [json.loads(row[0])["status"] for row in connection.execute("SELECT payload_json FROM job_events WHERE job_id=? AND kind='status' ORDER BY seq", (task,))]
        assert statuses == ["queued", "running", "cancelling", "cancelled"]
    finally:
        stop_and_reap(process)


def test_guardian_loss_without_receipt_blocks_and_unrelated_pid_is_untouched(data_root, monkeypatch):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start("tree" if os.name == "nt" else "valid_then_wait")
    directory = run_path(task)
    identities = []
    try:
        identities.append(wait_marker(directory, "started.json"))
        if os.name == "nt":
            identities.extend(wait_marker(directory, name) for name in ("child.json", "grandchild.json"))
        guard = wait_marker(directory, "identity.json")["guardian"]
        safely_kill(guard)
        assert process.wait(timeout=10) == 4
        if os.name == "nt":
            # Observe KILL_ON_JOB_CLOSE before cleanup can hide a missing effect.
            wait_until(lambda: all(exited(value) for value in identities))
        assert not (directory / "drained.json").exists()
        from app import worker
        original = worker.drain_receipt
        monkeypatch.setattr(worker, "drain_receipt", lambda row, **_: original(row, wait_seconds=0.05))
        assert recover() == [(task, "RECOVERY_BLOCKED_DRAIN_UNCONFIRMED")]
        assert record(task)["status"] == "running"
        unrelated = identity(os.getpid())
        altered = {**unrelated, "start_ticks" if os.name != "nt" else "creation_time": 1}
        with transaction() as connection:
            connection.execute("UPDATE jobs SET process_identity_json=? WHERE id=?", (json.dumps({"guardian": altered}), task))
        assert recover()
        assert not exited(unrelated)
    finally:
        stop_and_reap(process)
        for value in identities:
            safely_kill(value)


def test_go_before_commit_failure_requires_receipt_and_pending(data_root):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start("go_commit_failure")
    directory = run_path(task)
    try:
        wait_marker(directory, "go-before-commit.json")
        assert process.wait(timeout=10) == 4
        assert record(task)["launch_phase"] == "prepared"
        receipt = wait_marker(directory, "drained.json")
        wait_until(lambda: exited(receipt["guardian"]))
        work()
        assert record(task)["status"] == "interrupted"
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
    finally:
        stop_and_reap(process)


def test_recovery_drains_all_retained_logs(data_root):
    client, project = setup_admin(data_root)
    task = submit(client, upload(client, project).json()["id"])
    process = start("flood_wait")
    directory = run_path(task)
    try:
        wait_marker(directory, "flood-ready.json")
        process.kill()
        process.wait(timeout=10)
        receipt = wait_marker(directory, "drained.json")
        wait_until(lambda: exited(receipt["guardian"]))
        work()
        with transaction() as connection:
            count = connection.execute("SELECT COUNT(*) FROM job_events WHERE job_id=? AND kind='log'", (task,)).fetchone()[0]
        assert count == 2001
        assert record(task)["status"] == "interrupted"
    finally:
        stop_and_reap(process)


def test_cancel_after_rename_does_not_publish_report(data_root):
    client, project = setup_admin(data_root)
    task = submit(client, upload(client, project).json()["id"])
    process = start("kill_after_rename")
    directory = run_path(task)
    try:
        wait_marker(directory, "evidence-ready.json")
        (directory / "release-runner").touch()
        wait_marker(directory, "worker-after-rename.json")
        assert client.post(f"/api/v1/jobs/{task}/cancel", headers=headers(client)).json()["state"] == "cancelling"
        (directory / "release-worker").touch()
        assert process.wait(timeout=10) == 0
        assert record(task)["status"] == "cancelled"
        assert client.get(f"/api/v1/projects/{project}/artifacts").json()["total"] == 0
    finally:
        stop_and_reap(process)


def test_storage_fault_is_not_invalid_dataset(data_root):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start("storage_error")
    try:
        assert process.wait(timeout=10) == 0
        assert record(task)["status"] == "failed"
        assert record(task)["error_code"] != "DATASET_INVALID"
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
        assert client.get(f"/api/v1/projects/{project}/artifacts").json()["total"] == 0
    finally:
        stop_and_reap(process)


def test_spawning_unknown_and_malformed_receipt_fail_closed(data_root, monkeypatch):
    client, project = setup_admin(data_root)
    task = submit(client, upload(client, project).json()["id"])
    job_id, run_id = claim(str(uuid4()), None)
    directory = run_directory(job_id, run_id, create=True)
    from app import worker
    original = worker.drain_receipt
    monkeypatch.setattr(worker, "drain_receipt", lambda row, **_: original(row, wait_seconds=0))
    with transaction() as connection:
        connection.execute("UPDATE jobs SET launch_phase='spawning' WHERE id=?", (task,))
    assert recover() == [(task, "RECOVERY_BLOCKED_DRAIN_UNCONFIRMED")]
    from app.run_files import atomic_json
    atomic_json(directory / "drained.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id, "guardian": [], "tree_exited": True,
                "started": True, "exit_code": 0, "reason": "completed", "logs_complete": True})
    assert recover() == [(task, "RECOVERY_BLOCKED_DRAIN_UNCONFIRMED")]
    assert record(task)["status"] == "running"


@pytest.mark.parametrize("attempt", range(5))
def test_output_capacity_failure_remains_pending(data_root, attempt):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    process = start("output_capacity")
    try:
        assert process.wait(timeout=10) == 0
        receipt = read_json(run_path(task) / "drained.json")
        # Safe CI diagnosis only: no identities, paths, environment or payloads.
        diagnostic = {key: receipt.get(key) for key in ("reason", "exit_code", "logs_complete", "started", "tree_exited")}
        print("capacity_receipt=" + json.dumps(diagnostic, sort_keys=True))
        assert record(task)["error_code"] == "OUTPUT_CAPACITY_LIMIT", json.dumps(diagnostic, sort_keys=True)
        assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
    finally:
        stop_and_reap(process)


def test_log_sink_open_failure_still_drains_pipe(tmp_path):
    import threading
    from app.guardian import capture_output
    read, write = os.pipe()
    result = {}
    with os.fdopen(read, "rb") as source:
        capture = threading.Thread(target=capture_output, args=(source, tmp_path / "missing" / "logs.jsonl", result))
        capture.start()
        with os.fdopen(write, "wb") as sink:
            sink.write(b"x" * 256 * 1024)
        capture.join(timeout=5)
        assert not capture.is_alive() and result["complete"] is False


def test_boot_marker_policy_logic_rejects_malformed_and_accepts_changed_linux_uuid(data_root, monkeypatch):
    client, project = setup_admin(data_root)
    task = submit(client, upload(client, project).json()["id"])
    claim(str(uuid4()), None)
    from app import worker
    monkeypatch.setattr(worker, "drain_receipt", lambda *_args, **_kwargs: None)
    with transaction() as connection:
        connection.execute("UPDATE jobs SET launch_phase='spawning',host_boot_id='unknown' WHERE id=?", (task,))
    assert recover()
    assert record(task)["status"] == "running"
    # This is policy logic, NOT an actual host reboot acceptance test.
    if os.name != "nt":
        with transaction() as connection:
            connection.execute("UPDATE jobs SET host_boot_id=? WHERE id=?", (str(uuid4()), task))
        assert recover() == []
        assert record(task)["error_code"] == "HOST_RESTARTED"


def test_proc_stat_non_ascii_comm_does_not_break_identity(monkeypatch):
    from app.process_identity import linux_identity
    payload = b"321 (unrelated-\xff-\xe6\xa0\xa1\xe9\xaa\x8c) " + b" ".join([b"S", b"10", b"20", b"30", *([b"0"] * 15), b"400"])
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", lambda _self: payload)
        value = linux_identity(321)
    assert value == {"pid": 321, "start_ticks": 400, "session": 30, "ppid": 10, "state": "S"}


def test_control_pipe_exit_race_defers_to_drain_receipt():
    from app.worker import send_control
    class ExitedGuardian:
        def write(self, _command):
            raise BrokenPipeError("guardian already exited")
        def flush(self):
            raise AssertionError("write already failed")
    assert send_control(ExitedGuardian(), b"STOP\n") is False
