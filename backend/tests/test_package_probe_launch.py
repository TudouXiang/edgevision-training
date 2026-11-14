"""Fixed standalone launch boundaries, no model imports or process execution."""
from uuid import uuid4
from pathlib import Path
import pytest


def task():
    return {'schema_version':1,'kind':'package_standalone_probe','job_id':str(uuid4()),'run_id':str(uuid4()),
        'mode':'raw','cli_sha256':'a'*64,'bootstrap_sha256':'b'*64,'package_sha256':'c'*64,
        'package_size_bytes':100,'runtime_binding':'d'*64,'code_version':'e'*64,'model_sha256':'f'*64,
        'template_sha256':'a'*64,'image_sha256':'b'*64,'image_size_bytes':100}


def test_standalone_input_does_not_accept_commands_or_paths():
    from app.package_probe_contract import StandaloneInput
    value=task();assert StandaloneInput.model_validate(value).mode=='raw'
    for key in ('interpreter','command','script','environment','directory'):
        with pytest.raises(ValueError):StandaloneInput.model_validate({**value,key:'/arbitrary'})
    with pytest.raises(ValueError):StandaloneInput.model_validate({**value,'mode':'shell'})


def test_launch_uses_only_fixed_interpreter_and_sanitized_environment(tmp_path,monkeypatch):
    from app import package_launch
    from app.run_files import atomic_json
    value=task();directory=tmp_path/'run';directory.mkdir()
    atomic_json(directory/'input.json',value)
    monkeypatch.setattr(package_launch,'run_directory',lambda *args:directory)
    monkeypatch.setattr(package_launch,'check_environment',lambda:None)
    monkeypatch.setattr(package_launch,'source_hashes',lambda:{'cli_sha256':'a'*64,'bootstrap_sha256':'b'*64})
    monkeypatch.setenv('SECRET_SESSION','private');monkeypatch.setenv('PYTHONPATH','/injected')
    command,environment=package_launch.launch(value['job_id'],value['run_id'])
    assert command==[str(package_launch.PYTHON),'-I','-B',str(package_launch.BOOTSTRAP),value['job_id'],value['run_id']]
    assert 'SECRET_SESSION' not in environment and 'PYTHONPATH' not in environment
    assert environment['EDGEVISION_PACKAGE_RUN_DIR']==str(directory)
    assert environment['ORT_DISABLE_TELEMETRY']=='1'


def test_launch_rejects_changed_or_wrong_run_task(tmp_path,monkeypatch):
    from app import package_launch
    from app.run_files import atomic_json
    value=task();directory=tmp_path/'run';directory.mkdir();atomic_json(directory/'input.json',value)
    monkeypatch.setattr(package_launch,'run_directory',lambda *args:directory)
    monkeypatch.setattr(package_launch,'check_environment',lambda:None)
    monkeypatch.setattr(package_launch,'source_hashes',lambda:{'cli_sha256':'0'*64,'bootstrap_sha256':'b'*64})
    with pytest.raises(ValueError):package_launch.launch(value['job_id'],value['run_id'])
    with pytest.raises(ValueError):package_launch.launch(str(uuid4()),value['run_id'])
