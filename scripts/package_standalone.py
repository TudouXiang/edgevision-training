"""Fixed standalone probe bootstrap. Standard library only until validated GO.

No platform modules or model bytes are imported before the GO gate. Execution
uses the verified package source in a separate nine-package virtualenv.
"""
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
from uuid import UUID


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def read_regular(path,limit):
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:raise ValueError('file')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as source:
        current=os.fstat(source.fileno())
        if (current.st_dev,current.st_ino,current.st_size)!=(before.st_dev,before.st_ino,before.st_size):raise ValueError('identity')
        raw=source.read(limit+1)
        if len(raw)!=before.st_size:raise ValueError('size')
    return raw


def write_private(path,raw,limit):
    if not 0<len(raw)<=limit:raise ValueError('bound')
    with path.open('xb') as sink:
        sink.write(raw);sink.flush();os.fsync(sink.fileno())


def audit_imports():
    forbidden=('app','fastapi','torch','torchvision','ultralytics')
    if any(name.split('.')[0] in forbidden for name in sys.modules):raise ValueError('platform import')
    roots=(Path(sys.prefix).resolve(),Path(sys.base_prefix).resolve())
    for path in sys.path:
        if not path or not any(Path(path).resolve().is_relative_to(root) for root in roots):raise ValueError('import path')
    for name,module in tuple(sys.modules.items()):
        location=getattr(module,'__file__',None)
        if location and name!='__main__' and not any(Path(location).resolve().is_relative_to(root) for root in roots):raise ValueError('module origin')


def environment_identity(lock):
    from importlib import metadata
    expected={line.split('==')[0].lower().replace('_','-'):line.split('==')[1].split(' ')[0] for line in lock.decode('ascii').splitlines()}
    if set(expected)!={'pillow','numpy','onnx','onnxruntime','protobuf','ml-dtypes','flatbuffers','packaging','typing-extensions'}:raise ValueError('dependencies')
    packages={};seen=set()
    for dist in metadata.distributions():
        name=(dist.metadata.get('Name') or '').lower().replace('_','-')
        if name in seen:raise ValueError('duplicate distribution')
        seen.add(name)
        if name=='pip':continue
        if name not in expected or dist.version!=expected[name] or not dist.read_text('RECORD'):raise ValueError('dependency version')
        packages[name]={'version':dist.version,'record_sha256':sha256(dist.read_text('RECORD').encode()).hexdigest()}
    if set(packages)!=set(expected):raise ValueError('missing distribution')
    configuration=read_regular(Path(sys.prefix)/'pyvenv.cfg',16384)
    if 'include-system-site-packages = false' not in configuration.decode().lower():raise ValueError('venv isolation')
    return {'python_version':list(sys.version_info[:3]),'python_sha256':sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),
        'venv_config_sha256':sha256(configuration).hexdigest(),'packages':packages,'lock_sha256':sha256(lock).hexdigest()}


def verify_archive(directory, task, module, manifest):
    """Bind declared ZIP bytes and every expanded member before model execution."""
    import struct
    import zipfile
    raw = read_regular(directory/'package.zip',144*1024**2)
    if len(raw)!=task['package_size_bytes'] or sha256(raw).hexdigest()!=task['package_sha256']:raise ValueError('archive binding')
    if len(raw)<22:raise ValueError('archive footer')
    signature,disk,cd_disk,n_disk,n_total,cd_size,cd_offset,comment=struct.unpack('<4s4H2LH',raw[-22:])
    if signature!=b'PK\x05\x06' or disk or cd_disk or n_disk!=11 or n_total!=11 or comment or cd_size>8192 or cd_offset+cd_size!=len(raw)-22:raise ValueError('archive directory')
    expected={entry['path']:entry for entry in manifest['members']}
    manifest_raw=read_regular(directory/'package/manifest.json',1024**2)
    expected['manifest.json']={'path':'manifest.json','sha256':sha256(manifest_raw).hexdigest(),'size_bytes':len(manifest_raw)}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if [item.filename for item in archive.infolist()]!=sorted(expected):raise ValueError('archive members')
        for item in archive.infolist():
            wanted=expected[item.filename]
            if item.compress_type!=0 or item.flag_bits or item.extra or item.comment or item.file_size!=wanted['size_bytes'] or item.compress_size!=item.file_size or item.external_attr>>16!=(stat.S_IFREG|0o644):raise ValueError('archive member properties')
            if sha256(archive.read(item)).hexdigest()!=wanted['sha256']:raise ValueError('archive member bytes')


