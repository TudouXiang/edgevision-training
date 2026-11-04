"""Reconstructed E lightweight fixtures only; no fixture bytes are ML evidence."""
import json
from pathlib import Path
from uuid import uuid4
import pytest
from app import export_service, export_assets, export_publication
from app.database import transaction
from app.run_files import atomic_json, fingerprint, run_directory
from app.training_assets import digest_json
from app.export_contract import tensor_hashes, MAX_ONNX_BYTES
from app.export_service import provenance
from app.worker import claim, get_job
from test_training import ready, build_bundle
from test_dataset_api import data_root, headers, create_user

IDENTITY = {'adapter': {'test': 'explicit lightweight export fixture'}}


@pytest.fixture
def export_ready(ready, monkeypatch):
    from app.training_publication import publish
    job, _ = build_bundle(ready)
    assert publish(job)
    with transaction() as c:
        artifact = dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='pt_best'", (job['id'],)).fetchone())
    monkeypatch.setattr(export_service, 'capability', lambda: {'available': True})
    monkeypatch.setattr(export_service, 'runtime_identity', lambda: IDENTITY)
    monkeypatch.setattr(export_publication, 'runtime_identity', lambda: IDENTITY)
    monkeypatch.setattr('app.worker.drain_receipt', lambda *a, **kw: {'reason': 'completed', 'exit_code': 0, 'logs_complete': True, 'started': True})
    return ready, artifact


def post(context, key='export', **changes):
    ready, artifact = context
    client, project, _, _ = ready
    return client.post(f'/api/v1/projects/{project}/jobs', headers={**headers(client), 'Idempotency-Key': key},
        json={'kind': 'export_onnx', 'params': {'model_artifact_id': artifact['id'], **changes}})


def bundle(context):
    result = post(context)
    assert result.status_code == 202, result.text
    job_id = result.json()['job_id']
    assert claim('export-fixture', None)[0] == job_id
    job = get_job(job_id)
    directory = run_directory(job_id, job['run_id'], create=True)
    frozen = json.loads(job['input_snapshot_json'])
    output = directory / 'bundle'; output.mkdir()
    (output / 'model.onnx').write_bytes(b'explicit lightweight model fixture; never a real ONNX model')
    size, digest = fingerprint(output / 'model.onnx')
    classes = frozen['source_metadata']['classes']
    runtime = {'versions': {'torch': '2.15.0+cpu', 'torchvision': '0.29.2+cpu', 'ultralytics': '8.4.202', 'onnx': '1.23.2', 'onnxruntime': '1.31.1'}, 'provider': 'CPUExecutionProvider', 'device': 'cpu', 'threads': 2, 'opset': 18, 'ir_version': 8, 'precision': 'fp32', 'dynamic': False, 'simplify': False, 'nms': False}
    validation = {'schema_version': 1, 'job_id': job_id, 'run_id': job['run_id'], 'input_sha256': digest_json(frozen),
        'source_sha256': frozen['source_sha256'], 'original_graph_sha256': digest, 'model_sha256': digest,
        'model_size_bytes': size, 'classes': classes, 'input_name': 'images', 'input_shape': [1, 3, 640, 640],
        'output_name': 'output0', 'output_shape': [1, 4 + len(classes), 8400], 'dtype': 'float32', 'tensor_protocol': 'rgb-fixed-v1',
        'atol': 1e-4, 'rtol': 1e-4, 'checker_passed': True, 'runtime': runtime,
        'samples': [{'name': name, 'input_sha256': digest, 'pt_sha256': 'a' * 64, 'ort_sha256': 'b' * 64,
            'max_absolute_error': 0., 'max_tolerance_ratio': 0., 'elements': (4 + len(classes)) * 8400, 'passed': True}
            for name, digest in tensor_hashes().items()]}
    atomic_json(output / 'validation.json', validation)
    metadata = {'schema_version': 1, 'task': 'detection', 'architecture': 'yolo11n', 'classes': classes,
        'provenance': provenance(frozen, job_id, job['run_id']), 'validation': validation,
        'validation_sha256': fingerprint(output / 'validation.json')[1], 'validation_scope': 'checker_ort_raw_tensor_equivalence'}
    atomic_json(output / 'metadata.json', metadata)
    seal(job, directory)
    return job, directory


