"""Synthetic package API/worker tests. Never native standalone acceptance."""
from copy import deepcopy
import json
from uuid import uuid4
import pytest
from test_inference import inference_ready
from test_export import export_ready
from test_training import ready
from test_dataset_api import data_root, headers


def post(context,key='package',retry=None,model=None):
    base, _, onnx, _ = context
    client, project, _, _ = base
    return client.post(f'/api/v1/projects/{project}/jobs',headers={**headers(client),'Idempotency-Key':key},
        json={'kind':'package','params':{'onnx_artifact_id':model or onnx['id']},'source_job_id':retry})


@pytest.fixture
def package_ready(inference_ready,monkeypatch):
    from app import package_service
    from app.package_bundle import template_identity
    identity={'adapter':{'test':'a'*64},'package_template':template_identity()}
    monkeypatch.setattr(package_service,'runtime_identity',lambda:deepcopy(identity))
    monkeypatch.setattr(package_service,'capability',lambda:{'available':True})
    monkeypatch.setattr(package_service,'validated_template',lambda:{'template':identity['package_template'],'record_sha256':'b'*64})
    return inference_ready


def test_package_api_remains_closed_without_independent_proof(inference_ready):
    response=post(inference_ready)
    assert response.status_code==409
    assert response.json()['error']['code']=='PACKAGE_SETUP_REQUIRED'


def test_package_submit_freezes_sources_and_replays_idempotently(package_ready):
    from app.database import transaction
    response=post(package_ready);assert response.status_code==202,response.text
    assert post(package_ready).json()==response.json()
    with transaction() as c:
        row=c.execute('SELECT * FROM jobs WHERE id=?',(response.json()['job_id'],)).fetchone()
        frozen=json.loads(row['input_snapshot_json'])
        assert frozen['model']['source_artifact_id']==package_ready[2]['id']
        assert frozen['template_validation_sha256']=='b'*64
    assert post(package_ready,retry=str(uuid4())).status_code==409


def test_package_rejects_non_onnx_and_unknown_retry(package_ready):
    assert post(package_ready,model=package_ready[1]['id']).status_code==409
    assert post(package_ready,retry=str(uuid4())).status_code==409


def test_package_retry_requires_terminal_same_project_job(package_ready):
    from app.database import transaction
    first=post(package_ready);assert first.status_code==202
    identifier=first.json()['job_id']
    assert post(package_ready,key='retry',retry=identifier).status_code==409
    with transaction() as c:c.execute("UPDATE jobs SET status='failed' WHERE id=?",(identifier,))
    second=post(package_ready,key='retry',retry=identifier)
    assert second.status_code==202 and second.json()['job_id']!=identifier


def sealed(context,monkeypatch):
    from app import package_runner,package_publication,package_service
    from app.worker import claim,get_job
    from app.run_files import run_directory,atomic_json
    for module in (package_runner,package_publication):
        monkeypatch.setattr(module,'runtime_identity',package_service.runtime_identity)
        monkeypatch.setattr(module,'validated_template',package_service.validated_template)
    response=post(context);assert response.status_code==202,response.text
    identifier=response.json()['job_id'];assert claim('package-fixture',None)[0]==identifier
    job=get_job(identifier);directory=run_directory(identifier,job['run_id'],create=True)
    atomic_json(directory/'input.json',{'schema_version':1,'job_id':identifier,'run_id':job['run_id'],'kind':'package','input':json.loads(job['input_snapshot_json'])})
    assert package_runner.run(identifier,job['run_id'])==0
    return job,directory


def test_package_runner_seals_but_publication_needs_exit_receipt(package_ready,monkeypatch):
    from app.package_publication import publish
    job,directory=sealed(package_ready,monkeypatch)
    monkeypatch.setattr('app.worker.drain_receipt', lambda job: None)
    with pytest.raises(ValueError):publish(job)
    assert (directory/'bundle'/'package.zip').is_file()


