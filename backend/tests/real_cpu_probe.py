"""Explicit container-only real-data HTTP lifecycle and private measurements.

Never collected by pytest. No imports of the app or native libraries at import.
All IDs, credentials, predictions, models, images and diagnostics remain private.
"""
from contextlib import contextmanager
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import traceback
import zipfile

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'private'


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def guard():
    if ROOT!=Path('/opt/edgevision'):raise ValueError('container checkout required')
    load('isolated_ml_entry').verify_boundary(os.environ.get('EDGEVISION_ISOLATED_HOST_NETNS',''))
    if os.environ.get('PLATFORM_DATA_ROOT')!=str(PRIVATE/'real-platform'):raise ValueError('private root')


def command(args,log,timeout=120):
    subprocess.run([sys.executable,*args],cwd=ROOT/'backend',check=True,stdout=log,stderr=log,timeout=timeout)


class ExportTaskFailure(AssertionError):
    def __init__(self,state,code,detail=None):
        report=load('real_cpu_report')
        self.state=state if type(state) is str and state in report.EXPORT_TASK_STATES else 'unknown'
        self.code=code if type(code) is str and code in report.EXPORT_TASK_CODES else 'unknown'
        self.detail=detail if type(detail) is str and detail in report.EXPORT_DETAILS else None
        super().__init__('export task did not succeed')


def require_export_success(result,task,detail=None):
    if task['state']!='succeeded':raise ExportTaskFailure(task['state'],task.get('error_code'),detail)


@contextmanager
def export_step(result,phase):
    report=load('real_cpu_report')
    if phase not in report.EXPORT_PHASES:raise ValueError('invalid export phase')
    try:yield
    except BaseException as error:
        category='unknown'
        if isinstance(error,subprocess.TimeoutExpired):category='timeout'
        elif isinstance(error,subprocess.CalledProcessError):category='process_failed'
        elif isinstance(error,AssertionError):category='assertion'
        elif isinstance(error,(ValueError,KeyError,TypeError,StopIteration)):category='contract'
        result['export_failure']={'phase':phase,'error':category}
        if phase=='export_result' and isinstance(error,ExportTaskFailure):
            result['export_failure'].update(task_state=error.state,task_code=error.code)
            if error.state=='failed' and error.code=='ONNX_MODEL_INVALID' and error.detail is not None:
                result['export_failure']['detail']=error.detail
        raise


def completed_export_drain(row,receipt):
    return (type(receipt) is dict and row.get('kind')=='export_onnx' and row.get('status')=='failed'
            and row.get('error_code')=='ONNX_MODEL_INVALID' and bool(row.get('run_id'))
            and receipt.get('job_id')==row.get('id') and receipt.get('run_id')==row.get('run_id')
            and receipt.get('tree_exited') is True and receipt.get('reason')=='completed'
            and type(receipt.get('exit_code')) is int and receipt['exit_code']==74
            and receipt.get('started') is True and receipt.get('logs_complete') is True)


def read_export_detail(path):
    report=load('real_cpu_report')
    try:
        # Fail closed on links/special files before parsing a tiny immutable snapshot.
        if any(parent.is_symlink() for parent in path.parents):return 'unknown'
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=1024:return 'unknown'
            raw=source.read(1025)
        if len(raw)!=info.st_size:return 'unknown'
        value=json.loads(raw,object_pairs_hook=report.unique)
        if (type(value) is dict and set(value)=={'schema_version','code'}
                and type(value['schema_version']) is int and value['schema_version']==1
                and type(value['code']) is str and value['code'] in report.EXPORT_DETAILS):return value['code']
    except (OSError,ValueError,TypeError):pass
    return 'unknown'


