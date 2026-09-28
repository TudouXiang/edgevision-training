"""Execution boundary only; no production or fake runner is registered in T010."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .contracts import JobKind


@dataclass(frozen=True)
class TaskInput:
    job_id: UUID
    run_id: UUID
    kind: JobKind
    params_schema_version: int
    params_snapshot: str
    input_snapshot: str


@dataclass(frozen=True)
class TaskEvidence:
    output_keys: tuple[str, ...]
    output_sha256: tuple[str, ...]
    validation_report_key: str | None


class TaskRunner(Protocol):
    def run(self, task: TaskInput) -> TaskEvidence:
        """Raise on failure; returning evidence alone never commits success."""
