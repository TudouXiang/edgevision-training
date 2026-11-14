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
