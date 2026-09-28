"""Pydantic V1 HTTP contract. Stubs expose typed OpenAPI without executing business work."""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from .contracts import DatasetState, JobKind, JobState, ValidationState


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiErrorDetail(StrictModel):
    code: str
    message: str
    request_id: UUID
    details: dict[str, str] | None = None


class ApiError(StrictModel):
    error: ApiErrorDetail


class LiveResponse(StrictModel):
    status: Literal["ok"]
    service: Literal["api"]


class ReadyResponse(StrictModel):
    status: Literal["ready"]
    database: Literal["migrated"]
    storage: Literal["available"]


class FeatureCapability(StrictModel):
    available: bool
    reason_code: str | None
    reason: str | None
    detected_version: str | None


class CapabilitiesResponse(StrictModel):
    schema_version: Literal[1]
    features: dict[str, FeatureCapability]


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class UserPublic(StrictModel):
    id: UUID
    username: str
    role: Literal["user", "admin"]
    is_active: bool
    created_at: AwareDatetime


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UserCreate(StrictModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["user", "admin"] = "user"


class UserUpdate(StrictModel):
    is_active: bool


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def nonempty(self):
        if self.name is None and self.description is None:
            raise ValueError("project update requires at least one non-null field")
        return self


class ProjectPublic(StrictModel):
    id: UUID
    owner_id: UUID
    name: str
    description: str
    archived_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DatasetPublic(StrictModel):
    id: UUID
    project_id: UUID
    name: str
    state: DatasetState
    version: int
    sha256: str
    size_bytes: int
    classes: list[str]
    counts: dict[str, int] | None
    created_at: AwareDatetime


class DatasetCheckRequest(StrictModel):
    dataset_id: UUID


class TrainParams(StrictModel):
    dataset_id: UUID
    experiment_name: str = Field(min_length=1, max_length=160)
    base_model: Literal["yolo11n.pt"] = "yolo11n.pt"
    epochs: int = Field(ge=1, le=100)
    batch: int = Field(ge=1, le=16)
    imgsz: Literal[320, 640] = 640
    device: Literal["cpu", "cuda:0"] = "cpu"
    seed: int = Field(ge=0, le=4294967295)
    learning_rate: FiniteFloat | None = Field(default=None, ge=0.000001, le=0.1)


class ExportOnnxParams(StrictModel):
    model_artifact_id: UUID
    imgsz: Literal[640] = 640
    batch: Literal[1] = 1
    precision: Literal["fp32"] = "fp32"


class InferenceParams(StrictModel):
    model_artifact_id: UUID
    image_artifact_id: UUID
    backend: Literal["pt", "onnx"]
    confidence: FiniteFloat = Field(ge=0, le=1, default=0.25)
    iou: FiniteFloat = Field(ge=0, le=1, default=0.45)


class PackageParams(StrictModel):
    onnx_artifact_id: UUID


class DatasetCheckJobCreate(StrictModel):
    kind: Literal[JobKind.DATASET_CHECK]
    params: DatasetCheckRequest


class TrainJobCreate(StrictModel):
    kind: Literal[JobKind.TRAIN]
    params: TrainParams


class ExportJobCreate(StrictModel):
    kind: Literal[JobKind.EXPORT_ONNX]
    params: ExportOnnxParams


class InferenceJobCreate(StrictModel):
    kind: Literal[JobKind.INFER]
    params: InferenceParams


class PackageJobCreate(StrictModel):
    kind: Literal[JobKind.PACKAGE]
    params: PackageParams


JobCreate = Annotated[
    DatasetCheckJobCreate | TrainJobCreate | ExportJobCreate | InferenceJobCreate | PackageJobCreate,
    Field(discriminator="kind"),
]


class JobAccepted(StrictModel):
    job_id: UUID
    state: Literal[JobState.QUEUED]


class JobPublic(StrictModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    kind: JobKind
    state: JobState
    params_schema_version: int
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    error_code: str | None
    source_job_id: UUID | None


class JobLog(StrictModel):
    seq: int = Field(ge=1)
    at: AwareDatetime
    level: Literal["info", "warning", "error"]
    text: str = Field(max_length=8192)


class Metric(StrictModel):
    seq: int = Field(ge=1)
    epoch: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=128)
    value: FiniteFloat
    at: AwareDatetime


T = TypeVar("T")


class Page(StrictModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class Incremental(StrictModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
    eof: bool
    job_state: JobState


class ModelInput(StrictModel):
    shape: tuple[int, int, int, int]
    color: Literal["RGB", "BGR"]
    layout: Literal["NCHW"]
    normalization: Literal["0..1"]
    letterbox: bool


class ModelOutput(StrictModel):
    schema_name: str | None = Field(alias="schema")
    nms_in_graph: bool | None


class ModelValidation(StrictModel):
    runtime: str | None
    result: ValidationState
    evidence_key: str | None


class ModelTarget(StrictModel):
    format: Literal["pt", "onnx", "rknn"]
    chip: str | None
    quantization: str | None


class ModelMetadata(StrictModel):
    schema_version: Literal[1]
    family: Literal["YOLO"]
    task: Literal["detection"]
    source: Literal["trained_best", "trained_last", "exported_onnx"]
    dataset_id: UUID
    source_job_id: UUID
    parent_artifact_id: UUID | None
    framework: str
    framework_version: str
    architecture: Literal["yolo11n"]
    input: ModelInput
    classes: list[str]
    output: ModelOutput
    training: dict[str, object]
    validation: ModelValidation
    target: ModelTarget


class ArtifactPublic(StrictModel):
    id: UUID
    project_id: UUID
    job_id: UUID | None
    kind: Literal["dataset_report", "pt_best", "pt_last", "onnx", "inference_input", "inference_result", "deployment_zip"]
    format: str
    sha256: str
    size_bytes: int
    metadata_schema_version: int
    validation_state: ValidationState
    metadata: ModelMetadata | dict[str, object]
    created_at: AwareDatetime


class Detection(StrictModel):
    class_id: int = Field(ge=0)
    score: FiniteFloat = Field(ge=0, le=1)
    xyxy: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]


class InferenceResult(StrictModel):
    artifact_id: UUID
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    backend: Literal["pt", "onnx"]
    provider: str
    detections: list[Detection]