def seal(job, directory):
    output = directory / 'bundle'
    entries = [{'path': name, 'size_bytes': fingerprint(output / name)[0], 'sha256': fingerprint(output / name)[1]} for name in ('model.onnx', 'metadata.json', 'validation.json')]
    atomic_json(directory / 'evidence.json', {'schema_version': 1, 'job_id': job['id'], 'run_id': job['run_id'], 'input_sha256': digest_json(json.loads(job['input_snapshot_json'])), 'outputs': entries})


def test_submit_replay_and_hidden_paths(export_ready):
    client = export_ready[0][0]
    created = post(export_ready)
    assert created.status_code == 202, created.text
    assert post(export_ready).json() == created.json()
    detail = client.get('/api/v1/jobs/' + created.json()['job_id']).json()
    assert detail['export']['source_artifact_id'] == export_ready[1]['id']
    assert 'source_key' not in json.dumps(detail)
    assert post(export_ready, model_artifact_id=str(uuid4())).status_code == 409
    assert client.post('/api/v1/jobs/' + created.json()['job_id'] + '/cancel', headers=headers(client)).json()['state'] == 'cancelled'
    assert post(export_ready).json()['state'] == 'cancelled'


@pytest.mark.parametrize('change', [{'batch': True}, {'batch': 2}, {'imgsz': 320}, {'precision': 'fp16'}, {'opset': 17}, {'path': '/tmp/model.pt'}, {'simplify': True}, {'target_format': 'onnx'}])
def test_reject_nonfixed_parameters(export_ready, change):
    assert post(export_ready, **change).status_code == 422


@pytest.mark.parametrize('fault', ['status', 'kind', 'format', 'passed', 'metadata', 'source_bytes', 'dataset_bytes', 'report_bytes', 'runtime'])
def test_reject_source_corruption(export_ready, fault):
    _, artifact = export_ready
    from app.config import data_root
    with transaction() as c:
        if fault == 'status': c.execute("UPDATE jobs SET status='failed' WHERE id=?", (artifact['job_id'],))
        elif fault == 'kind': c.execute("UPDATE jobs SET kind='dataset_check' WHERE id=?", (artifact['job_id'],))
        elif fault == 'format': c.execute("UPDATE artifacts SET format='onnx' WHERE id=?", (artifact['id'],))
        elif fault == 'passed': c.execute("UPDATE artifacts SET validation_status='unverified' WHERE id=?", (artifact['id'],))
        elif fault == 'metadata': c.execute("UPDATE artifacts SET metadata_json='{}' WHERE id=?", (artifact['id'],))
        elif fault == 'runtime': c.execute("UPDATE jobs SET environment_json='{}' WHERE id=?", (artifact['job_id'],))
        elif fault == 'source_bytes': (data_root() / artifact['storage_key']).write_bytes(b'changed')
        else:
            training = json.loads(c.execute('SELECT input_snapshot_json FROM jobs WHERE id=?', (artifact['job_id'],)).fetchone()[0])
            path = training['report_key'] if fault == 'report_bytes' else training['snapshot_key'] + '/' + training['files'][0]['path']
            (data_root() / path).write_bytes(b'changed')
    response = post(export_ready)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'EXPORT_INPUT_UNAVAILABLE'


