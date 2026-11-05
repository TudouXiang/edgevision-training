"""Versioned private protocol for the fixed dataset runner and its verified outputs.

This is not a plugin registry: production can only invoke the fixed dataset
adapter. Public HTTP types continue to come from app.schemas.
"""
from typing import Literal
from uuid import UUID
from pydantic import Field
from .schemas import StrictModel


class FrozenDatasetInput(StrictModel):
    schema_version: Literal[1]
    dataset_id: UUID
    archive_key: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1, le=512 * 1024**2)


class TaskInput(StrictModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    kind: Literal["dataset_check"]
    input: FrozenDatasetInput


class OutputFile(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    role: Literal["report", "manifest", "snapshot"]
    size_bytes: int = Field(ge=0, le=2 * 1024**3)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValidationEvidence(StrictModel):
    schema_version: Literal[1]
    job_id: UUID
    run_id: UUID
    dataset_id: UUID
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid: bool = Field(strict=True)
    outputs: list[OutputFile] = Field(min_length=2, max_length=20002)
