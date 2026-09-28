"""Integration gates: a skeleton must not pretend features are complete."""
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
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
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users (id,username,password_hash,role,is_active,created_at) VALUES (?,?,?,?,?,?)", ("u", "isolated_test", "test-only", "user", True, "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO projects (id,owner_id,name,description,task_type,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", ("p", "u", "test", "", "detection", "active", "2026-09-23T00:00:00Z", "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (first_job, "p", "u", "train", "queued", "{}", "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (second_job, "p", "u", "train", "queued", "{}", "2026-09-23T00:00:01Z"))
    env = {**os.environ, "PLATFORM_DATA_ROOT": str(tmp_path)}
    result = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    with closing(sqlite3.connect(path)) as db, db:
        assert db.execute("SELECT status,error_code FROM jobs WHERE id=?", (first_job,)).fetchone() == ("failed", "UNSUPPORTED_JOB")
        assert db.execute("SELECT status FROM jobs WHERE id=?", (second_job,)).fetchone() == ("queued",)
        assert db.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM job_events WHERE job_id=?", (first_job,)).fetchone()[0] == 2


def test_worker_refuses_unknown_orphan_without_marking_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(tmp_path))
    path = migrate(tmp_path)
    owner, project, task = str(uuid4()), str(uuid4()), str(uuid4())
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users (id,username,password_hash,role,is_active,created_at) VALUES (?,?,?,?,?,?)", (owner, "orphan_test", "test-only", "user", True, "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO projects (id,owner_id,name,description,task_type,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", (project, owner, "test", "", "detection", "active", "2026-09-23T00:00:00Z", "2026-09-23T00:00:00Z"))
        db.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (task, project, owner, "train", "running", "{}", "2026-09-23T00:00:00Z"))
    result = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=BACKEND, env={**os.environ, "PLATFORM_DATA_ROOT": str(tmp_path)}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 4
    with closing(sqlite3.connect(path)) as db, db:
        assert db.execute("SELECT status FROM jobs").fetchone() == ("running",)


def test_legacy_0001_copy_upgrade_preserves_rows(tmp_path, monkeypatch):
    old_root, copy_root = tmp_path / "old", tmp_path / "copy"
    old_root.mkdir()
    copy_root.mkdir()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(old_root))
    command.upgrade(config, "0001_initial")
    old_path, copy_path = old_root / "platform.db", copy_root / "platform.db"
    user_id, project_id, dataset_id, job_id, artifact_id = (str(uuid4()) for _ in range(5))
    created_at = "2026-09-28T00:00:00Z"
    with closing(sqlite3.connect(old_path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users(id,username,password_hash,role,is_active,created_at) VALUES(?,?,?,?,?,?)", (user_id, "legacy", "test-only", "user", 1, created_at))
        db.execute("INSERT INTO projects(id,owner_id,name,description,task_type,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (project_id, user_id, "legacy", "", "detection", "active", created_at, created_at))
        db.execute("INSERT INTO datasets(id,project_id,version,name,archive_key,snapshot_key,sha256,size_bytes,status,counts_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (dataset_id, project_id, 1, "legacy", "archive", "snapshot", "0" * 64, 1, "uploaded", "{}", created_at))
        db.execute("INSERT INTO jobs(id,project_id,owner_id,kind,status,payload_json,created_at) VALUES(?,?,?,?,?,?,?)", (job_id, project_id, user_id, "validate", "queued", "{}", created_at))
        db.execute("INSERT INTO artifacts(id,project_id,job_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (artifact_id, project_id, job_id, "dataset_report", "json", "report", "0" * 64, 1, "pending", "{}", created_at))
    with closing(sqlite3.connect(f"file:{old_path}?mode=ro", uri=True)) as source, closing(sqlite3.connect(copy_path)) as target:
        source.backup(target)
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(copy_root))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with closing(sqlite3.connect(copy_path)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002_foundation",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert [db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("users", "projects", "datasets", "jobs", "artifacts")] == [1] * 5
        assert db.execute("SELECT status FROM datasets").fetchone() == ("pending",)
        assert db.execute("SELECT kind FROM jobs").fetchone() == ("dataset_check",)
        assert db.execute("SELECT validation_status FROM artifacts").fetchone() == ("unverified",)
        assert "run_id" in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE datasets SET status='uploaded' WHERE id=?", (dataset_id,))
        db.rollback()
    with closing(sqlite3.connect(old_path)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0001_initial",)


def test_generated_contract_is_current():
    check = subprocess.run([sys.executable, str(BACKEND.parent / "scripts" / "export_contract.py"), "--check"], cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
    assert check.returncode == 0, check.stderr
