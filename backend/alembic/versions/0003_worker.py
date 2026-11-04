"""Add run-bound process/publication evidence without changing historical rows."""
from alembic import op
import sqlalchemy as sa

revision = "0003_worker"
down_revision = "0002_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("process_identity_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("launch_phase", sa.String(24), nullable=False, server_default="unverified"))
        batch.add_column(sa.Column("publication_json", sa.Text(), nullable=False, server_default="{}"))
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("validation_job_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_datasets_validation_job", "jobs", ["validation_job_id"], ["id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT 1 FROM jobs WHERE status IN ('queued','running','cancelling') LIMIT 1").first():
        raise RuntimeError("Stop and reconcile active tasks before downgrading")
    if connection.exec_driver_sql("SELECT 1 FROM datasets WHERE status='validating' LIMIT 1").first():
        raise RuntimeError("Reconcile validating datasets before downgrading")
    with op.batch_alter_table("datasets") as batch:
        batch.drop_constraint("fk_datasets_validation_job", type_="foreignkey")
        batch.drop_column("validation_job_id")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("publication_json")
        batch.drop_column("launch_phase")
        batch.drop_column("process_identity_json")
