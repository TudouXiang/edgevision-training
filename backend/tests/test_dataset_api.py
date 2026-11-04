"""T030 staging, immutable records, ownership and bounded preview integration."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile
from zipfile import ZipInfo

from alembic import command
from alembic.config import Config
from fastapi import Request
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from starlette.requests import ClientDisconnect

from app.admin_cli import create_admin
from app.config import CSRF_COOKIE_NAME
from app import dataset_storage as storage
import app.main as main_module
from app.dataset_storage import StagedUpload, UploadError, publish_dataset_source, stage_multipart_zip
from app.dataset_validation import validate_dataset_archive
from app.main import app


BACKEND = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "admin-password-123"


def image_bytes(format_name: str, size: tuple[int, int] = (8, 8)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (30, 100, 150)).save(output, format=format_name)
    return output.getvalue()


def dataset_zip() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        values = {
            "data.yaml": b"train: images/train\nval: images/val\nnames: [object]\nnc: 1\n",
            "images/train/a.png": image_bytes("PNG"),
            "labels/train/a.txt": b"0 0.5 0.5 0.5 0.5\n",
            "images/val/b.jpg": image_bytes("JPEG"),
            "labels/val/b.txt": b"",
        }
        for name, content in values.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)
    return output.getvalue()


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("EDGEVISION_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("EDGEVISION_COOKIE_SECURE", raising=False)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    return tmp_path


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN}, json={"username": username, "password": password})
    assert response.status_code == 200, response.text


def headers(client: TestClient) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": client.cookies.get(CSRF_COOKIE_NAME)}


def setup_admin(data_root: Path) -> tuple[TestClient, str]:
    create_admin("root", PASSWORD)
    client = TestClient(app)
    login(client, "root", PASSWORD)
    project = client.post("/api/v1/projects", headers=headers(client), json={"name": "detector"})
    assert project.status_code == 201
    return client, project.json()["id"]


def create_user(admin: TestClient, username: str) -> TestClient:
    response = admin.post(
        "/api/v1/admin/users",
        headers=headers(admin),
        json={"username": username, "password": f"{username}-password-123", "role": "user"},
    )
    assert response.status_code == 201
    client = TestClient(app)
    login(client, username, f"{username}-password-123")
    return client


def upload(client: TestClient, project_id: str, filename: str = "tiny.zip"):
    return client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=headers(client),
        files={"file": (filename, dataset_zip(), "application/zip")},
    )


def test_upload_registers_real_pending_archive_and_same_name_creates_new_version(data_root):
    client, project_id = setup_admin(data_root)
    first = upload(client, project_id)
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["state"] == "pending" and first_body["version"] == 1
    assert first_body["sha256"] == sha256(dataset_zip()).hexdigest()
    assert first_body["size_bytes"] == len(dataset_zip())
    assert first_body["classes"] == [] and first_body["counts"] is None
    source = data_root / "datasets" / first_body["id"] / "source.zip"
    assert source.read_bytes() == dataset_zip()
    assert not (source.parent / "snapshot").exists()

    second = upload(client, project_id)
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first_body["id"] and second.json()["version"] == 2
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        rows = connection.execute("SELECT id,parent_id,version,status FROM datasets ORDER BY version").fetchall()
        assert rows == [(first_body["id"], None, 1, "pending"), (second.json()["id"], first_body["id"], 2, "pending")]

    listing = client.get(f"/api/v1/projects/{project_id}/datasets")
    assert listing.status_code == 200 and listing.json()["total"] == 2
    assert client.get(f"/api/v1/datasets/{first_body['id']}").json() == first_body
    preview = client.get(f"/api/v1/datasets/{first_body['id']}/samples")
    assert preview.status_code == 409 and preview.json()["error"]["code"] == "DATASET_NOT_READY"
    check = client.post(f"/api/v1/datasets/{first_body['id']}/check", headers={**headers(client), "Idempotency-Key": "check-1"})
    assert check.status_code == 202 and check.json()["state"] == "queued"


def test_upload_rejects_bad_archive_csrf_owner_and_archived_project_without_registration(data_root):
    admin, project_id = setup_admin(data_root)
    other = create_user(admin, "other")
    no_csrf = admin.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={"Origin": ORIGIN},
        files={"file": ("tiny.zip", dataset_zip(), "application/zip")},
    )
    assert no_csrf.status_code == 403
    hidden = upload(other, project_id)
    assert hidden.status_code == 404

    broken = admin.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=headers(admin),
        files={"file": ("broken.zip", b"not a zip", "application/zip")},
    )
    assert broken.status_code == 422 and broken.json()["error"]["code"] == "ARCHIVE_INVALID"
    assert list((data_root / "uploads").glob("*.part")) == []

    assert admin.post(f"/api/v1/projects/{project_id}/archive", headers=headers(admin)).status_code == 200
    archived = upload(admin, project_id)
    assert archived.status_code == 409 and archived.json()["error"]["code"] == "PROJECT_ARCHIVED"
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0


def test_ready_preview_uses_validated_manifest_and_is_owner_aware(data_root):
    admin, project_id = setup_admin(data_root)
    other = create_user(admin, "other")
    uploaded = upload(admin, project_id).json()
    source = data_root / "datasets" / uploaded["id"] / "source.zip"
    snapshot = source.parent / "snapshot"
    result = validate_dataset_archive(source, snapshot)
    with closing(sqlite3.connect(data_root / "platform.db")) as connection, connection:
        connection.execute(
            "UPDATE datasets SET status='ready',classes_json=?,counts_json=?,manifest_json=? WHERE id=?",
            (json.dumps(result.classes), json.dumps(result.counts), json.dumps(result.manifest()), uploaded["id"]),
        )
    samples = admin.get(f"/api/v1/datasets/{uploaded['id']}/samples?page_size=1")
    assert samples.status_code == 200, samples.text
    body = samples.json()
    assert body["total"] == 2 and len(body["items"]) == 1
    sample = body["items"][0]
    assert sample["image_path"] == "images/train/a.png"
    assert sample["annotations"][0]["class_name"] == "object"
    image = admin.get(sample["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "private, no-store"
    assert other.get(f"/api/v1/datasets/{uploaded['id']}/samples").status_code == 404
    assert other.get(sample["image_url"]).status_code == 404

    with closing(sqlite3.connect(data_root / "platform.db")) as connection, connection:
        connection.execute("UPDATE datasets SET manifest_json='{}' WHERE id=?", (uploaded["id"],))
    unavailable = admin.get(f"/api/v1/datasets/{uploaded['id']}/samples")
    assert unavailable.status_code == 409 and unavailable.json()["error"]["code"] == "DATASET_PREVIEW_UNAVAILABLE"


def request_for(body: bytes, content_type: str, *, disconnect_at: int | None = None) -> Request:
    messages = []
    if disconnect_at is None:
        messages.append({"type": "http.request", "body": body, "more_body": False})
    else:
        messages.append({"type": "http.request", "body": body[:disconnect_at], "more_body": True})
        messages.append({"type": "http.disconnect"})

    async def receive():
        return messages.pop(0)

    return Request(
        {
            "type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/", "raw_path": b"/", "query_string": b"", "headers": [(b"content-type", content_type.encode())],
            "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000),
        },
        receive,
    )


def multipart_body(file_content: bytes, *, second_part: bool = False) -> tuple[bytes, str]:
    boundary = "edgevision-boundary"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"tiny.zip\"\r\n"
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + file_content + b"\r\n"
    if second_part:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"other\"\r\n\r\nx\r\n".encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def test_raw_stream_limits_trailing_parts_and_disconnect_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MAX_DATASET_ZIP_BYTES", 8)
    body, content_type = multipart_body(b"123456789")
    destination = tmp_path / "large.part"
    with pytest.raises(UploadError) as large:
        asyncio.run(stage_multipart_zip(request_for(body, content_type), destination))
    assert large.value.status_code == 413 and not destination.exists()

    monkeypatch.setattr(storage, "MAX_DATASET_ZIP_BYTES", 1024)
    body, content_type = multipart_body(b"zip", second_part=True)
    destination = tmp_path / "parts.part"
    with pytest.raises(UploadError) as parts:
        asyncio.run(stage_multipart_zip(request_for(body, content_type), destination))
    assert parts.value.code == "MULTIPART_PART_COUNT" and not destination.exists()

    body, content_type = multipart_body(b"zip")
    destination = tmp_path / "disconnect.part"
    with pytest.raises(ClientDisconnect):
        asyncio.run(stage_multipart_zip(request_for(body, content_type, disconnect_at=len(body) // 2), destination))
    assert not destination.exists()


def test_exclusive_publication_never_overwrites_or_cleans_existing_dataset(data_root):
    dataset_id = str(uuid4())
    existing = data_root / "datasets" / dataset_id
    existing.mkdir(parents=True)
    (existing / "source.zip").write_bytes(b"existing")
    staged = data_root / "new.part"
    staged.write_bytes(b"new")
    with pytest.raises(FileExistsError):
        publish_dataset_source(staged, dataset_id)
    assert (existing / "source.zip").read_bytes() == b"existing"
    assert staged.read_bytes() == b"new"


@pytest.mark.parametrize("race", ["archive", "disable", "revoke"])
def test_final_auth_recheck_rejects_state_change_during_staging_and_leaves_no_record(data_root, monkeypatch, race):
    client, project_id = setup_admin(data_root)

    async def race_stage(_request, destination: Path):
        payload = dataset_zip()
        destination.write_bytes(payload)
        with closing(sqlite3.connect(data_root / "platform.db")) as connection, connection:
            if race == "archive":
                connection.execute("UPDATE projects SET status='archived',archived_at='2026-11-04T00:00:00Z' WHERE id=?", (project_id,))
            elif race == "disable":
                connection.execute("UPDATE users SET is_active=0 WHERE username='root'")
            else:
                connection.execute("UPDATE sessions SET revoked_at='2026-11-04T00:00:00Z'")
        return StagedUpload(destination, "tiny.zip", sha256(payload).hexdigest(), len(payload))

    monkeypatch.setattr(main_module, "stage_multipart_zip", race_stage)
    response = upload(client, project_id)
    assert response.status_code == (409 if race == "archive" else 401)
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0
    assert list((data_root / "uploads").glob("*.part")) == []
    assert not (data_root / "datasets").exists() or list((data_root / "datasets").iterdir()) == []


def test_staging_fsync_failure_is_normalized_and_cleans_part(data_root, monkeypatch):
    client, project_id = setup_admin(data_root)

    def fail_fsync(_descriptor):
        raise OSError("synthetic test fsync failure")

    monkeypatch.setattr(storage.os, "fsync", fail_fsync)
    response = upload(client, project_id)
    assert response.status_code == 503 and response.json()["error"]["code"] == "STORAGE_WRITE_FAILED"
    assert list((data_root / "uploads").glob("*.part")) == []
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0


def test_registration_failure_cleans_only_newly_published_directory(data_root, monkeypatch):
    client, project_id = setup_admin(data_root)
    existing_id = str(uuid4())
    existing = data_root / "datasets" / existing_id
    existing.mkdir(parents=True)
    (existing / "source.zip").write_bytes(b"existing")

    def fail_after_publication():
        raise sqlite3.OperationalError("synthetic registration failure")

    monkeypatch.setattr(main_module, "timestamp", fail_after_publication)
    response = upload(client, project_id)
    assert response.status_code == 503 and response.json()["error"]["code"] == "DATASET_REGISTRATION_FAILED"
    assert (existing / "source.zip").read_bytes() == b"existing"
    assert [path.name for path in (data_root / "datasets").iterdir()] == [existing_id]
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0


def test_parallel_same_name_uploads_allocate_distinct_serial_versions(data_root):
    first, project_id = setup_admin(data_root)
    second = TestClient(app)
    login(second, "root", PASSWORD)

    def submit(client: TestClient):
        return upload(client, project_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, (first, second)))
    assert [response.status_code for response in responses] == [201, 201]
    bodies = [response.json() for response in responses]
    assert sorted(body["version"] for body in bodies) == [1, 2]
    assert len({body["id"] for body in bodies}) == 2
    with closing(sqlite3.connect(data_root / "platform.db")) as connection:
        rows = connection.execute("SELECT id,parent_id,version FROM datasets ORDER BY version").fetchall()
    assert rows[0][2] == 1 and rows[0][1] is None
    assert rows[1][2] == 2 and rows[1][1] == rows[0][0]
