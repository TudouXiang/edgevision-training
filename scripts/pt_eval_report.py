"""Closed PT-only research receipt; a measured zero is not missing evidence."""
import json
import math

PROFILE='pt_eval_v1'
PROTOCOL='single-head-p025-iou050-v1'
STAGES=('isolation','dataset','dependency_check','training','evaluation','cleanup')


def require(ok):
    if not ok:raise ValueError('PT evaluation receipt rejected')


def initial():
    return {'schema_version':1,'profile':PROFILE,'protocol':PROTOCOL,'status':'failed',
            'stages':[{'stage':name,'status':'NOT_RUN'} for name in STAGES],
            'metrics':None,'lineage_verified':None}


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result);result[key]=value
    return result


def validate_metrics(value):
    require(type(value) is dict and set(value)=={'images','ground_truth','tp','fp','fn','precision','recall'})
    for name,limit in (('images',20),('ground_truth',20),('tp',20),('fp',6000),('fn',20)):
        require(type(value[name]) is int and 0<=value[name]<=limit)
    require(value['images']==value['ground_truth']==20 and value['fn']==20-value['tp'])
    for name in ('precision','recall'):
        require(type(value[name]) in (int,float) and math.isfinite(value[name]) and 0<=value[name]<=1)
    tp,fp=value['tp'],value['fp']
    require(tp+fp<=6000)
    require(value['precision']==(tp/(tp+fp) if tp+fp else 0.) and value['recall']==tp/20)
    return value


def validate(raw):
    require(type(raw) is str and len(raw.encode('utf-8'))<=4096)
    value=json.loads(raw,object_pairs_hook=unique)
    require(type(value) is dict and set(value)==set(initial()))
    require(type(value['schema_version']) is int and value['schema_version']==1)
    require(value['profile']==PROFILE and value['protocol']==PROTOCOL and value['status'] in ('passed','failed'))
    stages=value['stages'];require(type(stages) is list and len(stages)==len(STAGES))
    for entry,name in zip(stages,STAGES):
        require(type(entry) is dict and set(entry)=={'stage','status'} and entry['stage']==name)
        require(entry['status'] in ('passed','failed','NOT_RUN','unverified'))
    require(value['lineage_verified'] is None or type(value['lineage_verified']) is bool)
    if value['metrics'] is not None:validate_metrics(value['metrics'])
    if value['status']=='passed':
        require(all(stage['status']=='passed' for stage in stages))
        require(value['metrics'] is not None and value['lineage_verified'] is True)
    return value
