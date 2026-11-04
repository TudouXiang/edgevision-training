"""Opt-in real HTTP export after the fresh training probe. Never run by unit tests.

All IDs, hashes, logs and tracebacks remain in the private runtime directory.
The source must come from training_http_probe.py in this same data root.
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
import httpx


def run(root, diagnostic):
    from app.export_probe import run_probe
    from app.schemas import ArtifactPublic
    from app.database import transaction
    # This test-only session is confined to the synthetic smoke administrator.
    # It avoids persisting its random password or an external account credential.
    training = json.loads((root / 'first-result.json').read_text())
    assert training['state'] == 'succeeded'
    with transaction() as c:
        user = c.execute("SELECT * FROM users WHERE id=? AND username='smoke' AND role='admin'", (training['created_by'],)).fetchone()
        assert user is not None
    run_probe()
    port = int(os.environ.get('EDGEVISION_EXPORT_SMOKE_PORT', '8892'))
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)], stdout=diagnostic, stderr=diagnostic)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30, trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get('/api/v1/health/live').status_code == 200: break
                except httpx.TransportError: pass
                time.sleep(.1)
            # Resume only the private synthetic session saved by the training probe.
            cookies = json.loads((root / 'smoke-session.json').read_text())
            client.cookies.update(cookies)
            headers = {'Origin': 'http://127.0.0.1:5173', 'X-CSRF-Token': cookies['edgevision_csrf']}
            assert client.get('/api/v1/capabilities').json()['features']['onnx_export']['available'] is True
            project = training['project_id']
            artifacts = client.get(f'/api/v1/projects/{project}/artifacts').json()['items']
            source = next(a for a in artifacts if a['kind'] == 'pt_best' and a['job_id'] == training['id'])
            body = {'kind': 'export_onnx', 'params': {'model_artifact_id': source['id'], 'imgsz': 640, 'batch': 1, 'precision': 'fp32'}}
            response = client.post(f'/api/v1/projects/{project}/jobs', json=body, headers={**headers, 'Idempotency-Key': 'actual-export'})
            assert response.status_code == 202
            task = response.json()['job_id']
            assert client.post(f'/api/v1/projects/{project}/jobs', json=body, headers={**headers, 'Idempotency-Key': 'actual-export'}).json()['job_id'] == task
            subprocess.run([sys.executable, '-m', 'app.worker', '--once'], check=True, stdout=diagnostic, stderr=diagnostic, timeout=360)
            result = client.get('/api/v1/jobs/' + task).json()
            (root / 'export-result.json').write_text(json.dumps(result, indent=2))
            assert result['state'] == 'succeeded'
            artifacts = client.get(f'/api/v1/projects/{project}/artifacts').json()['items']
            onnx = [a for a in artifacts if a['kind'] == 'onnx' and a['job_id'] == task]
            assert len(onnx) == 1
            artifact = onnx[0]
            ArtifactPublic.model_validate(artifact)
            content = client.get('/api/v1/artifacts/' + artifact['id'] + '/download')
            assert content.status_code == 200 and len(content.content) == artifact['size_bytes'] and sha256(content.content).hexdigest() == artifact['sha256']
            assert artifact['metadata']['provenance']['source_sha256'] == source['sha256']
            assert all(sample['passed'] and sample['max_tolerance_ratio'] <= 1 for sample in artifact['metadata']['validation']['samples'])
            (root / 'export-artifact.json').write_text(json.dumps(artifact, indent=2))
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


def main():
    root = Path(os.environ['PLATFORM_DATA_ROOT']).resolve()
    if not (root / 'first-result.json').is_file() or (root / 'export-result.json').exists():
        print('FAIL export prerequisite: completed fresh training root required')
        return 1
    with (root / 'export-private.log').open('w') as diagnostic, contextlib.redirect_stdout(diagnostic), contextlib.redirect_stderr(diagnostic):
        try: run(root, diagnostic)
        except Exception:
            traceback.print_exc()
            success = False
        else: success = True
    print('PASS real managed HTTP ONNX export' if success else 'FAIL real managed HTTP ONNX export; private diagnostics retained')
    return 0 if success else 1


if __name__ == '__main__': raise SystemExit(main())
