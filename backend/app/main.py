"""Lightweight API with the T020 identity/project vertical slice."""

from contextlib import contextmanager
from importlib import metadata, util
import json
from hashlib import sha256
import sqlite3
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contracts import JobKind
from .job_service import artifact_public, cancel_job, incremental, job_public, submit_check
from .config import data_root
from .database import database_ready, transaction
from .dataset_storage import (
    UploadError, dataset_name_from_filename, publish_dataset_source,
    remove_dataset_storage, resolve_storage_file, safe_directory,
    stage_multipart_zip,
)
from .dataset_validation import DatasetValidationError, inspect_dataset_archive
from .schemas import (
    ApiError, ArtifactPublic, CapabilitiesResponse, ChangePasswordRequest,
    DatasetPublic, DatasetSamplePublic, FeatureCapability, Incremental, JobAccepted, JobCreate,
    InferenceResult, JobLog, JobPublic, LiveResponse, LoginRequest, Metric, Page, ProjectCreate,
    ProjectPublic, ProjectUpdate, ReadyResponse, UserCreate, UserPublic, UserUpdate,
)
from .security import (
    authenticate_password, clear_session_cookies, create_session, password_hash,
    password_matches, require_actor, require_admin, require_allowed_origin,
    revoke_session, revoke_user_sessions, set_session_cookies, timestamp,
)
from .services import active_project, begin_write, dataset_public, project_for_actor, project_for_resource, project_public, user_public

app = FastAPI(title="EdgeVision API", version="0.4.0")
API = "/api/v1"
_ERROR_RESPONSE = {501: {"model": ApiError, "description": "Not implemented in the production shell"}}
_JOB_RESPONSES = {status: {"model": ApiError} for status in (404, 409, 422, 503)}
_AUTH_RESPONSES = {
    401: {"model": ApiError, "description": "Authentication required or session invalid"},
    403: {"model": ApiError, "description": "Origin, CSRF, role or access denied"},
}
_DATASET_UPLOAD_RESPONSES = {
    status: {"model": ApiError}
    for status in (400, 409, 413, 415, 422, 503)
}
_DATASET_READ_RESPONSES = {status: {"model": ApiError} for status in (404, 409, 503)}
_UPLOAD_BODY = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}}}


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = uuid4()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request.state.request_id)
    return response


