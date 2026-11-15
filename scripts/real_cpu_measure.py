"""Fixed per-backend private benchmark, invoked only inside the real profile."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from hashlib import sha256

ROOT=Path(__file__).resolve().parents[1]

def guard():
    if ROOT!=Path('/opt/edgevision'):raise ValueError('container checkout required')
    spec=importlib.util.spec_from_file_location('boundary',ROOT/'scripts/isolated_ml_entry.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify_boundary(os.environ.get('EDGEVISION_ISOLATED_HOST_NETNS',''))


def prepare_model(private,work,backend,*,pt_only=False):
    """Bind the real measured copy before any model/native loading."""
    model=work/f'model.{backend}'
    if not pt_only:
        import shutil
        shutil.copyfile(private/f'trained.{backend}',model)
        return model,None
    if backend!='pt':raise ValueError('PT-only backend required')
    import stat
    from pt_eval_binding import safe_path,copy_verified
    from pt_eval_report import unique
    path=safe_path(private/'pt-eval-model.json')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=1024:raise ValueError('model binding file')
        raw=source.read(1025)
    if len(raw)!=info.st_size:raise ValueError('model binding changed')
    binding=json.loads(raw,object_pairs_hook=unique)
    copy_verified(private/'trained.pt',model,binding)
    return model,binding


def main():
    guard()
    if len(sys.argv)!=2 or sys.argv[1] not in ('pt','onnx'):raise ValueError('backend')
    backend=sys.argv[1];private=ROOT/'private';work=private/f'measure-{backend}'
    work.mkdir(mode=0o700)
    manifest=json.loads((private/'subset/manifest.json').read_text())
    from real_cpu_report import MANIFEST_SHA
    if sha256((private/'subset/manifest.json').read_bytes()).hexdigest()!=MANIFEST_SHA:raise ValueError('manifest')
    samples=[s for s in manifest['samples'] if s['split']=='test']
    if len(samples)!=20:raise ValueError('samples')
    # Decode work starts from these preloaded immutable bytes, excluding disk IO.
    images=[(private/'test-images'/f"{s['name']}.jpg").read_bytes() for s in samples]
    if any(sha256(raw).hexdigest()!=sample['image_sha256'] for raw,sample in zip(images,samples)):raise ValueError('image')
    pt_only=os.environ.get('EDGEVISION_PT_EVAL_PROFILE')=='v1'
    model,binding=prepare_model(private,work,backend,pt_only=pt_only)
    sys.path.insert(0,str(ROOT/'backend'))
    from app.training_runtime import prepare_environment
    from app.inference_runtime import install_policy,load_pt
    from app.delivery_infer import load_onnx,decode_image_bytes,preprocess,postprocess
    prepare_environment(work);install_policy(work)
    began=time.perf_counter()
    infer,_=load_pt(work,model,['cat_head','dog_head']) if backend=='pt' else load_onnx(model,['cat_head','dog_head'])
    loaded=(time.perf_counter()-began)*1000
    def once(content):
        start=time.perf_counter();rgb,_=decode_image_bytes(content,'jpeg');tensor,geometry=preprocess(rgb)
        prepared=time.perf_counter();raw=infer(tensor);inferred=time.perf_counter()
        prediction=postprocess(raw,['cat_head','dog_head'],geometry,.25,.45)
        finished=time.perf_counter()
        return raw,prediction['detections'],{'preprocess':(prepared-start)*1000,'model':(inferred-prepared)*1000,
                'postprocess':(finished-inferred)*1000,'total':(finished-start)*1000}
    for _ in range(5):once(images[0])
    series={key:[] for key in ('preprocess','model','postprocess','total')};detections=[]
    for index,content in enumerate(images):
        raw,prediction,timing=once(content)
        for key in series:series[key].append(timing[key])
        detections.append(prediction)
        (work/f'{index:02}.f32le').write_bytes(raw)
    result={'series':series,'detections':detections,'model_load_ms':loaded}
    if pt_only:
        from pt_eval_binding import verify_file
        verify_file(private/'trained.pt',binding);verify_file(model,binding)
        result['lineage_verified']=True
    (work/'result.json').write_text(json.dumps(result,allow_nan=False))

if __name__=='__main__':
    # -I omits script directory; only the reviewed fixed source directory is added.
    sys.path.insert(0,str(ROOT/'scripts'))
    main()
