import importlib.util,json
from pathlib import Path
import pytest
P=Path(__file__).resolve().parents[2]/'scripts/export_compare_report.py'
spec=importlib.util.spec_from_file_location('compare_report',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def proof(arm='A'):
    return {'schema_version':1,'arm':arm,'status':'failed','failure_code':'ONNX_MISMATCH','checks':{'source_bn':True,'onnx_batchnorm':False,'pt_repeat_pre':True,'pt_repeat_post':True,'source_unchanged':True,'network_unchanged':True,'reference_ort_match':dict.fromkeys(m.TENSORS,False),'fused_reference_match':False if arm=='C' else None}}

def test_observed_mismatch_never_becomes_export_acceptance():
    v=m.initial();assert m.validate(json.dumps(v))==v
    v['status']='passed'
    with pytest.raises(ValueError):m.validate(json.dumps(v))
    for s in v['stages']:s['status']='passed'
    v['arms']={a:proof(a) for a in m.ARMS}
    assert m.validate(json.dumps(v))['purpose']=='diagnostic_only'
    v['arms']['A']['status']='passed'
    with pytest.raises(ValueError):m.validate(json.dumps(v))

@pytest.mark.parametrize('key,value',[('arm','secret'),('failure_code','secret'),('schema_version',True)])
def test_closed_proof(key,value):
    v=proof();v[key]=value
    with pytest.raises(ValueError):m.validate_proof(v)

def test_unknown_partial_does_not_count_as_observed():
    v=proof();v['checks']['reference_ort_match']['zeros']=None
    assert not m.observed(v)
    v['path']='secret'
    with pytest.raises(ValueError):m.validate_proof(v)


def test_child_and_public_proof_contracts_match():
    from app import real_export_diagnostic as child
    assert set(child.FAILURE_CODES)==set(m.CODES)
    for arm in m.ARMS:
        p=child.empty_proof(arm)
        assert m.validate_proof(p)==child.validate_proof(p)
        p=proof(arm)
        p['status']='passed';p['failure_code']=None
        p['checks'].update(source_bn=False,onnx_batchnorm=False,reference_ort_match=dict.fromkeys(m.TENSORS,True),fused_reference_match=True if arm=='C' else None)
        assert m.validate_proof(p)==child.validate_proof(p)


def test_policy_or_infrastructure_failure_is_not_completed_observation():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'export_compare_report.py'
    spec = importlib.util.spec_from_file_location('closed_compare_report_test', path)
    report = importlib.util.module_from_spec(spec); spec.loader.exec_module(report)
    for code in ('POLICY_FAILED', 'SOURCE_INVALID', 'SOURCE_CHANGED', 'GRAPH_INVALID', 'RUNTIME_FAILED', 'UNKNOWN'):
        proof = {'schema_version':1, 'arm':'A', 'status':'failed', 'failure_code':code,
            'checks':{'source_bn':True, 'onnx_batchnorm':False, 'pt_repeat_pre':True,
                'pt_repeat_post':True, 'source_unchanged':True, 'network_unchanged':True,
                'reference_ort_match':{'zeros':True, 'gradient':True, 'pattern':False},
                'fused_reference_match':None}}
        assert report.observed(proof) is False