def error_body(request: Request, code: str, message: str, details: dict[str, str] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": str(getattr(request.state, "request_id", uuid4())), "details": details}}


@app.exception_handler(StarletteHTTPException)
async def api_error(request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, detail.get("code", "HTTP_ERROR"), detail.get("message", "Request failed"), detail.get("details")),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo raw input, uploaded data or secrets in the error response.
    return JSONResponse(status_code=422, content=error_body(request, "VALIDATION_ERROR", "Invalid request parameters"))


@app.get(API + "/health/live", response_model=LiveResponse)
def live():
    return {"status": "ok", "service": "api"}


@app.get(API + "/health/ready", response_model=ReadyResponse)
def ready():
    try:
        is_ready = database_ready() and data_root().is_dir()
    except ValueError:
        is_ready = False
    if not is_ready:
        raise HTTPException(503, {"code": "NOT_READY", "message": "Database migration or storage directory is unavailable"})
    return {"status": "ready", "database": "migrated", "storage": "available"}


def unavailable(package: str | None = None) -> FeatureCapability:
    if package is None:
        return FeatureCapability(available=False, reason_code="NOT_IMPLEMENTED", reason="Service route not implemented", detected_version=None)
    if util.find_spec(package) is None:
        return FeatureCapability(available=False, reason_code="DEPENDENCY_NOT_INSTALLED", reason="Optional runtime is not installed", detected_version=None)
    try:
        version = metadata.version(package)
    except metadata.PackageNotFoundError:
        version = None
    return FeatureCapability(available=False, reason_code="UNVERIFIED", reason="Installed runtime has not passed a real task", detected_version=version)


def available() -> FeatureCapability:
    return FeatureCapability(available=True, reason_code=None, reason=None, detected_version=None)


@app.get(API + "/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    return {
        "schema_version": 1,
        "features": {
            "auth": available(), "projects": available(), "datasets": available(),
            "training_cpu": unavailable("ultralytics"), "training_cuda": FeatureCapability(available=False, reason_code="NOT_PROBED", reason="CUDA device not verified", detected_version=None),
            "events": available(), "dataset_check": available(), "models": unavailable(), "onnx_export": unavailable("onnx"),
            "pt_inference": unavailable("ultralytics"), "onnx_inference": unavailable("onnxruntime"),
            "deployment": unavailable(), "rknn": FeatureCapability(available=False, reason_code="NOT_PROBED", reason="No RKNN target or board verification", detected_version=None),
        },
    }


def not_implemented():
    raise HTTPException(501, {"code": "NOT_IMPLEMENTED", "message": "This feature has no production implementation yet"})


@contextmanager
def api_transaction():
    if not database_ready():
        raise HTTPException(503, {"code": "NOT_READY", "message": "Database migration is unavailable"})
    with transaction() as connection:
        yield connection


def guard_project(request: Request, project_id: UUID, *, mutation: bool = False, require_active: bool = False) -> None:
    if mutation:
        require_allowed_origin(request)
    with api_transaction() as connection:
        if mutation:
            begin_write(connection)
        actor = require_actor(connection, request, csrf=mutation)
        row = project_for_actor(connection, str(project_id), actor)
        if require_active:
            active_project(row)


def guard_resource(request: Request, table: str, resource_id: UUID, *, mutation: bool = False, require_active: bool = False) -> None:
    if mutation:
        require_allowed_origin(request)
    with api_transaction() as connection:
        if mutation:
            begin_write(connection)
        actor = require_actor(connection, request, csrf=mutation)
        row = project_for_resource(connection, table, str(resource_id), actor)
        if require_active:
            active_project(row)


@app.post(API + "/auth/login", response_model=UserPublic, responses={401: _AUTH_RESPONSES[401], 403: _AUTH_RESPONSES[403]})
def login(body: LoginRequest, request: Request, response: Response):
    settings = require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        row = authenticate_password(connection, body.username, body.password)
        if row is None:
            raise HTTPException(401, {"code": "INVALID_CREDENTIALS", "message": "Username or password is incorrect"})
        tokens = create_session(connection, row["id"], settings)
        result = user_public(row)
    set_session_cookies(response, tokens, settings)
    return result


@app.post(API + "/auth/logout", status_code=204, responses=_AUTH_RESPONSES)
def logout(request: Request, response: Response):
    settings = require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        revoke_session(connection, actor.session_id)
    clear_session_cookies(response, settings)


@app.get(API + "/auth/me", response_model=UserPublic, responses=_AUTH_RESPONSES)
def me(request: Request):
    with api_transaction() as connection:
        return user_public(require_actor(connection, request))


@app.post(API + "/auth/change-password", status_code=204, responses={**_AUTH_RESPONSES, 400: {"model": ApiError}})
def change_password(body: ChangePasswordRequest, request: Request, response: Response):
    settings = require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        row = connection.execute("SELECT password_hash FROM users WHERE id=?", (actor.id,)).fetchone()
        if row is None or not password_matches(row["password_hash"], body.current_password):
            raise HTTPException(400, {"code": "CURRENT_PASSWORD_INVALID", "message": "Current password is incorrect"})
        connection.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(body.new_password), actor.id))
        revoke_user_sessions(connection, actor.id)
        tokens = create_session(connection, actor.id, settings)
    set_session_cookies(response, tokens, settings)


