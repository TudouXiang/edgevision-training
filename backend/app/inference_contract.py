"""Strict internal image task snapshots, free of native model imports."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from .schemas import (StrictInferenceModel, InferenceParams, InferenceInputMetadata,
                      TrainingArtifactMetadata, OnnxArtifactMetadata, SHA256)
from .training_contract import FrozenTraining
from .export_contract import FrozenExport
from .delivery_infer import PROTOCOL, MAX_IMAGE_BYTES, MAX_PREVIEW_BYTES

MAX_INFERENCE_JSON_BYTES = 1024**2


class TrustedPT(StrictInferenceModel):
    @model_validator(mode='wrap')
    @classmethod
    def no_legacy_scalar_coercion(cls, value, handler):
        result = handler(value)
        if isinstance(value, dict):
            from .training_assets import digest_json
            # Embedded legacy schemas are unchanged for T050/E compatibility;
            # I must reject coercion instead of silently rewriting their input.
            try:
                if digest_json(value) != digest_json(result.model_dump(mode='json')):
                    raise ValueError('legacy source scalar coercion is forbidden in I')
            except TypeError as exc:
                raise ValueError('I frozen source must use canonical JSON scalars') from exc
        return result

    backend: Literal['pt']
    project_id: UUID
    source_artifact_id: UUID
    source_job_id: UUID
    source_key: str = Field(min_length=1, max_length=512)
    source_sha256: str = Field(pattern=SHA256)
    source_size_bytes: int = Field(strict=True, gt=0, le=128 * 1024**2)
    source_metadata: TrainingArtifactMetadata
    source_metadata_sha256: str = Field(pattern=SHA256)
    training_input: FrozenTraining
    source_training_input_sha256: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        from .training_assets import digest_json
        from .training_service import provenance
        training = self.training_input.model_dump(mode='json')
        metadata = self.source_metadata.model_dump(mode='json')
        if metadata['classes'] != training['classes'] or metadata['provenance'] != provenance(training) or metadata['runtime']['completed_epochs'] != training['params']['epochs']:
            raise ValueError('PT source provenance mismatch')
        if self.source_metadata_sha256 != digest_json(metadata) or self.source_training_input_sha256 != digest_json(training):
            raise ValueError('PT source snapshot digest mismatch')
        return self


class TrustedOnnx(StrictInferenceModel):
    @model_validator(mode='wrap')
    @classmethod
    def no_legacy_scalar_coercion(cls, value, handler):
        result = handler(value)
        if isinstance(value, dict):
            from .training_assets import digest_json
            # Embedded legacy schemas are unchanged for T050/E compatibility;
            # I must reject coercion instead of silently rewriting their input.
            try:
                if digest_json(value) != digest_json(result.model_dump(mode='json')):
                    raise ValueError('legacy source scalar coercion is forbidden in I')
            except TypeError as exc:
                raise ValueError('I frozen source must use canonical JSON scalars') from exc
        return result

    backend: Literal['onnx']
    project_id: UUID
    source_artifact_id: UUID
    source_job_id: UUID
    source_key: str = Field(min_length=1, max_length=512)
    source_sha256: str = Field(pattern=SHA256)
    source_size_bytes: int = Field(strict=True, gt=0, le=128 * 1024**2)
    source_metadata: OnnxArtifactMetadata
    source_metadata_sha256: str = Field(pattern=SHA256)
    export_input: FrozenExport

    @model_validator(mode='after')
    def consistent(self):
        from .training_assets import digest_json
        from .export_service import provenance
        origin, proof = self.source_metadata.provenance, self.source_metadata.validation
        frozen = self.export_input.model_dump(mode='json')
        parent_fields = {name: frozen[name] for name in TrustedPT.model_fields if name != 'backend'}
        TrustedPT.model_validate({'backend': 'pt', **parent_fields})
        if origin.model_dump(mode='json') != provenance(frozen, str(self.source_job_id), str(proof.run_id)) or self.source_metadata_sha256 != digest_json(self.source_metadata.model_dump(mode='json')):
            raise ValueError('ONNX source provenance or digest mismatch')
        if self.project_id != self.export_input.project_id or self.source_job_id != origin.job_id or (self.source_sha256, self.source_size_bytes) != (proof.model_sha256, proof.model_size_bytes) or origin.parent_artifact_id != self.export_input.source_artifact_id:
            raise ValueError('ONNX source lineage mismatch')
        return self


TrustedModel = Annotated[TrustedPT | TrustedOnnx, Field(discriminator='backend')]


class FrozenImage(StrictInferenceModel):
    artifact_id: UUID
    project_id: UUID
    key: str = Field(min_length=1, max_length=512)
    image_sha256: str = Field(pattern=SHA256)
    image_size_bytes: int = Field(strict=True, gt=0, le=MAX_IMAGE_BYTES)
    metadata: InferenceInputMetadata


class FrozenInference(StrictInferenceModel):
    schema_version: Literal[1]
    protocol: Literal['detection-image-v1']
    project_id: UUID
    model: TrustedModel
    image: FrozenImage
    params: InferenceParams
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        if self.model.project_id != self.project_id or self.image.project_id != self.project_id or self.params.model_artifact_id != self.model.source_artifact_id or self.params.image_artifact_id != self.image.artifact_id or self.params.backend != self.model.backend:
            raise ValueError('inference frozen resources mismatch')
        return self


class InferenceInput(StrictInferenceModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    kind: Literal['infer']
    input: FrozenInference


class InferenceFileEntry(StrictInferenceModel):
    path: Literal['result.json', 'metadata.json', 'preview.png']
    size_bytes: int = Field(strict=True, gt=0, le=MAX_PREVIEW_BYTES)
    sha256: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def bounded_member(self):
        if self.size_bytes > (MAX_PREVIEW_BYTES if self.path == 'preview.png' else MAX_INFERENCE_JSON_BYTES):
            raise ValueError('image publication member exceeds its bound')
        return self


class InferenceEvidence(StrictInferenceModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    frozen_input_sha256: str = Field(pattern=SHA256)
    outputs: list[InferenceFileEntry] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def complete(self):
        if {entry.path for entry in self.outputs} != {'result.json', 'metadata.json', 'preview.png'}:
            raise ValueError('inference output members mismatch')
        return self