def export_diagnostic(identity,task,transaction,drain_receipt,run_directory):
    if task.get('state')!='failed' or task.get('error_code')!='ONNX_MODEL_INVALID':return None
    try:
        with transaction() as connection:
            found=connection.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
        if found is None:return 'unknown'
        row=dict(found)
        if row['kind']!='export_onnx' or row['status']!='failed' or row['error_code']!='ONNX_MODEL_INVALID' or not row['run_id']:return 'unknown'
        receipt=drain_receipt(row,wait_seconds=20)
        if not completed_export_drain(row,receipt):return 'unknown'
        return read_export_detail(run_directory(identity,row['run_id'])/'export-failure.json')
    except Exception:return 'unknown'

def stop(process):
    if process is None:return
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    if process.poll() is None:raise ValueError('owned process not stopped')


def response(value,status=200):
    if value.status_code!=status or len(value.content)>2*1024**2:raise ValueError('HTTP contract')
    return value.json()


def digest(path):
    h=sha256()
    with path.open('rb') as source:
        while raw:=source.read(1024*1024):h.update(raw)
    return h.hexdigest()


def verify_download(artifact,value):
    if artifact['kind']=='inference_input':
        if value.status_code!=409 or value.json().get('detail',{}).get('code')!='ARTIFACT_UNAVAILABLE':raise ValueError('input download policy')
    elif value.status_code!=200 or len(value.content)!=artifact['size_bytes'] or sha256(value.content).hexdigest()!=artifact['sha256']:
        raise ValueError('restored download fingerprint')


def started_metric(path,job_id,run_id):
    import math
    try:
        if path.is_symlink():return False
        with path.open('rb') as source:raw=source.readline(4097)
        if not raw.endswith(b'\n') or len(raw)>4096:return False
        value=json.loads(raw)
        return (type(value) is dict and set(value)=={'schema_version','job_id','run_id','seq','epoch','name','value'}
                and type(value['schema_version']) is int and value['schema_version']==1
                and value['job_id']==job_id and value['run_id']==run_id
                and type(value['seq']) is int and value['seq']>=1 and type(value['epoch']) is int and value['epoch']>=1
                and type(value['name']) is str and 0<len(value['name'])<=128
                and type(value['value']) in (int,float) and math.isfinite(value['value']))
    except (OSError,ValueError,KeyError,TypeError):return False


def cleanup_owned(completed,processes,verify):
    failed=False
    for process in processes:
        try:stop(process)
        except BaseException:failed=True
    if failed:return 'failed'
    if not completed:return 'unverified'
    try:return 'passed' if verify() is True else 'failed'
    except BaseException:return 'failed'