def execute(job_id,run_id):
    if not sys.flags.isolated or sys.platform!='linux' or sys.version_info[:2]!=(3,12):raise ValueError('runtime')
    if str(UUID(job_id))!=job_id or str(UUID(run_id))!=run_id:raise ValueError('run')
    directory=Path(os.environ['EDGEVISION_PACKAGE_RUN_DIR'])
    if not directory.is_absolute() or directory.name!=run_id or directory.parent.name!='runs' or directory.parent.parent.name!=job_id:raise ValueError('directory')
    if any(path.is_symlink() for path in (directory,*directory.parents)):raise ValueError('directory link')
    task=json.loads(read_regular(directory/'input.json',1024**2))
    names={'schema_version','kind','job_id','run_id','mode','cli_sha256','bootstrap_sha256','package_sha256','package_size_bytes','runtime_binding','code_version','model_sha256','template_sha256','image_sha256','image_size_bytes'}
    if type(task) is not dict or set(task)!=names or type(task['schema_version']) is not int or task['schema_version']!=1 or task['kind']!='package_standalone_probe':raise ValueError('task')
    if (task['job_id'],task['run_id'])!=(job_id,run_id) or task['mode'] not in {'raw','cli'}:raise ValueError('task identity')
    for name in names-{'schema_version','kind','job_id','run_id','mode','package_size_bytes','image_size_bytes'}:
        if type(task[name]) is not str or re.fullmatch('[0-9a-f]{64}',task[name]) is None:raise ValueError('hash')
    if type(task['package_size_bytes']) is not int or not 0<task['package_size_bytes']<=144*1024**2:raise ValueError('size')
    if type(task['image_size_bytes']) is not int or not 0<task['image_size_bytes']<=50*1024**2:raise ValueError('image size')
    task_hash=sha256(canonical(task)).hexdigest()
    if task_hash!=os.environ['EDGEVISION_PACKAGE_INPUT_SHA256']:raise ValueError('task changed')
    if sha256(read_regular(Path(__file__),1024**2)).hexdigest()!=task['bootstrap_sha256']:raise ValueError('bootstrap changed')
    package=directory/'package'
    raw=read_regular(package/'run.py',1024**2)
    if sha256(raw).hexdigest()!=task['cli_sha256']:raise ValueError('CLI changed')
    audit_imports()
    module=types.ModuleType('verified_standalone_package');module.__file__=str(package/'run.py')
    exec(compile(raw,'<verified-package-runner>','exec'),module.__dict__)
    manifest=module.verify_package(package)
    if manifest['source']['sha256']!=task['model_sha256'] or manifest['template']['template_sha256']!=task['template_sha256']:raise ValueError('candidate binding')
    verify_archive(directory,task,module,manifest)
    example=next(v for v in manifest['members'] if v['path']=='example.png')
    if (example['sha256'],example['size_bytes'])!=(task['image_sha256'],task['image_size_bytes']):raise ValueError('image binding')
    environment=environment_identity(read_regular(package/'requirements.lock',1024**2))
    if task['mode']=='raw':
        output,preview,raw_tensor=module.execute(package,package/'example.png','png')
        module.write_outputs(directory/'result',output,preview)
        write_private(directory/'raw.f32le',raw_tensor,33_734_400)
    else:
        from contextlib import redirect_stdout,redirect_stderr
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            status=module.main(['--image',str(package/'example.png'),'--format','png','--output',str(directory/'result')])
        if status!=0:raise ValueError('CLI failed')
        output=json.loads(read_regular(directory/'result/result.json',1024**2))
    audit_imports()
    if environment_identity(read_regular(package/'requirements.lock',1024**2))!=environment:raise ValueError('environment changed')
    proof={'schema_version':1,'mode':task['mode'],'job_id':job_id,'run_id':run_id,'task_sha256':task_hash,
        'environment_sha256':sha256(canonical(environment)).hexdigest(),'isolated_imports':True,
        'output':output,'receipt_sha256':None}
    write_private(directory/'probe-result.json',canonical(proof),1024**2)


def main():
    if len(sys.argv)!=3 or sys.stdin.buffer.readline(16)!=b'GO\n':return 125
    try:execute(sys.argv[1],sys.argv[2])
    except Exception:
        print('PACKAGE_STANDALONE_FAILED');return 72
    print('PACKAGE_STANDALONE_COMPLETE');return 0


if __name__=='__main__':raise SystemExit(main())
