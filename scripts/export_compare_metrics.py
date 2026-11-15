"""Fixed, anonymous numeric diagnostic. No native imports or model execution."""
import math
SAMPLES=('zeros','gradient','pattern')
DIRECTIONS=('current_ort','current_disabled','disabled_ort')
ELEMENTS={'boxes':33600,'scores':16800}
KEYS={'elements','finite','mismatch_count','max_absolute_error','max_tolerance_ratio'}


def require(value):
    if not value:raise ValueError('grouped diagnostic rejected')


def measure_values(reference,actual):
    require(len(reference)==len(actual)==50400)
    result={};offset=0
    for group,count in ELEMENTS.items():
        pairs=list(zip(reference[offset:offset+count],actual[offset:offset+count]));offset+=count
        finite=all(math.isfinite(a) and math.isfinite(b) for a,b in pairs)
        stats={'elements':count,'finite':finite,'mismatch_count':None,'max_absolute_error':None,'max_tolerance_ratio':None}
        if finite:
            mismatch=0;maximum=0.;ratio=0.
            for left,right in pairs:
                delta=abs(float(right)-float(left));allowed=1e-4+1e-4*abs(float(left))
                mismatch+=int(delta>allowed);maximum=max(maximum,delta);ratio=max(ratio,delta/allowed)
            stats.update(mismatch_count=mismatch,max_absolute_error=maximum,max_tolerance_ratio=ratio)
        result[group]=stats
    validate_groups(result)
    return result


def measure_arrays(np,reference,actual):
    require(reference.shape==actual.shape==(1,6,8400) and reference.dtype==np.float32 and actual.dtype==np.float32)
    return measure_values(reference.ravel().tolist(),actual.ravel().tolist())


def validate_groups(value):
    require(type(value) is dict and set(value)==set(ELEMENTS))
    for group,count in ELEMENTS.items():
        s=value[group];require(type(s) is dict and set(s)==KEYS)
        require(type(s['elements']) is int and s['elements']==count and type(s['finite']) is bool)
        if not s['finite']:
            require(all(s[k] is None for k in ('mismatch_count','max_absolute_error','max_tolerance_ratio')))
        else:
            n=s['mismatch_count'];require(type(n) is int and 0<=n<=count)
            for key,limit in (('max_absolute_error',1e40),('max_tolerance_ratio',1e44)):
                x=s[key];require(type(x) in (int,float) and math.isfinite(x) and 0<=x<=limit)
            require((n==0)==(s['max_tolerance_ratio']<=1))
    return value


def matches(groups):
    validate_groups(groups)
    return all(v['finite'] and v['mismatch_count']==0 for v in groups.values())


def empty_matrix(arm):
    require(arm in ('A','D'))
    return {d:({s:None for s in SAMPLES} if d=='current_ort' or arm=='D' else None) for d in DIRECTIONS}


def validate_matrix(value,arm,checks):
    require(type(value) is dict and set(value)==set(DIRECTIONS))
    for direction in DIRECTIONS:
        block=value[direction]
        if direction!='current_ort' and arm!='D':require(block is None);continue
        require(type(block) is dict and set(block)==set(SAMPLES))
        for sample,g in block.items():
            if g is not None:validate_groups(g)
            if direction=='current_ort':
                flag=checks['reference_ort_match'][sample]
                require(flag is None if g is None else flag is matches(g))
        if direction=='current_disabled':
            flag=checks['backend_reference_match']
            require(flag is None if any(g is None for g in block.values()) else flag is all(matches(g) for g in block.values()))
    return value


def complete(value,arm):
    return all(value[d] is not None and all(g is not None and all(v['finite'] for v in g.values()) for g in value[d].values())
               for d in DIRECTIONS if d=='current_ort' or arm=='D')


def validate_precision(value,arm):
    require(type(value) is dict and set(value)=={'mkldnn_enabled','global','backend','conv','matmul'})
    require(type(value['mkldnn_enabled']) is bool and value['mkldnn_enabled'] is (arm=='A'))
    require(all(type(value[k]) is str and value[k] in ('none','ieee','tf32','bf16') for k in ('global','backend','conv','matmul')))
    return value
