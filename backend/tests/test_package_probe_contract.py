"""Synthetic strict package proof fixtures; never native acceptance evidence."""
from copy import deepcopy
from uuid import uuid4
import pytest
from app.training_assets import digest_json
from app.delivery_infer import letterbox_record


def record():
    classes=['object'];template={'protocol':'edgevision-python-onnx-v1','image_protocol':'detection-image-v1','target':'linux-x86_64-cpython312-cpu','template_sha256':'a'*64,'core_sha256':'b'*64,'lock_sha256':'c'*64}
    versions={'pillow':'12.3.0','numpy':'2.5.4','onnx':'1.23.2','onnxruntime':'1.31.1','torch':None,'torchvision':None,'ultralytics':None}
    decoded={'encoded_width':3,'encoded_height':2,'image_width':3,'image_height':2,'orientation':1,'format':'png','rgb_sha256':'d'*64}
    geometry={**letterbox_record(3,2),'tensor_sha256':'e'*64}
    counts={'candidates':0,'candidate_truncated':0,'nms_kept':0,'result_truncated':0,'clip_removed':0}
    preview={'width':3,'height':2,'sha256':'f'*64,'size_bytes':100}
    output={'schema_version':1,'protocol':'detection-image-v1','backend':'onnx','model_sha256':'a'*64,
        'template':{k:template[k] for k in ('template_sha256','core_sha256','lock_sha256')},
        'image_sha256':'b'*64,'image_size_bytes':100,'decoded':decoded,'geometry':geometry,'confidence':.25,'iou':.45,
        'detections':[],'counts':counts,'classes':classes,'provider':'CPUExecutionProvider','runtime':versions,
        'raw_sha256':'c'*64,'raw_elements':42000,'preview':preview}
    runtime={'backend':'onnx','provider':'CPUExecutionProvider','device':'cpu','threads':2,'interop_threads':1,'warmup_runs':0,'versions':versions,'raw_sha256':'c'*64,'raw_elements':42000}
    reference={'schema_version':1,'protocol':'detection-image-v1','job_id':str(uuid4()),'run_id':str(uuid4()),'project_id':str(uuid4()),'model_artifact_id':str(uuid4()),'parent_pt_artifact_id':str(uuid4()),'model_sha256':'a'*64,'pair_sha256':'d'*64,'image_sha256':'e'*64,'image_size_bytes':100,'runtime_binding':'f'*64,'code_version':'a'*64,
        'output':{'image_width':3,'image_height':2,'backend':'onnx','provider':'CPUExecutionProvider','classes':classes,'image':decoded,'preprocess':geometry,'runtime':runtime,'preview':{**preview,'format':'png'},'counts':counts,'timings':{'unit':'ms','decode':0.,'preprocess':0.,'load':0.,'infer':0.,'postprocess':0.,'total':0.},'detections':[]},
        'raw_size_bytes':168000,'raw_sha256':'c'*64,'receipt_sha256':'b'*64}
    tasks={};proofs={}
    for mode in ('raw','cli'):
        task={'schema_version':1,'kind':'package_standalone_probe','job_id':str(uuid4()),'run_id':str(uuid4()),'mode':mode,'cli_sha256':'c'*64,'bootstrap_sha256':'d'*64,'package_sha256':'e'*64,'package_size_bytes':1000,'runtime_binding':'b'*64,'code_version':'c'*64,'model_sha256':'a'*64,'template_sha256':'a'*64,'image_sha256':'b'*64,'image_size_bytes':100}
        tasks[mode]=task;proofs[mode]={'schema_version':1,'mode':mode,'job_id':task['job_id'],'run_id':task['run_id'],'task_sha256':digest_json(task),'environment_sha256':'d'*64,'isolated_imports':True,'output':deepcopy(output),'receipt_sha256':'e'*64}
    return {'schema_version':1,'available':True,'protocol':'edgevision-python-onnx-v1','runtime_binding':'b'*64,'code_version':'c'*64,'reference_runtime_binding':'f'*64,'reference_code_version':'a'*64,'template':template,'environment_sha256':'d'*64,'package_sha256':'e'*64,'package_size_bytes':1000,'reference':reference,'raw_task':tasks['raw'],'cli_task':tasks['cli'],'standalone':proofs['raw'],'cli':proofs['cli'],'comparison':{'elements':42000,'max_absolute_error':0.,'max_tolerance_ratio':0.,'atol':.0001,'rtol':.0001,'detections_matched':True}}


def test_complete_package_probe_record_is_strict():
    from app.package_probe_contract import PackageProbeRecord
    value=record();assert PackageProbeRecord.model_validate(value).model_dump(mode='json')==value


@pytest.mark.parametrize('fault',['receipt','same_run','native_imports','classes','raw_count','template','task','environment','cli_output','comparison','extra','image'])
def test_package_probe_rejects_missing_or_cross_bound_proof(fault):
    from app.package_probe_contract import PackageProbeRecord
    value=record()
    if fault=='receipt':value['cli']['receipt_sha256']=None
    if fault=='same_run':value['cli']['job_id']=value['standalone']['job_id'];value['cli']['run_id']=value['standalone']['run_id']
    if fault=='native_imports':value['standalone']['isolated_imports']=False
    if fault=='classes':value['reference']['output']['classes']=['different']
    if fault=='raw_count':value['standalone']['output']['raw_elements']=84000
    if fault=='template':value['template']['core_sha256']='0'*64
    if fault=='task':value['raw_task']['package_sha256']='0'*64
    if fault=='environment':value['environment_sha256']='0'*64
    if fault=='cli_output':value['cli']['output']['raw_sha256']='0'*64
    if fault=='comparison':value['comparison']['max_tolerance_ratio']=1.1
    if fault=='extra':value['private_path']='secret'
    if fault=='image':value['standalone']['output']['decoded']['rgb_sha256']='0'*64
    with pytest.raises(ValueError):PackageProbeRecord.model_validate(value)
