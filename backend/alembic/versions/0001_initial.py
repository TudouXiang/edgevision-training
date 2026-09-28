"""Initial single-host metadata tables.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("role IN ('user','admin')", name="ck_users_role"))
    op.create_table("sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("revoked_at", sa.String(32)))
    op.create_table("projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("task_type = 'detection'", name="ck_projects_task_type"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_projects_status"))
    op.create_index("ix_projects_owner_updated", "projects", ["owner_id", "updated_at"])
    op.create_table("datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("datasets.id")),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("archive_key", sa.String(512), nullable=False),
        sa.Column("snapshot_key", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("report_key", sa.String(512)),
        sa.Column("counts_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("project_id", "name", "version", name="uq_dataset_version"),
        sa.CheckConstraint("status IN ('uploaded','validating','valid','invalid')", name="ck_datasets_status"),
        sa.CheckConstraint("size_bytes >= 0 AND version > 0", name="ck_datasets_size_version"))
    op.create_table("jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("retry_of_id", sa.String(36), sa.ForeignKey("jobs.id")),
        sa.Column("worker_pid", sa.Integer),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(32)),
        sa.Column("finished_at", sa.String(32)),
        sa.Column("heartbeat_at", sa.String(32)),
        sa.CheckConstraint("kind IN ('validate','train','export_onnx','infer','package')", name="ck_jobs_kind"),
        sa.CheckConstraint("status IN ('queued','running','cancelling','cancelled','succeeded','failed')", name="ck_jobs_status"))
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_table("job_events",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("seq", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("kind IN ('status','log','metric')", name="ck_job_events_kind"))
    op.create_table("metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("epoch", sa.Integer, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("job_id", "epoch", "name", name="uq_metric_epoch_name"))
    op.create_table("artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id")),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("artifacts.id")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("format", sa.String(24), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("metadata_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("validated_at", sa.String(32)),
        sa.CheckConstraint("kind IN ('dataset_report','pt_best','pt_last','onnx','inference_input','inference_result','deployment_zip')", name="ck_artifacts_kind"),
        sa.CheckConstraint("validation_status IN ('pending','validated','rejected')", name="ck_artifacts_validation"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifacts_size"))
    op.create_table("idempotency_keys",
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("owner_id", "request_key", "method", "path"))


def downgrade() -> None:
    for table in ("idempotency_keys", "artifacts", "metrics", "job_events", "jobs", "datasets", "projects", "sessions", "users"):
        op.drop_table(table)
