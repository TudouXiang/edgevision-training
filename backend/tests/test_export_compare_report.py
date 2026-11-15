import importlib.util,json
from pathlib import Path
import pytest
P=Path(__file__).resolve().parents[2]/'scripts/export_compare_report.py'
spec=importlib.util.spec_from_file_location('compare_report',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def with_metrics(p):
    if p.get('precision') is None:p['precision']={'mkldnn_enabled':p['arm']=='A','global':'ieee','backend':'none','conv':'ieee','matmul':'ieee'}
    if p['checks'].get('shared_input_unchanged') is None:p['checks']['shared_input_unchanged']=True
    p['metrics']=m.metrics.empty_matrix(p['arm'])
    for direction,block in p['metrics'].items():
        if block is None:continue
        for sample in block:
            flag=(p['checks']['reference_ort_match'][sample] if direction=='current_ort' else p['checks']['backend_reference_match'] if direction=='current_disabled' else True)
            if flag is None:continue
            block[sample]={g:{'elements':n,'finite':True,'mismatch_count':0 if flag else 1,'max_absolute_error':0.0 if flag else .0002,'max_tolerance_ratio':0.0 if flag else 2.0} for g,n in m.metrics.ELEMENTS.items()}
    return p

def proof(arm='A'):
    return with_metrics({'schema_version':3,'arm':arm,'status':'failed','failure_code':'ONNX_MISMATCH','checks':{'source_bn':True,'onnx_batchnorm':False,'pt_repeat_pre':True,'pt_repeat_post':True,'source_unchanged':True,'network_unchanged':True,'reference_ort_match':dict.fromkeys(m.TENSORS,False),'backend_reference_match':False if arm=='D' else None}})

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
    v=proof();v['checks']['reference_ort_match']['zeros']=None;v['metrics']['current_ort']['zeros']=None
    assert not m.observed(v)
    v['path']='secret'
    with pytest.raises(ValueError):m.validate_proof(v)


def test_child_and_public_proof_contracts_match():
    from app import real_export_diagnostic as child
    assert set(child.FAILURE_CODES)==set(m.CODES)
    for arm in m.ARMS:
        p=child.empty_proof(arm)
        with_metrics(p)
        assert m.validate_proof(p)==child.validate_proof(p)
        p=proof(arm)
        p['status']='passed';p['failure_code']=None
        p['checks'].update(source_bn=False,onnx_batchnorm=False,reference_ort_match=dict.fromkeys(m.TENSORS,True),backend_reference_match=True if arm=='D' else None)
        with_metrics(p)
        assert m.validate_proof(p)==child.validate_proof(p)


def test_policy_or_infrastructure_failure_is_not_completed_observation():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'export_compare_report.py'
    spec = importlib.util.spec_from_file_location('closed_compare_report_test', path)
    report = importlib.util.module_from_spec(spec); spec.loader.exec_module(report)
    for code in ('POLICY_FAILED', 'SOURCE_INVALID', 'SOURCE_CHANGED', 'GRAPH_INVALID', 'RUNTIME_FAILED', 'UNKNOWN'):
        proof = {'schema_version':3, 'arm':'A', 'status':'failed', 'failure_code':code,
            'checks':{'source_bn':True, 'onnx_batchnorm':False, 'pt_repeat_pre':True,
                'pt_repeat_post':True, 'source_unchanged':True, 'network_unchanged':True,
                'reference_ort_match':{'zeros':True, 'gradient':True, 'pattern':False},
                'backend_reference_match':None}}
        with_metrics(proof)
        assert report.observed(proof) is False


def test_largest_closed_report_stays_under_receipt_limit():
    v=m.initial();v['arms']={a:proof(a) for a in m.ARMS}
    for p in v['arms'].values():
        for block in p['metrics'].values():
            if block is None:continue
            for groups in block.values():
                for group in groups.values():
                    if group['mismatch_count']:
                        group.update(max_absolute_error=6.805646932770577e38,max_tolerance_ratio=6.805646932770577e42)
        assert len(json.dumps(p).encode())<8192
    assert len(json.dumps(v).encode())<32768
    m.validate(json.dumps(v))


def test_nonfinite_observations_never_complete():
    p=proof();g=p['metrics']['current_ort']['zeros']['boxes']
    g.update(finite=False,mismatch_count=None,max_absolute_error=None,max_tolerance_ratio=None)
    assert not m.observed(p)


def test_backend_control_rejects_noncomparable_precision():
    v=m.initial();v['arms']={a:proof(a) for a in m.ARMS}
    for s in v['stages']:s['status']='passed'
    v['status']='passed'
    m.validate(json.dumps(v))
    v['arms']['D']['precision']['conv']='tf32'
    with pytest.raises(ValueError):m.validate(json.dumps(v))


@pytest.mark.parametrize('arm,value',[('A',False),('D',True)])
def test_control_enabled_direction_is_fixed(arm,value):
    p=proof(arm);p['precision']['mkldnn_enabled']=value
    with pytest.raises(ValueError):m.validate_proof(p)


def test_shared_input_proof_cannot_be_missing():
    p=proof('D');p['checks']['shared_input_unchanged']=False
    assert not m.observed(p)


@pytest.mark.parametrize('check',['network_unchanged','pt_repeat_pre','pt_repeat_post'])
def test_unstable_reference_cannot_start_backend_control(check):
    p=proof('A');p['checks'][check]=False
    p['failure_code']='PT_REPEAT_MISMATCH'
    assert not m.observed(p)
