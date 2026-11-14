"""Portable package integrity tests using synthetic bytes, not model receipts."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
import pytest

NAMES = sorted(['model.onnx','run.py','delivery_infer.py','requirements.lock','README.md','example.png','LICENSE','LICENSE_SCOPE.md','THIRD_PARTY_NOTICES.md','MODEL_NOTICE.md'])
def digest(value): return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
def fixture(tmp_path):
    files=[]
    for name in NAMES:
        data=('synthetic '+name).encode();(tmp_path/name).write_bytes(data)
        files.append({'path':name,'size_bytes':len(data),'sha256':sha256(data).hexdigest()})
    entries={e['path']:e for e in files}
    value={'schema_version':1,'protocol':'edgevision-python-onnx-v1','image_protocol':'detection-image-v1',
           'target':'linux-x86_64-cpython312-cpu','classes':['object'],
           'source':{'onnx_artifact_id':str(uuid4()),'export_job_id':str(uuid4()),'parent_artifact_id':str(uuid4()),
                     'sha256':entries['model.onnx']['sha256'],'size_bytes':entries['model.onnx']['size_bytes'],'metadata_sha256':'d'*64},
           'template':{'template_sha256':digest([e for e in files if e['path']!='model.onnx']),
                       'core_sha256':entries['delivery_infer.py']['sha256'],'lock_sha256':entries['requirements.lock']['sha256']},
           'members':files}
    (tmp_path/'manifest.json').write_text(json.dumps(value));return value


def test_portable_manifest_and_files_validate_without_model_import(tmp_path):
    from app.package_cli import validate_manifest, verify_package
    value=fixture(tmp_path)
    assert validate_manifest(value)==value
    assert verify_package(tmp_path)==value


@pytest.mark.parametrize('fault',['extra','bool','traversal','duplicate','missing','model_hash','core_hash','template_hash','target','size','classes'])
def test_portable_manifest_rejects_invalid_shapes(tmp_path,fault):
    from app.package_cli import validate_manifest
    value=fixture(tmp_path)
    if fault=='extra': value['private']='secret'
    elif fault=='bool': value['schema_version']=True
    elif fault=='traversal': value['members'][0]['path']='../secret'
    elif fault=='duplicate': value['members'][1]=deepcopy(value['members'][0])
    elif fault=='missing': value['members'].pop()
    elif fault=='model_hash': value['source']['sha256']='a'*64
    elif fault=='core_hash': value['template']['core_sha256']='a'*64
    elif fault=='template_hash': value['template']['template_sha256']='a'*64
    elif fault=='target': value['target']='cuda'
    elif fault=='size': value['members'][0]['size_bytes']=True
    elif fault=='classes': value['classes']=['x'*129]
    with pytest.raises(ValueError): validate_manifest(value)


@pytest.mark.parametrize('fault',['tamper','extra','symlink','duplicate_json','oversize_json'])
def test_portable_package_rejects_modified_or_unsafe_files(tmp_path,fault):
    from app.package_cli import verify_package
    fixture(tmp_path)
    if fault=='tamper': (tmp_path/'model.onnx').write_bytes(b'bad')
    elif fault=='extra': (tmp_path/'private.txt').write_text('secret')
    elif fault=='symlink': (tmp_path/'model.onnx').unlink();(tmp_path/'model.onnx').symlink_to(tmp_path/'run.py')
    elif fault=='duplicate_json': (tmp_path/'manifest.json').write_text('{"schema_version":1,"schema_version":1}')
    elif fault=='oversize_json': (tmp_path/'manifest.json').write_bytes(b' '*(1024**2+1))
    with pytest.raises((ValueError,OSError)): verify_package(tmp_path)


def test_cli_help_runs_without_platform_or_ml(tmp_path):
    import subprocess, sys
    from pathlib import Path
    source = Path('app/package_cli.py').resolve()
    result = subprocess.run([sys.executable, '-I', str(source), '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert '--image' in result.stdout and '--output' in result.stdout
    assert not result.stderr


def test_cli_bad_package_reports_closed_error(tmp_path):
    import subprocess, sys
    from pathlib import Path
    source = tmp_path/'run.py';source.write_bytes(Path('app/package_cli.py').read_bytes())
    result = subprocess.run([sys.executable, '-I', str(source), '--image', '/private/path/photo.png', '--format', 'png', '--output', str(tmp_path/'out')], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stderr.strip() == 'PACKAGE_EXECUTION_FAILED'
    assert '/private/' not in result.stderr and 'Traceback' not in result.stderr
    assert not (tmp_path/'out').exists()


def test_execute_synthetic_core_preserves_detection_shape(tmp_path, monkeypatch):
    from app import package_cli as cli
    from types import SimpleNamespace
    package = tmp_path/'package';package.mkdir();fixture(package)
    image = tmp_path/'image.png';image.write_bytes(b'image')
    monkeypatch.setattr(cli, '_runtime', lambda *args: None)
    expected = [{'class_id': 0, 'score': .8, 'xyxy': [1.,2.,3.,4.]}]
    core = SimpleNamespace(decode_image=lambda *args: (object(), {}), preprocess=lambda rgb: (b'tensor', {}),
        load_onnx=lambda *args: (lambda tensor: b'raw0', {}),
        postprocess=lambda *args: {'detections': expected, 'counts': {'candidates': 1}},
        preview_png=lambda rgb: (b'preview', (1,1)))
    monkeypatch.setattr(cli, '_load_core', lambda content: core)
    result, preview, raw = cli.execute(package, image, 'png')
    assert result['detections'] == expected
    assert result['counts'] == {'candidates': 1}
    assert result['classes'] == ['object']
    assert raw == b'raw0' and preview == b'preview'


def test_output_failure_never_deletes_competing_file(tmp_path, monkeypatch):
    from app import package_cli as cli
    original = cli.os.open
    output = tmp_path/'output'
    def raced(path, flags, *args, **kwargs):
        if path == 'preview.png': (output/'preview.png').write_bytes(b'other-process')
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(cli.os, 'open', raced)
    with pytest.raises(FileExistsError): cli.write_outputs(output, {}, b'preview')
    assert (output/'preview.png').read_bytes() == b'other-process'
    assert (output/'result.json').read_bytes() == b'{}'  # Partial failure is retained, never destructively cleaned.
