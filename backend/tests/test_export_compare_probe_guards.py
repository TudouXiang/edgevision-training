"""Diagnostic harness gates, with synthetic receipts only."""
import importlib.util
from pathlib import Path
import pytest


def probe():
    path=Path(__file__).with_name('export_compare_probe.py')
    assert path.exists()
    spec=importlib.util.spec_from_file_location('compare_probe',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_noncontainer_rejected():
    with pytest.raises(ValueError):probe().guard()


def test_three_arm_budget_is_reserved(monkeypatch):
    m=probe();monkeypatch.setattr(m.time,'monotonic',lambda:100)
    assert m.require_arm_budget(731)==630
    with pytest.raises(TimeoutError):m.require_arm_budget(729)


def test_bound_completed_receipt_only():
    m=probe();r={'job_id':'j','run_id':'r','reason':'completed','tree_exited':True,'started':True,'logs_complete':True,'exit_code':74}
    assert m.accept_receipt(r,'j','r')
    for key,value in [('job_id','x'),('run_id','x'),('tree_exited',False),('reason','timeout'),('exit_code',68),('exit_code',True),('logs_complete',False)]:
        assert not m.accept_receipt({**r,key:value},'j','r')


def test_proof_read_rejects_link_oversize_duplicate(tmp_path):
    m=probe();p=tmp_path/'proof.json'
    for raw in ('x'*8193,'{"schema_version":1,"schema_version":1}'):
        p.write_text(raw)
        with pytest.raises(ValueError):m.read_proof(p,'A')
    p.unlink();p.symlink_to(tmp_path/'other')
    with pytest.raises((ValueError,OSError)):m.read_proof(p,'A')


def test_valid_complete_failed_observation_is_not_product_pass(tmp_path):
    import json
    m=probe();report=m.load('export_compare_report')
    checks={name:True for name in report.CHECKS}
    checks['reference_ort_match']={name:False for name in report.TENSORS}
    checks['fused_reference_match']=None
    proof={'schema_version':2,'arm':'A','status':'failed','checks':checks,'failure_code':'ONNX_MISMATCH'}
    from test_export_compare_report import with_metrics
    with_metrics(proof)
    p=tmp_path/'proof.json';p.write_text(json.dumps(proof))
    assert m.read_proof(p,'A')==proof
    assert report.observed(proof)
    with pytest.raises(ValueError):m.read_proof(p,'B')
    proof['checks']['source_unchanged']=False;p.write_text(json.dumps(proof))
    assert not report.observed(m.read_proof(p,'A'))


def test_bad_guard_flag_rejected_before_boundary(monkeypatch):
    m=probe();monkeypatch.setattr(m,'ROOT',Path('/opt/edgevision'))
    monkeypatch.delenv('EDGEVISION_EXPORT_COMPARE_PROFILE',raising=False)
    monkeypatch.setattr(m,'load',lambda _:pytest.fail('boundary/native not reached'))
    with pytest.raises(ValueError):m.guard()
