import os
from pathlib import Path

# Documented T010 ceilings. Upload/worker enforcement is T030/T040, not active.
MAX_DATASET_ZIP_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_IMAGE_PIXELS = 30_000_000


def data_root() -> Path:
    configured = os.environ.get("PLATFORM_DATA_ROOT")
    if configured is not None and not configured.strip():
        raise ValueError("PLATFORM_DATA_ROOT cannot be empty")
    root = Path(configured) if configured else Path(__file__).resolve().parents[2] / "data"
    return root.expanduser().resolve()


def db_path() -> Path:
    return data_root() / "platform.db"
