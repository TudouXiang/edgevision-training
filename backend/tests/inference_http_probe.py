"""Explicit real I HTTP evidence, following training and E in one private root.

No native imports or launch at import time. Requires a fresh inference opt-in;
never copies capabilities, creates model records, or changes a source artifact.
All resource IDs, proofs, bytes and diagnostics remain in the disposable root.
"""
import contextlib
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


def prerequisites():
    """Reject accidental standalone/default execution before any native child."""
    configured = os.environ.get('PLATFORM_DATA_ROOT')
    opted = os.environ.get('EDGEVISION_INFERENCE_HTTP_ROOT')
    if not configured or not opted or Path(configured).resolve() != Path(opted).resolve():
        raise ValueError('explicit same-root image opt-in required')
    root = Path(configured).resolve()
    required = ('first-result.json', 'export-result.json', 'export-artifact.json', 'smoke-session.json')
    if not all((root / name).is_file() for name in required):
        raise ValueError('fresh training and export prerequisites required')
    if any((root / name).exists() for name in ('inference-capability.json', 'inference-http-started.json', 'inference-http-result.json')):
        raise ValueError('image evidence must be generated fresh')
    return root


def read_json(root, name):
    from app.run_files import read_json as bounded_read
    return bounded_read(root / name, 1024**2)


def json_response(response, status=200):
    assert response.status_code == status
    assert len(response.content) <= 1024**2
    return response.json()


def execute(command, diagnostic, timeout=120):
    subprocess.run([sys.executable, *command], check=True, stdout=diagnostic,
                   stderr=diagnostic, timeout=timeout)


def verify_probe(root, pair):
    from app.inference_assets import capability, runtime_identity
    from app.inference_probe import compare_raw, verify_pair
    from app.inference_probe_contract import InferenceProbeRecord
    from app.training_assets import digest_json
    record = InferenceProbeRecord.model_validate(read_json(root, 'inference-capability.json')).model_dump(mode='json')
    identity = runtime_identity()
    assert record['runtime_binding'] == digest_json(identity)
    assert record['code_version'] == digest_json(identity['adapter'])
    assert record['synthetic_source_sha256'] == identity['adapter']['delivery_infer.py']
    for backend in ('pt', 'onnx'):
        proof, source = record[backend], pair[backend]
        assert proof['project_id'] == source['project_id']
        assert proof['model_artifact_id'] == source['source_artifact_id']
        assert proof['model_sha256'] == source['source_sha256']
        assert proof['pair_sha256'] == digest_json(pair)
    assert record['comparison'] == compare_raw(record['pt'], record['onnx'])
    verify_pair(pair)
    assert capability()['available'] is True
    return record


def check_result(result, artifact, job, model, image, record):
    """Strict DTO plus independent public source/model/image/code binding checks."""
    from app.schemas import InferenceResult
    from app.delivery_infer import match_detections
    InferenceResult.model_validate(result)
    origin = result['provenance']
    assert result['artifact_id'] == artifact['id']
    assert result['backend'] == model['backend']
    assert origin == artifact['metadata']['provenance']
    assert origin['job_id'] == job['id'] and origin['project_id'] == model['project_id']
    assert origin['model_artifact_id'] == model['source_artifact_id']
    assert origin['model_job_id'] == model['source_job_id']
    assert origin['model_sha256'] == model['source_sha256']
    assert origin['model_size_bytes'] == model['source_size_bytes']
    assert origin['model_metadata_sha256'] == model['source_metadata_sha256']
    assert origin['image_artifact_id'] == image['id']
    assert (origin['image_sha256'], origin['image_size_bytes']) == (image['sha256'], image['size_bytes'])
    assert origin['runtime_binding'] == record['runtime_binding']
    assert origin['code_version'] == record['code_version']
    assert result['classes'] == model['source_metadata']['classes']
    for name in ('model_artifact_id', 'model_job_id', 'model_sha256', 'image_artifact_id', 'image_sha256', 'runtime_binding', 'code_version'):
        assert job['inference'][name] == origin[name]
    assert job['inference']['params'] == result['params']
    proof = record[model['backend']]['output']
    for name in ('image', 'preprocess', 'preview'):
        assert result[name] == proof[name]
    assert match_detections(result['detections'], proof['detections'])


