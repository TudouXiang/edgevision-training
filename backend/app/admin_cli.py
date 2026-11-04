"""Explicit local bootstrap for the first active administrator."""

import argparse
from getpass import getpass
import sqlite3
import sys
from uuid import uuid4

from .database import database_ready, transaction
from .security import password_hash, timestamp
from .services import begin_write


def create_admin(username: str, password: str) -> str:
    if not 1 <= len(username) <= 128:
        raise ValueError("username must be 1 to 128 characters")
    if not 12 <= len(password) <= 256:
        raise ValueError("password must be 12 to 256 characters")
    if not database_ready():
        raise RuntimeError("database is not migrated; run the migrate command first")
    user_id = str(uuid4())
    with transaction() as connection:
        begin_write(connection)
        if connection.execute("SELECT 1 FROM users WHERE role='admin' AND is_active=1 LIMIT 1").fetchone():
            raise RuntimeError("an active administrator already exists; use the authenticated admin API")
        try:
            connection.execute(
                "INSERT INTO users (id,username,password_hash,role,is_active,created_at) VALUES (?,?,?,?,1,?)",
                (user_id, username, password_hash(password), "admin", timestamp()),
            )
        except sqlite3.IntegrityError as exc:
            raise RuntimeError("username already exists") from exc
    return user_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize the first active EdgeVision administrator")
    parser.add_argument("--username", required=True)
    options = parser.parse_args(argv)
    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match", file=sys.stderr)
        return 2
    try:
        user_id = create_admin(options.username, password)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Administrator {options.username!r} created ({user_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
