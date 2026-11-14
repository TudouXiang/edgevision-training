"""Strict package task snapshots; no native imports or implicit runtime claims."""
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .schemas import StrictInferenceModel, PackageParams, SHA256, PackageTemplate as TemplateIdentity, PackageArtifactMetadata
from .inference_contract import TrustedOnnx

MAX_PACKAGE_BYTES = 144 * 1024**2
MAX_PACKAGE_JSON_BYTES = 1024**2



class FrozenPackage(StrictInferenceModel):
    schema_version: Literal[1]
    project_id: UUID
    model: TrustedOnnx
    params: PackageParams
    template: TemplateIdentity
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)
    template_validation_sha256: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        if self.project_id != self.model.project_id or self.params.onnx_artifact_id != self.model.source_artifact_id:
            raise ValueError('package frozen source mismatch')
        return self


class PackageInput(StrictInferenceModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    kind: Literal['package']
    input: FrozenPackage


class PackageFileEntry(StrictInferenceModel):
    path: Literal['package.zip', 'metadata.json', 'validation.json']
    size_bytes: int = Field(strict=True, gt=0, le=MAX_PACKAGE_BYTES)
    sha256: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def bounded_member(self):
        if self.path != 'package.zip' and self.size_bytes > MAX_PACKAGE_JSON_BYTES:
            raise ValueError('package JSON exceeds bound')
        return self


class PackageEvidence(StrictInferenceModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    input_sha256: str = Field(pattern=SHA256)
    outputs: list[PackageFileEntry] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def complete(self):
        if {entry.path for entry in self.outputs} != {'package.zip', 'metadata.json', 'validation.json'}:
            raise ValueError('package output members mismatch')
        return self


class PackageValidation(StrictInferenceModel):
    schema_version: Literal[1]
    metadata: PackageArtifactMetadata
    manifest: dict[str, object]

    @model_validator(mode='after')
    def consistent(self):
        from .package_cli import validate_manifest, canonical
        from hashlib import sha256
        value = validate_manifest(self.manifest)
        raw = canonical(value)
        if (len(raw), sha256(raw).hexdigest()) != (self.metadata.manifest_size_bytes, self.metadata.manifest_sha256):
            raise ValueError('manifest metadata mismatch')
        proof = self.metadata.provenance
        expected = {'onnx_artifact_id':str(proof.onnx_artifact_id),'export_job_id':str(proof.export_job_id),
            'parent_artifact_id':str(proof.parent_artifact_id),'sha256':proof.model_sha256,
            'size_bytes':proof.model_size_bytes,'metadata_sha256':proof.model_metadata_sha256}
        if value['source'] != expected:
            raise ValueError('manifest source mismatch')
        if value['template'] != {key:getattr(self.metadata.template,key) for key in value['template']}:
            raise ValueError('manifest template mismatch')
        return self
