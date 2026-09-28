"""Lightweight HTTP shell; planned business routes fail explicitly."""

from importlib import metadata, util
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import data_root
from .database import database_ready
from .schemas import (
    ApiError, ArtifactPublic, CapabilitiesResponse, ChangePasswordRequest,
    DatasetPublic, FeatureCapability, Incremental, JobAccepted, JobCreate,
    InferenceResult, JobLog, JobPublic, LiveResponse, LoginRequest, Metric, Page, ProjectCreate,
    ProjectPublic, ProjectUpdate, ReadyResponse, UserCreate, UserPublic, UserUpdate,
)

app = FastAPI(title="EdgeVision API", version="0.1.0")
API = "/api/v1"
_ERROR_RESPONSE = {501: {"model": ApiError, "description": "Not implemented in the production shell"}}
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
    return JSONResponse(status_code=exc.status_code, content=error_body(request, detail.get("code", "HTTP_ERROR"), detail.get("message", "Request failed")))


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


@app.get(API + "/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    return {
        "schema_version": 1,
        "features": {
            "auth": unavailable(), "projects": unavailable(), "datasets": unavailable(),
            "training_cpu": unavailable("ultralytics"), "training_cuda": FeatureCapability(available=False, reason_code="NOT_PROBED", reason="CUDA device not verified", detected_version=None),
            "events": unavailable(), "models": unavailable(), "onnx_export": unavailable("onnx"),
            "pt_inference": unavailable("ultralytics"), "onnx_inference": unavailable("onnxruntime"),
            "deployment": unavailable(), "rknn": FeatureCapability(available=False, reason_code="NOT_PROBED", reason="No RKNN target or board verification", detected_version=None),
        },
    }


def not_implemented():
    raise HTTPException(501, {"code": "NOT_IMPLEMENTED", "message": "This feature has no production implementation yet"})


@app.post(API + "/auth/login", response_model=UserPublic, responses=_ERROR_RESPONSE)
def login(body: LoginRequest):
    not_implemented()


@app.post(API + "/auth/logout", status_code=204, responses=_ERROR_RESPONSE)
def logout():
    not_implemented()


@app.get(API + "/auth/me", response_model=UserPublic, responses=_ERROR_RESPONSE)
def me():
    not_implemented()


@app.post(API + "/auth/change-password", status_code=204, responses=_ERROR_RESPONSE)
def change_password(body: ChangePasswordRequest):
    not_implemented()


@app.get(API + "/projects", response_model=Page[ProjectPublic], responses=_ERROR_RESPONSE)
def projects(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.post(API + "/projects", response_model=ProjectPublic, status_code=201, responses=_ERROR_RESPONSE)
def create_project(body: ProjectCreate):
    not_implemented()


@app.get(API + "/projects/{project_id}", response_model=ProjectPublic, responses=_ERROR_RESPONSE)
def project(project_id: UUID):
    not_implemented()


@app.patch(API + "/projects/{project_id}", response_model=ProjectPublic, responses=_ERROR_RESPONSE)
def update_project(project_id: UUID, body: ProjectUpdate):
    not_implemented()


@app.post(API + "/projects/{project_id}/archive", response_model=ProjectPublic, responses=_ERROR_RESPONSE)
def archive_project(project_id: UUID):
    not_implemented()


@app.get(API + "/projects/{project_id}/datasets", response_model=Page[DatasetPublic], responses=_ERROR_RESPONSE)
def datasets(project_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.post(API + "/projects/{project_id}/datasets", response_model=DatasetPublic, status_code=201, responses=_ERROR_RESPONSE, openapi_extra=_UPLOAD_BODY)
def upload_dataset(project_id: UUID):
    # T030 adds a streaming multipart parser; no unbounded UploadFile is loaded here.
    not_implemented()


@app.post(API + "/projects/{project_id}/images", response_model=ArtifactPublic, status_code=201, responses=_ERROR_RESPONSE, openapi_extra=_UPLOAD_BODY)
def upload_image(project_id: UUID):
    # Bounded single-image upload belongs to T060, not the shell.
    not_implemented()


@app.get(API + "/datasets/{dataset_id}", response_model=DatasetPublic, responses=_ERROR_RESPONSE)
def dataset(dataset_id: UUID):
    not_implemented()


@app.post(API + "/datasets/{dataset_id}/check", response_model=JobAccepted, status_code=202, responses=_ERROR_RESPONSE)
def check_dataset(dataset_id: UUID, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128)):
    not_implemented()


@app.get(API + "/datasets/{dataset_id}/samples", response_model=Page[ArtifactPublic], responses=_ERROR_RESPONSE)
def dataset_samples(dataset_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.post(API + "/projects/{project_id}/jobs", response_model=JobAccepted, status_code=202, responses=_ERROR_RESPONSE)
def create_job(project_id: UUID, body: JobCreate, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128)):
    not_implemented()


@app.get(API + "/projects/{project_id}/jobs", response_model=Page[JobPublic], responses=_ERROR_RESPONSE)
def jobs(project_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.get(API + "/jobs/{job_id}", response_model=JobPublic, responses=_ERROR_RESPONSE)
def job(job_id: UUID):
    not_implemented()


@app.post(API + "/jobs/{job_id}/cancel", response_model=JobPublic, responses=_ERROR_RESPONSE)
def cancel(job_id: UUID):
    not_implemented()


@app.get(API + "/jobs/{job_id}/logs", response_model=Incremental[JobLog], responses=_ERROR_RESPONSE)
def logs(job_id: UUID, cursor: str | None = None, limit: int = Query(100, ge=1, le=500)):
    not_implemented()


@app.get(API + "/jobs/{job_id}/metrics", response_model=Incremental[Metric], responses=_ERROR_RESPONSE)
def metrics(job_id: UUID, cursor: str | None = None, limit: int = Query(100, ge=1, le=500)):
    not_implemented()


@app.get(API + "/projects/{project_id}/artifacts", response_model=Page[ArtifactPublic], responses=_ERROR_RESPONSE)
def artifacts(project_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.get(API + "/artifacts/{artifact_id}", response_model=ArtifactPublic, responses=_ERROR_RESPONSE)
def artifact(artifact_id: UUID):
    not_implemented()


@app.get(API + "/artifacts/{artifact_id}/download", response_class=Response, responses={**_ERROR_RESPONSE, 200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
def download_artifact(artifact_id: UUID):
    not_implemented()


@app.get(API + "/inferences/{inference_id}", response_model=InferenceResult, responses=_ERROR_RESPONSE)
def inference_result(inference_id: UUID):
    not_implemented()


@app.get(API + "/admin/users", response_model=Page[UserPublic], responses=_ERROR_RESPONSE)
def admin_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.post(API + "/admin/users", response_model=UserPublic, status_code=201, responses=_ERROR_RESPONSE)
def admin_create_user(body: UserCreate):
    not_implemented()


@app.patch(API + "/admin/users/{user_id}", response_model=UserPublic, responses=_ERROR_RESPONSE)
def admin_update_user(user_id: UUID, body: UserUpdate):
    not_implemented()


@app.get(API + "/admin/projects", response_model=Page[ProjectPublic], responses=_ERROR_RESPONSE)
def admin_projects(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()


@app.get(API + "/admin/jobs", response_model=Page[JobPublic], responses=_ERROR_RESPONSE)
def admin_jobs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    not_implemented()
