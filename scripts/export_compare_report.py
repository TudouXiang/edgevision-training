"""Closed diagnostic-only evidence; passed means observations, never export acceptance."""
import json
import importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location("export_compare_metrics",Path(__file__).with_name("export_compare_metrics.py"))
metrics=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(metrics)
STAGES=('isolation','dataset','dependency_check','training','diagnostic','cleanup')
ARMS=('A','B','C')
TENSORS=('zeros','gradient','pattern')
CODES=('POLICY_FAILED','SOURCE_INVALID','GRAPH_INVALID','PT_REPEAT_MISMATCH','FUSED_MISMATCH','SOURCE_CHANGED','ONNX_MISMATCH','RUNTIME_FAILED','UNKNOWN')
CHECKS=('source_bn','onnx_batchnorm','pt_repeat_pre','pt_repeat_post','source_unchanged','network_unchanged','reference_ort_match','fused_reference_match')


def require(ok):
    if not ok:raise ValueError('diagnostic evidence rejected')


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result);result[key]=value
    return result


def validate_proof(value):
    require(type(value) is dict and set(value)=={'schema_version','arm','status','checks','failure_code','metrics'})
    require(type(value['schema_version']) is int and value['schema_version']==2)
    require(value['arm'] in ARMS and value['status'] in ('passed','failed'))
    checks=value['checks'];require(type(checks) is dict and set(checks)==set(CHECKS))
    for name in CHECKS:
        if name!='reference_ort_match':require(checks[name] is None or type(checks[name]) is bool)
    matches=checks['reference_ort_match'];require(type(matches) is dict and set(matches)==set(TENSORS))
    require(all(v is None or type(v) is bool for v in matches.values()))
    if value['arm']!='C':require(checks['fused_reference_match'] is None)
    if value['status']=='passed':
        require(value['failure_code'] is None and checks['source_unchanged'] is True)
        require(type(checks['source_bn']) is bool and type(checks['onnx_batchnorm']) is bool)
        require(checks['pt_repeat_pre'] is True and checks['pt_repeat_post'] is True and checks['network_unchanged'] is True and all(v is True for v in matches.values()))
        if value['arm']=='C':require(checks['fused_reference_match'] is True)
    else:require(value['failure_code'] in CODES)
    metrics.validate_matrix(value['metrics'],value['arm'],checks)
    if value['status']=='passed':require(metrics.complete(value['metrics'],value['arm']))
    return value


def observed(value):
    validate_proof(value);c=value['checks']
    if value['status']=='failed' and value['failure_code'] not in ('PT_REPEAT_MISMATCH','FUSED_MISMATCH','ONNX_MISMATCH'):
        return False
    return (metrics.complete(value['metrics'],value['arm']) and all(type(c[n]) is bool for n in ('source_bn','onnx_batchnorm','pt_repeat_pre','pt_repeat_post','network_unchanged'))
            and c['source_unchanged'] is True and all(type(v) is bool for v in c['reference_ort_match'].values())
            and (value['arm']!='C' or type(c['fused_reference_match']) is bool))


def initial():
    return {'schema_version':2,'profile':'export_compare_v1','purpose':'diagnostic_only','status':'failed',
            'stages':[{'stage':s,'status':'NOT_RUN'} for s in STAGES], 'arms':{a:None for a in ARMS}}


def validate(raw):
    require(type(raw) is str and len(raw.encode())<=32768)
    value=json.loads(raw,object_pairs_hook=unique)
    require(type(value) is dict and set(value)==set(initial()))
    require(type(value['schema_version']) is int and value['schema_version']==2)
    require(value['profile']=='export_compare_v1' and value['purpose']=='diagnostic_only' and value['status'] in ('passed','failed'))
    stages=value['stages'];require(type(stages) is list and len(stages)==len(STAGES))
    for name,item in zip(STAGES,stages):
        require(type(item) is dict and set(item)=={'stage','status'} and item['stage']==name and item['status'] in ('passed','failed','NOT_RUN','unverified'))
    arms=value['arms'];require(type(arms) is dict and set(arms)==set(ARMS))
    for arm,proof in arms.items():
        if proof is not None:validate_proof(proof);require(proof['arm']==arm)
    if value['status']=='passed':
        require(all(s['status']=='passed' for s in stages) and all(p is not None and observed(p) for p in arms.values()))
    return value
