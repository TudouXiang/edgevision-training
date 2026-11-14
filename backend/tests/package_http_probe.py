"""Explicit disposable P HTTP + downloaded standalone CLI acceptance.

Only invoked in the isolated native recipe. All IDs, model bytes, diagnostic
text and complete proofs remain private. No native import at module import.
"""
import contextlib
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


def prerequisites():
    configured=os.environ.get('PLATFORM_DATA_ROOT');opted=os.environ.get('EDGEVISION_PACKAGE_HTTP_ROOT')
    if not configured or not opted or Path(configured).resolve()!=Path(opted).resolve():raise ValueError('explicit same-root package opt-in required')
    root=Path(configured).resolve()
    required=('first-result.json','export-result.json','export-artifact.json','smoke-session.json','inference-http-result.json','inference-capability.json')
    if not all((root/name).is_file() for name in required):raise ValueError('fresh training/export/inference lineage required')
    if any((root/name).exists() for name in ('package-capability.json','package-http-started.json','package-http-result.json')):raise ValueError('package evidence must be fresh')
    return root


def run(root,diagnostic):
    import httpx
    from app.run_files import read_json,atomic_json
    from app.schemas import ArtifactPublic,JobPublic
    from app.package_assets import runtime_identity,validated_template,capability
    from app.package_probe_contract import PackageProbeRecord
    from app.package_probe import standalone_stage
    from app.package_contract import FrozenPackage
    from app.inference_probe import sources
    from app.database import transaction
    from app.training_assets import digest_json
    from app.worker import worker_lock
    from app.inference_files import write_bytes
    from app.package_bundle import verify_bundle
    from inference_http_probe import execute,json_response
    training=JobPublic.model_validate(read_json(root/'first-result.json')).model_dump(mode='json')
    exported=JobPublic.model_validate(read_json(root/'export-result.json')).model_dump(mode='json')
    onnx=ArtifactPublic.model_validate(read_json(root/'export-artifact.json')).model_dump(mode='json')
    assert training['state']==exported['state']=='succeeded'
    assert onnx['kind']=='onnx' and onnx['job_id']==exported['id']
    project=training['project_id'];assert onnx['project_id']==exported['project_id']==project
    assert read_json(root/'inference-http-result.json')['status']=='passed'
    atomic_json(root/'package-http-started.json',{'schema_version':1,'status':'started'})
    execute(['-m','app.package_probe','--onnx-artifact-id',onnx['id']],diagnostic,330)
    record=PackageProbeRecord.model_validate(read_json(root/'package-capability.json')).model_dump(mode='json')
    before=runtime_identity();assert record['runtime_binding']==digest_json(before)
    assert capability()['available'] is True
    assert validated_template()['record_sha256']==digest_json(record)
    port=8894
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],stdout=diagnostic,stderr=diagnostic)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=60,trust_env=False) as client:
            for _ in range(100):
                if server.poll() is not None:raise ValueError('private API exited')
                try:
                    if client.get('/api/v1/health/live').status_code==200:break
                except httpx.TransportError:pass
                time.sleep(.1)
            else:raise ValueError('private API readiness failed')
            cookies=read_json(root/'smoke-session.json');client.cookies.update(cookies)
            headers={'Origin':'http://127.0.0.1:5173','X-CSRF-Token':cookies['edgevision_csrf'],'Idempotency-Key':'actual-independent-package'}
            assert json_response(client.get('/api/v1/capabilities'))['features']['deployment']['available'] is True
            body={'kind':'package','params':{'onnx_artifact_id':onnx['id']}}
            accepted=json_response(client.post(f'/api/v1/projects/{project}/jobs',json=body,headers=headers),202)
            assert json_response(client.post(f'/api/v1/projects/{project}/jobs',json=body,headers=headers),202)==accepted
            execute(['-m','app.worker','--once'],diagnostic)
            job=json_response(client.get('/api/v1/jobs/'+accepted['job_id']))
            JobPublic.model_validate(job);assert job['state']=='succeeded' and job['kind']=='package'
            matches=[a for a in json_response(client.get(f'/api/v1/projects/{project}/artifacts',params={'page_size':100}))['items'] if a['job_id']==job['id'] and a['kind']=='deployment_zip']
            assert len(matches)==1;artifact=matches[0];ArtifactPublic.model_validate(artifact)
            assert artifact['validation_state']=='passed'
            metadata=artifact['metadata']
            assert metadata['validation_scope']=='trusted_model_fixed_package_integrity'
            assert metadata['standalone_execution']=='not_run_for_this_artifact'
            response=client.get('/api/v1/artifacts/'+artifact['id']+'/download');assert response.status_code==200
            assert (len(response.content),sha256(response.content).hexdigest())==(artifact['size_bytes'],artifact['sha256'])
            assert artifact['sha256']==record['package_sha256']
            with httpx.Client(base_url=client.base_url,trust_env=False) as anonymous:
                assert anonymous.get('/api/v1/artifacts/'+artifact['id']+'/download').status_code==401
            downloaded=root/'package-downloaded';downloaded.mkdir()
            write_bytes(downloaded/'package.zip',response.content,144*1024**2)
            with transaction() as connection:
                connection.execute('BEGIN');pair=sources(connection,onnx['id'])
            frozen=FrozenPackage.model_validate({'schema_version':1,'project_id':project,'model':pair['onnx'],'params':body['params'],
                'template':record['template'],'runtime_binding':record['runtime_binding'],'code_version':record['code_version'],
                'template_validation_sha256':digest_json(record)}).model_dump(mode='json')
            info=verify_bundle(downloaded/'package.zip',frozen)
            # Fourth fresh process proves the actual authenticated download, not just a template.
            # This evidence is private; metadata is not rewritten to overclaim all packages.
            with worker_lock(root):
                task,proof,_=standalone_stage('cli',frozen,before,(downloaded/'package.zip',info))
            assert proof['output']==record['cli']['output']
            assert runtime_identity()==before and validated_template()['record_sha256']==digest_json(record)
            atomic_json(root/'package-http-job.json',job)
            atomic_json(root/'package-http-artifact.json',artifact)
            atomic_json(root/'package-http-result.json',{'schema_version':1,'status':'passed','job_id':job['id'],'artifact_id':artifact['id'],
                'proof_sha256':digest_json(record),'download_task':task,'download_proof':proof})
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)


def main():
    previous=os.umask(0o077)
    try:
        try:root=prerequisites()
        except Exception:
            print('FAIL independent package prerequisites');return 1
        with (root/'package-private.log').open('x') as diagnostic,contextlib.redirect_stdout(diagnostic),contextlib.redirect_stderr(diagnostic):
            try:run(root,diagnostic)
            except Exception:traceback.print_exc();success=False
            else:success=True
        print('PASS independent package HTTP and downloaded CLI' if success else 'FAIL independent package; private diagnostics retained')
        return 0 if success else 1
    finally:os.umask(previous)


if __name__=='__main__':raise SystemExit(main())
