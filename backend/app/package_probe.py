"""Operator-only fixed three-stage proof. Never invoked by a public API."""
from .config import data_root
from .inference_assets import capability as reference_capability
from .run_files import atomic_json


def completed_receipt(receipt):
    if not receipt or receipt.get('reason')!='completed' or receipt.get('exit_code')!=0 or receipt.get('logs_complete') is not True or receipt.get('started') is not True:
        raise ValueError('standalone tree exit or execution failed')
    return receipt


def run_probe(artifact_id):
    from .worker import worker_lock
    root=data_root();root.mkdir(parents=True,exist_ok=True)
    with worker_lock(root):
        atomic_json(root/'package-capability.json',{'schema_version':1,'available':False})
        if not reference_capability()['available']:raise ValueError('current managed reference capability required')
        from .training_probe import recover_probe
        from .worker import recover
        if not recover_probe():raise RuntimeError('Previous shared probe exit is unconfirmed')
        if recover():raise RuntimeError('Existing task exit is unconfirmed')
        record=assemble_proof(artifact_id)
        atomic_json(root/'package-capability.json',record)


def expand_candidate(path,frozen,directory):
    """Bounded fixed members only. Never use archive extraction APIs."""
    import zipfile
    from hashlib import sha256
    from .package_bundle import verify_bundle
    from .package_contract import MAX_PACKAGE_BYTES
    from .inference_files import verified_file,write_bytes
    info=verify_bundle(path,frozen)
    destination=directory/'package';destination.mkdir()
    with verified_file(path,info['size_bytes'],info['sha256'],MAX_PACKAGE_BYTES) as stream:
        with zipfile.ZipFile(stream) as archive:
            members=[*info['manifest']['members'],{'path':'manifest.json','size_bytes':info['manifest_size_bytes'],'sha256':info['manifest_sha256']}]
            for member in members:
                content=archive.read(member['path'])
                if len(content)!=member['size_bytes'] or sha256(content).hexdigest()!=member['sha256']:
                    raise ValueError('candidate member changed')
                write_bytes(destination/member['path'],content,member['size_bytes'])
    return info


def standalone_stage(mode,frozen,before,source=None):
    import json
    import os
    import subprocess
    from uuid import uuid4
    from .worker import guardian_command,drain_receipt,send_control
    from .python_launch import python_child
    from .process_identity import identity
    from .package_assets import runtime_identity
    from .package_bundle import build_bundle,verify_bundle
    from .package_contract import MAX_PACKAGE_BYTES
    from .package_launch import source_hashes
    from .package_probe_contract import StandaloneInput,StandaloneProof
    from .inference_files import verified_file,write_bytes
    from .run_files import read_json,run_directory
    from .training_assets import digest_json
    job_id,run_id=str(uuid4()),str(uuid4())
    directory=run_directory(job_id,run_id,create=True)
    if source is None:build_bundle(frozen,directory)
    else:
        path,info=source
        with verified_file(path,info['size_bytes'],info['sha256'],MAX_PACKAGE_BYTES) as stream:
            write_bytes(directory/'package.zip',stream.read(MAX_PACKAGE_BYTES+1),MAX_PACKAGE_BYTES)
    info=expand_candidate(directory/'package.zip',frozen,directory)
    image=next(v for v in info['manifest']['members'] if v['path']=='example.png')
    for name in ('home','tmp'):(directory/name).mkdir()
    task=StandaloneInput.model_validate({'schema_version':1,'kind':'package_standalone_probe','job_id':job_id,'run_id':run_id,'mode':mode,
        **source_hashes(),'package_sha256':info['sha256'],'package_size_bytes':info['size_bytes'],
        'runtime_binding':digest_json(before),'code_version':digest_json(before['adapter']),
        'model_sha256':frozen['model']['source_sha256'],'template_sha256':frozen['template']['template_sha256'],
        'image_sha256':image['sha256'],'image_size_bytes':image['size_bytes']}).model_dump(mode='json')
    atomic_json(directory/'input.json',task)
    active={'job_id':job_id,'run_id':run_id,'guardian':None}
    atomic_json(data_root()/'training-probe-active.json',active)
    command,env=python_child(guardian_command(job_id,run_id));child=None
    try:
        child=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            close_fds=True,start_new_session=os.name!='nt')
        active['guardian']=identity(child.pid);atomic_json(data_root()/'training-probe-active.json',active)
        send_control(child.stdin,b'GO\n')
        try:child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            send_control(child.stdin,b'STOP\n');child.wait(timeout=25)
    finally:
        if child is not None and child.stdin:
            try:child.stdin.close()
            except BrokenPipeError:pass
    receipt=completed_receipt(drain_receipt({'id':job_id,'run_id':run_id,'process_identity_json':json.dumps({'guardian':active['guardian']})},wait_seconds=2))
    proof=StandaloneProof.model_validate(read_json(directory/'probe-result.json',1024**2)).model_dump(mode='json')
    expected={'job_id':job_id,'run_id':run_id,'mode':mode,'task_sha256':digest_json(task),
        'environment_sha256':digest_json(before['package_environment']),'receipt_sha256':None}
    if any(proof[k]!=v for k,v in expected.items()):raise ValueError('standalone proof binding changed')
    if read_json(directory/'result/result.json',1024**2)!=proof['output']:raise ValueError('standalone result differs')
    preview=proof['output']['preview']
    with verified_file(directory/'result/preview.png',preview['size_bytes'],preview['sha256'],8*1024**2):pass
    if mode=='raw':
        with verified_file(directory/'raw.f32le',proof['output']['raw_elements']*4,proof['output']['raw_sha256'],33_734_400):pass
    from .package_cli import verify_package
    if verify_package(directory/'package')!=info['manifest']:raise ValueError('expanded package changed')
    if verify_bundle(directory/'package.zip',frozen)!=info or runtime_identity()!=before:raise ValueError('standalone candidate or environment changed')
    proof['receipt_sha256']=digest_json(receipt)
    return task,proof,(directory/'package.zip',info)



