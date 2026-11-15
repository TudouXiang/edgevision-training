"""Container-only PT research lifecycle; no ONNX export or model sweep."""
from contextlib import contextmanager
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'private'
WORK_BUDGET=1140  # Reserve60s of the entry1200s for owned cleanup.


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def guard():
    if ROOT!=Path('/opt/edgevision'):raise ValueError('container checkout required')
    if os.environ.get('EDGEVISION_PT_EVAL_PROFILE')!='v1':raise ValueError('PT profile required')
    if os.environ.get('PLATFORM_DATA_ROOT')!=str(PRIVATE/'real-platform'):raise ValueError('private root')
    load('isolated_ml_entry').verify_boundary(os.environ.get('EDGEVISION_ISOLATED_HOST_NETNS',''))


def remaining(deadline,limit,*,clock=time.monotonic):
    value=deadline-clock()
    if value<=0:raise TimeoutError('PT evaluation budget exhausted')
    return min(limit,value)


def http_request(client,deadline,method,url,*,clock=time.monotonic,**kwargs):
    value=client.request(method,url,timeout=remaining(deadline,30,clock=clock),**kwargs)
    remaining(deadline,1,clock=clock)
    return value


def training_settled(row,receipt):
    return (type(receipt) is dict and row.get('kind')=='train' and row.get('status')=='succeeded'
            and bool(row.get('run_id')) and receipt.get('job_id')==row.get('id')
            and receipt.get('run_id')==row.get('run_id') and receipt.get('reason')=='completed'
            and type(receipt.get('exit_code')) is int and receipt['exit_code']==0
            and receipt.get('started') is True and receipt.get('logs_complete') is True
            and receipt.get('tree_exited') is True)


def measurement_metrics(value,truth):
    if type(value) is not dict or set(value)!={'detections','series','model_load_ms','lineage_verified'} or value['lineage_verified'] is not True:
        raise ValueError('private measurement contract')
    timings=load('real_cpu_report')
    if type(value['series']) is not dict or set(value['series'])!={'preprocess','model','postprocess','total'}:
        raise ValueError('private timing contract')
    for series in value['series'].values():timings.statistics(series)
    timings.validate_loads({'pt':value['model_load_ms'],'onnx':value['model_load_ms']})
    return load('pt_eval_report').validate_metrics(load('real_cpu_metrics').evaluate(truth,value['detections']))


def read_private_json(path,limit):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('private path link')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit:raise ValueError('private receipt bound')
        raw=source.read(limit+1)
    if len(raw)!=info.st_size:raise ValueError('private receipt changed')
    return json.loads(raw,object_pairs_hook=load('pt_eval_report').unique)


