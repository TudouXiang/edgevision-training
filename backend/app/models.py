"""Metadata tables for revision 0002. Runtime writes are implemented per task.

The initial and follow-up Alembic revisions are authoritative; API startup
never calls create_all() and does not create users or sample results.
"""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user','admin')", name="ck_users_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[str] = mapped_column(String(32))


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32))
    revoked_at: Mapped[str | None] = mapped_column(String(32))


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("task_type = 'detection'", name="ck_projects_task_type"),
        CheckConstraint("status IN ('active','archived')", name="ck_projects_status"),
        Index("ix_projects_owner_updated", "owner_id", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    archived_at: Mapped[str | None] = mapped_column(String(32))


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "name", "version", name="uq_dataset_version"),
        CheckConstraint("status IN ('pending','validating','ready','invalid')", name="ck_datasets_status"),
        CheckConstraint("size_bytes >= 0 AND version > 0", name="ck_datasets_size_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("datasets.id"))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    archive_key: Mapped[str] = mapped_column(String(512))
    snapshot_key: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    report_key: Mapped[str | None] = mapped_column(String(512))
    counts_json: Mapped[str] = mapped_column(Text)
    classes_json: Mapped[str] = mapped_column(Text)
    manifest_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('dataset_check','train','export_onnx','infer','package')", name="ck_jobs_kind"),
        CheckConstraint("status IN ('queued','running','cancelling','cancelled','succeeded','failed','interrupted')", name="ck_jobs_status"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    payload_json: Mapped[str] = mapped_column(Text)
    retry_of_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"))
    worker_pid: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    heartbeat_at: Mapped[str | None] = mapped_column(String(32))
    params_schema_version: Mapped[int] = mapped_column(Integer, server_default="1")
    input_snapshot_json: Mapped[str] = mapped_column(Text, server_default="{}")
    environment_json: Mapped[str] = mapped_column(Text, server_default="{}")
    code_version: Mapped[str | None] = mapped_column(String(128))
    run_id: Mapped[str | None] = mapped_column(String(36))
    worker_instance: Mapped[str | None] = mapped_column(String(36))
    host_boot_id: Mapped[str | None] = mapped_column(String(64))
    child_pid: Mapped[int | None] = mapped_column(Integer)
    child_pgid: Mapped[int | None] = mapped_column(Integer)
    cancel_requested_at: Mapped[str | None] = mapped_column(String(32))


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (CheckConstraint("kind IN ('status','log','metric')", name="ck_job_events_kind"),)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("job_id", "epoch", "name", name="uq_metric_epoch_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    epoch: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(String(32))


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("kind IN ('dataset_report','pt_best','pt_last','onnx','inference_input','inference_result','deployment_zip')", name="ck_artifacts_kind"),
        CheckConstraint("validation_status IN ('unverified','passed','failed')", name="ck_artifacts_validation"),
        CheckConstraint("size_bytes >= 0", name="ck_artifacts_size"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"))
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("artifacts.id"))
    kind: Mapped[str] = mapped_column(String(32))
    format: Mapped[str] = mapped_column(String(24))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    validation_status: Mapped[str] = mapped_column(String(16))
    metadata_json: Mapped[str] = mapped_column(Text)
    metadata_schema_version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[str] = mapped_column(String(32))
    validated_at: Mapped[str | None] = mapped_column(String(32))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    method: Mapped[str] = mapped_column(String(8), primary_key=True)
    path: Mapped[str] = mapped_column(String(512), primary_key=True)
    body_sha256: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    created_at: Mapped[str] = mapped_column(String(32))