def test_package_publish_and_historical_download(package_ready,monkeypatch):
    from app import worker
    from app.package_publication import publish
    from app.database import transaction
    job,directory=sealed(package_ready,monkeypatch)
    monkeypatch.setattr(worker,'drain_receipt',lambda job:{'reason':'completed','exit_code':0,'logs_complete':True,'started':True})
    assert publish(job)
    with transaction() as c:row=dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='deployment_zip'",(job['id'],)).fetchone())
    response=package_ready[0][0].get(f"/api/v1/artifacts/{row['id']}/download")
    assert response.status_code==200,response.text[:100]
    assert response.content.startswith(b'PK')
    assert json.loads(row['metadata_json'])['standalone_execution']=='not_run_for_this_artifact'


def test_package_cancelled_before_publication_never_succeeds(package_ready,monkeypatch):
    from app import worker
    from app.package_publication import publish
    from app.database import transaction
    job,_=sealed(package_ready,monkeypatch)
    monkeypatch.setattr(worker,'drain_receipt',lambda job:{'reason':'completed','exit_code':0,'logs_complete':True,'started':True})
    with transaction() as c:c.execute("UPDATE jobs SET status='cancelling' WHERE id=?",(job['id'],))
    assert publish(job) is False
    with transaction() as c:assert c.execute('SELECT count(*) FROM artifacts WHERE job_id=?',(job['id'],)).fetchone()[0]==0


def test_package_changed_zip_is_rejected(package_ready,monkeypatch):
    from app import worker
    from app.package_publication import publish
    job,directory=sealed(package_ready,monkeypatch)
    monkeypatch.setattr(worker,'drain_receipt',lambda job:{'reason':'completed','exit_code':0,'logs_complete':True,'started':True})
    path=directory/'bundle'/'package.zip';path.write_bytes(path.read_bytes()+b'junk')
    with pytest.raises(ValueError):publish(job)


@pytest.mark.parametrize('fault',['exit','started','logs','reason'])
def test_package_requires_complete_successful_receipt(package_ready,monkeypatch,fault):
    from app.package_publication import publish
    job,_=sealed(package_ready,monkeypatch)
    receipt={'reason':'completed','exit_code':0,'logs_complete':True,'started':True}
    receipt[{'exit':'exit_code','started':'started','logs':'logs_complete','reason':'reason'}[fault]]={'exit':1,'started':False,'logs':False,'reason':'cancelled'}[fault]
    monkeypatch.setattr('app.worker.drain_receipt',lambda job:receipt)
    with pytest.raises(ValueError):publish(job)


@pytest.mark.parametrize('fault',['deleted','symlink','crc'])
def test_package_historical_download_corruption_is_409(package_ready,monkeypatch,fault):
    from app.package_publication import publish
    from app.database import transaction
    from app.dataset_storage import resolve_storage_file
    job,_=sealed(package_ready,monkeypatch);assert publish(job)
    with transaction() as c:row=dict(c.execute("SELECT * FROM artifacts WHERE job_id=? AND kind='deployment_zip'",(job['id'],)).fetchone())
    path=resolve_storage_file(row['storage_key'])
    if fault=='deleted':path.unlink()
    elif fault=='symlink':path.unlink();path.symlink_to(path.parent/'metadata.json')
    else:
        raw=bytearray(path.read_bytes());raw[100]^=1;path.write_bytes(raw)
    response=package_ready[0][0].get(f"/api/v1/artifacts/{row['id']}/download")
    assert response.status_code==409,response.text[:100]


def test_historical_package_download_ignores_current_capability(package_ready,monkeypatch):
    from app.package_publication import publish
    from app.database import transaction
    from app import package_assets
    job,_=sealed(package_ready,monkeypatch);assert publish(job)
    with transaction() as c:identifier=c.execute("SELECT id FROM artifacts WHERE job_id=? AND kind='deployment_zip'",(job['id'],)).fetchone()[0]
    monkeypatch.setattr(package_assets,'runtime_identity',lambda:(_ for _ in ()).throw(ValueError('runtime removed')))
    assert package_ready[0][0].get(f'/api/v1/artifacts/{identifier}/download').status_code==200


