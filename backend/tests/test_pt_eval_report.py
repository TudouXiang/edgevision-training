"""Synthetic report-contract tests, never model execution."""
import importlib.util
import json
from pathlib import Path
import pytest


def module():
    path=Path(__file__).resolve().parents[2]/'scripts/pt_eval_report.py'
    assert path.is_file(), 'PT-only closed report is not implemented'
    spec=importlib.util.spec_from_file_location('pt_report_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def passing(m):
    value=m.initial()
    for stage in value['stages']:stage['status']='passed'
    value.update(status='passed',lineage_verified=True,metrics={'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.})
    return value


def test_empty_and_real_zero_measurement_are_distinct():
    m=module();v=m.initial();assert v['metrics'] is None
    assert m.validate(json.dumps(v))==v
    v=passing(m);assert m.validate(json.dumps(v))==v


@pytest.mark.parametrize('fault',['unknown','duplicate','nan','bool_count','overflow','fn','precision','recall','lineage','stage','missing','protocol'])
def test_bad_receipts_cannot_pass(fault):
    m=module();v=passing(m)
    if fault=='unknown':v['secret']='private'
    if fault=='nan':v['metrics']['precision']=float('nan')
    if fault=='bool_count':v['metrics']['tp']=True
    if fault=='overflow':v['metrics']['fp']=6001
    if fault=='fn':v['metrics']['fn']=19
    if fault=='precision':v['metrics']['precision']=.1
    if fault=='recall':v['metrics']['recall']=.1
    if fault=='lineage':v['lineage_verified']=False
    if fault=='stage':v['stages'][-1]['status']='failed'
    if fault=='missing':v['metrics']=None
    if fault=='protocol':v['protocol']='mAP'
    raw=json.dumps(v)
    if fault=='duplicate':raw=raw.replace('"schema_version": 1','"schema_version": 1,"schema_version": 1')
    with pytest.raises(ValueError):m.validate(raw)


def test_correct_nonzero_counts_and_partial_failure():
    m=module();v=passing(m);v['metrics'].update(tp=4,fp=1,fn=16,precision=.8,recall=.2)
    assert m.validate(json.dumps(v))==v
    v['status']='failed';v['stages'][-1]['status']='failed'
    assert m.validate(json.dumps(v))==v


def test_total_prediction_count_cannot_exceed_twenty_times_cap():
    m=module();v=passing(m);v['metrics'].update(tp=20,fp=6000,fn=0,precision=20/6020,recall=1.)
    with pytest.raises(ValueError):m.validate(json.dumps(v))
