"""T020 identity, authorization and project integration coverage."""

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest

from app import admin_cli
from app.admin_cli import create_admin
from app.config import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from app.main import app
from app.security import secret_hash

BACKEND = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:5173"
ADMIN_PASSWORD = "admin-password-123"


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("EDGEVISION_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("EDGEVISION_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("EDGEVISION_SESSION_TTL_SECONDS", raising=False)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    return tmp_path


def login(client: TestClient, username: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": username, "password": password},
    )


def mutation_headers(client: TestClient, token: str | None = None) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": token or client.cookies.get(CSRF_COOKIE_NAME)}


def admin_client(data_root: Path) -> TestClient:
    create_admin("root", ADMIN_PASSWORD)
    client = TestClient(app)
    assert login(client, "root", ADMIN_PASSWORD).status_code == 200
    return client


def create_user(client: TestClient, username: str, password: str, role: str = "user") -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=mutation_headers(client),
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_explicit_admin_bootstrap_has_no_default_or_logged_password(data_root, monkeypatch, capsys):
    path = data_root / "platform.db"
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    entered = iter((ADMIN_PASSWORD, ADMIN_PASSWORD))
    monkeypatch.setattr(admin_cli, "getpass", lambda prompt: next(entered))
    assert admin_cli.main(["--username", "root"]) == 0
    output = capsys.readouterr()
    assert ADMIN_PASSWORD not in output.out + output.err
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT id,password_hash,role,is_active FROM users").fetchone()
        assert row[0]
        assert row[1].startswith("$argon2id$")
        assert ADMIN_PASSWORD not in row[1]
        assert row[2:] == ("admin", 1)
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    with pytest.raises(RuntimeError, match="active administrator"):
        create_admin("another", "another-password-123")


def test_login_origin_cookie_csrf_and_configuration_fail_closed(data_root, monkeypatch):
    create_admin("root", ADMIN_PASSWORD)
    with TestClient(app) as client:
        missing = client.post("/api/v1/auth/login", json={"username": "root", "password": ADMIN_PASSWORD})
        assert missing.status_code == 403 and missing.json()["error"]["code"] == "ORIGIN_REQUIRED"
        null_origin = client.post("/api/v1/auth/login", headers={"Origin": "null"}, json={"username": "root", "password": ADMIN_PASSWORD})
        assert null_origin.status_code == 403 and null_origin.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        wrong = login(client, "root", "wrong-password")
        assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
        success = login(client, "root", ADMIN_PASSWORD)
        assert success.status_code == 200
        cookie_headers = success.headers.get_list("set-cookie")
        assert any(SESSION_COOKIE_NAME in value and "HttpOnly" in value and "SameSite=lax" in value for value in cookie_headers)
        assert any(CSRF_COOKIE_NAME in value and "HttpOnly" not in value and "SameSite=lax" in value for value in cookie_headers)
        raw_token = client.cookies.get(SESSION_COOKIE_NAME)
        with closing(sqlite3.connect(data_root / "platform.db")) as connection:
            stored = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
            assert stored == secret_hash(raw_token) and raw_token not in stored
        no_csrf = client.post("/api/v1/projects", headers={"Origin": ORIGIN}, json={"name": "x"})
        assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "CSRF_INVALID"
        malformed = client.post(
            "/api/v1/projects",
            headers=[(b"origin", ORIGIN.encode()), (b"x-csrf-token", b"\xff" * 43)],
            json={"name": "x"},
        )
        assert malformed.status_code == 403 and malformed.json()["error"]["code"] == "CSRF_INVALID"

    monkeypatch.setenv("EDGEVISION_ALLOWED_ORIGINS", "http://localhost:99999")
    with TestClient(app) as client:
        invalid_port = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN}, json={"username": "root", "password": ADMIN_PASSWORD})
        assert invalid_port.status_code == 503 and invalid_port.json()["error"]["code"] == "AUTH_CONFIGURATION_INVALID"
    monkeypatch.setenv("EDGEVISION_ALLOWED_ORIGINS", "https://edge.example")
    with TestClient(app) as client:
        insecure = client.post("/api/v1/auth/login", headers={"Origin": "https://edge.example"}, json={"username": "root", "password": ADMIN_PASSWORD})
        assert insecure.status_code == 503
    monkeypatch.setenv("EDGEVISION_COOKIE_SECURE", "true")
    with TestClient(app, base_url="https://edge.example") as client:
        secure = client.post("/api/v1/auth/login", headers={"Origin": "https://edge.example"}, json={"username": "root", "password": ADMIN_PASSWORD})
        assert secure.status_code == 200
        assert all("Secure" in value for value in secure.headers.get_list("set-cookie"))