def run(root, diagnostic):
    import httpx
    from app.database import transaction
    from app.delivery_infer import synthetic_png, match_detections
    from app.inference_probe import sources
    from app.run_files import atomic_json
    from app.schemas import ArtifactPublic, JobPublic, InferenceDocument

    training = JobPublic.model_validate(read_json(root, 'first-result.json')).model_dump(mode='json')
    exported = JobPublic.model_validate(read_json(root, 'export-result.json')).model_dump(mode='json')
    onnx = ArtifactPublic.model_validate(read_json(root, 'export-artifact.json')).model_dump(mode='json')
    assert training['kind'] == 'train' and training['state'] == 'succeeded'
    assert exported['kind'] == 'export_onnx' and exported['state'] == 'succeeded'
    assert onnx['kind'] == 'onnx' and onnx['job_id'] == exported['id']
    assert onnx['project_id'] == training['project_id'] == exported['project_id']
    with transaction() as connection:
        connection.execute('BEGIN')
        user = connection.execute("SELECT id FROM users WHERE id=? AND username='smoke' AND role='admin'", (training['created_by'],)).fetchone()
        assert user is not None
        pair = sources(connection, onnx['id'])
        assert pair['pt']['source_job_id'] == training['id']
        assert pair['onnx']['source_sha256'] == onnx['sha256']
    atomic_json(root / 'inference-http-started.json', {'schema_version': 1, 'status': 'started'})
    # This CLI owns the same worker lock and executes two fresh guardians. Its
    # record is produced here, not cloned from E or another data root.
    execute(['-m', 'app.inference_probe', '--onnx-artifact-id', onnx['id']], diagnostic, 330)
    record = verify_probe(root, pair)
    image_bytes = synthetic_png()
    assert record['pt']['image_sha256'] == sha256(image_bytes).hexdigest()
    port = int(os.environ.get('EDGEVISION_INFERENCE_SMOKE_PORT', '8893'))
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                              stdout=diagnostic, stderr=diagnostic)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30, trust_env=False) as client:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('private API exited before readiness')
                try:
                    if client.get('/api/v1/health/live').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError('private API not ready')
            cookies = read_json(root, 'smoke-session.json')
            client.cookies.update(cookies)
            headers = {'Origin': 'http://127.0.0.1:5173', 'X-CSRF-Token': cookies['edgevision_csrf']}
            features = json_response(client.get('/api/v1/capabilities'))['features']
            assert all(features[key]['available'] is True for key in ('pt_inference', 'onnx_inference'))
            project = training['project_id']
            image = json_response(client.post(f'/api/v1/projects/{project}/images', headers=headers,
                files={'file': ('synthetic.png', image_bytes, 'image/png')}), 201)
            ArtifactPublic.model_validate(image)
            assert image['validation_state'] == 'unverified' and image['job_id'] is None
            assert (image['size_bytes'], image['sha256']) == (len(image_bytes), sha256(image_bytes).hexdigest())
            results = {}
            for backend in ('pt', 'onnx'):
                source = pair[backend]
                body = {'kind': 'infer', 'params': {'model_artifact_id': source['source_artifact_id'],
                    'image_artifact_id': image['id'], 'backend': backend, 'confidence': .25, 'iou': .45}}
                request_headers = {**headers, 'Idempotency-Key': 'actual-image-' + backend}
                accepted = json_response(client.post(f'/api/v1/projects/{project}/jobs', json=body, headers=request_headers), 202)
                task = accepted['job_id']
                assert json_response(client.post(f'/api/v1/projects/{project}/jobs', json=body, headers=request_headers), 202)['job_id'] == task
                execute(['-m', 'app.worker', '--once'], diagnostic)
                job = json_response(client.get('/api/v1/jobs/' + task))
                JobPublic.model_validate(job)
                atomic_json(root / ('inference-' + backend + '-job.json'), job)
                assert job['state'] == 'succeeded'
                artifacts = json_response(client.get(f'/api/v1/projects/{project}/artifacts', params={'page_size': 100}))['items']
                matches = [item for item in artifacts if item['kind'] == 'inference_result' and item['job_id'] == task]
                assert len(matches) == 1
                artifact = matches[0]
                ArtifactPublic.model_validate(artifact)
                result = json_response(client.get('/api/v1/inferences/' + artifact['id']))
                check_result(result, artifact, job, source, image, record)
                content = client.get('/api/v1/artifacts/' + artifact['id'] + '/download')
                assert content.status_code == 200 and len(content.content) == artifact['size_bytes']
                assert sha256(content.content).hexdigest() == artifact['sha256']
                document = InferenceDocument.model_validate_json(content.content).model_dump(mode='json')
                assert document == {key: value for key, value in result.items() if key not in {'artifact_id', 'image_url'}}
                preview = client.get(result['image_url'])
                assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
                assert len(preview.content) == result['preview']['size_bytes']
                assert sha256(preview.content).hexdigest() == result['preview']['sha256']
                # The preview and downloadable result remain authenticated.
                with httpx.Client(base_url=client.base_url, timeout=30, trust_env=False) as anonymous:
                    for route in ('/api/v1/inferences/' + artifact['id'], result['image_url'], '/api/v1/artifacts/' + artifact['id'] + '/download'):
                        assert anonymous.get(route).status_code == 401
                atomic_json(root / ('inference-' + backend + '-result.json'), result)
                results[backend] = result
            assert match_detections(results['pt']['detections'], results['onnx']['detections'])
            for name in ('image', 'preprocess', 'preview'):
                assert results['pt'][name] == results['onnx'][name]
            assert json_response(client.get('/api/v1/artifacts/' + image['id'])) == image
            # Bad encoded bytes are accepted only as unverified upload, then the
            # actual managed decoder must fail without a result publication.
            bad = json_response(client.post(f'/api/v1/projects/{project}/images', headers=headers,
                files={'file': ('invalid.png', b'not an encoded image', 'image/png')}), 201)
            failed = json_response(client.post(f'/api/v1/projects/{project}/jobs', headers={**headers, 'Idempotency-Key': 'actual-image-invalid'},
                json={'kind': 'infer', 'params': {'model_artifact_id': onnx['id'], 'image_artifact_id': bad['id'], 'backend': 'onnx'}}), 202)
            execute(['-m', 'app.worker', '--once'], diagnostic)
            failure = json_response(client.get('/api/v1/jobs/' + failed['job_id']))
            assert failure['state'] == 'failed' and failure['error_code'] == 'IMAGE_DECODE_FAILED'
            with transaction() as connection:
                assert connection.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?', (failed['job_id'],)).fetchone()[0] == 0
            assert json_response(client.get('/api/v1/artifacts/' + bad['id']))['validation_state'] == 'unverified'
            # Revalidate the exact same source pair and current runtime at end.
            verify_probe(root, pair)
            atomic_json(root / 'inference-http-result.json', {'schema_version': 1, 'status': 'passed',
                'pt': results['pt']['artifact_id'], 'onnx': results['onnx']['artifact_id'],
                'comparison': record['comparison'], 'invalid_image_error': failure['error_code']})
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def main():
    previous = os.umask(0o077)
    try:
        try:
            root = prerequisites()
        except Exception:
            print('FAIL real managed image prerequisites')
            return 1
        with (root / 'inference-private.log').open('x') as diagnostic, contextlib.redirect_stdout(diagnostic), contextlib.redirect_stderr(diagnostic):
            try:
                run(root, diagnostic)
            except Exception:
                traceback.print_exc()
                success = False
            else:
                success = True
        print('PASS real managed HTTP image inference' if success else 'FAIL real managed HTTP image inference; private diagnostics retained')
        return 0 if success else 1
    finally:
        os.umask(previous)


if __name__ == '__main__':
    raise SystemExit(main())
