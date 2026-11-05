"""T050 lightweight boundary/fault tests. PT bytes here are explicit publication fixtures, not ML evidence."""
import json
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_dataset_api import data_root, setup_admin, upload, headers, create_user
from test_worker_api import submit, work
from app import training_service, training_inputs, training_assets
from app.training_assets import BASE_MANIFEST, digest_json
from app.database import transaction
from app.run_files import atomic_json, fingerprint, run_directory
from app.job_service import canonical
from app.training_metrics import ingest_metrics
from app.training_publication import publish, verify
from app.worker import claim, get_job

@pytest.fixture
def ready(data_root, monkeypatch):
    client, project = setup_admin(data_root)
    dataset = upload(client, project).json()
    submit(client, dataset['id']); work()
    monkeypatch.setattr(training_service, 'capability', lambda: {'available':True})
    monkeypatch.setattr(training_service, 'verify_asset', lambda: BASE_MANIFEST)
    monkeypatch.setattr(training_inputs, 'verify_asset', lambda: BASE_MANIFEST)
    monkeypatch.setattr(training_service, 'runtime_identity', lambda: {'adapter': {'test': 'explicit lightweight fixture'}})
    params = {'dataset_id': dataset['id'], 'experiment_name':'test', 'epochs':1,'batch':1,'seed':0,'imgsz':320,'device':'cpu','learning_rate':.01}
    return client, project, dataset['id'], params


def post(ready, key='train', **changes):
    client, project, _, params = ready
    return client.post(f'/api/v1/projects/{project}/jobs', headers={**headers(client),'Idempotency-Key':key}, json={'kind':'train','params':{**params, **changes}})


def test_train_submission_replay_conflict_retry_and_ready_unchanged(ready):
    client, project, dataset, params = ready
    created = post(ready); assert created.status_code == 202, created.text
    job = created.json()['job_id']
    assert post(ready).json()['job_id'] == job
    assert post(ready, epochs=2).status_code == 409
    detail = client.get(f'/api/v1/jobs/{job}').json()
    assert detail['training']['params']['learning_rate'] == .01
    assert 'snapshot_key' not in json.dumps(detail)
    assert client.post(f'/api/v1/jobs/{job}/cancel',headers=headers(client)).json()['state']=='cancelled'
    assert client.get(f'/api/v1/datasets/{dataset}').json()['state']=='ready'
    retry=client.post(f'/api/v1/projects/{project}/jobs',headers={**headers(client),'Idempotency-Key':'retry'},json={'kind':'train','params':params,'source_job_id':job})
    assert retry.status_code==202
    assert client.get('/api/v1/jobs/'+retry.json()['job_id']).json()['source_job_id']==job

@pytest.mark.parametrize('changes', [{'batch':0},{'batch':True},{'epochs':101},{'imgsz':128},{'learning_rate':'NaN'},{'workers':2},{'device':'cuda:1'},{'resume':True},{'base_model':'/tmp/other.pt'}])
def test_strict_training_parameters(ready, changes):
    assert post(ready, **changes).status_code==422


def test_device_capability_archived_and_cross_owner(ready, monkeypatch):
    client, project, dataset, _=ready
    assert post(ready,device='cuda:0').json()['error']['code']=='DEVICE_UNAVAILABLE'
    monkeypatch.setattr(training_service,'capability',lambda:{'available':False})
    assert post(ready).json()['error']['code']=='TRAINING_SETUP_REQUIRED'
    other=create_user(client,'other')
    assert other.post(f'/api/v1/projects/{project}/jobs',headers={**headers(other),'Idempotency-Key':'x'},json={'kind':'train','params':ready[3]}).status_code==404
    client.post(f'/api/v1/projects/{project}/archive',headers=headers(client))
    assert post(ready).status_code==409


