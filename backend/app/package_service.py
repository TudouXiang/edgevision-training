"""Two-phase package submission; P availability never follows I implicitly."""
from importlib.metadata import PackageNotFoundError
from uuid import uuid4
from fastapi import HTTPException
from .contracts import TERMINAL_STATES
from .security import require_actor, timestamp
from .services import project_for_actor, project_for_resource, active_project
from .job_service import canonical, append_event
from .training_assets import digest_json
from .package_inputs import freeze_source, source_binding
from .package_contract import FrozenPackage
from .package_assets import capability, runtime_identity, validated_template


def provenance(frozen, job_id, run_id):
    model = frozen['model']
    return {'job_id': job_id, 'run_id': run_id, 'project_id': frozen['project_id'],
        'frozen_input_sha256': digest_json(frozen), 'onnx_artifact_id': model['source_artifact_id'],
        'export_job_id': model['source_job_id'], 'parent_artifact_id': model['export_input']['source_artifact_id'],
        'model_sha256': model['source_sha256'], 'model_size_bytes': model['source_size_bytes'],
        'model_metadata_sha256': model['source_metadata_sha256'],
        'runtime_binding': frozen['runtime_binding'], 'code_version': frozen['code_version']}


def submit_package(connection, actor, project_id, params, retry_id, key, path, request):
    project = project_for_actor(connection, project_id, actor)
    values = params.model_dump(mode='json')
    body_hash = digest_json({'kind': 'package', 'params': values, 'source_job_id': retry_id})
    def replay():
        previous = connection.execute("SELECT * FROM idempotency_keys WHERE owner_id=? AND request_key=? AND method='POST' AND path=?", (actor.id,key,path)).fetchone()
        if not previous: return None
        if previous['body_sha256'] != body_hash:
            raise HTTPException(409, {'code':'IDEMPOTENCY_CONFLICT','message':'This key was used with different parameters'})
        old = connection.execute('SELECT id,status FROM jobs WHERE id=?',(previous['job_id'],)).fetchone()
        return {'job_id':old['id'],'state':old['status']}
    def retry():
        if retry_id is None: return
        old = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='package'",(retry_id,project_id)).fetchone()
        if not old or old['status'] not in {state.value for state in TERMINAL_STATES}:
            raise HTTPException(409, {'code':'PACKAGE_INPUT_UNAVAILABLE','message':'Retry source must be a terminal package job in this project'})
    previous = replay()
    if previous: return previous
    connection.execute('BEGIN'); active_project(project); retry()
    identifier = values['onnx_artifact_id']
    project_for_resource(connection,'artifacts',identifier,actor)
    model = connection.execute('SELECT kind,format FROM artifacts WHERE id=? AND project_id=?',(identifier,project_id)).fetchone()
    if model is None: raise HTTPException(404, {'code':'RESOURCE_NOT_FOUND','message':'Input was not found in this project'})
    if (model['kind'],model['format']) != ('onnx','onnx'):
        raise HTTPException(409, {'code':'PACKAGE_INPUT_UNAVAILABLE','message':'A trusted ONNX export is required'})
    if not capability()['available']:
        raise HTTPException(409, {'code':'PACKAGE_SETUP_REQUIRED','message':'Current independent package runtime proof is required'})
    try:
        identity = runtime_identity(); proof = validated_template()
        if proof['template'] != identity['package_template']: raise ValueError('template proof stale')
        frozen = FrozenPackage.model_validate({'schema_version':1,'project_id':project_id,
            'model':freeze_source(connection,project_id,identifier),'params':values,'template':identity['package_template'],
            'runtime_binding':digest_json(identity),'code_version':digest_json(identity['adapter']),
            'template_validation_sha256':proof['record_sha256']}).model_dump(mode='json')
        binding = source_binding(connection,frozen)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,PackageNotFoundError) as exc:
        raise HTTPException(409, {'code':'PACKAGE_INPUT_UNAVAILABLE','message':'Package sources or validation changed'}) from exc
    connection.rollback(); connection.execute('BEGIN IMMEDIATE')
    actor = require_actor(connection,request,csrf=True)
    project = project_for_actor(connection,project_id,actor)
    previous = replay()
    if previous: return previous
    active_project(project); retry()
    try: unchanged = source_binding(connection,frozen) == binding
    except ValueError: unchanged = False
    if not unchanged:
        raise HTTPException(409, {'code':'PACKAGE_INPUT_UNAVAILABLE','message':'Source records changed during validation'})
    identifier = str(uuid4())
    connection.execute("INSERT INTO jobs(id,project_id,owner_id,kind,status,payload_json,input_snapshot_json,code_version,retry_of_id,created_at) VALUES(?,?,?,'package','queued',?,?,?,?,?)",
        (identifier,project_id,actor.id,canonical(values),canonical(frozen),frozen['code_version'],retry_id,timestamp()))
    append_event(connection,identifier,'status',{'status':'queued'})
    connection.execute("INSERT INTO idempotency_keys(owner_id,request_key,method,path,body_sha256,job_id,created_at) VALUES(?,?,'POST',?,?,?,?)",(actor.id,key,path,body_hash,identifier,timestamp()))
    return {'job_id':identifier,'state':'queued'}
