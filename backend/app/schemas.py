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
    confidence: FiniteFloat = Field(strict=True, ge=0, le=1, default=0.25)
    iou: FiniteFloat = Field(strict=True, ge=0, le=1, default=0.45)


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
    source_job_id: UUID | None = None


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


class InferenceJobSource(StrictModel):
    model_artifact_id: UUID
    model_job_id: UUID
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_artifact_id: UUID
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    params: InferenceParams
    protocol: Literal["detection-image-v1"]
    runtime_binding: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_version: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode='after')
    def consistent(self):
        if (self.model_artifact_id, self.image_artifact_id) != (self.params.model_artifact_id, self.params.image_artifact_id):
            raise ValueError('inference source summary resources mismatch')
        return self


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
    inference: InferenceJobSource | None = None


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


# Image protocol fields deliberately do not inherit permissive generic metadata.
StrictFinite = Annotated[FiniteFloat, Field(strict=True)]
StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
ImageDimension = Annotated[int, Field(strict=True, gt=0, le=30_000_000)]


class StrictInferenceModel(StrictModel):
    @model_validator(mode='before')
    @classmethod
    def literal_scalar_types(cls, value):
        from typing import get_args, get_origin
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                choices = get_args(field.annotation)
                if name in value and get_origin(field.annotation) is Literal and choices:
                    if type(choices[0]) in (int, bool) and type(value[name]) is not type(choices[0]):
                        raise ValueError('image protocol literal scalar type required')
        return value


class InferenceInputMetadata(StrictInferenceModel):
    schema_version: Literal[1]
    declared_format: Literal['jpeg', 'png']
    validation_scope: Literal['bounded_upload_bytes']


class InferenceInputArtifactPublic(ArtifactBase, StrictInferenceModel):
    kind: Literal['inference_input']
    format: Literal['jpeg', 'png']
    job_id: None
    size_bytes: int = Field(strict=True, gt=0, le=50 * 1024**2)
    metadata_schema_version: Literal[1]
    validation_state: Literal[ValidationState.UNVERIFIED]
    metadata: InferenceInputMetadata

    @model_validator(mode='after')
    def consistent(self):
        if self.format != self.metadata.declared_format:
            raise ValueError('image declared format mismatch')
        return self


class DecodedImageRecord(StrictInferenceModel):
    encoded_width: ImageDimension
    encoded_height: ImageDimension
    image_width: ImageDimension
    image_height: ImageDimension
    orientation: int = Field(strict=True, ge=1, le=8)
    format: Literal['jpeg', 'png']
    rgb_sha256: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        dims = (self.encoded_width, self.encoded_height)
        if self.encoded_width * self.encoded_height > 30_000_000 or (self.image_width, self.image_height) != (dims[::-1] if self.orientation >= 5 else dims):
            raise ValueError('decoded image geometry mismatch')
        return self


class PreprocessRecord(StrictInferenceModel):
    image_width: ImageDimension
    image_height: ImageDimension
    resized_width: int = Field(strict=True, ge=1, le=640)
    resized_height: int = Field(strict=True, ge=1, le=640)
    left: int = Field(strict=True, ge=0, le=639)
    right: int = Field(strict=True, ge=0, le=639)
    top: int = Field(strict=True, ge=0, le=639)
    bottom: int = Field(strict=True, ge=0, le=639)
    scale_x: StrictFinite = Field(gt=0)
    scale_y: StrictFinite = Field(gt=0)
    target_width: Literal[640]
    target_height: Literal[640]
    padding: Literal[114]
    resampling: Literal['pillow_bilinear']
    layout: Literal['NCHW']
    dtype: Literal['float32']
    color: Literal['RGB']
    normalization: Literal['divide_255']
    tensor_sha256: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        from .delivery_infer import letterbox_record
        expected = letterbox_record(self.image_width, self.image_height)
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError('integer letterbox protocol mismatch')
        return self


class PreviewRecord(StrictInferenceModel):
    width: int = Field(strict=True, ge=1, le=1280)
    height: int = Field(strict=True, ge=1, le=1280)
    size_bytes: int = Field(strict=True, gt=0, le=8 * 1024**2)
    sha256: str = Field(pattern=SHA256)
    format: Literal['png']


