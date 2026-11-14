"""Private probe protocol and stdlib raw comparator only; never executes models."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import struct
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.run_files import run_directory, atomic_json
from app.inference_probe import compare_raw
from test_dataset_api import data_root


def raw_proof(content):
    job,run=str(uuid4()),str(uuid4()); directory=run_directory(job,run,create=True)
    (directory/'raw.f32le').write_bytes(content)
    return {'job_id':job,'run_id':run,'raw_size_bytes':len(content),'raw_sha256':sha256(content).hexdigest()}


def test_nonidentical_raw_within_frozen_tolerance(data_root):
    first=raw_proof(struct.pack('<f',1.)*42000)
    second=raw_proof(struct.pack('<f',1.00001)*42000)
    assert first['raw_sha256']!=second['raw_sha256']
    comparison=compare_raw(first,second)
    assert comparison['elements']==42000 and 0<comparison['max_tolerance_ratio']<1


@pytest.mark.parametrize('fault',['truncated','extra','hash','nan','inf','outside','unaligned'])
def test_bad_raw_comparison_fails_closed(data_root,fault):
    first=raw_proof(struct.pack('<f',1.)*42000); second=raw_proof(struct.pack('<f',1.)*42000)
    path=run_directory(second['job_id'],second['run_id'])/'raw.f32le'
    if fault=='truncated':path.write_bytes(path.read_bytes()[:-1])
    if fault=='extra':path.write_bytes(path.read_bytes()+b'x')
    if fault=='hash':second['raw_sha256']='0'*64
    if fault in {'nan','inf','outside','unaligned'}:
        content=b'x' if fault=='unaligned' else struct.pack('<f',{'nan':float('nan'),'inf':float('inf'),'outside':2.}[fault])*42000
        path.write_bytes(content); second['raw_size_bytes']=len(content); second['raw_sha256']=sha256(content).hexdigest()
    with pytest.raises(ValueError):compare_raw(first,second)


def test_shared_recovery_blocks_launch_and_disables_previous_record(data_root,monkeypatch):
    from app import inference_probe
    atomic_json(data_root/'inference-capability.json',{'schema_version':1,'available':True})
    monkeypatch.setattr('app.training_probe.recover_probe',lambda:False)
    monkeypatch.setattr(inference_probe.subprocess,'Popen',lambda *a,**kw:pytest.fail('must not launch'))
    with pytest.raises(RuntimeError,match='Previous shared'):inference_probe.run_probe(str(uuid4()))
    assert json.loads((data_root/'inference-capability.json').read_text())['available'] is False
    monkeypatch.setattr('app.training_probe.recover_probe',lambda:True)
    monkeypatch.setattr('app.worker.recover',lambda:[('blocked','unconfirmed')])
    with pytest.raises(RuntimeError,match='Existing task'):inference_probe.run_probe(str(uuid4()))


def test_missing_and_stale_image_record_unavailable(data_root,monkeypatch):
    from app import inference_assets
    monkeypatch.setattr(inference_assets,'runtime_identity',lambda:{'adapter':{'delivery_infer.py':'a'*64}})
    assert not inference_assets.capability()['available']
    atomic_json(data_root/'inference-capability.json',{'schema_version':1,'available':True})
    assert not inference_assets.capability()['available']


def test_lightweight_api_worker_probe_imports_no_native_models():
    import subprocess,sys
    run=subprocess.run([sys.executable,'-c',"import app.main,app.worker,app.inference_probe,app.inference_runtime,app.delivery_infer,sys; assert not {'torch','numpy','onnx','onnxruntime','ultralytics'}.intersection(sys.modules)"],capture_output=True,text=True)
    assert run.returncode==0,run.stderr


def test_missing_ort_identity_is_classified_without_native_import(monkeypatch):
    from app import inference_assets
    from app.delivery_infer import ImageInferenceError
    from importlib.metadata import PackageNotFoundError
    def missing():raise PackageNotFoundError('onnxruntime')
    monkeypatch.setattr(inference_assets,'export_identity',missing)
    with pytest.raises(ImageInferenceError,match='ORT_DEPENDENCY_MISSING'):inference_assets.runtime_identity()
