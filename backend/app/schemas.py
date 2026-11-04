"""Pydantic V1 HTTP contract. Stubs expose typed OpenAPI without executing business work."""

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, RootModel, model_validator

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
    version: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    classes: list[str]
    counts: dict[str, int] | None
    validation_job_id: UUID | None = None
    report_artifact_id: UUID | None = None
    created_at: AwareDatetime


class DatasetAnnotationPublic(StrictModel):
    class_id: int = Field(ge=0)
    class_name: str = Field(min_length=1, max_length=128)
    xywh: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]


class DatasetSamplePublic(StrictModel):
    id: str = Field(min_length=24, max_length=24, pattern=r"^[0-9a-f]{24}$")
    split: Literal["train", "val", "test"]
    image_path: str = Field(min_length=1, max_length=1024)
    label_path: str = Field(min_length=1, max_length=1024)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    annotations: list[DatasetAnnotationPublic]
    annotations_truncated: bool
    image_url: str = Field(min_length=1, max_length=2048)


class DatasetCheckRequest(StrictModel):
    dataset_id: UUID


class TrainParams(StrictModel):
    dataset_id: UUID
    experiment_name: str = Field(min_length=1, max_length=160)
    base_model: Literal["yolo11n.pt"] = "yolo11n.pt"
    epochs: int = Field(strict=True, ge=1, le=100)
    batch: int = Field(strict=True, ge=1, le=16)
    imgsz: Literal[320, 640] = 640
    device: Literal["cpu", "cuda:0"] = "cpu"
    seed: int = Field(strict=True, ge=0, le=4294967295)
    learning_rate: FiniteFloat | None = Field(strict=True, default=None, ge=0.000001, le=0.1)


class ExportOnnxParams(StrictModel):
    model_artifact_id: UUID
    imgsz: Literal[640] = 640
    batch: Literal[1] = 1
    precision: Literal["fp32"] = "fp32"

    @model_validator(mode="before")
    @classmethod
    def fixed_integer_parameters(cls, value):
        if isinstance(value, dict) and any(key in value and type(value[key]) is not int for key in ("imgsz", "batch")):
            raise ValueError("fixed export dimensions require integers")
        return value


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
    source_job_id: UUID | None = None


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
    state: JobState


class TrainingProvenance(StrictModel):
    schema_version: Literal[1]
    dataset_id: UUID
    dataset_version: int = Field(ge=1)
    archive_sha256: str
    snapshot_sha256: str
    report_artifact_id: UUID
    report_sha256: str
    classes: list[str]
    counts: dict[str, int]
    params: TrainParams
    base_manifest_sha256: str
    base_model_sha256: str
    runtime_binding: str
    code_version: str


class ExportJobSource(StrictModel):
    source_artifact_id: UUID
    source_job_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    params: ExportOnnxParams
    runtime_binding: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_version: str = Field(pattern=r"^[0-9a-f]{64}$")


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
    training: TrainingProvenance | None = None
    export: ExportJobSource | None = None


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


class EffectiveTrainingParams(StrictModel):
    optimizer: Literal["SGD"]
    lr0: FiniteFloat
    lrf: FiniteFloat
    warmup_epochs: FiniteFloat
    warmup_bias_lr: FiniteFloat
    warmup_momentum: FiniteFloat
    momentum: FiniteFloat
    weight_decay: FiniteFloat
    nbs: int
    seed: int
    batch: int
    epochs: int
    imgsz: int
    device: Literal["cpu"]
    workers: Literal[0]
    amp: Literal[False]
    plots: Literal[False]
    cache: Literal[False]
    deterministic: Literal[True]


class TrainingVersions(StrictModel):
    torch: Literal["2.15.0+cpu"]
    torchvision: Literal["0.29.2+cpu"]
    ultralytics: Literal["8.4.202"]


class TrainingRuntime(StrictModel):
    effective: EffectiveTrainingParams
    versions: TrainingVersions
    optimizer_steps: int = Field(ge=1)
    completed_epochs: int = Field(ge=1, le=100)
    safe_load_count: int = Field(ge=2)
    threads: Literal[2]
    device: Literal["cpu"]


class TrainingArtifactMetadata(StrictModel):
    schema_version: Literal[1]
    task: Literal["detection"]
    architecture: Literal["yolo11n"]
    classes: list[str]
    provenance: TrainingProvenance
    runtime: TrainingRuntime
    validation_scope: Literal["weights_only_detection_checkpoint"]


SHA256 = r"^[0-9a-f]{64}$"


class StrictExportModel(StrictModel):
    @model_validator(mode="before")
    @classmethod
    def fixed_scalar_types(cls, value):
        if isinstance(value, dict):
            for name in ("schema_version", "threads", "opset", "ir_version"):
                if name in value and type(value[name]) is not int:
                    raise ValueError("export protocol integer required")
            for name in ("dynamic", "simplify", "nms", "passed", "checker_passed"):
                if name in value and type(value[name]) is not bool:
                    raise ValueError("export protocol boolean required")
            for name in ("input_shape", "output_shape"):
                if name in value and (not isinstance(value[name], (list, tuple)) or any(type(item) is not int for item in value[name])):
                    raise ValueError("export shape integers required")
        return value