def test_task_dispatch_package_is_fixed_and_not_model_native(package_ready,monkeypatch):
    from app import package_runner,task_process
    job,_=sealed(package_ready,monkeypatch)
    monkeypatch.setattr(package_runner,'run',lambda job_id,run_id:42)
    assert task_process.execute(job['id'],job['run_id'])==42


def test_package_job_public_summary_is_safe_and_bound(package_ready):
    response=post(package_ready);assert response.status_code==202
    job=package_ready[0][0].get('/api/v1/jobs/'+response.json()['job_id']).json()
    assert job['package']['onnx_artifact_id']==package_ready[2]['id']
    assert set(job['package'])=={'onnx_artifact_id','export_job_id','source_sha256','template_sha256','params','runtime_binding','code_version'}


@pytest.mark.parametrize('route',['detail','list','download'])
def test_bad_package_metadata_is_409_on_every_route(package_ready,monkeypatch,route):
    from app.package_publication import publish
    from app.database import transaction
    job,_=sealed(package_ready,monkeypatch);assert publish(job)
    with transaction() as c:
        identifier=c.execute("SELECT id FROM artifacts WHERE job_id=? AND kind='deployment_zip'",(job['id'],)).fetchone()[0]
        c.execute("UPDATE artifacts SET metadata_json='{}' WHERE id=?",(identifier,))
    url={'detail':f'/api/v1/artifacts/{identifier}','list':f'/api/v1/projects/{job["project_id"]}/artifacts','download':f'/api/v1/artifacts/{identifier}/download'}[route]
    assert package_ready[0][0].get(url).status_code==409


@pytest.mark.parametrize('exception',['zip','struct'])
def test_archive_parser_failure_is_closed_409(package_ready,monkeypatch,exception):
    import zipfile,struct
    from app.package_publication import publish
    from app.database import transaction
    job,_=sealed(package_ready,monkeypatch);assert publish(job)
    with transaction() as c:identifier=c.execute("SELECT id FROM artifacts WHERE job_id=? AND kind='deployment_zip'",(job['id'],)).fetchone()[0]
    def broken(*args,**kwargs):raise (zipfile.BadZipFile if exception=='zip' else struct.error)('private parse detail')
    monkeypatch.setattr(zipfile,'ZipFile',broken)
    response=package_ready[0][0].get(f'/api/v1/artifacts/{identifier}/download')
    assert response.status_code==409
    assert 'private parse detail' not in response.text


@pytest.mark.parametrize('behavior',['tree','worker_lost','pre_go','exit_zero'])
def test_managed_package_process_contract(package_ready,behavior):
    """Real guardian process lifecycle with explicit non-model fixture runner."""
    from test_worker_process import start,run_path,wait_marker,record,wait_until,stop_and_reap
    from test_worker_api import work
    from app.process_identity import exited
    from app.database import transaction
    client=package_ready[0][0];identifier=post(package_ready).json()['job_id']
    process=start('package_'+('tree' if behavior=='worker_lost' else behavior));directory=run_path(identifier)
    try:
        if behavior=='exit_zero':
            assert process.wait(timeout=20)==0
            assert record(identifier)['status']=='failed' and record(identifier)['error_code']=='OUTPUT_INVALID'
        elif behavior=='pre_go':
            wait_marker(directory,'worker-before-go.json')
            client.post('/api/v1/jobs/'+identifier+'/cancel',headers=headers(client));(directory/'release-worker').touch()
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
        with transaction() as c:assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?',(identifier,)).fetchone()[0]==0
    finally:stop_and_reap(process)