def test_auth_cross_project_archive_capability_and_501(export_ready, monkeypatch):
    ready, artifact = export_ready
    client, project, _, _ = ready
    other = create_user(client, 'export-other')
    request = {'kind': 'export_onnx', 'params': {'model_artifact_id': artifact['id']}}
    assert other.post(f'/api/v1/projects/{project}/jobs', headers={**headers(other), 'Idempotency-Key': 'x'}, json=request).status_code == 404
    own = client.post('/api/v1/projects', headers=headers(client), json={'name': 'other-project'}).json()['id']
    assert client.post(f'/api/v1/projects/{own}/jobs', headers={**headers(client), 'Idempotency-Key': 'x'}, json=request).status_code == 404
    monkeypatch.setattr(export_service, 'capability', lambda: {'available': False})
    assert post(export_ready).json()['error']['code'] == 'DELIVERY_SETUP_REQUIRED'
    for kind, params in [('infer', {'model_artifact_id': artifact['id'], 'image_artifact_id': str(uuid4()), 'backend': 'onnx'}), ('package', {'onnx_artifact_id': artifact['id']})]:
        assert client.post(f'/api/v1/projects/{project}/jobs', headers={**headers(client), 'Idempotency-Key': kind}, json={'kind': kind, 'params': params}).status_code == 501
    client.post(f'/api/v1/projects/{project}/archive', headers=headers(client))
    assert post(export_ready).status_code == 409


@pytest.mark.parametrize('fault', ['missing', 'corrupt', 'extra', 'symlink', 'evidence', 'metadata', 'tensor', 'graph', 'runtime', 'source', 'no_drain'])
def test_corrupt_bundle_never_succeeds(export_ready, monkeypatch, fault):
    job, directory = bundle(export_ready)
    output = directory / 'bundle'
    if fault == 'missing': (output / 'model.onnx').unlink()
    elif fault == 'corrupt': (output / 'model.onnx').write_bytes(b'changed')
    elif fault == 'extra': (output / 'other').write_bytes(b'other')
    elif fault == 'symlink':
        (output / 'model.onnx').unlink(); (output / 'model.onnx').symlink_to(output / 'metadata.json')
    elif fault == 'evidence':
        evidence = json.loads((directory / 'evidence.json').read_text()); evidence['run_id'] = str(uuid4()); atomic_json(directory / 'evidence.json', evidence)
    elif fault == 'source':
        from app.config import data_root
        (data_root() / export_ready[1]['storage_key']).write_bytes(b'changed')
    elif fault == 'runtime': monkeypatch.setattr(export_publication, 'runtime_identity', lambda: {'changed': True})
    elif fault == 'no_drain': monkeypatch.setattr('app.worker.drain_receipt', lambda *a, **kw: None)
    else:
        metadata = json.loads((output / 'metadata.json').read_text())
        if fault == 'metadata': metadata['provenance']['source_job_id'] = str(uuid4())
        if fault == 'tensor': metadata['validation']['samples'][0]['input_sha256'] = '0' * 64
        if fault == 'graph': metadata['validation']['original_graph_sha256'] = '0' * 64
        atomic_json(output / 'metadata.json', metadata); seal(job, directory)
    with pytest.raises((ValueError, OSError)): export_publication.publish(job)
    with transaction() as c: assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?', (job['id'],)).fetchone()[0] == 0


