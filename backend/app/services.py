"""Small database helpers shared by T020 routes and later authorization guards."""

from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from .security import Actor


def begin_write(connection: sqlite3.Connection) -> None:
    # Authenticate and mutate under one reserved-writer transaction so a
    # concurrent disable/revoke cannot slip between the two operations.
    connection.execute("BEGIN IMMEDIATE")


def user_public(row: sqlite3.Row | Actor) -> dict:
    return {
        "id": row.id if isinstance(row, Actor) else row["id"],
        "username": row.username if isinstance(row, Actor) else row["username"],
        "role": row.role if isinstance(row, Actor) else row["role"],
        "is_active": row.is_active if isinstance(row, Actor) else bool(row["is_active"]),
        "created_at": row.created_at if isinstance(row, Actor) else row["created_at"],
    }


def project_public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "name": row["name"],
        "description": row["description"],
        "archived_at": row["archived_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def dataset_public(row: sqlite3.Row) -> dict:
    try:
        classes = json.loads(row["classes_json"])
        counts = json.loads(row["counts_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(500, {"code": "DATASET_RECORD_INVALID", "message": "Dataset metadata is not readable"}) from exc
    if not isinstance(classes, list) or not all(isinstance(name, str) for name in classes):
        raise HTTPException(500, {"code": "DATASET_RECORD_INVALID", "message": "Dataset class metadata is invalid"})
    if not isinstance(counts, dict) or any(not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int) or value < 0 for key, value in counts.items()):
        raise HTTPException(500, {"code": "DATASET_RECORD_INVALID", "message": "Dataset count metadata is invalid"})
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "state": row["status"],
        "version": row["version"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "classes": classes,
        "counts": counts if row["status"] in {"ready", "invalid"} else None,
        "created_at": row["created_at"],
    }


def project_for_actor(connection: sqlite3.Connection, project_id: str, actor: Actor) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT id,owner_id,name,description,status,archived_at,created_at,updated_at
        FROM projects
        WHERE id=? AND (owner_id=? OR ?='admin')
        """,
        (project_id, actor.id, actor.role),
    ).fetchone()
    if row is None:
        # Do not reveal another user's object existence.
        raise HTTPException(404, {"code": "PROJECT_NOT_FOUND", "message": "Project was not found"})
    return row


def project_for_resource(
    connection: sqlite3.Connection,
    table: str,
    resource_id: str,
    actor: Actor,
) -> sqlite3.Row:
    if table not in {"datasets", "jobs", "artifacts"}:
        raise ValueError("unsupported resource table")
    row = connection.execute(
        f"""
        SELECT p.id,p.owner_id,p.name,p.description,p.status,p.archived_at,p.created_at,p.updated_at
        FROM {table} AS r JOIN projects AS p ON p.id=r.project_id
        WHERE r.id=? AND (p.owner_id=? OR ?='admin')
        """,
        (resource_id, actor.id, actor.role),
    ).fetchone()
    if row is None:
        raise HTTPException(404, {"code": "RESOURCE_NOT_FOUND", "message": "Resource was not found"})
    return row


def active_project(row: sqlite3.Row) -> None:
    if row["status"] == "archived" or row["archived_at"] is not None:
        raise HTTPException(409, {"code": "PROJECT_ARCHIVED", "message": "Archived projects do not accept new work"})
