"""Synthetic/lightweight I fixtures. No fixture is a real model or inference proof."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from uuid import uuid4
import pytest
from PIL import Image
from app import inference_service, inference_publication, inference_assets
from app.database import transaction
from app.run_files import run_directory, atomic_json, fingerprint
from app.training_assets import digest_json
from app.inference_contract import FrozenInference
from app.inference_inputs import copy_input
from app.inference_service import provenance
from app.delivery_infer import decode_image, preprocess, preview_png
from app.worker import claim, get_job
from test_export import export_ready, bundle as export_bundle, IDENTITY
from test_training import ready
from test_dataset_api import data_root, headers, create_user


@pytest.fixture
def inference_ready(export_ready, monkeypatch):
    from app.export_publication import publish
    job, _ = export_bundle(export_ready); assert publish(job)
    with transaction() as c:
        onnx = dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='onnx'", (job['id'],)).fetchone())
    client, project, _, _ = export_ready[0]
    stream = BytesIO(); Image.new('RGB', (3, 2), (40, 100, 200)).save(stream, format='PNG')
    response = client.post(f'/api/v1/projects/{project}/images', headers=headers(client), files={'file': ('image.png', stream.getvalue(), 'image/png')})
    assert response.status_code == 201, response.text
    monkeypatch.setattr(inference_service, 'capability', lambda: {'available': True})
    monkeypatch.setattr(inference_service, 'runtime_identity', lambda: IDENTITY)
    monkeypatch.setattr(inference_publication, 'runtime_identity', lambda: IDENTITY)
    return export_ready[0], export_ready[1], onnx, response.json()


def post(context, key='infer', backend='pt', **changes):
    ready, pt, onnx, image = context
    client, project, _, _ = ready
    retry = changes.pop('source_job_id', None)
    return client.post(f'/api/v1/projects/{project}/jobs', headers={**headers(client), 'Idempotency-Key': key}, json={'kind': 'infer',
        'params': {'model_artifact_id': (pt if backend == 'pt' else onnx)['id'], 'image_artifact_id': image['id'], 'backend': backend, **changes}, 'source_job_id': retry})


def bundle(context, backend='pt'):
    response = post(context, backend=backend); assert response.status_code == 202, response.text
    identifier = response.json()['job_id']; assert claim('inference-fixture', None)[0] == identifier
    job = get_job(identifier); frozen = json.loads(job['input_snapshot_json'])
    directory = run_directory(identifier, job['run_id'], create=True)
    atomic_json(directory/'input.json', {'schema_version': 1, 'job_id': identifier, 'run_id': job['run_id'], 'kind': 'infer', 'input': frozen})
    _, image_path = copy_input(frozen, directory)
    rgb, image = decode_image(image_path, 'png'); _, geometry = preprocess(rgb); preview, size = preview_png(rgb)
    versions = {'pillow': '12.3.0', 'numpy': '2.5.4', 'torch': '2.15.0+cpu' if backend=='pt' else None,
                'torchvision': '0.29.2+cpu' if backend=='pt' else None, 'ultralytics': '8.4.202' if backend=='pt' else None,
                'onnx': '1.23.2' if backend=='onnx' else None, 'onnxruntime': '1.31.1' if backend=='onnx' else None}
    provider = 'pytorch_cpu' if backend == 'pt' else 'CPUExecutionProvider'
    document = {'schema_version': 1, 'protocol': 'detection-image-v1', 'provenance': provenance(frozen, identifier, job['run_id']),
        'params': frozen['params'], 'image_width': rgb.width, 'image_height': rgb.height, 'backend': backend, 'provider': provider,
        'classes': frozen['model']['source_metadata']['classes'], 'image': image, 'preprocess': geometry,
        'runtime': {'backend': backend, 'provider': provider, 'device': 'cpu', 'threads': 2, 'interop_threads': 1, 'warmup_runs': 0,
                    'versions': versions, 'raw_sha256': 'a'*64, 'raw_elements': (4+len(frozen['model']['source_metadata']['classes']))*8400},
        'preview': {'width': size[0], 'height': size[1], 'size_bytes': len(preview), 'sha256': sha256(preview).hexdigest(), 'format': 'png'},
        'counts': {'candidates': 0, 'candidate_truncated': 0, 'nms_kept': 0, 'result_truncated': 0, 'clip_removed': 0},
        'timings': {'unit': 'ms', 'decode': 1., 'preprocess': 1., 'load': 1., 'infer': 1., 'postprocess': 1., 'total': 5.}, 'detections': []}
    output = directory/'bundle'; output.mkdir(); (output/'preview.png').write_bytes(preview)
    atomic_json(output/'result.json', document)
    size, digest = fingerprint(output/'result.json')
    atomic_json(output/'metadata.json', {'schema_version': 1, 'protocol': 'detection-image-v1', 'provenance': document['provenance'],
        'preview': document['preview'], 'result_size_bytes': size, 'result_sha256': digest, 'validation_scope': 'real_single_image_inference'})
    seal(job, directory)
    return job, directory


def seal(job, directory):
    outputs = [{'path': name, 'size_bytes': fingerprint(directory/'bundle'/name)[0], 'sha256': fingerprint(directory/'bundle'/name)[1]} for name in ('result.json','metadata.json','preview.png')]
    atomic_json(directory/'evidence.json', {'schema_version': 1, 'job_id': job['id'], 'run_id': job['run_id'], 'frozen_input_sha256': digest_json(json.loads(job['input_snapshot_json'])), 'outputs': outputs})


@pytest.mark.parametrize('backend', ['pt', 'onnx'])
def test_idempotency_publication_download_and_unmodified_input(inference_ready, backend):
    context = inference_ready; client, project, _, _ = context[0]
    job, directory = bundle(context, backend)
    assert post(context, backend=backend).json()['job_id'] == job['id']
    assert post(context, backend=backend, confidence=.5).status_code == 409
    assert inference_publication.publish(job)
    with transaction() as c:
        artifact = dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='inference_result'", (job['id'],)).fetchone())
        image = c.execute('SELECT * FROM artifacts WHERE id=?', (context[3]['id'],)).fetchone()
        assert image['validation_status'] == 'unverified' and image['job_id'] is None
    response = client.get('/api/v1/inferences/'+artifact['id']); assert response.status_code == 200, response.text
    assert response.json()['artifact_id'] == artifact['id'] and response.json()['detections'] == []
    assert response.json()['backend'] == backend
    preview = client.get(response.json()['image_url']); assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
    assert sha256(preview.content).hexdigest() == response.json()['preview']['sha256']
    assert client.get('/api/v1/artifacts/'+artifact['id']+'/download').status_code == 200
    assert client.get('/api/v1/artifacts/'+context[3]['id']+'/download').status_code == 409
    assert client.get('/api/v1/inferences/'+context[3]['id']).status_code == 404
    assert client.get('/api/v1/jobs/'+job['id']).json()['inference']['image_artifact_id'] == context[3]['id']
    # Historical reads need no current runtime/source model capability.
    monkey = pytest.MonkeyPatch(); monkey.setattr(inference_assets, 'runtime_identity', lambda: (_ for _ in ()).throw(ValueError('stale')))
    try: assert client.get('/api/v1/inferences/'+artifact['id']).status_code == 200
    finally: monkey.undo()
    other = create_user(client, 'inference-other')
    assert other.get('/api/v1/inferences/'+artifact['id']).status_code == 404


@pytest.mark.parametrize('fault', ['image', 'model', 'metadata', 'train_status', 'parent', 'sibling', 'extra'])
def test_source_changes_rejected(inference_ready, fault):
    from app.config import data_root as root
    ready, pt, onnx, image = inference_ready
    with transaction() as c:
        if fault == 'image': (root()/c.execute('SELECT storage_key FROM artifacts WHERE id=?', (image['id'],)).fetchone()[0]).write_bytes(b'changed')
        elif fault == 'model': (root()/onnx['storage_key']).write_bytes(b'changed')
        elif fault == 'metadata': c.execute("UPDATE artifacts SET metadata_json='{}' WHERE id=?", (onnx['id'],))
        elif fault == 'train_status': c.execute("UPDATE jobs SET status='failed' WHERE id=?", (pt['job_id'],))
        elif fault == 'parent': (root()/pt['storage_key']).write_bytes(b'changed')
        elif fault == 'sibling': (root()/pt['storage_key']).with_name('last.pt').write_bytes(b'changed')
        else: (root()/onnx['storage_key']).with_name('unexpected').write_bytes(b'x')
    response = post(inference_ready, backend='onnx')
    assert response.status_code == 409 and response.json()['error']['code'] == 'INFERENCE_INPUT_UNAVAILABLE'


@pytest.mark.parametrize('fault', ['missing', 'changed', 'extra', 'symlink', 'evidence', 'source', 'copy', 'runtime', 'no_drain'])
def test_bad_bundle_never_publishes(inference_ready, monkeypatch, fault):
    job, directory = bundle(inference_ready); output=directory/'bundle'
    if fault == 'missing': (output/'preview.png').unlink()
    elif fault == 'changed': (output/'result.json').write_text('{}')
    elif fault == 'extra': (output/'extra').write_bytes(b'no')
    elif fault == 'symlink':
        (output/'preview.png').unlink(); (output/'preview.png').symlink_to(output/'result.json')
    elif fault == 'evidence':
        proof=json.loads((directory/'evidence.json').read_text()); proof['run_id']=str(uuid4()); atomic_json(directory/'evidence.json',proof)
    elif fault == 'source':
        from app.config import data_root as root
        (root()/inference_ready[1]['storage_key']).write_bytes(b'bad')
    elif fault == 'copy': (directory/'image.png').write_bytes(b'bad')
    elif fault == 'runtime': monkeypatch.setattr(inference_publication, 'runtime_identity', lambda: {'changed':True})
    else: monkeypatch.setattr('app.worker.drain_receipt',lambda *a,**kw:None)
    with pytest.raises((ValueError,OSError)): inference_publication.publish(job)
    with transaction() as c: assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(job['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('window', ['before_intent', 'after_rename', 'cas_failure'])
def test_cancel_publication_races(inference_ready, monkeypatch, window):
    job,_=bundle(inference_ready); client=inference_ready[0][0]
    def cancel(): client.post('/api/v1/jobs/'+job['id']+'/cancel',headers=headers(client))
    if window=='before_intent': cancel()
    elif window=='cas_failure': monkeypatch.setattr(inference_publication,'transition',lambda *a,**kw:False)
    else:
        rename=inference_publication.os.rename
        def race(source,destination): rename(source,destination);cancel()
        monkeypatch.setattr(inference_publication.os,'rename',race)
    if window=='cas_failure':
        with pytest.raises(RuntimeError): inference_publication.publish(job)
    else: assert not inference_publication.publish(job)
    with transaction() as c: assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(job['id'],)).fetchone()[0] == 0


def test_auth_archive_retry_mismatch_and_closed_capability(inference_ready, monkeypatch):
    client, project, _, _ = inference_ready[0]
    assert post(inference_ready, model_artifact_id=inference_ready[2]['id']).json()['error']['code']=='MODEL_BACKEND_MISMATCH'
    monkeypatch.setattr(inference_service,'capability',lambda:{'available':False})
    assert post(inference_ready).json()['error']['code']=='INFERENCE_SETUP_REQUIRED'
    monkeypatch.setattr(inference_service,'capability',lambda:{'available':True})
    first=post(inference_ready).json()['job_id']
    assert post(inference_ready,key='retry',source_job_id=first).status_code==409
    client.post('/api/v1/jobs/'+first+'/cancel',headers=headers(client))
    retried=post(inference_ready,key='retry',source_job_id=first)
    assert retried.status_code==202 and retried.json()['job_id']!=first
    client.post(f'/api/v1/projects/{project}/archive',headers=headers(client))
    assert post(inference_ready).json()['job_id']==first
    assert post(inference_ready,key='new').status_code==409
    assert client.post(f'/api/v1/projects/{project}/images',headers=headers(client),files={'file':('image.png',b'x','image/png')}).status_code==409


@pytest.mark.parametrize('field', ['metadata_origin', 'metadata_classes', 'epochs', 'metadata_digest', 'training_digest'])
def test_frozen_pt_cross_binding(inference_ready, field):
    from app.inference_inputs import model_snapshot
    from app.inference_contract import TrustedPT
    with transaction() as c: value=model_snapshot(c,inference_ready[1]['project_id'],inference_ready[1]['id'],'pt')
    if field=='metadata_origin': value['source_metadata']['provenance']['dataset_id']=str(uuid4())
    elif field=='metadata_classes': value['source_metadata']['provenance']['classes']=['wrong']
    elif field=='epochs': value['source_metadata']['runtime']['completed_epochs']+=1
    elif field=='metadata_digest': value['source_metadata_sha256']='0'*64
    else: value['source_training_input_sha256']='0'*64
    with pytest.raises(ValueError): TrustedPT.model_validate(value)


@pytest.mark.parametrize('behavior',['tree','worker_lost','pre_go','exit_zero'])
def test_real_managed_inference_lifecycle(inference_ready,behavior):
    from test_worker_process import start,run_path,wait_marker,stop_and_reap,record,wait_until
    from test_worker_api import work
    from app.process_identity import exited
    client=inference_ready[0][0]; identifier=post(inference_ready).json()['job_id']
    process=start('infer_'+('tree' if behavior=='worker_lost' else behavior)); directory=run_path(identifier)
    try:
        if behavior=='exit_zero':
            assert process.wait(timeout=20)==0
            assert record(identifier)['status']=='failed' and record(identifier)['error_code']=='OUTPUT_INVALID'
        elif behavior=='pre_go':
            wait_marker(directory,'worker-before-go.json');client.post('/api/v1/jobs/'+identifier+'/cancel',headers=headers(client));(directory/'release-worker').touch()
            assert process.wait(timeout=20)==0 and record(identifier)['status']=='cancelled'
            assert not (directory/'started.json').exists()
        else:
            wait_marker(directory,'grandchild.json')
            if behavior=='worker_lost':
                process.kill();process.wait(timeout=10);receipt=wait_marker(directory,'drained.json');wait_until(lambda:exited(receipt['guardian']));work()
                assert record(identifier)['status']=='interrupted'
            else:
                client.post('/api/v1/jobs/'+identifier+'/cancel',headers=headers(client));assert process.wait(timeout=20)==0
                assert record(identifier)['status']=='cancelled'
        with transaction() as c:
            assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(identifier,)).fetchone()[0]==0
            assert c.execute('SELECT validation_status FROM artifacts WHERE id=?',(inference_ready[3]['id'],)).fetchone()[0]=='unverified'
    finally:stop_and_reap(process)


@pytest.mark.parametrize('code',[80,85,86,87,88,89,90,91])
def test_managed_inference_errors_are_structured(inference_ready,code):
    from test_worker_process import start,stop_and_reap,record
    from app.inference_errors import INFERENCE_EXIT_ERRORS
    identifier=post(inference_ready).json()['job_id'];process=start('infer_inference_code_'+str(code))
    try:
        assert process.wait(timeout=20)==0
        assert record(identifier)['status']=='failed' and record(identifier)['error_code']==INFERENCE_EXIT_ERRORS[code]
    finally:stop_and_reap(process)


@pytest.mark.parametrize('preview',[False,True])
@pytest.mark.parametrize('fault',['deleted','symlink'])
def test_http_download_open_race_is_normalized(inference_ready,monkeypatch,preview,fault):
    from app import inference_download
    from app.config import data_root as root
    job,_=bundle(inference_ready);assert inference_publication.publish(job)
    with transaction() as c:row=dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='inference_result'",(job['id'],)).fetchone())
    original=inference_download.verified_result
    def raced(value):
        document,intent=original(value)
        target=root()/intent['bundle_key']/('preview.png' if preview else 'result.json')
        target.unlink()
        if fault=='symlink':target.symlink_to(root()/intent['bundle_key']/'metadata.json')
        return document,intent
    monkeypatch.setattr(inference_download,'verified_result',raced)
    url='/api/v1/inferences/'+row['id']+'/image' if preview else '/api/v1/artifacts/'+row['id']+'/download'
    response=inference_ready[0][0].get(url)
    assert response.status_code==409 and response.json()['error']['code']=='ARTIFACT_UNAVAILABLE'


@pytest.mark.parametrize('backend',['pt','onnx'])
def test_embedded_legacy_scalars_cannot_be_coerced(inference_ready,backend):
    from app.inference_inputs import model_snapshot
    from app.inference_contract import TrustedPT,TrustedOnnx
    model=inference_ready[1] if backend=='pt' else inference_ready[2]
    with transaction() as c:value=model_snapshot(c,model['project_id'],model['id'],backend)
    target=value['training_input'] if backend=='pt' else value['export_input']['training_input']
    target['dataset_version']=True
    with pytest.raises(ValueError):(TrustedPT if backend=='pt' else TrustedOnnx).model_validate(value)


@pytest.mark.parametrize('stage,error,expected',[
    ('initial_source',OSError,70),('initial_source',ValueError,66),('runtime',ValueError,67),
    ('runtime',OSError,70),('copy',ValueError,66),('copy',OSError,70),
    ('final_source',ValueError,66),('final_source',OSError,70),('final_copy',ValueError,66),('final_copy',OSError,70)])
def test_execute_maps_stage_errors_without_native_execution(inference_ready,monkeypatch,stage,error,expected):
    from app import inference_runner, inference_runtime
    from app.task_process import execute
    from contextlib import contextmanager
    job,directory=bundle(inference_ready);frozen=json.loads(job['input_snapshot_json'])
    fields=json.loads((directory/'bundle'/'result.json').read_text())
    fields={key:value for key,value in fields.items() if key not in {'schema_version','protocol','params','provenance'}}
    calls=0
    def verify(value):
        nonlocal calls
        calls+=1
        if (stage=='initial_source' and calls==1) or (stage=='final_source' and calls==2):raise error('private fixture message')
        return frozen
    def runtime():
        if stage=='runtime':raise error('private fixture message')
        return IDENTITY
    def copy(*args):
        if stage=='copy':raise error('private fixture message')
        return directory/'model.pt',directory/'image.png'
    @contextmanager
    def checked(*args):
        if stage=='final_copy':raise error('private fixture message')
        yield None
    monkeypatch.setattr(inference_runner,'verify_input',verify)
    monkeypatch.setattr(inference_runner,'runtime_identity',runtime)
    monkeypatch.setattr(inference_runner,'copy_input',copy)
    monkeypatch.setattr(inference_runner,'verified_file',checked)
    def synthetic_execution(*args):
        assert stage.startswith('final_'),'pre-native failures must stop before adapter'
        return fields,b'',b''
    monkeypatch.setattr(inference_runtime,'execute_image',synthetic_execution)
    assert execute(job['id'],job['run_id'])==expected


@pytest.mark.parametrize('kind',['inference_input','inference_result'])
@pytest.mark.parametrize('route',['detail','list'])
def test_corrupt_image_artifact_metadata_is_normalized(inference_ready,kind,route):
    client,project,_,_=inference_ready[0]
    identifier=inference_ready[3]['id']
    if kind=='inference_result':
        job,_=bundle(inference_ready);assert inference_publication.publish(job)
        with transaction() as c:identifier=c.execute("SELECT id FROM artifacts WHERE job_id=? AND kind='inference_result'",(job['id'],)).fetchone()[0]
    with transaction() as c:c.execute("UPDATE artifacts SET metadata_json='{}' WHERE id=?",(identifier,))
    url='/api/v1/artifacts/'+identifier if route=='detail' else f'/api/v1/projects/{project}/artifacts'
    response=client.get(url)
    assert response.status_code==409 and response.headers['content-type']=='application/json'
    assert response.json()['error']['code']=='ARTIFACT_UNAVAILABLE'
