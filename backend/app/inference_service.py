"""Two-phase, idempotent inference submission without holding the writer for hashes."""
from importlib.metadata import PackageNotFoundError
from uuid import uuid4
from fastapi import HTTPException
from .contracts import TERMINAL_STATES
from .security import require_actor, timestamp
from .services import project_for_actor, project_for_resource, active_project
from .job_service import canonical, append_event
from .training_assets import digest_json
from .inference_inputs import model_snapshot, image_snapshot, source_binding
from .inference_contract import FrozenInference
from .inference_assets import capability, runtime_identity


def job_source(frozen):
    return {'model_artifact_id': frozen['model']['source_artifact_id'], 'model_job_id': frozen['model']['source_job_id'],
        'model_sha256': frozen['model']['source_sha256'], 'image_artifact_id': frozen['image']['artifact_id'],
        'image_sha256': frozen['image']['image_sha256'], 'params': frozen['params'], 'protocol': frozen['protocol'],
        'runtime_binding': frozen['runtime_binding'], 'code_version': frozen['code_version']}


def provenance(frozen, job_id, run_id):
    model, image = frozen['model'], frozen['image']
    return {'schema_version': 1, 'job_id': job_id, 'run_id': run_id, 'project_id': frozen['project_id'],
        'frozen_input_sha256': digest_json(frozen), 'model_artifact_id': model['source_artifact_id'],
        'model_job_id': model['source_job_id'], 'model_sha256': model['source_sha256'],
        'model_size_bytes': model['source_size_bytes'], 'model_metadata_sha256': model['source_metadata_sha256'],
        'image_artifact_id': image['artifact_id'], 'image_sha256': image['image_sha256'], 'image_size_bytes': image['image_size_bytes'],
        'runtime_binding': frozen['runtime_binding'], 'code_version': frozen['code_version']}


def submit_inference(connection, actor, project_id, params, retry_id, key, path, request):
    project = project_for_actor(connection, project_id, actor)
    values = params.model_dump(mode='json')
    body_hash = digest_json({'kind': 'infer', 'params': values, 'source_job_id': retry_id})
    def replay():
        previous = connection.execute("SELECT * FROM idempotency_keys WHERE owner_id=? AND request_key=? AND method='POST' AND path=?", (actor.id, key, path)).fetchone()
        if not previous: return None
        if previous['body_sha256'] != body_hash:
            raise HTTPException(409, {'code': 'IDEMPOTENCY_CONFLICT', 'message': 'This key was used with different parameters'})
        old = connection.execute('SELECT id,status FROM jobs WHERE id=?', (previous['job_id'],)).fetchone()
        return {'job_id': old['id'], 'state': old['status']}
    def retry():
        if retry_id is None: return
        old = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='infer'", (retry_id, project_id)).fetchone()
        if not old or old['status'] not in {state.value for state in TERMINAL_STATES}:
            raise HTTPException(409, {'code': 'INFERENCE_INPUT_UNAVAILABLE', 'message': 'Retry source must be a terminal inference in this project'})
    previous = replay()
    if previous: return previous
    connection.execute('BEGIN'); active_project(project); retry()
    for identifier in (values['model_artifact_id'], values['image_artifact_id']):
        project_for_resource(connection, 'artifacts', identifier, actor)
        if not connection.execute('SELECT 1 FROM artifacts WHERE id=? AND project_id=?', (identifier, project_id)).fetchone():
            raise HTTPException(404, {'code': 'RESOURCE_NOT_FOUND', 'message': 'Input was not found in this project'})
    model = connection.execute('SELECT kind,format FROM artifacts WHERE id=?', (values['model_artifact_id'],)).fetchone()
    if (values['backend'] == 'pt' and (model['kind'] not in {'pt_best', 'pt_last'} or model['format'] != 'pt')) or (values['backend'] == 'onnx' and (model['kind'], model['format']) != ('onnx', 'onnx')):
        raise HTTPException(409, {'code': 'MODEL_BACKEND_MISMATCH', 'message': 'Selected model and backend do not match'})
    if not capability()['available']:
        raise HTTPException(409, {'code': 'INFERENCE_SETUP_REQUIRED', 'message': 'Current managed dual-mode image probe is required'})
    try:
        identity = runtime_identity()
        frozen = FrozenInference.model_validate({'schema_version': 1, 'protocol': 'detection-image-v1', 'project_id': project_id,
            'model': model_snapshot(connection, project_id, values['model_artifact_id'], values['backend']),
            'image': image_snapshot(connection, project_id, values['image_artifact_id']), 'params': values,
            'runtime_binding': digest_json(identity), 'code_version': digest_json(identity['adapter'])}).model_dump(mode='json')
        binding = source_binding(connection, frozen)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, PackageNotFoundError) as exc:
        raise HTTPException(409, {'code': 'INFERENCE_INPUT_UNAVAILABLE', 'message': 'Inference sources or runtime changed'}) from exc
    connection.rollback(); connection.execute('BEGIN IMMEDIATE')
    actor = require_actor(connection, request, csrf=True)
    project = project_for_actor(connection, project_id, actor)
    previous = replay()
    if previous: return previous
    active_project(project); retry()
    try: unchanged = source_binding(connection, frozen) == binding
    except ValueError: unchanged = False
    if not unchanged:
        raise HTTPException(409, {'code': 'INFERENCE_INPUT_UNAVAILABLE', 'message': 'Source records changed during validation'})
    identifier = str(uuid4())
    connection.execute("INSERT INTO jobs(id,project_id,owner_id,kind,status,payload_json,input_snapshot_json,code_version,retry_of_id,created_at) VALUES(?,?,?,'infer','queued',?,?,?,?,?)",
        (identifier, project_id, actor.id, canonical(values), canonical(frozen), frozen['code_version'], retry_id, timestamp()))
    append_event(connection, identifier, 'status', {'status': 'queued'})
    connection.execute("INSERT INTO idempotency_keys(owner_id,request_key,method,path,body_sha256,job_id,created_at) VALUES(?,?,'POST',?,?,?,?)", (actor.id, key, path, body_hash, identifier, timestamp()))
    return {'job_id': identifier, 'state': 'queued'}