class InferenceVersions(StrictInferenceModel):
    pillow: Literal['12.3.0']
    numpy: Literal['2.5.4']
    torch: Literal['2.15.0+cpu'] | None
    torchvision: Literal['0.29.2+cpu'] | None
    ultralytics: Literal['8.4.202'] | None
    onnx: Literal['1.23.2'] | None
    onnxruntime: Literal['1.31.1'] | None


class InferenceRuntime(StrictInferenceModel):
    backend: Literal['pt', 'onnx']
    provider: Literal['pytorch_cpu', 'CPUExecutionProvider']
    device: Literal['cpu']
    threads: Literal[2]
    interop_threads: Literal[1]
    warmup_runs: Literal[0]
    versions: InferenceVersions
    raw_sha256: str = Field(pattern=SHA256)
    raw_elements: int = Field(strict=True, ge=5 * 8400, le=1004 * 8400)

    @model_validator(mode='after')
    def consistent(self):
        versions = self.versions
        pt = (versions.torch, versions.torchvision, versions.ultralytics)
        ort = (versions.onnx, versions.onnxruntime)
        if self.backend == 'pt':
            valid = self.provider == 'pytorch_cpu' and all(x is not None for x in pt) and all(x is None for x in ort)
        else:
            valid = self.provider == 'CPUExecutionProvider' and all(x is None for x in pt) and all(x is not None for x in ort)
        if not valid: raise ValueError('actual runtime and backend mismatch')
        return self


class InferenceProvenance(StrictInferenceModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    project_id: UUID
    frozen_input_sha256: str = Field(pattern=SHA256)
    model_artifact_id: UUID
    model_job_id: UUID
    model_sha256: str = Field(pattern=SHA256)
    model_size_bytes: int = Field(strict=True, gt=0, le=128 * 1024**2)
    model_metadata_sha256: str = Field(pattern=SHA256)
    image_artifact_id: UUID
    image_sha256: str = Field(pattern=SHA256)
    image_size_bytes: int = Field(strict=True, gt=0, le=50 * 1024**2)
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)


class PostprocessCounts(StrictInferenceModel):
    candidates: int = Field(strict=True, ge=0, le=8400)
    candidate_truncated: int = Field(strict=True, ge=0, le=5400)
    nms_kept: int = Field(strict=True, ge=0, le=3000)
    result_truncated: int = Field(strict=True, ge=0, le=2700)
    clip_removed: int = Field(strict=True, ge=0, le=300)

    @model_validator(mode='after')
    def consistent(self):
        if self.candidate_truncated != max(0, self.candidates-3000) or self.nms_kept > min(3000, self.candidates) or self.result_truncated != max(0, self.nms_kept-300) or self.clip_removed > min(300, self.nms_kept):
            raise ValueError('postprocess counts mismatch')
        return self


class InferenceTimings(StrictInferenceModel):
    unit: Literal['ms']
    decode: StrictFinite = Field(ge=0)
    preprocess: StrictFinite = Field(ge=0)
    load: StrictFinite = Field(ge=0)
    infer: StrictFinite = Field(ge=0)
    postprocess: StrictFinite = Field(ge=0)
    total: StrictFinite = Field(ge=0)

    @model_validator(mode='after')
    def consistent(self):
        if self.total + 1e-6 < sum((self.decode, self.preprocess, self.load, self.infer, self.postprocess)):
            raise ValueError('timing phases exceed total')
        return self


class Detection(StrictInferenceModel):
    class_id: int = Field(strict=True, ge=0, le=999)
    score: StrictFinite = Field(ge=0, le=1)
    xyxy: tuple[StrictFinite, StrictFinite, StrictFinite, StrictFinite]


