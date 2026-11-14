"""Strict private standalone probe protocol. No caller-selected commands."""
from typing import Literal
from uuid import UUID
from pydantic import Field
from .schemas import StrictInferenceModel,SHA256


class StandaloneInput(StrictInferenceModel):
    schema_version: Literal[1]
    kind: Literal['package_standalone_probe']
    job_id: UUID
    run_id: UUID
    mode: Literal['raw','cli']
    cli_sha256: str = Field(pattern=SHA256)
    bootstrap_sha256: str = Field(pattern=SHA256)
    package_sha256: str = Field(pattern=SHA256)
    package_size_bytes: int = Field(strict=True,gt=0,le=144*1024**2)
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)
    model_sha256: str = Field(pattern=SHA256)
    template_sha256: str = Field(pattern=SHA256)
    image_sha256: str = Field(pattern=SHA256)
    image_size_bytes: int = Field(strict=True,gt=0,le=50*1024**2)


from typing import Annotated
from pydantic import model_validator
from .schemas import (PackageTemplate,DecodedImageRecord,PreprocessRecord,Detection,PostprocessCounts,
    InferenceVersions,InferenceOutputFields,StrictFinite)
from .inference_probe_contract import InferenceProbeProof,ProbeComparison


class TemplateHashes(StrictInferenceModel):
    template_sha256: str = Field(pattern=SHA256)
    core_sha256: str = Field(pattern=SHA256)
    lock_sha256: str = Field(pattern=SHA256)


class StandalonePreview(StrictInferenceModel):
    width: int = Field(strict=True,gt=0,le=1280)
    height: int = Field(strict=True,gt=0,le=1280)
    size_bytes: int = Field(strict=True,gt=0,le=8*1024**2)
    sha256: str = Field(pattern=SHA256)


class StandaloneOutput(StrictInferenceModel):
    schema_version: Literal[1]
    protocol: Literal['detection-image-v1']
    backend: Literal['onnx']
    provider: Literal['CPUExecutionProvider']
    model_sha256: str = Field(pattern=SHA256)
    template: TemplateHashes
    image_sha256: str = Field(pattern=SHA256)
    image_size_bytes: int = Field(strict=True,gt=0,le=50*1024**2)
    decoded: DecodedImageRecord
    geometry: PreprocessRecord
    confidence: Literal[0.25]
    iou: Literal[0.45]
    detections: list[Detection] = Field(max_length=300)
    counts: PostprocessCounts
    classes: list[Annotated[str,Field(min_length=1,max_length=128)]] = Field(min_length=1,max_length=1000)
    runtime: InferenceVersions
    raw_sha256: str = Field(pattern=SHA256)
    raw_elements: int = Field(strict=True,ge=5*8400,le=1004*8400)
    preview: StandalonePreview

    @model_validator(mode='after')
    def consistent(self):
        # Reuse geometric/runtime/count invariants, without inventing public timings.
        InferenceOutputFields.model_validate({'image_width':self.decoded.image_width,'image_height':self.decoded.image_height,
            'backend':'onnx','provider':'CPUExecutionProvider','classes':self.classes,'image':self.decoded.model_dump(mode='json'),
            'preprocess':self.geometry.model_dump(mode='json'),'runtime':{'backend':'onnx','provider':'CPUExecutionProvider',
            'device':'cpu','threads':2,'interop_threads':1,'warmup_runs':0,'versions':self.runtime.model_dump(mode='json'),
            'raw_sha256':self.raw_sha256,'raw_elements':self.raw_elements},'preview':{**self.preview.model_dump(mode='json'),'format':'png'},
            'counts':self.counts.model_dump(mode='json'),'detections':[d.model_dump(mode='json') for d in self.detections],
            'timings':{'unit':'ms','decode':0.,'preprocess':0.,'load':0.,'infer':0.,'postprocess':0.,'total':0.}})
        if any(d.score<=self.confidence for d in self.detections):raise ValueError('standalone confidence mismatch')
        return self


