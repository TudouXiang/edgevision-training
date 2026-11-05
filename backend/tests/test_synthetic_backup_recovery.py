"""Synthetic stopped-writer exercise, not an operational backup/restore utility.

No source-directory input; fresh fixture-owned SQLite/files only. No API,
Worker, guardian or writer runs during copying. Hashes detect accidental
corruption, not malicious modification of a backup and its manifest.
"""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
import pytest

BACKEND = Path(__file__).resolve().parents[1]
STAMP = "2026-11-04T00:00:00Z"
TABLES = ("alembic_version", "users", "sessions", "projects", "datasets", "jobs", "job_events", "metrics", "artifacts", "idempotency_keys")
DATASET = "datasets/synthetic-dataset"
RUN = "jobs/synthetic-job/runs/synthetic-run"
REPORT = f"{DATASET}/validations/synthetic-run/report.json"
LABEL = f"{DATASET}/validations/synthetic-run/snapshot/labels/train/sample.txt"
FILES = {
    f"{DATASET}/source.zip": b"synthetic bytes; not a usable ZIP\n",
    LABEL: b"0 0.5 0.5 0.2 0.2\n",
    f"{DATASET}/validations/synthetic-run/manifest.json": b'{"synthetic":true}\n',
    REPORT: b'{"synthetic":true,"valid":false}\n',
    f"{RUN}/input.json": b'{"synthetic":true}\n',
    f"{RUN}/logs.jsonl": b'{"message":"synthetic failure"}\n',
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def rows(db):
    return {table: db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in TABLES}


class SyntheticExercise:
    """Private harness with fresh owned temporary state; no external path input."""

    def __init__(self, monkeypatch):
        self.temporary = TemporaryDirectory(prefix="edgevision-synthetic-backup-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.snapshot = self.root / "snapshot"
        self.restored = self.root / "restored"
        monkeypatch.setenv("PLATFORM_DATA_ROOT", str(self.source))
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")
        self.db = sqlite3.connect(self.source / "platform.db")
        self.db.execute("PRAGMA foreign_keys=ON")
        assert self.db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        self.db.execute("PRAGMA wal_autocheckpoint=0")
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for key, content in FILES.items():
            path = self.source / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.insert("users", id="u", username="synthetic", password_hash="not-a-credential", role="user", is_active=1, created_at=STAMP)
        self.insert("sessions", id="s", user_id="u", token_hash="1" * 64, csrf_hash="2" * 64, expires_at=STAMP, created_at=STAMP)
        self.insert("projects", id="p", owner_id="u", name="synthetic", description="", task_type="detection", status="active", created_at=STAMP, updated_at=STAMP)
        self.insert("jobs", id="j", project_id="p", owner_id="u", kind="dataset_check", status="failed", payload_json="{}", created_at=STAMP, finished_at=STAMP, error_code="SYNTHETIC_ONLY")
        self.insert("datasets", id="d", project_id="p", version=1, name="synthetic", archive_key=f"{DATASET}/source.zip", snapshot_key=f"{DATASET}/validations/synthetic-run/snapshot", sha256=digest(self.source / f"{DATASET}/source.zip"), size_bytes=len(FILES[f"{DATASET}/source.zip"]), status="pending", report_key=REPORT, validation_job_id="j", counts_json="{}", classes_json="[]", manifest_json="{}", created_at=STAMP)
        self.insert("job_events", job_id="j", seq=1, kind="log", payload_json='{"message":"synthetic failure"}', created_at=STAMP)
        # Preservation fixture only, not actual training/metric evidence.
        self.insert("metrics", id="m", job_id="j", epoch=1, name="synthetic", value=0.125, created_at=STAMP)
        self.insert("artifacts", id="a", project_id="p", job_id="j", kind="dataset_report", format="json", storage_key=REPORT, sha256=digest(self.source / REPORT), size_bytes=len(FILES[REPORT]), validation_status="unverified", metadata_json='{"synthetic":true}', created_at=STAMP)
        self.insert("idempotency_keys", owner_id="u", request_key="synthetic", method="POST", path="/synthetic", body_sha256="3" * 64, job_id="j", created_at=STAMP)
        self.db.commit()
        self.expected_rows = rows(self.db)
        self.source_before = self.fingerprints(self.source)

    def insert(self, table, **values):
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        self.db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))

    @staticmethod
    def fingerprints(root):
        # Readers can update SHM coordination bytes. DB/WAL/application bytes
        # must stay unchanged while the idle keeper connection remains open.
        return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file() and p.name != "platform.db-shm"}

    def backup(self):
        assert not self.db.in_transaction
        if self.db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','cancelling')").fetchone()[0]:
            raise ValueError("fixture must have no active jobs")
        self.snapshot.mkdir()
        with closing(sqlite3.connect(f"{(self.source / 'platform.db').as_uri()}?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(self.snapshot / "platform.db")) as target:
                source.backup(target)
        for key in FILES:  # Fixed inventory; never user-supplied paths.
            destination = self.snapshot / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.source / key, destination)
        self.manifest = self.fingerprints(self.snapshot)
        (self.snapshot / "synthetic-manifest.json").write_text(json.dumps(self.manifest, sort_keys=True))

    def restore(self):
        manifest_file = self.snapshot / "synthetic-manifest.json"
        if not manifest_file.is_file() or json.loads(manifest_file.read_text()) != self.manifest:
            raise ValueError("snapshot manifest missing or changed")
        actual = self.fingerprints(self.snapshot)
        actual.pop("synthetic-manifest.json", None)
        if actual != self.manifest:
            raise ValueError("snapshot inventory or hash mismatch")
        with closing(sqlite3.connect(f"{(self.snapshot / 'platform.db').as_uri()}?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("snapshot database integrity failure")
        self.restored.mkdir()  # Never overwrite source or any existing restore.
        for key in self.manifest:
            destination = self.restored / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.snapshot / key, destination)

    def close(self):
        self.db.close()
        self.temporary.cleanup()


@pytest.fixture
def exercise(monkeypatch):
    harness = SyntheticExercise(monkeypatch)
    try:
        yield harness
    finally:
        harness.close()


def test_stopped_writer_snapshot_includes_committed_wal_and_files(exercise):
    e = exercise
    assert (e.source / "platform.db-wal").stat().st_size > 32
    bare = e.root / "bare.db"
    shutil.copyfile(e.source / "platform.db", bare)
    with closing(sqlite3.connect(bare)) as db:
        assert db.execute("SELECT count(*) FROM users").fetchone() == (0,)
    e.backup()
    e.restore()
    assert e.fingerprints(e.source) == e.source_before
    assert e.fingerprints(e.restored) == e.manifest
    with closing(sqlite3.connect(e.restored / "platform.db")) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert rows(db) == e.expected_rows
        key, expected_hash, size = db.execute("SELECT storage_key,sha256,size_bytes FROM artifacts").fetchone()
        assert digest(e.restored / key) == expected_hash
        assert (e.restored / key).stat().st_size == size
        archive, expected_hash = db.execute("SELECT archive_key,sha256 FROM datasets").fetchone()
        assert digest(e.restored / archive) == expected_hash
    for key, content in FILES.items():
        assert (e.restored / key).read_bytes() == content
    assert not (e.restored / "platform.db-wal").exists()


@pytest.mark.parametrize("key", ["platform.db", *FILES, "synthetic-manifest.json"])
@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_rejects_missing_or_corrupted_snapshot_before_restore(exercise, key, damage):
    e = exercise
    e.backup()
    path = e.snapshot / key
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"{}" if key.endswith(".json") else b"corrupt")
    with pytest.raises(ValueError):
        e.restore()
    assert not e.restored.exists()
    assert e.fingerprints(e.source) == e.source_before
    assert rows(e.db) == e.expected_rows


def test_rejects_unlisted_snapshot_file(exercise):
    exercise.backup()
    (exercise.snapshot / "unexpected.txt").write_text("unexpected")
    with pytest.raises(ValueError, match="inventory"):
        exercise.restore()
    assert not exercise.restored.exists()


def test_never_overwrites_existing_restore(exercise):
    exercise.backup()
    exercise.restored.mkdir()
    marker = exercise.restored / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        exercise.restore()
    assert marker.read_text() == "keep"
    assert list(exercise.restored.iterdir()) == [marker]


@pytest.mark.parametrize("status", ["queued", "running", "cancelling"])
def test_active_job_fixture_is_outside_exercise_precondition(exercise, status):
    exercise.db.execute("UPDATE jobs SET status=?", (status,))
    exercise.db.commit()
    with pytest.raises(ValueError, match="no active jobs"):
        exercise.backup()
    assert not exercise.snapshot.exists()


def test_foreign_key_violation_is_rejected_even_with_refreshed_hash(exercise):
    e = exercise
    e.backup()
    with closing(sqlite3.connect(e.snapshot / "platform.db")) as db, db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("UPDATE artifacts SET project_id='missing'")
    e.manifest = e.fingerprints(e.snapshot)
    e.manifest.pop("synthetic-manifest.json")
    (e.snapshot / "synthetic-manifest.json").write_text(json.dumps(e.manifest, sort_keys=True))
    with pytest.raises(ValueError, match="database integrity"):
        e.restore()
    assert not e.restored.exists()
    assert e.fingerprints(e.source) == e.source_before