def test_session_expiry_logout_disable_and_password_rotation(data_root):
    admin = admin_client(data_root)
    user = create_user(admin, "alice", "alice-password-123")
    first, second = TestClient(app), TestClient(app)
    assert login(first, "alice", "alice-password-123").status_code == 200
    assert login(second, "alice", "alice-password-123").status_code == 200
    old_session = first.cookies.get(SESSION_COOKIE_NAME)
    old_csrf = first.cookies.get(CSRF_COOKIE_NAME)
    changed = first.post(
        "/api/v1/auth/change-password",
        headers=mutation_headers(first),
        json={"current_password": "alice-password-123", "new_password": "alice-password-456"},
    )
    assert changed.status_code == 204
    assert first.cookies.get(SESSION_COOKIE_NAME) != old_session
    assert first.cookies.get(CSRF_COOKIE_NAME) != old_csrf
    assert first.get("/api/v1/auth/me").status_code == 200
    assert second.get("/api/v1/auth/me").status_code == 401
    assert login(TestClient(app), "alice", "alice-password-123").status_code == 401
    assert login(TestClient(app), "alice", "alice-password-456").status_code == 200

    logged_out = first.post("/api/v1/auth/logout", headers=mutation_headers(first))
    assert logged_out.status_code == 204
    assert first.get("/api/v1/auth/me").status_code == 401

    expiring = TestClient(app)
    assert login(expiring, "alice", "alice-password-456").status_code == 200
    with closing(sqlite3.connect(data_root / "platform.db")) as connection, connection:
        connection.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00Z' WHERE token_hash=?", (secret_hash(expiring.cookies.get(SESSION_COOKIE_NAME)),))
    assert expiring.get("/api/v1/auth/me").status_code == 401

    active = TestClient(app)
    assert login(active, "alice", "alice-password-456").status_code == 200
    disabled = admin.patch(f"/api/v1/admin/users/{user['id']}", headers=mutation_headers(admin), json={"is_active": False})
    assert disabled.status_code == 200 and disabled.json()["is_active"] is False
    assert active.get("/api/v1/auth/me").status_code == 401


def test_admin_user_rules_and_last_admin_guard(data_root):
    admin = admin_client(data_root)
    created = create_user(admin, "alice", "alice-password-123")
    duplicate = admin.post(
        "/api/v1/admin/users",
        headers=mutation_headers(admin),
        json={"username": "alice", "password": "different-password-123", "role": "user"},
    )
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "USERNAME_EXISTS"
    last_admin = admin.patch(
        f"/api/v1/admin/users/{admin.get('/api/v1/auth/me').json()['id']}",
        headers=mutation_headers(admin),
        json={"is_active": False},
    )
    assert last_admin.status_code == 409 and last_admin.json()["error"]["code"] == "LAST_ADMIN"
    ordinary = TestClient(app)
    assert login(ordinary, "alice", "alice-password-123").status_code == 200
    assert ordinary.get("/api/v1/admin/users").status_code == 403
    assert ordinary.patch(f"/api/v1/admin/users/{created['id']}", headers=mutation_headers(ordinary), json={"is_active": False}).status_code == 403


