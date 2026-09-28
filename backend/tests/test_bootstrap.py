"""Integration gates: a skeleton must not pretend features are complete."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import app

BACKEND = Path(__file__).resolve().parents[1]


def migrate(root: Path) -> Path:
    os.environ["PLATFORM_DATA_ROOT"] = str(root)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # Idempotent migration.
    return root / "platform.db"


def test_live_is_not_readiness_or_a_business_result(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").json() == {"status": "ok", "service": "api"}
        assert client.get("/api/v1/health/ready").status_code == 503
        assert client.post("/api/v1/auth/login", json={"username": "x", "password": "x"}).json()["error"]["code"] == "NOT_IMPLEMENTED"
        invalid = client.post("/api/v1/auth/login", json={})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
        assert client.get("/api/v1/unknown-path").status_code == 404
        assert not any(feature["available"] for feature in client.get("/api/v1/capabilities").json()["features"].values())
        migrate(tmp_path)
        assert client.get("/api/v1/health/ready").json()["status"] == "ready"
        assert client.get("/api/v1/jobs/" + str(uuid4()) + "/logs").status_code == 501


def test_unimplemented_worker_cannot_report_success(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(tmp_path))
    path = migrate(tmp_path)
    first_job, second_job = str(uuid4()), str(uuid4())
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users (id,username,password_hash,role,is_active,created_at) VALUES (?,?,?,?,?,?)", ("u", "isolated_test", "test-only", "user", True, "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO projects (id,owner_id,name,description,task_type,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", ("p", "u", "test", "", "detection", "active", "2026-09-23T00:00:00Z", "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (first_job, "p", "u", "train", "queued", "{}", "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (second_job, "p", "u", "train", "queued", "{}", "2026-09-23T00:00:01Z"))
    env = {**os.environ, "PLATFORM_DATA_ROOT": str(tmp_path)}
    result = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status,error_code FROM jobs WHERE id=?", (first_job,)).fetchone() == ("failed", "UNSUPPORTED_JOB")
        assert db.execute("SELECT status FROM jobs WHERE id=?", (second_job,)).fetchone() == ("queued",)
        assert db.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM job_events WHERE job_id=?", (first_job,)).fetchone()[0] == 2


def test_worker_refuses_unknown_orphan_without_marking_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(tmp_path))
    path = migrate(tmp_path)
    owner, project, task = str(uuid4()), str(uuid4()), str(uuid4())
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users (id,username,password_hash,role,is_active,created_at) VALUES (?,?,?,?,?,?)", (owner, "orphan_test", "test-only", "user", True, "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO projects (id,owner_id,name,description,task_type,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", (project, owner, "test", "", "detection", "active", "2026-09-23T00:00:00Z", "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (task, project, owner, "train", "running", "{}", "2026-09-23T00:00:00Z"))
    result = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=BACKEND, env={**os.environ, "PLATFORM_DATA_ROOT": str(tmp_path)}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 4
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status FROM jobs").fetchone() == ("running",)


def test_generated_contract_is_current():
    check = subprocess.run([sys.executable, str(BACKEND.parent / "scripts" / "export_contract.py"), "--check"], cwd=BACKEND, capture_output=True, text=True, timeout=40)
    assert check.returncode == 0, check.stderr
