"""Bounded immutable upload. Only a managed infer task may decode these bytes."""
import os
import sqlite3
from uuid import uuid4
from fastapi import HTTPException
from .config import data_root
from .database import transaction, database_ready
from .dataset_storage import UploadError, safe_directory, stage_multipart_upload
from .delivery_infer import MAX_IMAGE_BYTES
from .inference_files import verified_file
from .job_service import artifact_public, canonical
from .schemas import InferenceInputArtifactPublic
from .security import require_allowed_origin, require_actor, timestamp
from .services import project_for_actor, active_project


def image_format(filename):
    if not filename or len(filename) > 160 or filename != filename.strip() or '/' in filename or '\\' in filename or any(ord(c) < 32 or ord(c) == 127 for c in filename):
        raise UploadError(400, 'UPLOAD_FILENAME_INVALID', 'Image filename must be a simple basename of at most 160 characters')
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if extension not in {'jpg', 'jpeg', 'png'}:
        raise UploadError(415, 'IMAGE_TYPE_UNSUPPORTED', 'Only JPEG and PNG uploads are supported')
    return 'png' if extension == 'png' else 'jpeg'


async def upload(project_id, request):
    require_allowed_origin(request)
    if not database_ready(): raise HTTPException(503, {'code': 'NOT_READY', 'message': 'Database migration is unavailable'})
    with transaction() as connection:
        actor = require_actor(connection, request, csrf=True)
        active_project(project_for_actor(connection, project_id, actor))
    try:
        staged_path = safe_directory(data_root(), 'uploads') / (str(uuid4()) + '.part')
        staged = await stage_multipart_upload(request, staged_path, max_bytes=MAX_IMAGE_BYTES,
            filename_check=image_format,
            media_check=lambda filename, media: media in {b'application/octet-stream', b'image/' + image_format(filename).encode()},
            too_large_code='IMAGE_TOO_LARGE', type_code='IMAGE_TYPE_UNSUPPORTED',
            type_message='Image part media type must match its filename', empty_message='Image upload cannot be empty')
        declared = image_format(staged.filename)
        identifier = str(uuid4()); extension = 'png' if declared == 'png' else 'jpg'
        # Open/hash outside the sole writer reservation; retain this exact identity.
        with verified_file(staged.path, staged.size_bytes, staged.sha256, MAX_IMAGE_BYTES) as source:
            identity = os.fstat(source.fileno())
            with transaction() as connection:
                connection.execute('BEGIN IMMEDIATE')
                actor = require_actor(connection, request, csrf=True)
                active_project(project_for_actor(connection, project_id, actor))
                now = staged.path.lstat()
                if (now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) != (identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns):
                    raise ValueError('staging identity changed')
                directory = safe_directory(data_root(), 'images') / identifier
                directory.mkdir(mode=0o700, exist_ok=False)
                destination = directory / ('source.' + extension)
                os.rename(staged.path, destination)
                published = destination.lstat()
                if (published.st_dev, published.st_ino, published.st_size, published.st_mtime_ns) != (identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns):
                    raise ValueError('published upload identity changed')
                if os.name != 'nt':
                    descriptor = os.open(directory, os.O_RDONLY)
                    try: os.fsync(descriptor)
                    finally: os.close(descriptor)
                key = f'images/{identifier}/source.{extension}'
                metadata = {'schema_version': 1, 'declared_format': declared, 'validation_scope': 'bounded_upload_bytes'}
                connection.execute("INSERT INTO artifacts(id,project_id,job_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at) VALUES(?,?,NULL,'inference_input',?,?,?,?,'unverified',?,?)",
                    (identifier, project_id, declared, key, staged.sha256, staged.size_bytes, canonical(metadata), timestamp()))
                row = connection.execute('SELECT * FROM artifacts WHERE id=?', (identifier,)).fetchone()
                result = InferenceInputArtifactPublic.model_validate(artifact_public(row)).model_dump(mode='json')
        return result
    except UploadError as exc:
        raise HTTPException(exc.status_code, {'code': exc.code, 'message': exc.message}) from exc
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        # Any unpublished .part or renamed orphan remains isolated; never upgrade it.
        raise HTTPException(503, {'code': 'STORAGE_WRITE_FAILED', 'message': 'Image could not be stored and registered durably'}) from exc
