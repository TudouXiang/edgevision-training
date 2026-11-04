"""Idempotent authorized export submission, freezing only trusted training outputs."""
from uuid import uuid4
from importlib.metadata import PackageNotFoundError
from fastapi import HTTPException
from .services import project_for_actor, project_for_resource, active_project
from .job_service import canonical, append_event
from .security import timestamp, require_actor
from .training_assets import digest_json
from .export_assets import capability, runtime_identity
from .export_contract import FrozenExport
from .export_inputs import source_snapshot, source_binding


def provenance(frozen, job_id, run_id):
    return {'schema_version': 1, 'job_id': job_id, 'run_id': run_id, 'input_sha256': digest_json(frozen),
        'parent_artifact_id': frozen['source_artifact_id'], 'source_job_id': frozen['source_job_id'],
        'source_sha256': frozen['source_sha256'], 'source_size_bytes': frozen['source_size_bytes'],
        'source_metadata_sha256': frozen['source_metadata_sha256'], 'source_training_input_sha256': frozen['source_training_input_sha256'],
        'training': frozen['source_metadata']['provenance'], 'runtime_binding': frozen['runtime_binding'], 'code_version': frozen['code_version']}


def submit_export(connection, actor, project_id, params, key, path, request):
    project = project_for_actor(connection, project_id, actor)
    values = params.model_dump(mode='json')
    body_hash = digest_json({'kind': 'export_onnx', 'params': values})
    def replay():
        previous = connection.execute("SELECT * FROM idempotency_keys WHERE owner_id=? AND request_key=? AND method='POST' AND path=?", (actor.id, key, path)).fetchone()
        if previous:
            if previous['body_sha256'] != body_hash:
                raise HTTPException(409, {'code': 'IDEMPOTENCY_CONFLICT', 'message': 'This key was used with different parameters'})
            old = connection.execute('SELECT id,status FROM jobs WHERE id=?', (previous['job_id'],)).fetchone()
            return {'job_id': old['id'], 'state': old['status']}
        return None
    previous = replay()
    if previous: return previous
    # Hashing the full immutable dataset may be slow. A read snapshot must not
    # hold SQLite's sole writer or block cancellation and unrelated requests.
    connection.execute('BEGIN')
    active_project(project)
    project_for_resource(connection, 'artifacts', values['model_artifact_id'], actor)
    if not connection.execute('SELECT 1 FROM artifacts WHERE id=? AND project_id=?', (values['model_artifact_id'], project_id)).fetchone():
        raise HTTPException(404, {'code': 'RESOURCE_NOT_FOUND', 'message': 'Model was not found in this project'})
    try:
        source = source_snapshot(connection, project_id, values['model_artifact_id'])
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, PackageNotFoundError) as exc:
        raise HTTPException(409, {'code': 'EXPORT_INPUT_UNAVAILABLE', 'message': 'Export requires an unchanged passed checkpoint from successful training'}) from exc
    if not capability()['available']:
        raise HTTPException(409, {'code': 'DELIVERY_SETUP_REQUIRED', 'message': 'A current operator-managed export probe is required'})
    try:
        identity = runtime_identity()
        frozen = FrozenExport.model_validate({'schema_version': 1, **source, 'params': values, 'runtime_binding': digest_json(identity), 'code_version': digest_json(identity['adapter'])}).model_dump(mode='json')
        binding = source_binding(connection, frozen)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, PackageNotFoundError) as exc:
        raise HTTPException(409, {'code': 'EXPORT_INPUT_UNAVAILABLE', 'message': 'Validated export inputs or runtime bindings changed'}) from exc
    connection.rollback()  # End the read snapshot before acquiring the writer.
    connection.execute('BEGIN IMMEDIATE')
    actor = require_actor(connection, request, csrf=True)
    project = project_for_actor(connection, project_id, actor)
    previous = replay()
    if previous: return previous
    active_project(project)
    try:
        unchanged = source_binding(connection, frozen) == binding
    except ValueError:
        unchanged = False
    if not unchanged:
        raise HTTPException(409, {'code': 'EXPORT_INPUT_UNAVAILABLE', 'message': 'Source records changed during validation'})
    job_id = str(uuid4())
    connection.execute("INSERT INTO jobs(id,project_id,owner_id,kind,status,payload_json,input_snapshot_json,code_version,created_at) VALUES(?,?,?,'export_onnx','queued',?,?,?,?)", (job_id, project_id, actor.id, canonical(values), canonical(frozen), frozen['code_version'], timestamp()))
    append_event(connection, job_id, 'status', {'status': 'queued'})
    connection.execute("INSERT INTO idempotency_keys(owner_id,request_key,method,path,body_sha256,job_id,created_at) VALUES(?,?,'POST',?,?,?,?)", (actor.id, key, path, body_hash, job_id, timestamp()))
    return {'job_id': job_id, 'state': 'queued'}
