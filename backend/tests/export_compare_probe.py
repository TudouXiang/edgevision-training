"""Container-only diagnostic coordinator. No product acceptance or ML at import."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'private'
ARM_BUDGET=210


def load(name):
    path=ROOT/'scripts'/f'{name}.py'
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def guard():
    if ROOT!=Path('/opt/edgevision') or os.environ.get('EDGEVISION_EXPORT_COMPARE_PROFILE')!='v1':raise ValueError('diagnostic container required')
    load('isolated_ml_entry').verify_boundary(os.environ.get('EDGEVISION_ISOLATED_HOST_NETNS',''))
    if os.environ.get('PLATFORM_DATA_ROOT')!=str(PRIVATE/'real-platform'):raise ValueError('private root required')


def require_arm_budget(deadline):
    if deadline-time.monotonic()<2*ARM_BUDGET:raise TimeoutError('full diagnostic budget unavailable')
    return 2*ARM_BUDGET


def accept_receipt(receipt,job_id,run_id):
    return (type(receipt) is dict and receipt.get('job_id')==job_id and receipt.get('run_id')==run_id
            and receipt.get('reason')=='completed' and receipt.get('tree_exited') is True
            and receipt.get('started') is True and receipt.get('logs_complete') is True
            and type(receipt.get('exit_code')) is int and receipt['exit_code'] in (0,74))


def read_proof(path,arm):
    report=load('export_compare_report')
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('proof link')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=8192:raise ValueError('proof type or size')
        raw=source.read(8193)
    if len(raw)!=info.st_size:raise ValueError('proof changed')
    proof=report.validate_proof(json.loads(raw,object_pairs_hook=report.unique))
    if proof['arm']!=arm:raise ValueError('proof arm')
    return proof


def run_arms(frozen,result,save,deadline):
    from app.config import data_root
    from app.worker import worker_lock,guardian_command,drain_receipt,recover
    from app.training_probe import recover_probe
    from app.python_launch import python_child
    from app.process_identity import identity
    from app.run_files import atomic_json,run_directory,fingerprint
    from app.export_contract import ExportInput
    from app.export_inputs import verify_input
    from app.export_assets import runtime_identity
    from app.training_assets import digest_json
    from app.export_backend_handoff import capture, verify
    report=load('export_compare_report');root=data_root();backend_source=None
    with worker_lock(root):
        if not recover_probe() or recover():raise ValueError('prior process unsettled')
        require_arm_budget(deadline)
        for arm in report.ARMS:
            if arm=='D':verify(backend_source,frozen)
            verify_input(frozen)
            if digest_json(runtime_identity())!=frozen['runtime_binding']:raise ValueError('runtime changed')
            if deadline-time.monotonic()<ARM_BUDGET:raise TimeoutError('arm budget')
            job_id,run_id=str(uuid4()),str(uuid4())
            directory=run_directory(job_id,run_id,create=True)
            source_export=ExportInput.model_validate({'schema_version':1,'job_id':job_id,'run_id':run_id,'kind':'export_onnx','input':frozen}).model_dump(mode='json')
            atomic_json(directory/'input.json',{'schema_version':1,'job_id':job_id,'run_id':run_id,'kind':'real_export_diagnostic','arm':arm,'source_export':source_export,'backend_source':backend_source})
            input_binding=fingerprint(directory/'input.json')
            active={'job_id':job_id,'run_id':run_id,'guardian':None}
            atomic_json(root/'training-probe-active.json',active)
            command,env=python_child(guardian_command(job_id,run_id));child=None
            try:
                child=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
                active['guardian']=identity(child.pid)
                atomic_json(root/'training-probe-active.json',active)
                child.stdin.write(b'GO\n');child.stdin.flush()
                try:child.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    child.stdin.write(b'STOP\n');child.stdin.flush();child.wait(timeout=25)
            finally:
                if child is not None and child.stdin:
                    try:child.stdin.close()
                    except BrokenPipeError:pass
            row={'id':job_id,'run_id':run_id,'process_identity_json':json.dumps({'guardian':active['guardian']})}
            receipt=drain_receipt(row,wait_seconds=5)
            if not accept_receipt(receipt,job_id,run_id):raise ValueError('diagnostic drain rejected')
            verify_input(frozen)
            if digest_json(runtime_identity())!=frozen['runtime_binding']:raise ValueError('runtime changed')
            if fingerprint(directory/'input.json')!=input_binding:raise ValueError('diagnostic input changed')
            proof=read_proof(directory/'diagnostic-proof.json',arm)
            if (receipt['exit_code']==0)!=(proof['status']=='passed'):raise ValueError('proof exit mismatch')
            result['arms'][arm]=proof;save()
            if proof['failure_code'] in ('POLICY_FAILED','SOURCE_INVALID','SOURCE_CHANGED') or not report.observed(proof):raise ValueError('incomplete or unsafe observations')
            if proof['checks']['network_unchanged'] is not True:raise ValueError('network changed')
            if arm=='A':backend_source=capture(job_id,run_id,frozen,proof['precision'])
            else:
                verify(backend_source,frozen)
                if any(proof['precision'][k]!=backend_source['precision'][k] for k in ('global','backend','conv','matmul')):raise ValueError('precision changed')


def run(result,save,log):
    # Entry guard executes before these platform imports.
    import httpx
    from app.admin_cli import create_admin
    from app.database import transaction
    from app.export_inputs import source_snapshot,verify_input
    from app.export_contract import FrozenExport
    from app.export_assets import runtime_identity
    from app.training_assets import digest_json
    report=load('export_compare_report');dataset=load('real_cpu_dataset');pins=load('real_cpu_report')
    deadline=time.monotonic()+1360
    server=None;client=None;completed=False
    @contextmanager
    def stage(name):
        item=next(s for s in result['stages'] if s['stage']==name);item['status']='unverified';save()
        try:yield
        except BaseException:item['status']='failed';save();raise
        else:item['status']='passed';save()
    def command(args,limit):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('experiment budget')
        subprocess.run([sys.executable,*args],cwd=ROOT/'backend',check=True,stdout=log,stderr=log,timeout=min(limit,remaining))
    def response(value,status=200):
        if value.status_code!=status or len(value.content)>2*1024**2:raise ValueError('HTTP contract')
        return value.json()
    def headers():return {'Origin':'http://127.0.0.1:5173','X-CSRF-Token':client.cookies.get('edgevision_csrf')}
    try:
        with stage('dataset'):
            data=dataset.prepare_subset(ROOT/'public-data/images.tar.gz',ROOT/'public-data/annotations.tar.gz',PRIVATE/'subset')
            if data['manifest_sha256']!=pins.MANIFEST_SHA or data['dataset_sha256']!=pins.DATASET_SHA:raise ValueError('frozen dataset changed')
        with stage('dependency_check'):
            command(['-I','-m','pip','check'],120);command(['-m','alembic','upgrade','head'],30)
            command(['-m','app.training_probe','--asset',str(ROOT/'asset/yolo11n.pt')],120)
            password=secrets.token_urlsafe(24);create_admin('experiment',password)
            server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8896'],cwd=ROOT/'backend',stdout=log,stderr=log)
            client=httpx.Client(base_url='http://127.0.0.1:8896',timeout=30,trust_env=False)
            for _ in range(100):
                try:
                    if client.get('/api/v1/health/live').status_code==200:break
                except httpx.TransportError:pass
                if server.poll() is not None:raise ValueError('server exited')
                time.sleep(.1)
            else:raise ValueError('server unavailable')
            response(client.post('/api/v1/auth/login',headers={'Origin':'http://127.0.0.1:5173'},json={'username':'experiment','password':password}));del password
            project=response(client.post('/api/v1/projects',headers=headers(),json={'name':'Frozen Oxford export diagnostic'}),201)['id']
            dataset_id=response(client.post(f'/api/v1/projects/{project}/datasets',headers=headers(),files={'file':('frozen-subset.zip',(PRIVATE/'subset/dataset.zip').read_bytes(),'application/zip')}),201)['id']
            response(client.post(f'/api/v1/datasets/{dataset_id}/check',headers={**headers(),'Idempotency-Key':'compare-check'}),202)
            command(['-m','app.worker','--once'],120)
            assert response(client.get('/api/v1/datasets/'+dataset_id))['state']=='ready'
        with stage('training'):
            body={'kind':'train','params':{'dataset_id':dataset_id,'experiment_name':'frozen real CPU one epoch','epochs':1,'batch':1,'imgsz':320,'device':'cpu','seed':0,'learning_rate':.01}}
            training=response(client.post(f'/api/v1/projects/{project}/jobs',headers={**headers(),'Idempotency-Key':'compare-training'},json=body),202)['job_id']
            command(['-m','app.worker','--once'],600)
            assert response(client.get('/api/v1/jobs/'+training))['state']=='succeeded'
            artifacts=response(client.get(f'/api/v1/projects/{project}/artifacts',params={'page_size':100}))['items']
            pt=next(a for a in artifacts if a['kind']=='pt_best' and a['job_id']==training)
            with transaction() as connection:source=source_snapshot(connection,project,pt['id'])
            if source['source_job_id']!=training or source['source_sha256']!=pt['sha256'] or source['source_size_bytes']!=pt['size_bytes']:raise ValueError('source binding changed')
            runtime=runtime_identity()
            frozen=FrozenExport.model_validate({'schema_version':1,**source,'params':{'model_artifact_id':pt['id'],'imgsz':640,'batch':1,'precision':'fp32'},'runtime_binding':digest_json(runtime),'code_version':digest_json(runtime['adapter'])}).model_dump(mode='json')
            verify_input(frozen)
        # Insufficient budget leaves all arms NOT_RUN rather than partial execution.
        require_arm_budget(deadline)
        with stage('diagnostic'):run_arms(frozen,result,save,deadline)
        completed=True
    finally:
        cleanup=next(s for s in result['stages'] if s['stage']=='cleanup');cleanup['status']='unverified'
        try:
            if client is not None:client.close()
            if server is not None:
                if server.poll() is None:
                    server.terminate()
                    try:server.wait(timeout=10)
                    except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
                if server.poll() is None:raise ValueError('server unsettled')
            from app.training_probe import recover_probe
            from app.worker import drain_receipt
            if not recover_probe():raise ValueError('probe unsettled')
            with transaction() as connection:
                if connection.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancelling','queued') LIMIT 1").fetchone():raise ValueError('tasks unsettled')
                rows=[dict(r) for r in connection.execute('SELECT * FROM jobs WHERE run_id IS NOT NULL')]
            if any(drain_receipt(row,wait_seconds=5) is None for row in rows):raise ValueError('task drain missing')
            cleanup['status']='passed' if completed else 'unverified'
        except BaseException:cleanup['status']='failed'
        save()


def main():
    guard();sys.path.insert(0,str(ROOT/'backend'))
    report=load('export_compare_report');result=report.initial();result['stages'][0]['status']='passed'
    receipt=PRIVATE/'compare-receipt.json'
    if receipt.exists() or (PRIVATE/'real-platform').exists():raise ValueError('fresh experiment required')
    def save():receipt.write_text(json.dumps(result,allow_nan=False))
    try:
        with (PRIVATE/'compare-private.log').open('x') as log:run(result,save,log)
        result['status']='passed';report.validate(json.dumps(result));save();return 0
    except BaseException:
        result['status']='failed';save();return 1


if __name__=='__main__':raise SystemExit(main())
