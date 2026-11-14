"""Closed anonymous real-data evidence protocol. No execution or ML imports.

Separate from legacy isolated_ml schema: a fixture test of this validator is
not evidence that a real experiment, cancellation or restore ever ran.
"""
import json
import math

SCHEMA_VERSION=1
PROFILE='real_cpu_v1'
MANIFEST_SHA='fea46ddb1fbe822acbc7cfaa79fdeea6b986f50f71c2cae85992fde0ad93d124'
DATASET_SHA='16b58d944a2c414063409e7bb95a8007e1b117a672c249d28c2d4a9c51df3ee6'
STAGES=('isolation','dataset','dependency_check','training','export','evaluation','timings','cancel','worker_recovery','backup_restore','cleanup')
SERIES=tuple(f'{backend}_{part}' for backend in ('pt','onnx') for part in ('preprocess','model','postprocess','total','http'))


def require(ok):
    if not ok:raise ValueError('real experiment receipt rejected')


def statistics(values):
    require(type(values) is list and len(values)==20)
    require(all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=600000 for v in values))
    ordered=sorted(values)
    return {'median_ms':(ordered[9]+ordered[10])/2,'p95_ms':ordered[18]}


def measurements(series):
    require(type(series) is dict and set(series)==set(SERIES))
    return {'unit':'ms','samples':20,'warmups':5,'threads':2,'batch':1,
            'series':{key:{'raw':list(series[key]),'summary':statistics(series[key])} for key in SERIES}}


def initial():
    return {'schema_version':SCHEMA_VERSION,'profile':PROFILE,'status':'failed',
            'manifest_sha256':MANIFEST_SHA,'dataset_sha256':DATASET_SHA,
            'stages':[{'stage':s,'status':'NOT_RUN'} for s in STAGES],'measurements':None}


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result);result[key]=value
    return result


def validate(raw):
    require(type(raw) is str and len(raw.encode('utf-8'))<=16384)
    value=json.loads(raw,object_pairs_hook=unique)
    require(type(value) is dict and set(value)==set(initial()))
    require(type(value['schema_version']) is int and value['schema_version']==SCHEMA_VERSION)
    require(value['profile']==PROFILE and value['manifest_sha256']==MANIFEST_SHA and value['dataset_sha256']==DATASET_SHA)
    require(value['status'] in ('passed','failed'))
    stages=value['stages'];require(type(stages) is list and len(stages)==len(STAGES))
    for name,item in zip(STAGES,stages):
        require(type(item) is dict and set(item)=={'stage','status'})
        require(item['stage']==name and item['status'] in ('passed','failed','NOT_RUN','unverified'))
    measured=value['measurements']
    if measured is not None:
        require(type(measured) is dict and set(measured)=={'unit','samples','warmups','threads','batch','series'})
        for key,expected in (('samples',20),('warmups',5),('threads',2),('batch',1)):
            require(type(measured[key]) is int and measured[key]==expected)
        require(measured['unit']=='ms')
        series=measured['series'];require(type(series) is dict and set(series)==set(SERIES))
        for item in series.values():
            require(type(item) is dict and set(item)=={'raw','summary'})
            expected=statistics(item['raw'])
            summary=item['summary'];require(type(summary) is dict and set(summary)==set(expected))
            require(all(type(summary[k]) in (int,float) and math.isfinite(summary[k]) and summary[k]==v for k,v in expected.items()))
        require(stages[STAGES.index('timings')]['status']=='passed')
    if value['status']=='passed':
        require(all(s['status']=='passed' for s in stages) and measured is not None)
    return value
