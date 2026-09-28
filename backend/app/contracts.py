"""One authoritative vocabulary and transition guard for persisted jobs.

The worker and future service layer must use this module. Database compare-and-set
and OS process ownership checks still belong to T040; this guard does not replace them.
"""

from enum import Enum


class JobKind(str, Enum):
    DATASET_CHECK = "dataset_check"
    TRAIN = "train"
    EXPORT_ONNX = "export_onnx"
    INFER = "infer"
    PACKAGE = "package"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class DatasetState(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    READY = "ready"
    INVALID = "invalid"


class ValidationState(str, Enum):
    UNVERIFIED = "unverified"
    PASSED = "passed"
    FAILED = "failed"


TERMINAL_STATES = frozenset({JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.INTERRUPTED})
ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
    JobState.RUNNING: frozenset({JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLING, JobState.INTERRUPTED}),
    JobState.CANCELLING: frozenset({JobState.CANCELLED, JobState.INTERRUPTED}),
}


def require_transition(
    before: JobState,
    after: JobState,
    *,
    process_exited: bool = False,
    evidence_verified: bool = False,
) -> None:
    """Reject illegal terminal writes; caller must also atomically compare DB state."""
    if after not in ALLOWED_TRANSITIONS.get(before, frozenset()):
        raise ValueError(f"illegal job transition {before.value} -> {after.value}")
    if after == JobState.SUCCEEDED and (not process_exited or not evidence_verified):
        raise ValueError("success requires confirmed exit, verified evidence and atomic artifact registration")
    if before != JobState.QUEUED and after in TERMINAL_STATES - {JobState.SUCCEEDED} and not process_exited:
        raise ValueError("terminal state requires confirmed task process exit")