def test_complete_publication_strict_union_download_auth(export_ready):
    from app.schemas import ArtifactPublic
    job, _ = bundle(export_ready)
    assert export_publication.publish(job)
    client, project, _, _ = export_ready[0]
    artifact = next(a for a in client.get(f'/api/v1/projects/{project}/artifacts').json()['items'] if a['kind'] == 'onnx')
    ArtifactPublic.model_validate(artifact)
    with pytest.raises(ValueError): ArtifactPublic.model_validate({**artifact, 'metadata': {'invalid': 'no object fallback'}})
    response = client.get('/api/v1/artifacts/' + artifact['id'] + '/download')
    assert response.status_code == 200 and int(response.headers['Content-Length']) == len(response.content)
    other = create_user(client, 'download-other')
    assert other.get('/api/v1/artifacts/' + artifact['id'] + '/download').status_code == 404
    assert client.get('/api/v1/jobs/' + job['id']).json()['state'] == 'succeeded'
    from app.config import data_root
    with transaction() as c: row = c.execute('SELECT * FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()
    (data_root() / row['storage_key']).write_bytes(b'corrupted')
    assert client.get('/api/v1/artifacts/' + artifact['id'] + '/download').status_code == 409


@pytest.mark.parametrize('window', ['before_intent', 'after_rename', 'cas_failure', 'source_after_rename'])
def test_publication_races_and_rollback(export_ready, monkeypatch, window):
    job, directory = bundle(export_ready)
    client = export_ready[0][0]
    def cancel(): client.post('/api/v1/jobs/' + job['id'] + '/cancel', headers=headers(client))
    if window == 'before_intent': cancel()
    elif window == 'cas_failure': monkeypatch.setattr(export_publication, 'transition', lambda *a, **kw: False)
    else:
        rename = export_publication.os.rename
        def race(source, destination):
            rename(source, destination)
            if window == 'after_rename': cancel()
            else:
                from app.config import data_root
                (data_root() / export_ready[1]['storage_key']).write_bytes(b'changed')
        monkeypatch.setattr(export_publication.os, 'rename', race)
    if window in {'cas_failure', 'source_after_rename'}:
        with pytest.raises((ValueError, RuntimeError)): export_publication.publish(job)
    else: assert export_publication.publish(job) is False
    with transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?', (job['id'],)).fetchone()[0] == 0
        assert c.execute('SELECT status FROM jobs WHERE id=?', (job['id'],)).fetchone()[0] != 'succeeded'


def test_oversized_graph_rejected_before_read_parse_import(tmp_path, monkeypatch):
    from app.export_runtime import read_model_bytes
    path = tmp_path / 'large.onnx'
    with path.open('wb') as sink: sink.truncate(MAX_ONNX_BYTES + 1)
    monkeypatch.setattr(Path, 'open', lambda *a, **kw: pytest.fail('oversized model must not be read'))
    with pytest.raises(ValueError): read_model_bytes(path)


def test_probe_blocks_active_worker_or_shared_probe(data_root, monkeypatch):
    from app.export_probe import run_probe
    monkeypatch.setattr('app.training_probe.recover_probe', lambda: False)
    monkeypatch.setattr('app.export_probe.subprocess.Popen', lambda *a, **kw: pytest.fail('must not launch'))
    with pytest.raises(RuntimeError, match='Previous shared'): run_probe()
    monkeypatch.setattr('app.training_probe.recover_probe', lambda: True)
    monkeypatch.setattr('app.worker.recover', lambda: [('blocked', 'unconfirmed')])
    with pytest.raises(RuntimeError, match='Existing task'): run_probe()


def test_capability_missing_or_stale_unavailable(data_root, monkeypatch):
    monkeypatch.setattr(export_assets, 'runtime_identity', lambda: IDENTITY)
    monkeypatch.setattr(export_assets, 'verify_asset', lambda: {'sha256': 'a' * 64})
    assert export_assets.capability()['available'] is False
    atomic_json(data_root / 'delivery-capability.json', {'schema_version': 1, 'available': True})
    assert export_assets.capability()['available'] is False


def test_lightweight_imports_do_not_load_any_ml():
    import subprocess, sys
    result = subprocess.run([sys.executable, '-c', "import app.main,app.worker,app.export_runtime,app.export_probe,sys; assert not {'torch','numpy','onnx','onnxruntime','ultralytics'}.intersection(sys.modules)"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

@pytest.mark.parametrize('behavior', ['tree', 'worker_lost', 'pre_go', 'exit_zero'])
def test_real_managed_export_process_lifecycle(export_ready, monkeypatch, behavior):
    from test_worker_process import start, run_path, wait_marker, stop_and_reap, record, wait_until
    from test_worker_api import work
    from app.process_identity import exited
    client = export_ready[0][0]
    job = post(export_ready).json()['job_id']
    process = start('export_' + ('tree' if behavior == 'worker_lost' else behavior))
    directory = run_path(job)
    try:
        if behavior == 'exit_zero':
            assert process.wait(timeout=20) == 0
            assert record(job)['status'] == 'failed' and record(job)['error_code'] == 'OUTPUT_INVALID'
        elif behavior == 'pre_go':
            wait_marker(directory, 'worker-before-go.json')
            client.post('/api/v1/jobs/' + job + '/cancel', headers=headers(client))
            (directory / 'release-worker').touch()
            assert process.wait(timeout=20) == 0
            assert record(job)['status'] == 'cancelled'
            assert not (directory / 'started.json').exists()
        else:
            wait_marker(directory, 'grandchild.json')
            if behavior == 'worker_lost':
                process.kill(); process.wait(timeout=10)
                receipt = wait_marker(directory, 'drained.json')
                wait_until(lambda: exited(receipt['guardian']))
                work()
                assert record(job)['status'] == 'interrupted'
            else:
                client.post('/api/v1/jobs/' + job + '/cancel', headers=headers(client))
                assert process.wait(timeout=20) == 0
                assert record(job)['status'] == 'cancelled'
        with transaction() as c:
            assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?', (job,)).fetchone()[0] == 0
    finally:
        stop_and_reap(process)


def fake_graph():
    from types import SimpleNamespace as S
    def message(kind, **values):
        return S(DESCRIPTOR=S(name=kind), ListFields=lambda: [], **values)
    def interface(name, dims):
        tensor = S(elem_type=1, shape=S(dim=[S(dim_value=value, WhichOneof=lambda _: 'dim_value') for value in dims]))
        return S(name=name, type=S(tensor_type=tensor, WhichOneof=lambda _: 'tensor_type'))
    graph = message('GraphProto', input=[interface('images', [1, 3, 640, 640])], output=[interface('output0', [1, 5, 8400])], sparse_initializer=[])
    model = message('ModelProto', ir_version=8, functions=[], training_info=[], metadata_props=[], opset_import=[S(domain='', version=18)], graph=graph)
    field = S(message_type=True, is_repeated=True)
    model.ListFields = lambda: [(field, [graph])]
    onnx = S(TensorProto=S(FLOAT=1, DEFAULT=0), defs=S(has=lambda op, version, domain: op == 'Conv'))
    return model, graph, onnx, message, field


@pytest.mark.parametrize('case', ['external', 'external_flag', 'sparse', 'custom', 'unknown', 'nested_external', 'function', 'training', 'ir', 'opset', 'shape'])
def test_recursive_graph_guard_without_native_import(case):
    from app.export_runtime import guard_graph
    model, graph, onnx, message, field = fake_graph()
    if case in {'external', 'external_flag', 'nested_external'}:
        bad = message('TensorProto', external_data=['location'] if case != 'external_flag' else [], data_location=1 if case == 'external_flag' else 0)
        if case == 'nested_external':
            nested = message('GraphProto', sparse_initializer=[])
            nested.ListFields = lambda: [(field, [bad])]
            graph.ListFields = lambda: [(field, [nested])]
        else: graph.ListFields = lambda: [(field, [bad])]
    elif case == 'sparse': graph.ListFields = lambda: [(field, [message('SparseTensorProto')])]
    elif case in {'custom', 'unknown'}: graph.ListFields = lambda: [(field, [message('NodeProto', domain='custom' if case == 'custom' else '', op_type='Conv' if case == 'custom' else 'Unknown')])]
    elif case == 'function': model.functions = [object()]
    elif case == 'training': model.training_info = [object()]
    elif case == 'ir': model.ir_version = 9
    elif case == 'opset': model.opset_import[0].version = 17
    elif case == 'shape': graph.output[0].type.tensor_type.shape.dim[1].dim_value = 6
    with pytest.raises(ValueError): guard_graph(model, onnx, ['object'])


def test_valid_standard_graph_guard_without_native_import():
    from app.export_runtime import guard_graph
    model, _, onnx, _, _ = fake_graph()
    guard_graph(model, onnx, ['object'])


def test_matching_probe_available_until_runtime_changes(export_ready, data_root, monkeypatch):
    job, directory = bundle(export_ready)
    validation = json.loads((directory / 'bundle' / 'validation.json').read_text())
    manifest = {'sha256': validation['source_sha256']}
    validation['input_sha256'] = digest_json({'manifest': manifest, 'runtime': IDENTITY})
    monkeypatch.setattr(export_assets, 'runtime_identity', lambda: IDENTITY)
    monkeypatch.setattr(export_assets, 'verify_asset', lambda: manifest)
    record = {'schema_version': 1, 'available': True, 'runtime_binding': digest_json(IDENTITY),
        'manifest_sha256': digest_json(manifest), 'source_sha256': manifest['sha256'], 'validation': validation}
    atomic_json(data_root / 'delivery-capability.json', record)
    assert export_assets.capability()['available'] is True
    monkeypatch.setattr(export_assets, 'runtime_identity', lambda: {'adapter': {'changed': True}})
    assert export_assets.capability()['available'] is False


def test_source_row_and_file_replacement_cannot_forge_original_publication(export_ready):
    from app.config import data_root
    artifact = export_ready[1]
    path = data_root() / artifact['storage_key']
    path.write_bytes(b'new byte content pretending to be a trusted model')
    size, digest = fingerprint(path)
    with transaction() as c:
        c.execute('UPDATE artifacts SET size_bytes=?,sha256=? WHERE id=?', (size, digest, artifact['id']))
    response = post(export_ready)
    assert response.status_code == 409 and response.json()['error']['code'] == 'EXPORT_INPUT_UNAVAILABLE'


def test_download_caps_stream_after_growth_on_same_descriptor(data_root):
    import asyncio
    from hashlib import sha256
    from app.training_download import download_model
    path = data_root / 'model.onnx'; path.write_bytes(b'abc')
    row = {'validation_status': 'passed', 'size_bytes': 3, 'sha256': sha256(b'abc').hexdigest(), 'storage_key': 'model.onnx', 'kind': 'onnx'}
    response = download_model(row, str(uuid4()), limit=MAX_ONNX_BYTES, extension='onnx')
    with path.open('ab') as target: target.write(b'not in validated body')
    async def consume(): return b''.join([chunk async for chunk in response.body_iterator])
    assert asyncio.run(consume()) == b'abc'
    assert response.background.func.__self__.closed
    assert response.headers['Content-Length'] == '3'


@pytest.mark.parametrize('fault', ['metadata_file', 'validation_file', 'source_job', 'intent'])
def test_download_rejects_published_lineage_tamper(export_ready, fault):
    job, _ = bundle(export_ready)
    assert export_publication.publish(job)
    with transaction() as c:
        artifact = dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='onnx'", (job['id'],)).fetchone())
        if fault == 'source_job': c.execute("UPDATE jobs SET status='failed' WHERE id=?", (job['id'],))
        if fault == 'intent': c.execute("UPDATE jobs SET publication_json='{}' WHERE id=?", (job['id'],))
    if fault.endswith('_file'):
        from app.config import data_root
        name = 'metadata.json' if fault == 'metadata_file' else 'validation.json'
        (data_root() / artifact['storage_key']).with_name(name).write_text('{}')
    response = export_ready[0][0].get('/api/v1/artifacts/' + artifact['id'] + '/download')
    assert response.status_code == 409


def test_delivery_probe_identity_failure_closes_control_and_retains_recovery(data_root, monkeypatch):
    from app import export_probe
    from io import BytesIO
    from types import SimpleNamespace
    monkeypatch.setattr('app.training_probe.recover_probe', lambda: True)
    monkeypatch.setattr('app.worker.recover', lambda: [])
    monkeypatch.setattr(export_probe, 'verify_asset', lambda: {})
    monkeypatch.setattr(export_probe, 'runtime_identity', lambda: IDENTITY)
    stream = BytesIO()
    child = SimpleNamespace(pid=123, stdin=stream)
    monkeypatch.setattr(export_probe.subprocess, 'Popen', lambda *a, **kw: child)
    def fail_identity(pid): raise OSError('injected identity failure')
    monkeypatch.setattr('app.process_identity.identity', fail_identity)
    with pytest.raises(OSError): export_probe.run_probe()
    assert stream.closed
    assert json.loads((data_root / 'training-probe-active.json').read_text())['guardian'] is None
    assert json.loads((data_root / 'delivery-capability.json').read_text())['available'] is False


@pytest.mark.parametrize('field', ['checker_passed', 'runtime_dynamic', 'schema_version', 'sample_passed', 'input_shape'])
def test_public_validation_rejects_boolean_integer_coercion(export_ready, field):
    from app.schemas import ExportValidation
    _, directory = bundle(export_ready)
    value = json.loads((directory / 'bundle' / 'validation.json').read_text())
    if field == 'runtime_dynamic': value['runtime']['dynamic'] = 0
    elif field == 'sample_passed': value['samples'][0]['passed'] = 1
    elif field == 'input_shape': value['input_shape'][0] = True
    elif field == 'schema_version': value[field] = True
    else: value[field] = 1
    with pytest.raises(ValueError): ExportValidation.model_validate(value)


def test_slow_publication_hashing_does_not_block_cancel(export_ready, monkeypatch):
    """The final full byte pass runs outside SQLite's writer reservation."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    job, _ = bundle(export_ready)
    entered, release = Event(), Event()
    original = export_publication.verify
    calls = 0
    def delayed(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
            assert release.wait(15)
        return original(*args, **kwargs)
    monkeypatch.setattr(export_publication, 'verify', delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(export_publication.publish, job)
        assert entered.wait(10)
        client = export_ready[0][0]
        cancellation = pool.submit(client.post, '/api/v1/jobs/' + job['id'] + '/cancel', headers=headers(client))
        try:
            response = cancellation.result(timeout=2)
            assert response.status_code == 200 and response.json()['state'] == 'cancelling'
        finally: release.set()
        assert future.result(timeout=10) is False


@pytest.mark.parametrize('change', ['archive', 'disable', 'revoke', 'source'])
def test_slow_submission_allows_writes_and_rechecks_authority(export_ready, monkeypatch, change):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.security import timestamp
    entered, release = Event(), Event()
    original = export_service.source_snapshot
    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(15)
        return result
    monkeypatch.setattr(export_service, 'source_snapshot', delayed)
    client, project, _, _ = export_ready[0]
    def concurrent_write():
        with transaction() as c:
            c.execute('BEGIN IMMEDIATE')
            if change == 'archive': c.execute("UPDATE projects SET status='archived',archived_at=? WHERE id=?", (timestamp(), project))
            if change == 'disable': c.execute("UPDATE users SET is_active=0 WHERE id=(SELECT owner_id FROM projects WHERE id=?)", (project,))
            if change == 'revoke': c.execute('UPDATE sessions SET revoked_at=?', (timestamp(),))
            if change == 'source': c.execute("UPDATE jobs SET status='failed' WHERE id=?", (export_ready[1]['job_id'],))
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(post, export_ready)
        assert entered.wait(10)
        try: pool.submit(concurrent_write).result(timeout=2)
        finally: release.set()
        response = future.result(timeout=10)
    assert response.status_code == (401 if change in {'disable', 'revoke'} else 409)
    with transaction() as c: assert c.execute("SELECT COUNT(*) FROM jobs WHERE kind='export_onnx'").fetchone()[0] == 0


@pytest.mark.parametrize('fault', ['distribution_removed', 'source_record_removed'])
def test_late_submission_unavailability_is_normalized(export_ready, monkeypatch, fault):
    if fault == 'distribution_removed':
        from importlib.metadata import PackageNotFoundError
        def unavailable(): raise PackageNotFoundError('explicit missing package fixture')
        monkeypatch.setattr(export_service, 'runtime_identity', unavailable)
    else:
        original = export_service.source_binding
        calls = 0
        def removed(*args):
            nonlocal calls
            calls += 1
            if calls == 2: raise ValueError('source binding disappeared')
            return original(*args)
        monkeypatch.setattr(export_service, 'source_binding', removed)
    response = post(export_ready)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'EXPORT_INPUT_UNAVAILABLE'
    with transaction() as c: assert c.execute("SELECT COUNT(*) FROM jobs WHERE kind='export_onnx'").fetchone()[0] == 0