def test_project_ownership_archive_and_admin_visibility(data_root):
    admin = admin_client(data_root)
    alice = create_user(admin, "alice", "alice-password-123")
    create_user(admin, "bob", "bob-password-123")
    alice_client, bob_client = TestClient(app), TestClient(app)
    assert login(alice_client, "alice", "alice-password-123").status_code == 200
    assert login(bob_client, "bob", "bob-password-123").status_code == 200
    created = alice_client.post(
        "/api/v1/projects",
        headers=mutation_headers(alice_client),
        json={"name": "Detector", "description": "owned by alice"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert alice_client.get("/api/v1/projects").json()["total"] == 1
    assert bob_client.get("/api/v1/projects").json()["total"] == 0
    assert bob_client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert bob_client.patch(f"/api/v1/projects/{project_id}", headers=mutation_headers(bob_client), json={"name": "stolen"}).status_code == 404
    assert bob_client.post(f"/api/v1/projects/{project_id}/archive", headers=mutation_headers(bob_client)).status_code == 404
    assert admin.get(f"/api/v1/projects/{project_id}").status_code == 200
    assert admin.get("/api/v1/admin/projects").json()["total"] == 1

    updated = alice_client.patch(
        f"/api/v1/projects/{project_id}",
        headers=mutation_headers(alice_client),
        json={"description": "updated"},
    )
    assert updated.status_code == 200 and updated.json()["description"] == "updated"
    archived = alice_client.post(f"/api/v1/projects/{project_id}/archive", headers=mutation_headers(alice_client))
    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    repeated = alice_client.post(f"/api/v1/projects/{project_id}/archive", headers=mutation_headers(alice_client))
    assert repeated.status_code == 200 and repeated.json()["archived_at"] == archived.json()["archived_at"]
    rejected_job = alice_client.post(
        f"/api/v1/projects/{project_id}/jobs",
        headers={**mutation_headers(alice_client), "Idempotency-Key": "archived-job"},
        json={
            "kind": "train",
            "params": {
                "dataset_id": str(uuid4()), "experiment_name": "blocked", "epochs": 1,
                "batch": 1, "imgsz": 320, "device": "cpu", "seed": 1,
            },
        },
    )
    assert rejected_job.status_code == 409 and rejected_job.json()["error"]["code"] == "PROJECT_ARCHIVED"
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        row = connection.execute("SELECT owner_id,status,archived_at FROM projects WHERE id=?", (project_id,)).fetchone()
        assert row[0] == alice["id"] and row[1] == "archived" and row[2] is not None


def test_cross_owner_derived_resource_guards_precede_unimplemented(data_root):
    admin = admin_client(data_root)
    alice = create_user(admin, "alice", "alice-password-123")
    create_user(admin, "bob", "bob-password-123")
    owner, other = TestClient(app), TestClient(app)
    assert login(owner, "alice", "alice-password-123").status_code == 200
    assert login(other, "bob", "bob-password-123").status_code == 200
    project_id, dataset_id, job_id, artifact_id = (str(uuid4()) for _ in range(4))
    now = "2026-11-04T00:00:00Z"
    with closing(sqlite3.connect(data_root / "platform.db")) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("INSERT INTO projects (id,owner_id,name,description,task_type,status,created_at,updated_at,archived_at) VALUES (?,?,?,?,?,?,?,?,NULL)", (project_id, alice["id"], "p", "", "detection", "active", now, now))
        connection.execute("INSERT INTO datasets (id,project_id,parent_id,version,name,archive_key,snapshot_key,sha256,size_bytes,status,report_key,counts_json,classes_json,manifest_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (dataset_id, project_id, None, 1, "d", "a", "s", "0" * 64, 1, "pending", None, "{}", "[]", "{}", now))
        connection.execute("INSERT INTO jobs (id,project_id,owner_id,kind,status,payload_json,created_at) VALUES (?,?,?,?,?,?,?)", (job_id, project_id, alice["id"], "train", "queued", "{}", now))
        connection.execute("INSERT INTO artifacts (id,project_id,job_id,parent_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (artifact_id, project_id, job_id, None, "dataset_report", "json", "report", "0" * 64, 1, "unverified", "{}", now))

    for path in (
        f"/api/v1/datasets/{dataset_id}", f"/api/v1/jobs/{job_id}", f"/api/v1/jobs/{job_id}/logs",
        f"/api/v1/jobs/{job_id}/metrics", f"/api/v1/artifacts/{artifact_id}", f"/api/v1/artifacts/{artifact_id}/download",
    ):
        assert owner.get(path).status_code == 501
        assert other.get(path).status_code == 404
    assert owner.post(f"/api/v1/jobs/{job_id}/cancel", headers=mutation_headers(owner)).status_code == 501
    assert other.post(f"/api/v1/jobs/{job_id}/cancel", headers=mutation_headers(other)).status_code == 404