def test_pending_dataset_and_corrupt_report_rejected(ready):
    client,project,dataset,_=ready
    pending=upload(client,project,'second.zip').json()
    assert post(ready,dataset_id=pending['id']).json()['error']['code']=='DATASET_NOT_READY'
    with transaction() as c: report=c.execute('SELECT report_key FROM datasets WHERE id=?',(dataset,)).fetchone()[0]
    from app.config import data_root
    (data_root()/report).write_text('{}')
    assert post(ready).json()['error']['code']=='TRAINING_INPUT_UNAVAILABLE'


def fixture_run(ready):
    response=post(ready); assert response.status_code==202,response.text
    job_id=response.json()['job_id']; _,run_id=claim('test-worker',None)
    directory=run_directory(job_id,run_id,create=True)
    job=get_job(job_id); frozen=json.loads(job['input_snapshot_json'])
    event={'schema_version':1,'job_id':job_id,'run_id':run_id,'seq':1,'epoch':1,'name':'train/box_loss','value':.75}
    (directory/'metrics.jsonl').write_text(canonical(event)+'\n')
    return job_id,run_id,directory,frozen,event


def test_metric_journal_atomic_replay_tail_and_bounds(ready):
    job_id,run_id,directory,_,event=fixture_run(ready)
    ingest_metrics(job_id,run_id); ingest_metrics(job_id,run_id)
    with transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM metrics WHERE job_id=?',(job_id,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM job_events WHERE job_id=? AND kind='metric'",(job_id,)).fetchone()[0]==1
    event.update(seq=2,name='train/cls_loss',value=.3)
    with (directory/'metrics.jsonl').open('a') as f:f.write(canonical(event))
    ingest_metrics(job_id,run_id)
    with pytest.raises(ValueError):ingest_metrics(job_id,run_id,final=True)
    with (directory/'metrics.jsonl').open('a') as f:f.write('\n')
    ingest_metrics(job_id,run_id,final=True)
    with transaction() as c:assert c.execute('SELECT COUNT(*) FROM metrics WHERE job_id=?',(job_id,)).fetchone()[0]==2

@pytest.mark.parametrize('changes',[{'epoch':2},{'seq':2},{'name':'secret/path'},{'run_id':str(uuid4())},{'value':float('nan')},{'value':True}])
def test_metric_invalid_event_rolls_back(ready,changes):
    job_id,run_id,directory,_,event=fixture_run(ready)
    (directory/'metrics.jsonl').write_text(json.dumps({**event,**changes})+'\n')
    with pytest.raises(ValueError):ingest_metrics(job_id,run_id,final=True)
    with transaction() as c:assert c.execute('SELECT COUNT(*) FROM metrics WHERE job_id=?',(job_id,)).fetchone()[0]==0


def build_bundle(ready):
    job_id,run_id,directory,frozen,event=fixture_run(ready)
    ingest_metrics(job_id,run_id,final=True)
    bundle=directory/'bundle';bundle.mkdir()
    for name in ('best.pt','last.pt'):(bundle/name).write_bytes(b'explicit lightweight publication fixture, not a real checkpoint')
    size,digest=fingerprint(directory/'metrics.jsonl')
    runtime={'completed_epochs':1,'optimizer_steps':1,'device':'cpu','effective':{'optimizer':'SGD','lr0':.01,'lrf':.01,'warmup_epochs':3.,'warmup_bias_lr':.1,'warmup_momentum':.8,'momentum':.937,'weight_decay':.0005,'nbs':64,'seed':0,'batch':1,'epochs':1,'imgsz':320,'device':'cpu','workers':0,'amp':False,'plots':False,'cache':False,'deterministic':True},'versions':{'torch':'2.15.0+cpu','torchvision':'0.29.2+cpu','ultralytics':'8.4.202'},'safe_load_count':2,'threads':2}
    atomic_json(bundle/'metadata.json',{'schema_version':1,'job_id':job_id,'run_id':run_id,'classes':frozen['classes'],'runtime':runtime,'input_sha256':digest_json(frozen),'metrics_size_bytes':size,'metrics_sha256':digest,'metric_count':1})
    outputs=[{'path':name,'size_bytes':fingerprint(bundle/name)[0],'sha256':fingerprint(bundle/name)[1]} for name in ('best.pt','last.pt','metadata.json')]
    atomic_json(directory/'evidence.json',{'schema_version':1,'job_id':job_id,'run_id':run_id,'input_sha256':digest_json(frozen),'outputs':outputs,'metric_count':1,'completed_epochs':1,'optimizer_steps':1})
    return get_job(job_id),directory

