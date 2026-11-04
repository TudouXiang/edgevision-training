"""T040 real API/worker tests use only migrated temporary roots and synthetic ZIPs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from fastapi.testclient import TestClient

from test_dataset_api import data_root, setup_admin, upload, headers, create_user, dataset_zip, BACKEND
from app.job_service import incremental, append_event
from app.database import transaction
from app.main import app
from app.run_files import relative_file, read_json
from app.python_launch import python_child


def submit(client, dataset_id, key="check"):
    response = client.post(f"/api/v1/datasets/{dataset_id}/check", headers={**headers(client), "Idempotency-Key": key})
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def work():
    args, environment = python_child([sys.executable, "-m", "app.worker", "--once"], os.environ.copy())
    result = subprocess.run(args, cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_real_validation_publication_log_report_preview_and_terminal_idempotency(data_root):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    assert submit(client, dataset["id"], "other-key") == task
    work()
    completed = client.get(f"/api/v1/jobs/{task}").json()
    assert completed["state"] == "succeeded"
    assert submit(client, dataset["id"]) == task
    state = client.get(f"/api/v1/datasets/{dataset['id']}").json()
    assert state["state"] == "ready" and state["counts"]["images"] == 2
    report = client.get(f"/api/v1/artifacts/{state['report_artifact_id']}/download")
    assert report.status_code == 200 and report.json()["valid"]
    assert report.json()["job_id"] == task
    listing = client.get(f"/api/v1/projects/{project}/artifacts").json()
    assert listing["total"] == 1
    assert listing["items"][0]["validation_state"] == "passed"
    logs = client.get(f"/api/v1/jobs/{task}/logs?limit=1").json()
    assert len(logs["items"]) == 1 and not logs["eof"]
    previous = logs["items"][0]["seq"]
    while not logs["eof"]:
        logs = client.get(f"/api/v1/jobs/{task}/logs", params={"cursor": logs["next_cursor"], "limit": 1}).json()
        if logs["items"]:
            assert logs["items"][0]["seq"] > previous
            previous = logs["items"][0]["seq"]
    assert logs["job_state"] == "succeeded"
    assert client.get(f"/api/v1/jobs/{task}/metrics").json()["items"] == []
    assert client.get(f"/api/v1/jobs/{task}/metrics", params={"cursor": logs["next_cursor"]}).status_code == 422
    assert client.get(f"/api/v1/jobs/{task}/logs", params={"cursor": "bad"}).status_code == 422
    assert client.get(f"/api/v1/jobs/{task}/logs", params={"cursor": f"v1:{task}:log:999999"}).status_code == 422
    samples = client.get(f"/api/v1/datasets/{dataset['id']}/samples").json()["items"]
    assert len(samples) == 2
    assert client.get(samples[0]["image_url"]).status_code == 200
    assert client.post(f"/api/v1/datasets/{dataset['id']}/check", headers={**headers(client), "Idempotency-Key": "new"}).status_code == 409
    assert client.post(f"/api/v1/jobs/{task}/cancel", headers=headers(client)).json()["state"] == "succeeded"


def test_real_invalid_report_retry_cancellation_and_history(data_root):
    client, project = setup_admin(data_root)
    original = BytesIO(dataset_zip())
    bad = BytesIO()
    with ZipFile(original) as source, ZipFile(bad, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            target.writestr(name, b"9 0.5 0.5 0.5 0.5" if name == "labels/train/a.txt" else source.read(name))
    dataset = client.post(f"/api/v1/projects/{project}/datasets", headers=headers(client), files={"file": ("invalid.zip", bad.getvalue(), "application/zip")}).json()
    task = submit(client, dataset["id"])
    work()
    state = client.get(f"/api/v1/datasets/{dataset['id']}").json()
    assert state["state"] == "invalid"
    report_id = state["report_artifact_id"]
    assert client.get(f"/api/v1/artifacts/{report_id}/download").json()["errors"][0]["code"] == "LABEL_CLASS_RANGE"
    assert client.get(f"/api/v1/jobs/{task}").json()["error_code"] == "DATASET_INVALID"
    retry = submit(client, dataset["id"], "retry")
    assert retry != task
    assert client.get(f"/api/v1/jobs/{retry}").json()["source_job_id"] == task
    assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["report_artifact_id"] is None
    assert client.post(f"/api/v1/jobs/{retry}/cancel", headers=headers(client)).json()["state"] == "cancelled"
    assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["state"] == "pending"
    assert client.get(f"/api/v1/artifacts/{report_id}/download").status_code == 200
    work()  # queued cancellation must never launch.
    assert not list((data_root / "jobs" / retry).glob("runs/*"))


def test_concurrent_submission_single_job_key_conflict_and_actor_authority(data_root):
    admin, project = setup_admin(data_root)
    user = create_user(admin, "owner")
    other = create_user(admin, "other")
    own = user.post("/api/v1/projects", headers=headers(user), json={"name": "owned"}).json()["id"]
    first, second = upload(user, own).json(), upload(user, own, "second.zip").json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = list(pool.map(lambda _: submit(admin, first["id"], "concurrent"), range(4)))
    assert len(set(tasks)) == 1
    task = tasks[0]
    actor = admin.get("/api/v1/auth/me").json()["id"]
    assert admin.get(f"/api/v1/jobs/{task}").json()["created_by"] == actor
    assert user.get(f"/api/v1/jobs/{task}").status_code == 200
    path = f"/api/v1/projects/{own}/jobs"
    payload = {"kind": "dataset_check", "params": {"dataset_id": first["id"]}}
    assert admin.post(path, headers={**headers(admin), "Idempotency-Key": "same"}, json=payload).status_code == 202
    payload["params"]["dataset_id"] = second["id"]
    assert admin.post(path, headers={**headers(admin), "Idempotency-Key": "same"}, json=payload).status_code == 409
    for suffix in ("", "/logs", "/metrics"):
        assert other.get(f"/api/v1/jobs/{task}{suffix}").status_code == 404
    assert other.post(f"/api/v1/jobs/{task}/cancel", headers=headers(other)).status_code == 404
    assert user.post(f"/api/v1/jobs/{task}/cancel", headers={"Origin": "http://127.0.0.1:5173"}).status_code == 403
    assert user.post(f"/api/v1/projects/{own}/archive", headers=headers(user)).status_code == 200
    assert submit(admin, first["id"], "concurrent") == task  # replay is not new work.
    assert admin.post(f"/api/v1/datasets/{first['id']}/check", headers={**headers(admin), "Idempotency-Key": "new"}).status_code == 409
    work()  # already queued work may finish after archive.
    report_id = user.get(f"/api/v1/datasets/{first['id']}").json()["report_artifact_id"]
    assert other.get(f"/api/v1/artifacts/{report_id}").status_code == 404
    assert other.get(f"/api/v1/artifacts/{report_id}/download").status_code == 404
    with transaction() as connection:
        key = connection.execute("SELECT storage_key FROM artifacts WHERE id=?", (report_id,)).fetchone()[0]
    (data_root / key).write_bytes(b"changed")
    assert user.get(f"/api/v1/artifacts/{report_id}/download").status_code == 409


def test_incremental_cursor_is_bound_to_read_high_watermark(data_root):
    client, project = setup_admin(data_root)
    task = submit(client, upload(client, project).json()["id"])
    with transaction() as connection:
        append_event(connection, task, "log", {"level": "info", "text": "first"})
    with transaction() as connection:
        class AppendAfterHigh:
            def execute(self, query, args=()):
                result = connection.execute(query, args)
                if query.startswith("SELECT COALESCE(MAX(seq),0)"):
                    high = result.fetchone()
                    with transaction() as other:
                        append_event(other, task, "log", {"level": "info", "text": "new"})
                    class Row:
                        def fetchone(self): return high
                    return Row()
                return result
        first = incremental(AppendAfterHigh(), task, "log", None, 100)
    assert [item["text"] for item in first["items"]] == ["first"]
    with transaction() as connection:
        second = incremental(connection, task, "log", first["next_cursor"], 100)
    assert [item["text"] for item in second["items"]] == ["new"]
    assert int(second["next_cursor"].rsplit(":", 1)[1]) > int(first["next_cursor"].rsplit(":", 1)[1])


def test_protocol_paths_and_bounded_json(tmp_path):
    (tmp_path / "ok").write_text("{}")
    assert read_json(tmp_path / "ok", 2) == {}
    for key in ("C:outside", "C:/outside", "a/../ok", "../ok", "a\\ok", "/ok"):
        with pytest.raises((ValueError, FileNotFoundError)):
            relative_file(tmp_path, key)
    with pytest.raises(ValueError):
        read_json(tmp_path / "ok", 1)


def test_0003_downgrade_refuses_queued_validation_and_preserves_link(data_root):
    from alembic import command
    from alembic.config import Config
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    task = submit(client, dataset["id"])
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    with pytest.raises(RuntimeError, match="reconcile active tasks"):
        command.downgrade(config, "0002_foundation")
    with transaction() as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_worker"
        assert connection.execute("SELECT validation_job_id FROM datasets WHERE id=?", (dataset["id"],)).fetchone()[0] == task
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