def run(result,save,log):
    # Invoked only after guard; imports below may inspect platform dependencies.
    import httpx
    from app.admin_cli import create_admin
    from app.database import transaction
    from app.export_inputs import source_snapshot
    from app.worker import drain_receipt
    from app.training_probe import recover_probe
    helper_path=ROOT/'backend/tests/real_cpu_probe.py'
    spec=importlib.util.spec_from_file_location('real_helpers',helper_path)
    helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    dataset=load('real_cpu_dataset');pins=load('real_cpu_report');metric=load('real_cpu_metrics');binding_helper=load('pt_eval_binding')
    deadline=time.monotonic()+WORK_BUDGET;server=client=None;completed=False
    @contextmanager
    def stage(name):
        remaining(deadline,1)
        item=next(s for s in result['stages'] if s['stage']==name);item['status']='unverified';save()
        try:yield
        except BaseException:item['status']='failed';save();raise
        else:item['status']='passed';save()
    def command(args,limit=120):
        subprocess.run([sys.executable,*args],cwd=ROOT/'backend',check=True,stdout=log,stderr=log,timeout=remaining(deadline,limit))
    def response(value,status=200):return helpers.response(value,status)
    def request(method,url,**kwargs):return http_request(client,deadline,method,url,**kwargs)
    def headers():return {'Origin':'http://127.0.0.1:5173','X-CSRF-Token':client.cookies.get('edgevision_csrf')}
    def once(limit=120):command(['-m','app.worker','--once'],limit)
    def lineage():
        with transaction() as connection:
            snapshot=source_snapshot(connection,project,pt['id'])
            row=connection.execute('SELECT * FROM jobs WHERE id=?',(training,)).fetchone()
        if row is None or not training_settled(dict(row),drain_receipt(dict(row),wait_seconds=5)):
            raise ValueError('training not completely drained')
        if (snapshot['source_job_id']!=training or snapshot['source_sha256']!=binding['sha256']
                or snapshot['source_size_bytes']!=binding['size_bytes']):raise ValueError('training lineage changed')
        return snapshot
    try:
        with stage('dataset'):
            frozen=dataset.prepare_subset(ROOT/'public-data/images.tar.gz',ROOT/'public-data/annotations.tar.gz',PRIVATE/'subset')
            if frozen['manifest_sha256']!=pins.MANIFEST_SHA or frozen['dataset_sha256']!=pins.DATASET_SHA:raise ValueError('frozen dataset changed')
            manifest=read_private_json(PRIVATE/'subset/manifest.json',1024*1024)
            samples=[s for s in manifest['samples'] if s['split']=='test']
            if len(samples)!=20 or len({s['name'] for s in samples})!=20:raise ValueError('fixed test split')
            images=PRIVATE/'test-images';images.mkdir(mode=0o700);truth=[]
            with zipfile.ZipFile(PRIVATE/'subset/dataset.zip') as archive:
                for sample in samples:
                    name=sample['name'];raw=archive.read(f'images/test/{name}.jpg');label=archive.read(f'labels/test/{name}.txt')
                    if sha256(raw).hexdigest()!=sample['image_sha256'] or sha256(label).hexdigest()!=sample['label_sha256']:raise ValueError('test fingerprints')
                    (images/f'{name}.jpg').write_bytes(raw)
                    truth.append(metric.voc_box_from_yolo(label,sample['width'],sample['height']))
        with stage('dependency_check'):
            command(['-I','-m','pip','check']);command(['-m','alembic','upgrade','head'],30)
            command(['-m','app.training_probe','--asset',str(ROOT/'asset/yolo11n.pt')],120)
            password=secrets.token_urlsafe(24);create_admin('experiment',password)
            server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8896'],cwd=ROOT/'backend',stdout=log,stderr=log)
            client=httpx.Client(base_url='http://127.0.0.1:8896',timeout=30,trust_env=False)
            for _ in range(100):
                remaining(deadline,1)
                try:
                    if request('GET','/api/v1/health/live').status_code==200:break
                except httpx.TransportError:pass
                if server.poll() is not None:raise ValueError('API startup')
                time.sleep(.1)
            else:raise ValueError('API startup timeout')
            response(request('POST','/api/v1/auth/login',headers={'Origin':'http://127.0.0.1:5173'},json={'username':'experiment','password':password}));del password
            project=response(request('POST','/api/v1/projects',headers=headers(),json={'name':'Frozen PT-only research'}),201)['id']
            uploaded=response(request('POST',f'/api/v1/projects/{project}/datasets',headers=headers(),files={'file':('frozen-subset.zip',(PRIVATE/'subset/dataset.zip').read_bytes(),'application/zip')}),201)
            dataset_id=uploaded['id']
            response(request('POST',f'/api/v1/datasets/{dataset_id}/check',headers={**headers(),'Idempotency-Key':'pt-check'}),202)
            once()
            if response(request('GET','/api/v1/datasets/'+dataset_id))['state']!='ready':raise ValueError('dataset validation')
        with stage('training'):
            body={'kind':'train','params':{'dataset_id':dataset_id,'experiment_name':'frozen PT-only one epoch','epochs':1,'batch':1,'imgsz':320,'device':'cpu','seed':0,'learning_rate':.01}}
            training=response(request('POST',f'/api/v1/projects/{project}/jobs',headers={**headers(),'Idempotency-Key':'pt-training'},json=body),202)['job_id']
            once(600)
            if response(request('GET','/api/v1/jobs/'+training))['state']!='succeeded':raise ValueError('training did not succeed')
            artifacts=response(request('GET',f'/api/v1/projects/{project}/artifacts',params={'page_size':100}))['items']
            pt=next(a for a in artifacts if a['kind']=='pt_best' and a['job_id']==training)
            binding={'sha256':pt['sha256'],'size_bytes':pt['size_bytes']};binding_helper.validate(binding)
            snapshot=lineage()
            download=request('GET','/api/v1/artifacts/'+pt['id']+'/download');helpers.verify_download(pt,download)
            (PRIVATE/'trained.pt').write_bytes(download.content);binding_helper.verify_file(PRIVATE/'trained.pt',binding)
            (PRIVATE/'pt-eval-model.json').write_text(json.dumps(binding,allow_nan=False))
        with stage('evaluation'):
            if lineage()!=snapshot:raise ValueError('source snapshot changed')
            command(['-I',str(ROOT/'scripts/real_cpu_measure.py'),'pt'],180)
            measured=read_private_json(PRIVATE/'measure-pt/result.json',1024*1024)
            value=measurement_metrics(measured,truth)
            if lineage()!=snapshot:raise ValueError('source snapshot changed after evaluation')
            binding_helper.verify_file(PRIVATE/'trained.pt',binding)
            binding_helper.verify_file(PRIVATE/'measure-pt/model.pt',binding)
            result['metrics']=value;result['lineage_verified']=True
        completed=True
    finally:
        if client is not None:client.close()
        def settled():
            if recover_probe() is not True:return False
            with transaction() as connection:
                if connection.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancelling','queued') LIMIT 1").fetchone():return False
                rows=[dict(r) for r in connection.execute('SELECT * FROM jobs WHERE run_id IS NOT NULL')]
            return all(drain_receipt(row,wait_seconds=5) is not None for row in rows)
        result['stages'][-1]['status']=helpers.cleanup_owned(completed,[server],settled);save()


def main():
    guard();sys.path.insert(0,str(ROOT/'backend'))
    report=load('pt_eval_report');result=report.initial();result['stages'][0]['status']='passed'
    receipt=PRIVATE/'pt-eval-receipt.json'
    if receipt.exists() or (PRIVATE/'real-platform').exists():raise ValueError('fresh PT evaluation required')
    def save():receipt.write_text(json.dumps(report.validate(json.dumps(result)),allow_nan=False))
    save()
    try:
        with (PRIVATE/'pt-eval-private.log').open('w') as log:run(result,save,log)
        result['status']='passed';save();return 0
    except BaseException:
        result['status']='failed';save();return 1

if __name__=='__main__':raise SystemExit(main())