@pytest.mark.parametrize('fault',['missing','extra','hash','metric','cancel'])
def test_bundle_missing_extra_hash_metric_and_cancel(ready,fault):
    job,directory=build_bundle(ready)
    if fault=='missing':(directory/'bundle'/'last.pt').unlink()
    elif fault=='extra':(directory/'bundle'/'other').write_text('unexpected')
    elif fault=='hash':(directory/'bundle'/'best.pt').write_text('changed')
    elif fault=='metric':(directory/'metrics.jsonl').write_text('')
    else:
        ready[0].post(f"/api/v1/jobs/{job['id']}/cancel",headers=headers(ready[0]))
        assert publish(job) is False
    if fault!='cancel':
        with pytest.raises((ValueError,OSError)):publish(job)
    with transaction() as c:assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(job['id'],)).fetchone()[0]==0


def test_bundle_pair_publication_download_owner_and_hash(ready):
    job,directory=build_bundle(ready)
    assert publish(job)
    client,project,dataset,_=ready
    arts=client.get(f'/api/v1/projects/{project}/artifacts').json()['items']
    pts=[a for a in arts if a['job_id']==job['id']];assert {a['kind'] for a in pts}=={'pt_best','pt_last'}
    other=create_user(client,'other')
    for art in pts:
        assert client.get(f"/api/v1/artifacts/{art['id']}/download").status_code==200
        assert other.get(f"/api/v1/artifacts/{art['id']}/download").status_code==404
    assert client.get(f'/api/v1/datasets/{dataset}').json()['state']=='ready'
    assert client.get(f"/api/v1/jobs/{job['id']}").json()['state']=='succeeded'


def test_probe_recovery_blocks_missing_receipt(data_root):
    from app.training_probe import recover_probe
    atomic_json(data_root/'training-probe-active.json',{'job_id':str(uuid4()),'run_id':str(uuid4()),'guardian':None})
    # No process is launched by this test. A persisted ambiguous launch must block.
    from unittest.mock import patch
    with patch('app.worker.drain_receipt',return_value=None):assert recover_probe() is False


def test_probe_does_not_overlap_active_job(data_root,monkeypatch):
    from app.training_probe import run_probe
    monkeypatch.setattr('app.training_probe.recover_probe',lambda:True)
    monkeypatch.setattr('app.worker.recover',lambda:[('job','RECOVERY_BLOCKED')])
    monkeypatch.setattr('app.training_probe.subprocess.Popen',lambda *a,**k:pytest.fail('must not launch'))
    with pytest.raises(RuntimeError,match='Existing task'):run_probe()


def test_lightweight_import_does_not_load_ml():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-c',"import app.main,app.worker,sys; assert 'torch' not in sys.modules and 'ultralytics' not in sys.modules"],capture_output=True,text=True)
    assert result.returncode==0,result.stderr

@pytest.mark.parametrize('fault',['tree','bad_metrics','worker_lost'])
def test_train_real_managed_process_cancel_bad_metrics_worker_loss(ready,fault):
    from test_worker_process import start,run_path,wait_marker,stop_and_reap,record,wait_until
    from app.process_identity import exited
    client,_,dataset,_=ready
    job=post(ready).json()['job_id']
    process=start('training_'+('tree' if fault=='worker_lost' else fault))
    directory=run_path(job)
    try:
        if fault=='bad_metrics':
            assert process.wait(timeout=15)==0,process.stderr.read().decode()
            assert record(job)['status']=='failed' and record(job)['error_code']=='METRICS_INVALID'
        else:
            wait_marker(directory,'grandchild.json')
            if fault=='worker_lost':
                process.kill();process.wait(timeout=10)
                receipt=wait_marker(directory,'drained.json');wait_until(lambda:exited(receipt['guardian']))
                work();assert record(job)['status']=='interrupted'
            else:
                assert client.post(f'/api/v1/jobs/{job}/cancel',headers=headers(client)).json()['state']=='cancelling'
                assert process.wait(timeout=15)==0
                assert record(job)['status']=='cancelled'
        assert client.get(f'/api/v1/datasets/{dataset}').json()['state']=='ready'
        with transaction() as c:assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(job,)).fetchone()[0]==0
    finally:stop_and_reap(process)