def run(result,save,log):
    import httpx
    from app.admin_cli import create_admin
    from app.database import transaction
    from app.worker import drain_receipt
    from app.delivery_infer import match_detections
    report=load('real_cpu_report');dataset=load('real_cpu_dataset');metric=load('real_cpu_metrics')
    server=None;worker=None;client=None;current='dataset';completed=False
    @contextmanager
    def stage(name):
        nonlocal current
        current=name
        item=next(x for x in result['stages'] if x['stage']==name);item['status']='unverified';save()
        try:yield
        except BaseException:item['status']='failed';save();raise
        else:item['status']='passed';save()
    def boot(data):
        env={**os.environ,'PLATFORM_DATA_ROOT':str(data)}
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8896'],cwd=ROOT/'backend',env=env,stdout=log,stderr=log)
        session=httpx.Client(base_url='http://127.0.0.1:8896',timeout=30,trust_env=False)
        try:
            for _ in range(100):
                try:
                    if session.get('/api/v1/health/live').status_code==200:return process,session
                except httpx.TransportError:pass
                if process.poll() is not None:break
                time.sleep(.1)
            raise ValueError('API startup')
        except BaseException:session.close();stop(process);raise
    def headers():return {'Origin':'http://127.0.0.1:5173','X-CSRF-Token':client.cookies.get('edgevision_csrf')}
    def submit(body,key):return response(client.post(f'/api/v1/projects/{project}/jobs',headers={**headers(),'Idempotency-Key':key},json=body),202)['job_id']
    def job(identity):return response(client.get('/api/v1/jobs/'+identity))
    def artifacts():return response(client.get(f'/api/v1/projects/{project}/artifacts',params={'page_size':100}))['items']
    def once(timeout=120):command(['-m','app.worker','--once'],log,timeout)
    def download(artifact,path):
        value=client.get('/api/v1/artifacts/'+artifact['id']+'/download')
        if value.status_code!=200 or len(value.content)!=artifact['size_bytes'] or sha256(value.content).hexdigest()!=artifact['sha256']:raise ValueError('artifact fingerprint')
        path.write_bytes(value.content)
    try:
        with stage('dataset'):
            frozen=dataset.prepare_subset(ROOT/'public-data/images.tar.gz',ROOT/'public-data/annotations.tar.gz',PRIVATE/'subset')
            if frozen['manifest_sha256']!=report.MANIFEST_SHA or frozen['dataset_sha256']!=report.DATASET_SHA:raise ValueError('frozen subset changed')
            manifest=json.loads((PRIVATE/'subset/manifest.json').read_text())
            samples=[s for s in manifest['samples'] if s['split']=='test'];truth=[]
            images=PRIVATE/'test-images';images.mkdir(mode=0o700)
            with zipfile.ZipFile(PRIVATE/'subset/dataset.zip') as archive:
                for sample in samples:
                    name=sample['name'];raw=archive.read(f'images/test/{name}.jpg')
                    if sha256(raw).hexdigest()!=sample['image_sha256']:raise ValueError('test image')
                    (images/f'{name}.jpg').write_bytes(raw)
                    label=archive.read(f'labels/test/{name}.txt')
                    if sha256(label).hexdigest()!=sample['label_sha256']:raise ValueError('test label')
                    truth.append(metric.voc_box_from_yolo(label,sample['width'],sample['height']))
        with stage('dependency_check'):
            command(['-I','-m','pip','check'],log)
            command(['-m','alembic','upgrade','head'],log,30)
            command(['-m','app.training_probe','--asset',str(ROOT/'asset/yolo11n.pt')],log,120)
            password=secrets.token_urlsafe(24);create_admin('experiment',password)
            server,client=boot(PRIVATE/'real-platform')
            response(client.post('/api/v1/auth/login',headers={'Origin':'http://127.0.0.1:5173'},json={'username':'experiment','password':password}))
            del password
            project=response(client.post('/api/v1/projects',headers=headers(),json={'name':'Frozen Oxford head research subset'}),201)['id']
            uploaded=response(client.post(f'/api/v1/projects/{project}/datasets',headers=headers(),files={'file':('frozen-subset.zip',(PRIVATE/'subset/dataset.zip').read_bytes(),'application/zip')}),201)
            dataset_id=uploaded['id']
            response(client.post(f'/api/v1/datasets/{dataset_id}/check',headers={**headers(),'Idempotency-Key':'frozen-check'}),202)
            once();assert response(client.get('/api/v1/datasets/'+dataset_id))['state']=='ready'
        train={'kind':'train','params':{'dataset_id':dataset_id,'experiment_name':'frozen real CPU one epoch','epochs':1,'batch':1,'imgsz':320,'device':'cpu','seed':0,'learning_rate':.01}}
        with stage('training'):
            training=submit(train,'real-training');once(600);assert job(training)['state']=='succeeded'
            pt=next(a for a in artifacts() if a['kind']=='pt_best' and a['job_id']==training)
            download(pt,PRIVATE/'trained.pt')
            (PRIVATE/'validation-metrics.json').write_text(client.get(f'/api/v1/jobs/{training}/metrics').text)
        with stage('export'):
            with export_step(result,'export_probe'):
                command(['-m','app.export_probe'],log,180)
            with export_step(result,'export_submit'):
                export=submit({'kind':'export_onnx','params':{'model_artifact_id':pt['id'],'imgsz':640,'batch':1,'precision':'fp32'}},'real-export')
            with export_step(result,'export_worker'):
                once(180)
            with export_step(result,'export_result'):
                from app.run_files import run_directory
                task=job(export)
                require_export_success(result,task,export_diagnostic(export,task,transaction,drain_receipt,run_directory))
                onnx=next(a for a in artifacts() if a['kind']=='onnx' and a['job_id']==export)
            with export_step(result,'export_download'):
                download(onnx,PRIVATE/'trained.onnx')
            with export_step(result,'export_lineage'):
                assert onnx['metadata']['provenance']['source_sha256']==pt['sha256']
            with export_step(result,'inference_probe'):
                command(['-m','app.inference_probe','--onnx-artifact-id',onnx['id']],log,180)
        measured={};series={}
        with stage('evaluation'):
            for backend in ('pt','onnx'):
                command(['-I',str(ROOT/'scripts/real_cpu_measure.py'),backend],log,180)
                measured[backend]=json.loads((PRIVATE/f'measure-{backend}/result.json').read_text())
                for key,values in measured[backend]['series'].items():series[f'{backend}_{key}']=values
            from array import array
            maximum=0.;ratio=0.
            for i in range(20):
                assert match_detections(measured['pt']['detections'][i],measured['onnx']['detections'][i])
                pair=[]
                for backend in ('pt','onnx'):
                    values=array('f');values.frombytes((PRIVATE/f'measure-{backend}/{i:02}.f32le').read_bytes())
                    if sys.byteorder!='little':values.byteswap()
                    pair.append(values)
                assert len(pair[0])==len(pair[1])==6*8400
                for a,b in zip(*pair):
                    import math
                    assert math.isfinite(a) and math.isfinite(b)
                    error=abs(a-b);maximum=max(maximum,error);ratio=max(ratio,error/(1e-4+1e-4*abs(a)))
                assert ratio<=1
            (PRIVATE/'numeric-comparison.json').write_text(json.dumps({'max_absolute_error':maximum,'max_tolerance_ratio':ratio,'atol':1e-4,'rtol':1e-4}))
            result['evaluation']={'protocol':'single-head-p025-iou050-v1',**{b:metric.evaluate(truth,measured[b]['detections']) for b in ('pt','onnx')}}
            result['evaluation']['comparison']={'images':20,'elements':1008000,'max_absolute_error':maximum,'max_tolerance_ratio':ratio,'atol':1e-4,'rtol':1e-4,'detections_matched':True}
        with stage('timings'):
            for backend,source in (('pt',pt),('onnx',onnx)):
                values=[]
                for index,sample in enumerate(samples):
                    raw=(PRIVATE/'test-images'/f"{sample['name']}.jpg").read_bytes()
                    began=time.perf_counter()
                    image=response(client.post(f'/api/v1/projects/{project}/images',headers=headers(),files={'file':('test.jpg',raw,'image/jpeg')}),201)
                    task=submit({'kind':'infer','params':{'model_artifact_id':source['id'],'image_artifact_id':image['id'],'backend':backend,'confidence':.25,'iou':.45}},f'http-{backend}-{index}')
                    once(60);assert job(task)['state']=='succeeded'
                    artifact=next(a for a in artifacts() if a['kind']=='inference_result' and a['job_id']==task)
                    output=response(client.get('/api/v1/inferences/'+artifact['id']))
                    values.append((time.perf_counter()-began)*1000)
                    assert match_detections(output['detections'],measured[backend]['detections'][index])
                series[f'{backend}_http']=values
            result['measurements']=report.measurements(series,{b:measured[b]['model_load_ms'] for b in ('pt','onnx')})
        for mode in ('cancel','worker_recovery'):
            with stage(mode):
                fault_train={**train,'params':{**train['params'],'epochs':2,'experiment_name':'fault drill after first epoch'}}
                identity=submit(fault_train,'real-'+mode)
                worker=subprocess.Popen([sys.executable,'-m','app.worker','--once'],cwd=ROOT/'backend',stdout=log,stderr=log)
                deadline=time.monotonic()+180;row=None
                while time.monotonic()<deadline:
                    with transaction() as connection:row=dict(connection.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
                    if row['status']=='running' and row['launch_phase']=='go_authorized':
                        from app.run_files import run_directory
                        # A complete bound epoch metric proves native training executed; an empty journal does not.
                        directory=run_directory(identity,row['run_id'])
                        if started_metric(directory/'metrics.jsonl',identity,row['run_id']):break
                    if worker.poll() is not None:raise ValueError('task finished before interruption')
                    time.sleep(.05)
                else:raise ValueError('runner readiness budget')
                if mode=='cancel':
                    response(client.post('/api/v1/jobs/'+identity+'/cancel',headers=headers()))
                    worker.wait(timeout=45);expected='cancelled'
                else:
                    worker.kill();worker.wait(timeout=5);once(60);expected='interrupted'
                worker=None
                assert job(identity)['state']==expected
                assert not any(a['job_id']==identity for a in artifacts())
                assert drain_receipt(row,wait_seconds=20) is not None
        with stage('backup_restore'):
            original=artifacts();cookies=dict(client.cookies);client.close();client=None;stop(server);server=None
            data=PRIVATE/'real-platform';backup=PRIVATE/'real-backup';restored=PRIVATE/'real-restored'
            with sqlite3.connect(data/'platform.db') as connection:
                assert connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('running','cancelling','queued')").fetchone()[0]==0
            files={}
            for path in data.rglob('*'):
                if path.is_symlink():raise ValueError('backup symlink')
                if path.is_file() and path.name not in ('platform.db','platform.db-wal','platform.db-shm'):
                    files[str(path.relative_to(data))]=digest(path)
            shutil.copytree(data,backup,ignore=shutil.ignore_patterns('platform.db','platform.db-wal','platform.db-shm'))
            with sqlite3.connect(data/'platform.db') as source,sqlite3.connect(backup/'platform.db') as target:source.backup(target)
            shutil.copytree(backup,restored)
            assert all(digest(restored/name)==expected for name,expected in files.items())
            with sqlite3.connect(restored/'platform.db') as connection:assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            server,client=boot(restored);client.cookies.update(cookies)
            assert response(client.get('/api/v1/auth/me'))['username']=='experiment'
            assert artifacts()==original
            for artifact in original:
                value=client.get('/api/v1/artifacts/'+artifact['id']+'/download')
                verify_download(artifact,value)
        completed=True
    finally:
        if client is not None:client.close()
        def verify_settled():
            from app.training_probe import recover_probe
            if recover_probe() is not True:return False
            with transaction() as connection:
                if connection.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancelling','queued') LIMIT 1").fetchone():return False
                rows=[dict(row) for row in connection.execute("SELECT * FROM jobs WHERE run_id IS NOT NULL")]
            return all(drain_receipt(row,wait_seconds=20) is not None for row in rows)
        result['stages'][-1]['status']=cleanup_owned(completed,[worker,server],verify_settled);save()


def main():
    guard()
    sys.path.insert(0,str(ROOT/'backend'))
    report=load('real_cpu_report');result=report.initial();result['stages'][0]['status']='passed'
    receipt=PRIVATE/'real-receipt.json'
    if receipt.exists() or (PRIVATE/'real-platform').exists():raise ValueError('fresh experiment required')
    def save():
        raw=json.dumps(result,allow_nan=False)
        # Intermediate stage data may be assigned just before the stage passes;
        # public release occurs only through the final strict entry validator.
        receipt.write_text(raw)
    try:
        with (PRIVATE/'native-private.log').open('x') as log:
            try:run(result,save,log)
            except BaseException:traceback.print_exc(file=log);raise
        result['status']='passed';report.validate(json.dumps(result));save();return 0
    except BaseException:
        result['status']='failed';save();return 1

if __name__=='__main__':raise SystemExit(main())