def assemble_proof(artifact_id):
    from .database import transaction
    from .delivery_infer import synthetic_png
    from .inference_assets import runtime_identity as reference_identity
    from .inference_probe import sources,verify_pair,stage,compare_raw
    from .package_assets import runtime_identity
    from .package_contract import FrozenPackage
    from .package_probe_contract import PackageProbeRecord
    from .training_assets import digest_json
    with transaction() as connection:
        connection.execute('BEGIN');pair=sources(connection,artifact_id)
    before=runtime_identity();reference_before=reference_identity()
    reference=stage(pair,'onnx',reference_before,synthetic_png())
    frozen=FrozenPackage.model_validate({'schema_version':1,'project_id':pair['onnx']['project_id'],'model':pair['onnx'],
        'params':{'onnx_artifact_id':artifact_id},'template':before['package_template'],'runtime_binding':digest_json(before),
        'code_version':digest_json(before['adapter']),'template_validation_sha256':digest_json({'candidate_only':True})}).model_dump(mode='json')
    raw_task,raw,candidate=standalone_stage('raw',frozen,before)
    cli_task,cli,_=standalone_stage('cli',frozen,before,candidate)
    comparison=compare_raw(reference,{'job_id':raw['job_id'],'run_id':raw['run_id'],
        'raw_size_bytes':raw['output']['raw_elements']*4,'raw_sha256':raw['output']['raw_sha256']})
    verify_pair(pair)
    if runtime_identity()!=before or reference_identity()!=reference_before:raise ValueError('probe environment changed')
    return PackageProbeRecord.model_validate({'schema_version':1,'available':True,'protocol':'edgevision-python-onnx-v1',
        'runtime_binding':digest_json(before),'code_version':digest_json(before['adapter']),
        'reference_runtime_binding':digest_json(reference_before),'reference_code_version':digest_json(reference_before['adapter']),
        'template':before['package_template'],'environment_sha256':digest_json(before['package_environment']),
        'package_sha256':candidate[1]['sha256'],'package_size_bytes':candidate[1]['size_bytes'],
        'reference':reference,'raw_task':raw_task,'cli_task':cli_task,'standalone':raw,'cli':cli,'comparison':comparison}).model_dump(mode='json')


def main():
    import argparse
    from uuid import UUID
    parser=argparse.ArgumentParser(description='Verify fixed package in independent managed CPU runtime')
    parser.add_argument('--onnx-artifact-id',type=lambda v:str(UUID(v)),required=True)
    args=parser.parse_args()
    try:run_probe(args.onnx_artifact_id)
    except Exception:
        print('Package probe failed; capability remains unavailable');return 1
    print('Independent package template probe passed for current runtime');return 0


if __name__=='__main__':raise SystemExit(main())