def test_training_publication_cancel_after_rename(ready,monkeypatch):
    from app import training_publication
    job,directory=build_bundle(ready)
    rename=training_publication.os.rename
    def race(source,destination):
        rename(source,destination)
        ready[0].post(f"/api/v1/jobs/{job['id']}/cancel",headers=headers(ready[0]))
    monkeypatch.setattr(training_publication.os,'rename',race)
    assert publish(job) is False
    with transaction() as c:assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(job['id'],)).fetchone()[0]==0


def test_training_publication_transaction_rolls_back_pair(ready,monkeypatch):
    from app import training_publication
    job,directory=build_bundle(ready)
    monkeypatch.setattr(training_publication,'transition',lambda *a,**k:False)
    with pytest.raises(RuntimeError):publish(job)
    with transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(job['id'],)).fetchone()[0]==0
        assert c.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]=='running'

@pytest.mark.parametrize('version,disconnect',[('2.4',True),('2.0',True),('2.4',False)])
def test_download_closes_verified_descriptor_on_disconnect(data_root,version,disconnect):
    import asyncio
    from app.training_download import download_pt
    from starlette.requests import ClientDisconnect
    from hashlib import sha256
    path=data_root/'test.pt';path.write_bytes(b'abc')
    response=download_pt({'validation_status':'passed','size_bytes':3,'sha256':sha256(b'abc').hexdigest(),'storage_key':'test.pt','kind':'pt_best'},str(uuid4()))
    source=response.background.func.__self__
    sent=[]
    async def send(message):
        if disconnect and message['type']=='http.response.body':raise OSError('disconnected')
        sent.append(message)
    async def receive():
        if disconnect:return {'type':'http.disconnect'}
        await asyncio.sleep(10)
    async def run():
        try:await response({'type':'http','asgi':{'spec_version':version}},receive,send)
        except ClientDisconnect:pass
    asyncio.run(run())
    assert source.closed
    if not disconnect:assert b''.join(message.get('body',b'') for message in sent)==b'abc'


def test_probe_launch_ambiguity_persists_and_blocks_recovery(data_root,monkeypatch):
    from app import training_probe
    monkeypatch.setattr(training_probe,'verify_asset',lambda:BASE_MANIFEST)
    monkeypatch.setattr('app.worker.recover',lambda:[])
    def failed_launch(*args,**kwargs):raise OSError('injected launch failure')
    monkeypatch.setattr(training_probe.subprocess,'Popen',failed_launch)
    with pytest.raises(OSError):training_probe.run_probe()
    pointer=json.loads((data_root/'training-probe-active.json').read_text())
    assert pointer['guardian'] is None
    assert json.loads((data_root/'training-capability.json').read_text())['available'] is False
    monkeypatch.setattr('app.worker.drain_receipt',lambda *a,**k:None)
    assert training_probe.recover_probe() is False


def test_worker_refuses_unconfirmed_probe_before_claim(data_root,monkeypatch):
    from app import worker,training_probe
    monkeypatch.setattr(training_probe,'recover_probe',lambda:False)
    monkeypatch.setattr(worker,'claim',lambda *a:pytest.fail('unconfirmed probe must prevent claim'))
    monkeypatch.setattr('sys.argv',['worker','--once'])
    assert worker.main()==4
