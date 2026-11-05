"""Lightweight fixed training protocol. No ML imports."""
from typing import Literal
from uuid import UUID
from pydantic import Field, FiniteFloat
from .schemas import StrictModel, TrainParams

SHA = r"^[0-9a-f]{64}$"
MAX_PT_BYTES = 128 * 1024**2
METRIC_NAMES = frozenset({"train/box_loss", "train/cls_loss", "train/dfl_loss", "val/box_loss", "val/cls_loss", "val/dfl_loss", "metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)"})
MAX_METRIC_BYTES = 1024 * 1024

class FileEntry(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(ge=0, le=2 * 1024**3)
    sha256: str = Field(pattern=SHA)

class FrozenTraining(StrictModel):
    schema_version: Literal[1]
    dataset_id: UUID
    dataset_version: int = Field(ge=1)
    archive_sha256: str = Field(pattern=SHA)
    snapshot_key: str = Field(min_length=1, max_length=512)
    snapshot_sha256: str = Field(pattern=SHA)
    report_artifact_id: UUID
    report_key: str = Field(min_length=1, max_length=512)
    report_size_bytes: int = Field(gt=0, le=16 * 1024**2)
    report_sha256: str = Field(pattern=SHA)
    files: list[FileEntry] = Field(min_length=1, max_length=20000)
    classes: list[str] = Field(min_length=1, max_length=1000)
    counts: dict[str, int]
    params: TrainParams
    base_manifest: dict
    base_manifest_sha256: str = Field(pattern=SHA)
    runtime_binding: str = Field(pattern=SHA)
    code_version: str = Field(min_length=1, max_length=64)

class TrainingInput(StrictModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    kind: Literal["train"]
    input: FrozenTraining

class TrainingMetric(StrictModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    seq: int = Field(strict=True, ge=1, le=1000)
    epoch: int = Field(strict=True, ge=1, le=100)
    name: str
    value: FiniteFloat = Field(strict=True)

class TrainingEvidence(StrictModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    input_sha256: str = Field(pattern=SHA)
    outputs: list[FileEntry] = Field(min_length=3, max_length=3)
    metric_count: int = Field(strict=True, ge=1, le=1000)
    completed_epochs: int = Field(strict=True, ge=1, le=100)
    optimizer_steps: int = Field(strict=True, ge=1)