class ExportVersions(TrainingVersions):
    onnx: Literal["1.23.2"]
    onnxruntime: Literal["1.31.1"]


class ExportRuntime(StrictExportModel):
    versions: ExportVersions
    provider: Literal["CPUExecutionProvider"]
    device: Literal["cpu"]
    threads: Literal[2]
    opset: Literal[18]
    ir_version: Literal[8]
    precision: Literal["fp32"]
    dynamic: Literal[False]
    simplify: Literal[False]
    nms: Literal[False]


class TensorComparison(StrictExportModel):
    name: Literal["zeros", "gradient", "pattern"]
    input_sha256: str = Field(pattern=SHA256)
    pt_sha256: str = Field(pattern=SHA256)
    ort_sha256: str = Field(pattern=SHA256)
    max_absolute_error: FiniteFloat = Field(strict=True, ge=0)
    max_tolerance_ratio: FiniteFloat = Field(strict=True, ge=0, le=1)
    elements: int = Field(strict=True, gt=0)
    passed: Literal[True]


class ExportValidation(StrictExportModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    input_sha256: str = Field(pattern=SHA256)
    source_sha256: str = Field(pattern=SHA256)
    original_graph_sha256: str = Field(pattern=SHA256)
    model_sha256: str = Field(pattern=SHA256)
    model_size_bytes: int = Field(strict=True, gt=0, le=128 * 1024**2)
    classes: list[str] = Field(min_length=1, max_length=1000)
    input_name: Literal["images"]
    input_shape: tuple[Literal[1], Literal[3], Literal[640], Literal[640]]
    output_name: Literal["output0"]
    output_shape: tuple[Literal[1], int, Literal[8400]]
    dtype: Literal["float32"]
    tensor_protocol: Literal["rgb-fixed-v1"]
    atol: Literal[0.0001]
    rtol: Literal[0.0001]
    checker_passed: Literal[True]
    runtime: ExportRuntime
    samples: list[TensorComparison] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def consistent(self):
        if self.model_sha256 != self.original_graph_sha256:
            raise ValueError("the original graph must be published unchanged")
        if self.output_shape != (1, 4 + len(self.classes), 8400):
            raise ValueError("output does not match bound class count")
        if [sample.name for sample in self.samples] != ["zeros", "gradient", "pattern"]:
            raise ValueError("all fixed tensors must be compared in order")
        if any(sample.elements != (4 + len(self.classes)) * 8400 for sample in self.samples):
            raise ValueError("incomplete tensor comparison")
        return self


class ExportProvenance(StrictExportModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    input_sha256: str = Field(pattern=SHA256)
    parent_artifact_id: UUID
    source_job_id: UUID
    source_sha256: str = Field(pattern=SHA256)
    source_size_bytes: int = Field(strict=True, gt=0, le=128 * 1024**2)
    source_metadata_sha256: str = Field(pattern=SHA256)
    source_training_input_sha256: str = Field(pattern=SHA256)
    training: TrainingProvenance
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)


class OnnxArtifactMetadata(StrictExportModel):
    schema_version: Literal[1]
    task: Literal["detection"]
    architecture: Literal["yolo11n"]
    classes: list[str] = Field(min_length=1, max_length=1000)
    provenance: ExportProvenance
    validation: ExportValidation
    validation_sha256: str = Field(pattern=SHA256)
    validation_scope: Literal["checker_ort_raw_tensor_equivalence"]

    @model_validator(mode="after")
    def consistent(self):
        proof, origin = self.validation, self.provenance
        if self.classes != proof.classes or self.classes != origin.training.classes:
            raise ValueError("class binding mismatch")
        if (proof.job_id, proof.run_id, proof.input_sha256, proof.source_sha256) != (origin.job_id, origin.run_id, origin.input_sha256, origin.source_sha256):
            raise ValueError("validation provenance mismatch")
        return self


class ArtifactBase(StrictModel):
    id: UUID
    project_id: UUID
    job_id: UUID | None
    format: str
    sha256: str = Field(pattern=SHA256)
    size_bytes: int = Field(ge=0)
    metadata_schema_version: int
    validation_state: ValidationState
    created_at: AwareDatetime


class TrainingArtifactPublic(ArtifactBase):
    kind: Literal["pt_best", "pt_last"]
    format: Literal["pt"]
    metadata: TrainingArtifactMetadata


class OnnxArtifactPublic(ArtifactBase):
    kind: Literal["onnx"]
    format: Literal["onnx"]
    metadata_schema_version: Literal[1]
    validation_state: Literal[ValidationState.PASSED]
    metadata: OnnxArtifactMetadata

    @model_validator(mode="after")
    def consistent(self):
        proof = self.metadata.validation
        if self.job_id != proof.job_id or self.sha256 != proof.model_sha256 or self.size_bytes != proof.model_size_bytes:
            raise ValueError("artifact does not match validation")
        return self


class OtherArtifactPublic(ArtifactBase):
    kind: Literal["dataset_report", "inference_input", "inference_result", "deployment_zip"]
    metadata: dict[str, object]


class ArtifactPublic(RootModel[Annotated[TrainingArtifactPublic | OnnxArtifactPublic | OtherArtifactPublic, Field(discriminator="kind")]]):
    """Kind-discriminated public schema: malformed ONNX never falls back to dict."""


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