class InferenceOutputFields(StrictInferenceModel):
    image_width: ImageDimension
    image_height: ImageDimension
    backend: Literal['pt', 'onnx']
    provider: Literal['pytorch_cpu', 'CPUExecutionProvider']
    classes: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(min_length=1, max_length=1000)
    image: DecodedImageRecord
    preprocess: PreprocessRecord
    runtime: InferenceRuntime
    preview: PreviewRecord
    counts: PostprocessCounts
    timings: InferenceTimings
    detections: list[Detection] = Field(max_length=300)

    @model_validator(mode='after')
    def consistent(self):
        import math
        if (self.backend, self.provider) != (self.runtime.backend, self.runtime.provider):
            raise ValueError('inference actual backend mismatch')
        if (self.image_width, self.image_height) != (self.image.image_width, self.image.image_height) or (self.image_width, self.image_height) != (self.preprocess.image_width, self.preprocess.image_height):
            raise ValueError('inference dimensions mismatch')
        scale = min(1., 1280 / max(self.image_width, self.image_height))
        if (self.preview.width, self.preview.height) != tuple(max(1, math.floor(v*scale+.5)) for v in (self.image_width, self.image_height)):
            raise ValueError('preview geometry mismatch')
        if self.runtime.raw_elements != (4 + len(self.classes)) * 8400 or len(self.detections) != min(300, self.counts.nms_kept) - self.counts.clip_removed:
            raise ValueError('inference output counts mismatch')
        for detection in self.detections:
            x1, y1, x2, y2 = detection.xyxy
            if detection.class_id >= len(self.classes) or not (0 <= x1 < x2 <= self.image_width and 0 <= y1 < y2 <= self.image_height):
                raise ValueError('detection bounds mismatch')
        return self


class InferenceDocument(InferenceOutputFields):
    schema_version: Literal[1]
    protocol: Literal['detection-image-v1']
    provenance: InferenceProvenance
    params: InferenceParams

    @model_validator(mode='after')
    def document_binding(self):
        if self.backend != self.params.backend or (self.params.model_artifact_id, self.params.image_artifact_id) != (self.provenance.model_artifact_id, self.provenance.image_artifact_id):
            raise ValueError('inference resource or backend binding mismatch')
        if any(d.score <= self.params.confidence for d in self.detections):
            raise ValueError('detection confidence mismatch')
        return self


class InferenceResultMetadata(StrictInferenceModel):
    schema_version: Literal[1]
    protocol: Literal['detection-image-v1']
    provenance: InferenceProvenance
    result_sha256: str = Field(pattern=SHA256)
    result_size_bytes: int = Field(strict=True, gt=0, le=1024**2)
    preview: PreviewRecord
    validation_scope: Literal['real_single_image_inference']


class InferenceResultArtifactPublic(ArtifactBase, StrictInferenceModel):
    kind: Literal['inference_result']
    format: Literal['json']
    job_id: UUID
    size_bytes: int = Field(strict=True, gt=0, le=1024**2)
    metadata_schema_version: Literal[1]
    validation_state: Literal[ValidationState.PASSED]
    metadata: InferenceResultMetadata

    @model_validator(mode='after')
    def consistent(self):
        if (self.project_id, self.job_id, self.sha256, self.size_bytes) != (self.metadata.provenance.project_id, self.metadata.provenance.job_id, self.metadata.result_sha256, self.metadata.result_size_bytes):
            raise ValueError('result Artifact metadata mismatch')
        return self


class OtherArtifactPublic(ArtifactBase):
    kind: Literal['dataset_report', 'deployment_zip']
    metadata: dict[str, object]


class ArtifactPublic(RootModel[Annotated[TrainingArtifactPublic | OnnxArtifactPublic | InferenceInputArtifactPublic | InferenceResultArtifactPublic | OtherArtifactPublic, Field(discriminator='kind')]]):
    """Malformed typed image/ONNX metadata never falls back to arbitrary dict."""


class InferenceResult(InferenceDocument):
    artifact_id: UUID
    image_url: str = Field(pattern=r'^/api/v1/inferences/[0-9a-f-]{36}/image$')

    @model_validator(mode='after')
    def image_url_binding(self):
        if self.image_url != f'/api/v1/inferences/{self.artifact_id}/image':
            raise ValueError('preview route does not match result Artifact')
        return self