class StandaloneProof(StrictInferenceModel):
    schema_version: Literal[1]
    mode: Literal['raw','cli']
    job_id: UUID
    run_id: UUID
    task_sha256: str = Field(pattern=SHA256)
    environment_sha256: str = Field(pattern=SHA256)
    isolated_imports: Literal[True]
    output: StandaloneOutput
    receipt_sha256: str | None = Field(pattern=SHA256)


class PackageProbeRecord(StrictInferenceModel):
    schema_version: Literal[1]
    available: Literal[True]
    protocol: Literal['edgevision-python-onnx-v1']
    runtime_binding: str = Field(pattern=SHA256)
    code_version: str = Field(pattern=SHA256)
    reference_runtime_binding: str = Field(pattern=SHA256)
    reference_code_version: str = Field(pattern=SHA256)
    template: PackageTemplate
    environment_sha256: str = Field(pattern=SHA256)
    package_sha256: str = Field(pattern=SHA256)
    package_size_bytes: int = Field(strict=True,gt=0,le=144*1024**2)
    reference: InferenceProbeProof
    raw_task: StandaloneInput
    cli_task: StandaloneInput
    standalone: StandaloneProof
    cli: StandaloneProof
    comparison: ProbeComparison

    @model_validator(mode='after')
    def consistent(self):
        from .training_assets import digest_json
        from .delivery_infer import match_detections
        reference=self.reference;raw=self.standalone;cli=self.cli
        if reference.output.backend!='onnx' or reference.receipt_sha256 is None:raise ValueError('managed ONNX reference required')
        if (reference.runtime_binding,reference.code_version)!=(self.reference_runtime_binding,self.reference_code_version):raise ValueError('reference runtime mismatch')
        identities={(p.job_id,p.run_id) for p in (reference,raw,cli)}
        if len(identities)!=3:raise ValueError('three independent managed runs required')
        for mode,task,proof in (('raw',self.raw_task,raw),('cli',self.cli_task,cli)):
            if task.mode!=mode or proof.mode!=mode or (task.job_id,task.run_id)!=(proof.job_id,proof.run_id):raise ValueError('standalone task role mismatch')
            if proof.receipt_sha256 is None or proof.task_sha256!=digest_json(task.model_dump(mode='json')):raise ValueError('standalone receipt or task missing')
            if (task.runtime_binding,task.code_version,task.package_sha256,task.package_size_bytes)!=(self.runtime_binding,self.code_version,self.package_sha256,self.package_size_bytes):raise ValueError('standalone candidate binding mismatch')
            if task.model_sha256!=reference.model_sha256 or task.template_sha256!=self.template.template_sha256:raise ValueError('standalone source mismatch')
            if proof.environment_sha256!=self.environment_sha256 or proof.output.model_sha256!=task.model_sha256:raise ValueError('standalone environment mismatch')
            if (proof.output.image_sha256,proof.output.image_size_bytes)!=(task.image_sha256,task.image_size_bytes):raise ValueError('standalone image mismatch')
            if proof.output.template.model_dump()!= {key:getattr(self.template,key) for key in TemplateHashes.model_fields}:raise ValueError('standalone template mismatch')
        if (self.raw_task.cli_sha256,self.raw_task.bootstrap_sha256)!=(self.cli_task.cli_sha256,self.cli_task.bootstrap_sha256):raise ValueError('standalone entry changed')
        if raw.output.model_dump()!=cli.output.model_dump():raise ValueError('CLI result differs from independent raw run')
        if raw.output.classes!=reference.output.classes or raw.output.decoded!=reference.output.image or raw.output.geometry!=reference.output.preprocess:raise ValueError('common source pixels or preprocessing differ')
        if {**raw.output.preview.model_dump(),'format':'png'}!=reference.output.preview.model_dump():raise ValueError('common preview differs')
        if raw.output.raw_elements!=self.comparison.elements or reference.raw_size_bytes!=self.comparison.elements*4:raise ValueError('full raw comparison missing')
        if not match_detections([d.model_dump() for d in reference.output.detections],[d.model_dump() for d in raw.output.detections]):raise ValueError('standalone detections differ')
        return self
