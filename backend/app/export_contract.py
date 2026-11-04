"""Frozen export protocol. Only standard library and Pydantic are imported."""
from functools import lru_cache
from hashlib import sha256
import struct
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .schemas import StrictExportModel, ExportOnnxParams, TrainingArtifactMetadata
from .training_contract import FileEntry, FrozenTraining, SHA

MAX_ONNX_BYTES = 128 * 1024**2
MAX_EXPORT_JSON_BYTES = 1024 * 1024
TENSOR_NAMES = ("zeros", "gradient", "pattern")
INPUT_SHAPE = (1, 3, 640, 640)


class FrozenExport(StrictExportModel):
    schema_version: Literal[1]
    project_id: UUID
    source_artifact_id: UUID
    source_job_id: UUID
    source_key: str = Field(min_length=1, max_length=512)
    source_sha256: str = Field(pattern=SHA)
    source_size_bytes: int = Field(strict=True, gt=0, le=MAX_ONNX_BYTES)
    source_metadata: TrainingArtifactMetadata
    source_metadata_sha256: str = Field(pattern=SHA)
    training_input: FrozenTraining
    source_training_input_sha256: str = Field(pattern=SHA)
    params: ExportOnnxParams
    runtime_binding: str = Field(pattern=SHA)
    code_version: str = Field(pattern=SHA)

    @model_validator(mode="after")
    def consistent(self):
        if self.params.model_artifact_id != self.source_artifact_id or self.source_metadata.classes != self.training_input.classes:
            raise ValueError("frozen source binding mismatch")
        return self


class ExportInput(StrictExportModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    kind: Literal["export_onnx"]
    input: FrozenExport


class ExportEvidence(StrictExportModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    input_sha256: str = Field(pattern=SHA)
    outputs: list[FileEntry] = Field(min_length=3, max_length=3)


@lru_cache(maxsize=3)
def tensor_bytes(name):
    """Portable little-endian FP32, independently reconstructable without NumPy."""
    count = 3 * 640 * 640
    if name == "zeros":
        return bytes(count * 4)
    if name == "gradient":
        cycle = b"".join(struct.pack("<f", i / 639) for i in range(640))
    elif name == "pattern":
        cycle = b"".join(struct.pack("<f", ((i * 37 + 17) % 256) / 255) for i in range(256))
    else:
        raise ValueError("unknown fixed tensor")
    return cycle * (count // (len(cycle) // 4))


def tensor_hashes():
    return {name: sha256(tensor_bytes(name)).hexdigest() for name in TENSOR_NAMES}
