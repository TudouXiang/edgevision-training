"""Password and opaque server-session primitives for T020."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import re
import secrets
import sqlite3
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, Response

from .config import AuthSettings, CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, auth_settings

PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_dummy_hash: str | None = None
_TOKEN = re.compile(r"[A-Za-z0-9_-]{40,128}\Z")


@dataclass(frozen=True)
class Actor:
    id: str
    username: str
    role: str
    is_active: bool
    created_at: str
    session_id: str


@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def secret_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def password_hash(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def _verification_hash(stored_hash: str | None) -> str:
    global _dummy_hash
    if stored_hash is not None:
        return stored_hash
    if _dummy_hash is None:
        _dummy_hash = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
    return _dummy_hash


def password_matches(stored_hash: str | None, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(_verification_hash(stored_hash), password) and stored_hash is not None
    except (InvalidHashError, VerificationError):
        return False


def authenticate_password(connection: sqlite3.Connection, username: str, password: str) -> sqlite3.Row | None:
    row = connection.execute(
        "SELECT id,username,password_hash,role,is_active,created_at FROM users WHERE username=?",
        (username,),
    ).fetchone()
    stored_hash = row["password_hash"] if row is not None else None
    if not password_matches(stored_hash, password) or row is None or not row["is_active"]:
        return None
    if PASSWORD_HASHER.check_needs_rehash(stored_hash):
        connection.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), row["id"]))
    return row


def validated_settings() -> AuthSettings:
    try:
        return auth_settings()
    except ValueError as exc:
        raise HTTPException(
            503,
            {"code": "AUTH_CONFIGURATION_INVALID", "message": "Authentication configuration is invalid"},
        ) from exc


def require_allowed_origin(request: Request, settings: AuthSettings | None = None) -> AuthSettings:
    settings = settings or validated_settings()
    origin = request.headers.get("origin")
    if origin is None:
        raise HTTPException(403, {"code": "ORIGIN_REQUIRED", "message": "Origin header is required"})
    if origin == "null" or origin.rstrip("/") not in settings.allowed_origins:
        raise HTTPException(403, {"code": "ORIGIN_NOT_ALLOWED", "message": "Request origin is not allowed"})
    return settings


def create_session(connection: sqlite3.Connection, user_id: str, settings: AuthSettings) -> SessionTokens:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(seconds=settings.session_ttl_seconds)
    connection.execute(
        "INSERT INTO sessions (id,user_id,token_hash,csrf_hash,expires_at,created_at,revoked_at) VALUES (?,?,?,?,?,?,NULL)",
        (
            str(uuid4()),
            user_id,
            secret_hash(session_token),
            secret_hash(csrf_token),
            timestamp(expires_at),
            timestamp(),
        ),
    )
    return SessionTokens(session_token=session_token, csrf_token=csrf_token, expires_at=expires_at)


def set_session_cookies(response: Response, tokens: SessionTokens, settings: AuthSettings) -> None:
    max_age = max(0, int((tokens.expires_at - utc_now()).total_seconds()))
    common = {
        "max_age": max_age,
        "expires": tokens.expires_at,
        "path": "/",
        "secure": settings.cookie_secure,
        "samesite": "lax",
    }
    response.set_cookie(SESSION_COOKIE_NAME, tokens.session_token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE_NAME, tokens.csrf_token, httponly=False, **common)


def clear_session_cookies(response: Response, settings: AuthSettings) -> None:
    common = {"path": "/", "secure": settings.cookie_secure, "samesite": "lax"}
    response.delete_cookie(SESSION_COOKIE_NAME, httponly=True, **common)
    response.delete_cookie(CSRF_COOKIE_NAME, httponly=False, **common)


def require_actor(connection: sqlite3.Connection, request: Request, *, csrf: bool = False) -> Actor:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or _TOKEN.fullmatch(token) is None:
        raise HTTPException(401, {"code": "AUTH_REQUIRED", "message": "Authentication is required"})
    row = connection.execute(
        """
        SELECT s.id AS session_id,s.csrf_hash,s.expires_at,s.revoked_at,
               u.id,u.username,u.role,u.is_active,u.created_at
        FROM sessions AS s JOIN users AS u ON u.id=s.user_id
        WHERE s.token_hash=?
        """,
        (secret_hash(token),),
    ).fetchone()
    if (
        row is None
        or row["revoked_at"] is not None
        or not row["is_active"]
        or parse_timestamp(row["expires_at"]) <= utc_now()
    ):
        raise HTTPException(401, {"code": "SESSION_INVALID", "message": "Session is invalid or expired"})
    if csrf:
        csrf_header = request.headers.get("x-csrf-token")
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        if (
            not csrf_header
            or not csrf_cookie
            or _TOKEN.fullmatch(csrf_header) is None
            or _TOKEN.fullmatch(csrf_cookie) is None
            or not hmac.compare_digest(csrf_header, csrf_cookie)
            or not hmac.compare_digest(secret_hash(csrf_header), row["csrf_hash"])
        ):
            raise HTTPException(403, {"code": "CSRF_INVALID", "message": "CSRF token is missing or invalid"})
    return Actor(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        session_id=row["session_id"],
    )


def require_admin(actor: Actor) -> None:
    if actor.role != "admin":
        raise HTTPException(403, {"code": "ADMIN_REQUIRED", "message": "Administrator role is required"})


def revoke_session(connection: sqlite3.Connection, session_id: str) -> None:
    connection.execute(
        "UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
        (timestamp(), session_id),
    )


def revoke_user_sessions(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
        (timestamp(), user_id),
    )
