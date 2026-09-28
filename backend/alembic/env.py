from alembic import context
from sqlalchemy import engine_from_config, event, pool

from app.config import db_path
from app.models import Base

config = context.config
db_path().parent.mkdir(mode=0o700, parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path()}")
target_metadata = Base.metadata  # Revisions are explicit; inspect models, never create_all.


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable, "connect")
    def sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        # Batch migrations recreate tables referenced by foreign keys. Disable
        # enforcement on this isolated migration connection only; check every
        # relationship before allowing the upgraded schema to be used.
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Migration created {len(violations)} foreign-key violations")
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            raise RuntimeError("Could not re-enable SQLite foreign keys after migration")
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
