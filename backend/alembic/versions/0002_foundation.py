"""Align the existing 0001 schema with the EdgeVision foundation contract.

Revision ID: 0002_foundation
Revises: 0001_initial

Keep 0001 untouched: it has already been run on a developer machine. Stop the
API and Worker and take a consistent backup before upgrading an existing DB.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_foundation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite checks old values during the copy. Use a temporary union CHECK so
    # existing rows can be transformed before the final stricter table copy.
    with op.batch_alter_table("datasets", recreate="always") as batch:
        batch.drop_constraint("ck_datasets_status", type_="check")
        batch.create_check_constraint("ck_datasets_status_union", "status IN ('uploaded','pending','validating','valid','ready','invalid')")
    op.execute("UPDATE datasets SET status='pending' WHERE status='uploaded'")
    op.execute("UPDATE datasets SET status='ready' WHERE status='valid'")
    with op.batch_alter_table("datasets", recreate="always") as batch:
        batch.drop_constraint("ck_datasets_status_union", type_="check")
        batch.create_check_constraint("ck_datasets_status", "status IN ('pending','validating','ready','invalid')")
        batch.add_column(sa.Column("classes_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("manifest_json", sa.Text(), nullable=False, server_default="{}"))

    with op.batch_alter_table("jobs", recreate="always") as batch:
        batch.drop_constraint("ck_jobs_kind", type_="check")
        batch.create_check_constraint("ck_jobs_kind_union", "kind IN ('validate','dataset_check','train','export_onnx','infer','package')")
    op.execute("UPDATE jobs SET kind='dataset_check' WHERE kind='validate'")
    with op.batch_alter_table("jobs", recreate="always") as batch:
        batch.drop_constraint("ck_jobs_kind_union", type_="check")
        batch.drop_constraint("ck_jobs_status", type_="check")
        batch.create_check_constraint("ck_jobs_kind", "kind IN ('dataset_check','train','export_onnx','infer','package')")
        batch.create_check_constraint("ck_jobs_status", "status IN ('queued','running','cancelling','cancelled','succeeded','failed','interrupted')")
        batch.add_column(sa.Column("params_schema_version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("input_snapshot_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("environment_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("code_version", sa.String(128)))
        batch.add_column(sa.Column("run_id", sa.String(36)))
        batch.add_column(sa.Column("worker_instance", sa.String(36)))
        batch.add_column(sa.Column("host_boot_id", sa.String(64)))
        batch.add_column(sa.Column("child_pid", sa.Integer()))
        batch.add_column(sa.Column("child_pgid", sa.Integer()))
        batch.add_column(sa.Column("cancel_requested_at", sa.String(32)))

    with op.batch_alter_table("artifacts", recreate="always") as batch:
        batch.drop_constraint("ck_artifacts_validation", type_="check")
        batch.create_check_constraint("ck_artifacts_validation_union", "validation_status IN ('pending','unverified','validated','passed','rejected','failed')")
    op.execute("UPDATE artifacts SET validation_status='unverified' WHERE validation_status='pending'")
    op.execute("UPDATE artifacts SET validation_status='passed' WHERE validation_status='validated'")
    op.execute("UPDATE artifacts SET validation_status='failed' WHERE validation_status='rejected'")
    with op.batch_alter_table("artifacts", recreate="always") as batch:
        batch.drop_constraint("ck_artifacts_validation_union", type_="check")
        batch.create_check_constraint("ck_artifacts_validation", "validation_status IN ('unverified','passed','failed')")
        batch.add_column(sa.Column("metadata_schema_version", sa.Integer(), nullable=False, server_default="1"))

    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("archived_at", sa.String(32)))


def downgrade() -> None:
    # 0002 accepts interrupted and records execution identity. Silent rollback
    # would erase safety evidence and remap terminal states. Require a reviewed
    # data migration instead of deleting/rewriting user rows implicitly.
    raise RuntimeError("0002 downgrade requires a reviewed migration of existing job and artifact data")
