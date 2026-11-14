"""Strict private dual-mode probe evidence; no model or image bytes in records."""
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .schemas import StrictInferenceModel, StrictFinite, SHA256, InferenceOutputFields
from .inference_contract import TrustedModel, TrustedPT, TrustedOnnx


class ProbePair(StrictInferenceModel):
    pt: TrustedPT
    onnx: TrustedOnnx

    @model_validator(mode='after')
    def consistent(self):
        source = self.onnx.export_input.model_dump(mode='json')
        if self.pt.model_dump(mode='json') != {'backend': 'pt', **{key: source[key] for key in TrustedPT.model_fields if key != 'backend'}}:
            raise ValueError('probe sources do not share the exact parent PT')
        return self


class ProbeInput(StrictInferenceModel):
    schema_version: Literal[1]
    kind: Literal['inference_probe']
    protocol: Literal['detection-image-v1']
    job_id: UUID
    run_id: UUID
    pair: ProbePair
    backend: Literal['pt', 'onnx']
    pair_sha256: str = Field(pattern=SHA256)
    image_sha256: str = Field(pattern=SHA256)
    image_size_bytes: int = Field(strict=True, gt=0, le=50*1024**2)
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        from .training_assets import digest_json
        if self.pair_sha256 != digest_json(self.pair.model_dump(mode='json')): raise ValueError('probe source pair changed')
        return self


class InferenceProbeProof(StrictInferenceModel):
    schema_version: Literal[1]
    protocol: Literal['detection-image-v1']
    job_id: UUID
    run_id: UUID
    project_id: UUID
    model_artifact_id: UUID
    parent_pt_artifact_id: UUID
    model_sha256: str = Field(pattern=SHA256)
    pair_sha256: str = Field(pattern=SHA256)
    image_sha256: str = Field(pattern=SHA256)
    image_size_bytes: int = Field(strict=True, gt=0, le=50*1024**2)
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)
    output: InferenceOutputFields
    raw_size_bytes: int = Field(strict=True, gt=0, le=33_734_400)
    raw_sha256: str = Field(pattern=SHA256)
    receipt_sha256: str | None = Field(pattern=SHA256)

    @model_validator(mode='after')
    def consistent(self):
        if self.raw_size_bytes != self.output.runtime.raw_elements * 4 or self.raw_sha256 != self.output.runtime.raw_sha256:
            raise ValueError('probe raw dimensions or fingerprint mismatch')
        if self.output.backend == 'pt' and self.model_artifact_id != self.parent_pt_artifact_id:
            raise ValueError('PT probe source mismatch')
        if any(d.score <= .25 for d in self.output.detections): raise ValueError('probe confidence mismatch')
        return self


class ProbeComparison(StrictInferenceModel):
    elements: int = Field(strict=True, ge=5*8400, le=1004*8400)
    max_absolute_error: StrictFinite = Field(ge=0)
    max_tolerance_ratio: StrictFinite = Field(ge=0, le=1)
    atol: Literal[0.0001]
    rtol: Literal[0.0001]
    detections_matched: Literal[True]


class InferenceProbeRecord(StrictInferenceModel):
    schema_version: Literal[1]
    available: Literal[True]
    protocol: Literal['detection-image-v1']
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)
    synthetic_source_sha256: str = Field(pattern=SHA256)
    pt: InferenceProbeProof
    onnx: InferenceProbeProof
    comparison: ProbeComparison

    @model_validator(mode='after')
    def consistent(self):
        if self.pt.output.backend != 'pt' or self.onnx.output.backend != 'onnx': raise ValueError('both modes required')
        for proof in (self.pt, self.onnx):
            if proof.runtime_binding != self.runtime_binding or proof.code_version != self.code_version or proof.receipt_sha256 is None:
                raise ValueError('probe runtime or completed receipt mismatch')
        if (self.pt.job_id, self.pt.run_id) == (self.onnx.job_id, self.onnx.run_id): raise ValueError('independent managed runs required')
        for key in ('project_id', 'pair_sha256', 'image_sha256', 'image_size_bytes', 'parent_pt_artifact_id'):
            if getattr(self.pt, key) != getattr(self.onnx, key): raise ValueError('probe source binding mismatch')
        if self.pt.output.classes != self.onnx.output.classes or self.pt.output.preprocess != self.onnx.output.preprocess or self.pt.output.image != self.onnx.output.image or self.pt.output.preview != self.onnx.output.preview:
            raise ValueError('probe common image algorithm mismatch')
        if self.pt.raw_size_bytes != self.onnx.raw_size_bytes or self.comparison.elements * 4 != self.pt.raw_size_bytes:
            raise ValueError('incomplete probe raw comparison')
        from .delivery_infer import match_detections
        if not match_detections([d.model_dump() for d in self.pt.output.detections], [d.model_dump() for d in self.onnx.output.detections]):
            raise ValueError('probe detection comparison mismatch')
        return self
