import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

# Dataset limits are enforced by the T030 staging/validation core. T040 owns
# invoking the full validator from a Worker and publishing a ready snapshot.
MAX_DATASET_ZIP_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_CENTRAL_DIRECTORY_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200
MAX_IMAGE_PIXELS = 30_000_000
MAX_IMAGE_FILE_BYTES = 50 * 1024 * 1024
MAX_DATASET_YAML_BYTES = 64 * 1024
MAX_LABEL_FILE_BYTES = 4 * 1024 * 1024
MAX_LABEL_LINE_BYTES = 4096
MAX_LABELS_PER_FILE = 100_000
MAX_PREVIEW_SAMPLES = 100
MAX_PREVIEW_ANNOTATIONS = 200
MAX_MULTIPART_OVERHEAD_BYTES = 128 * 1024

SESSION_COOKIE_NAME = "edgevision_session"
CSRF_COOKIE_NAME = "edgevision_csrf"
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


@dataclass(frozen=True)
class AuthSettings:
    allowed_origins: frozenset[str]
    cookie_secure: bool
    session_ttl_seconds: int


def _boolean_setting(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def auth_settings() -> AuthSettings:
    """Read and validate the cookie/origin boundary without permissive fallbacks."""
    configured = os.environ.get("EDGEVISION_ALLOWED_ORIGINS")
    origins = tuple(part.strip() for part in configured.split(",")) if configured is not None else DEFAULT_ALLOWED_ORIGINS
    if not origins or any(not origin for origin in origins):
        raise ValueError("EDGEVISION_ALLOWED_ORIGINS must contain explicit origins")
    secure = _boolean_setting("EDGEVISION_COOKIE_SECURE", False)
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            parsed.port  # Force validation of malformed and out-of-range ports.
        except ValueError as exc:
            raise ValueError("EDGEVISION_ALLOWED_ORIGINS contains an invalid origin") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or origin == "null"
        ):
            raise ValueError("EDGEVISION_ALLOWED_ORIGINS contains an invalid origin")
        is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme == "http" and not is_loopback:
            raise ValueError("non-loopback origins must use HTTPS")
        if parsed.scheme == "https" and not secure:
            raise ValueError("HTTPS origins require EDGEVISION_COOKIE_SECURE=true")
    ttl_text = os.environ.get("EDGEVISION_SESSION_TTL_SECONDS", "43200")
    if not ttl_text.isdecimal() or not 300 <= int(ttl_text) <= 604800:
        raise ValueError("EDGEVISION_SESSION_TTL_SECONDS must be between 300 and 604800")
    return AuthSettings(frozenset(origin.rstrip("/") for origin in origins), secure, int(ttl_text))


def data_root() -> Path:
    configured = os.environ.get("PLATFORM_DATA_ROOT")
    if configured is not None and not configured.strip():
        raise ValueError("PLATFORM_DATA_ROOT cannot be empty")
    root = Path(configured) if configured else Path(__file__).resolve().parents[2] / "data"
    return root.expanduser().resolve()


def db_path() -> Path:
    return data_root() / "platform.db"