@app.get(API + "/projects", response_model=Page[ProjectPublic], responses=_AUTH_RESPONSES)
def projects(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        where, params = ("", ()) if actor.role == "admin" else (" WHERE owner_id=?", (actor.id,))
        total = connection.execute("SELECT COUNT(*) FROM projects" + where, params).fetchone()[0]
        rows = connection.execute(
            "SELECT id,owner_id,name,description,status,archived_at,created_at,updated_at FROM projects"
            + where + " ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
        return {"items": [project_public(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.post(API + "/projects", response_model=ProjectPublic, status_code=201, responses=_AUTH_RESPONSES)
def create_project(body: ProjectCreate, request: Request):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        now, project_id = timestamp(), str(uuid4())
        connection.execute(
            "INSERT INTO projects (id,owner_id,name,description,task_type,status,created_at,updated_at,archived_at) VALUES (?,?,?,?,?,?,?,?,NULL)",
            (project_id, actor.id, body.name, body.description, "detection", "active", now, now),
        )
        row = connection.execute(
            "SELECT id,owner_id,name,description,status,archived_at,created_at,updated_at FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()
        return project_public(row)


@app.get(API + "/projects/{project_id}", response_model=ProjectPublic, responses=_AUTH_RESPONSES)
def project(project_id: UUID, request: Request):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        return project_public(project_for_actor(connection, str(project_id), actor))


@app.patch(API + "/projects/{project_id}", response_model=ProjectPublic, responses=_AUTH_RESPONSES)
def update_project(project_id: UUID, body: ProjectUpdate, request: Request):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        project_for_actor(connection, str(project_id), actor)
        values = body.model_dump(exclude_none=True)
        assignments = ",".join(f"{field}=?" for field in values)
        connection.execute(f"UPDATE projects SET {assignments},updated_at=? WHERE id=?", (*values.values(), timestamp(), str(project_id)))
        return project_public(project_for_actor(connection, str(project_id), actor))


@app.post(API + "/projects/{project_id}/archive", response_model=ProjectPublic, responses=_AUTH_RESPONSES)
def archive_project(project_id: UUID, request: Request):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        row = project_for_actor(connection, str(project_id), actor)
        if row["status"] != "archived":
            now = timestamp()
            connection.execute("UPDATE projects SET status='archived',archived_at=?,updated_at=? WHERE id=?", (now, now, str(project_id)))
            row = project_for_actor(connection, str(project_id), actor)
        return project_public(row)


@app.get(API + "/projects/{project_id}/datasets", response_model=Page[DatasetPublic], responses={**_AUTH_RESPONSES, **_DATASET_READ_RESPONSES})
def datasets(project_id: UUID, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_actor(connection, str(project_id), actor)
        total = connection.execute("SELECT COUNT(*) FROM datasets WHERE project_id=?", (str(project_id),)).fetchone()[0]
        rows = connection.execute(
            "SELECT datasets.*,(SELECT id FROM artifacts WHERE storage_key=datasets.report_key) AS report_artifact_id FROM datasets WHERE project_id=? ORDER BY created_at DESC,id LIMIT ? OFFSET ?",
            (str(project_id), page_size, (page - 1) * page_size),
        ).fetchall()
        return {"items": [dataset_public(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.post(API + "/projects/{project_id}/datasets", response_model=DatasetPublic, status_code=201, responses={**_AUTH_RESPONSES, **_DATASET_UPLOAD_RESPONSES}, openapi_extra=_UPLOAD_BODY)
async def upload_dataset(project_id: UUID, request: Request):
    # Authenticate before consuming untrusted bytes, but do not hold a SQLite
    # writer transaction for the duration of the upload.
    require_allowed_origin(request)
    with api_transaction() as connection:
        actor = require_actor(connection, request, csrf=True)
        active_project(project_for_actor(connection, str(project_id), actor))
    upload_id = str(uuid4())
    try:
        uploads = safe_directory(data_root(), "uploads")
        staged_path = uploads / f"{upload_id}.part"
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, {"code": "STORAGE_UNAVAILABLE", "message": "Dataset staging storage is unavailable"}) from exc
    dataset_id = str(uuid4())
    published = False
    try:
        try:
            staged = await stage_multipart_zip(request, staged_path)
        except UploadError as exc:
            raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message}) from exc
        except OSError as exc:
            raise HTTPException(503, {"code": "STORAGE_WRITE_FAILED", "message": "Dataset upload could not be written durably"}) from exc
        try:
            inspect_dataset_archive(staged.path)
        except DatasetValidationError as exc:
            details = {"path": exc.issue.path}
            if exc.issue.line is not None:
                details["line"] = str(exc.issue.line)
            raise HTTPException(422, {"code": exc.issue.code, "message": exc.issue.message, "details": details}) from exc
        except OSError as exc:
            raise HTTPException(503, {"code": "STORAGE_READ_FAILED", "message": "Staged dataset could not be read"}) from exc
        name = dataset_name_from_filename(staged.filename)
        try:
            with api_transaction() as connection:
                begin_write(connection)
                actor = require_actor(connection, request, csrf=True)
                active_project(project_for_actor(connection, str(project_id), actor))
                previous = connection.execute(
                    "SELECT id,version FROM datasets WHERE project_id=? AND name=? ORDER BY version DESC LIMIT 1",
                    (str(project_id), name),
                ).fetchone()
                version = 1 if previous is None else previous["version"] + 1
                parent_id = None if previous is None else previous["id"]
                archive_key, snapshot_key = publish_dataset_source(staged.path, dataset_id)
                published = True
                now = timestamp()
                manifest = json.dumps(
                    {"schema_version": 1, "original_filename": staged.filename, "validation": "not_started"},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                connection.execute(
                    """INSERT INTO datasets
                    (id,project_id,parent_id,version,name,archive_key,snapshot_key,sha256,size_bytes,status,report_key,counts_json,classes_json,manifest_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,'pending',NULL,'{}','[]',?,?)""",
                    (dataset_id, str(project_id), parent_id, version, name, archive_key, snapshot_key, staged.sha256, staged.size_bytes, manifest, now),
                )
                row = connection.execute("SELECT datasets.*,(SELECT id FROM artifacts WHERE storage_key=datasets.report_key) AS report_artifact_id FROM datasets WHERE id=?", (dataset_id,)).fetchone()
            return dataset_public(row)
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            if published:
                remove_dataset_storage(dataset_id)
            if isinstance(exc, sqlite3.IntegrityError):
                raise HTTPException(409, {"code": "DATASET_VERSION_CONFLICT", "message": "Dataset version allocation conflicted; retry upload"}) from exc
            raise HTTPException(503, {"code": "DATASET_REGISTRATION_FAILED", "message": "Dataset could not be registered durably"}) from exc
    finally:
        try:
            staged_path.unlink(missing_ok=True)
        except OSError:
            # Preserve the primary response; unregistered .part files remain
            # isolated and are never treated as datasets.
            pass


@app.post(API + "/projects/{project_id}/images", response_model=ArtifactPublic, status_code=201, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES}, openapi_extra=_UPLOAD_BODY)
def upload_image(project_id: UUID, request: Request):
    guard_project(request, project_id, mutation=True, require_active=True)
    not_implemented()


@app.get(API + "/datasets/{dataset_id}", response_model=DatasetPublic, responses={**_AUTH_RESPONSES, **_DATASET_READ_RESPONSES})
def dataset(dataset_id: UUID, request: Request):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "datasets", str(dataset_id), actor)
        row = connection.execute("SELECT datasets.*,(SELECT id FROM artifacts WHERE storage_key=datasets.report_key) AS report_artifact_id FROM datasets WHERE id=?", (str(dataset_id),)).fetchone()
        return dataset_public(row)


@app.post(API + "/datasets/{dataset_id}/check", response_model=JobAccepted, status_code=202, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def check_dataset(dataset_id: UUID, request: Request, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128)):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        project = project_for_resource(connection, "datasets", str(dataset_id), actor)
        return submit_check(connection, actor, project["id"], str(dataset_id), idempotency_key, request.url.path)


@app.get(API + "/datasets/{dataset_id}/samples", response_model=Page[DatasetSamplePublic], responses={**_AUTH_RESPONSES, **_DATASET_READ_RESPONSES})
def dataset_samples(dataset_id: UUID, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "datasets", str(dataset_id), actor)
        row = connection.execute("SELECT status,manifest_json FROM datasets WHERE id=?", (str(dataset_id),)).fetchone()
    if row["status"] != "ready":
        raise HTTPException(409, {"code": "DATASET_NOT_READY", "message": "Only validated ready datasets expose previews"})
    try:
        manifest = json.loads(row["manifest_json"])
        samples = manifest["preview_samples"]
        if manifest.get("schema_version") != 1 or not isinstance(samples, list):
            raise ValueError
    except (TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(409, {"code": "DATASET_PREVIEW_UNAVAILABLE", "message": "Validated preview metadata is unavailable"}) from exc
    start = (page - 1) * page_size
    items = []
    for sample in samples[start:start + page_size]:
        if not isinstance(sample, dict) or "id" not in sample:
            raise HTTPException(409, {"code": "DATASET_PREVIEW_UNAVAILABLE", "message": "Validated preview metadata is unavailable"})
        try:
            parsed = DatasetSamplePublic.model_validate({**sample, "image_url": f"{API}/datasets/{dataset_id}/samples/{sample['id']}/image"})
        except ValidationError as exc:
            raise HTTPException(409, {"code": "DATASET_PREVIEW_UNAVAILABLE", "message": "Validated preview metadata is unavailable"}) from exc
        items.append(parsed.model_dump())
    return {"items": items, "total": len(samples), "page": page, "page_size": page_size}


@app.get(API + "/datasets/{dataset_id}/samples/{sample_id}/image", response_class=FileResponse, responses={**_AUTH_RESPONSES, 409: {"model": ApiError}})
def dataset_sample_image(dataset_id: UUID, sample_id: str, request: Request):
    if len(sample_id) != 24 or any(character not in "0123456789abcdef" for character in sample_id):
        raise HTTPException(404, {"code": "SAMPLE_NOT_FOUND", "message": "Sample was not found"})
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "datasets", str(dataset_id), actor)
        row = connection.execute("SELECT status,snapshot_key,manifest_json FROM datasets WHERE id=?", (str(dataset_id),)).fetchone()
    if row["status"] != "ready":
        raise HTTPException(409, {"code": "DATASET_NOT_READY", "message": "Only validated ready datasets expose previews"})
    try:
        manifest = json.loads(row["manifest_json"])
        sample = next(item for item in manifest["preview_samples"] if isinstance(item, dict) and item.get("id") == sample_id)
        parsed = DatasetSamplePublic.model_validate({**sample, "image_url": f"{API}/datasets/{dataset_id}/samples/{sample_id}/image"})
        relative = parsed.image_path
        image = resolve_storage_file(f"{row['snapshot_key']}/{relative}")
    except (KeyError, StopIteration, TypeError, ValueError, ValidationError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise HTTPException(404, {"code": "SAMPLE_NOT_FOUND", "message": "Sample was not found"}) from exc
    media_type = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(image, media_type=media_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.post(API + "/projects/{project_id}/jobs", response_model=JobAccepted, status_code=202, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def create_job(project_id: UUID, body: JobCreate, request: Request, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128)):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        project = project_for_actor(connection, str(project_id), actor)
        if body.kind != JobKind.DATASET_CHECK:
            active_project(project)
            not_implemented()
        return submit_check(connection, actor, str(project_id), str(body.params.dataset_id), idempotency_key, request.url.path)


@app.get(API + "/projects/{project_id}/jobs", response_model=Page[JobPublic], responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def jobs(project_id: UUID, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_actor(connection, str(project_id), actor)
        total = connection.execute("SELECT COUNT(*) FROM jobs WHERE project_id=?", (str(project_id),)).fetchone()[0]
        rows = connection.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (str(project_id), page_size, (page-1)*page_size)).fetchall()
        return {"items": [job_public(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.get(API + "/jobs/{job_id}", response_model=JobPublic, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def job(job_id: UUID, request: Request):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "jobs", str(job_id), actor)
        return job_public(connection.execute("SELECT * FROM jobs WHERE id=?", (str(job_id),)).fetchone())


@app.post(API + "/jobs/{job_id}/cancel", response_model=JobPublic, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def cancel(job_id: UUID, request: Request):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        project_for_resource(connection, "jobs", str(job_id), actor)
        return cancel_job(connection, str(job_id))


@app.get(API + "/jobs/{job_id}/logs", response_model=Incremental[JobLog], responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def logs(job_id: UUID, request: Request, cursor: str | None = None, limit: int = Query(100, ge=1, le=500)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "jobs", str(job_id), actor)
        return incremental(connection, str(job_id), "log", cursor, limit)


@app.get(API + "/jobs/{job_id}/metrics", response_model=Incremental[Metric], responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def metrics(job_id: UUID, request: Request, cursor: str | None = None, limit: int = Query(100, ge=1, le=500)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "jobs", str(job_id), actor)
        return incremental(connection, str(job_id), "metric", cursor, limit)


@app.get(API + "/projects/{project_id}/artifacts", response_model=Page[ArtifactPublic], responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def artifacts(project_id: UUID, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_actor(connection, str(project_id), actor)
        total = connection.execute("SELECT COUNT(*) FROM artifacts WHERE project_id=?", (str(project_id),)).fetchone()[0]
        rows = connection.execute("SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (str(project_id), page_size, (page-1)*page_size)).fetchall()
        return {"items": [artifact_public(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.get(API + "/artifacts/{artifact_id}", response_model=ArtifactPublic, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def artifact(artifact_id: UUID, request: Request):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "artifacts", str(artifact_id), actor)
        return artifact_public(connection.execute("SELECT * FROM artifacts WHERE id=?", (str(artifact_id),)).fetchone())


@app.get(API + "/artifacts/{artifact_id}/download", response_class=Response, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, 200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
def download_artifact(artifact_id: UUID, request: Request):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        project_for_resource(connection, "artifacts", str(artifact_id), actor)
        row = connection.execute("SELECT * FROM artifacts WHERE id=?", (str(artifact_id),)).fetchone()
    if row["kind"] != "dataset_report":
        not_implemented()
    if row["validation_status"] != "passed":
        raise HTTPException(409, {"code": "ARTIFACT_UNAVAILABLE", "message": "Report integrity has not been verified"})
    try:
        path = resolve_storage_file(row["storage_key"])
        # Reports have a bounded schema. Return verified bytes, avoiding a reopen race.
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("report exceeds its bound")
        with path.open("rb") as source:
            content = source.read(16 * 1024 * 1024 + 1)
        if len(content) > 16 * 1024 * 1024:
            raise ValueError("report exceeds its bound")
        if len(content) != row["size_bytes"] or sha256(content).hexdigest() != row["sha256"]:
            raise ValueError("report fingerprint mismatch")
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(409, {"code": "ARTIFACT_UNAVAILABLE", "message": "Report is missing or its fingerprint changed"}) from exc
    return Response(content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="dataset-report-{artifact_id}.json"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.get(API + "/inferences/{inference_id}", response_model=InferenceResult, responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def inference_result(inference_id: UUID, request: Request):
    guard_resource(request, "artifacts", inference_id)
    not_implemented()


@app.get(API + "/admin/users", response_model=Page[UserPublic], responses=_AUTH_RESPONSES)
def admin_users(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        require_admin(actor)
        total = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        rows = connection.execute("SELECT id,username,role,is_active,created_at FROM users ORDER BY created_at,id LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)).fetchall()
        return {"items": [user_public(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.post(API + "/admin/users", response_model=UserPublic, status_code=201, responses={**_AUTH_RESPONSES, 409: {"model": ApiError}})
def admin_create_user(body: UserCreate, request: Request):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        require_admin(actor)
        user_id, now = str(uuid4()), timestamp()
        try:
            connection.execute("INSERT INTO users (id,username,password_hash,role,is_active,created_at) VALUES (?,?,?,?,1,?)", (user_id, body.username, password_hash(body.password), body.role, now))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, {"code": "USERNAME_EXISTS", "message": "Username already exists"}) from exc
        row = connection.execute("SELECT id,username,role,is_active,created_at FROM users WHERE id=?", (user_id,)).fetchone()
        return user_public(row)


@app.patch(API + "/admin/users/{user_id}", response_model=UserPublic, responses={**_AUTH_RESPONSES, 404: {"model": ApiError}, 409: {"model": ApiError}})
def admin_update_user(user_id: UUID, body: UserUpdate, request: Request):
    require_allowed_origin(request)
    with api_transaction() as connection:
        begin_write(connection)
        actor = require_actor(connection, request, csrf=True)
        require_admin(actor)
        row = connection.execute("SELECT id,username,role,is_active,created_at FROM users WHERE id=?", (str(user_id),)).fetchone()
        if row is None:
            raise HTTPException(404, {"code": "USER_NOT_FOUND", "message": "User was not found"})
        if row["role"] == "admin" and row["is_active"] and not body.is_active:
            active_admins = connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
            if active_admins <= 1:
                raise HTTPException(409, {"code": "LAST_ADMIN", "message": "The last active administrator cannot be disabled"})
        connection.execute("UPDATE users SET is_active=? WHERE id=?", (body.is_active, str(user_id)))
        if not body.is_active:
            revoke_user_sessions(connection, str(user_id))
        row = connection.execute("SELECT id,username,role,is_active,created_at FROM users WHERE id=?", (str(user_id),)).fetchone()
        return user_public(row)


@app.get(API + "/admin/projects", response_model=Page[ProjectPublic], responses=_AUTH_RESPONSES)
def admin_projects(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        require_admin(actor)
        total = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        rows = connection.execute("SELECT id,owner_id,name,description,status,archived_at,created_at,updated_at FROM projects ORDER BY updated_at DESC,id LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)).fetchall()
        return {"items": [project_public(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.get(API + "/admin/jobs", response_model=Page[JobPublic], responses={**_AUTH_RESPONSES, **_ERROR_RESPONSE, **_JOB_RESPONSES})
def admin_jobs(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    with api_transaction() as connection:
        actor = require_actor(connection, request)
        require_admin(actor)
    not_implemented()
