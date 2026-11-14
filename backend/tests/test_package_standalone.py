"""Standalone bootstrap gates; tests never import or execute model-native code."""
from pathlib import Path
import subprocess,sys
from uuid import uuid4
import pytest

BOOTSTRAP=Path(__file__).resolve().parents[2]/'scripts/package_standalone.py'


@pytest.mark.parametrize('control',['','STOP\n','OTHER\n'])
def test_standalone_requires_go_before_reading_inputs(control,tmp_path):
    result=subprocess.run([sys.executable,'-I',str(BOOTSTRAP),str(uuid4()),str(uuid4())],input=control,text=True,capture_output=True,env={})
    assert result.returncode==125
    assert result.stdout=='' and result.stderr==''


def test_standalone_bad_input_has_only_closed_error(tmp_path):
    result=subprocess.run([sys.executable,'-I',str(BOOTSTRAP),str(uuid4()),str(uuid4())],input='GO\n',text=True,capture_output=True,env={})
    assert result.returncode==72
    assert result.stdout.strip()=='PACKAGE_STANDALONE_FAILED'
    assert result.stderr==''


def test_bootstrap_binds_declared_archive_and_expanded_manifest(tmp_path):
    import importlib.util,json,zipfile,stat
    from hashlib import sha256
    from test_package_cli import fixture
    spec=importlib.util.spec_from_file_location('package_bootstrap_test',BOOTSTRAP)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    package=tmp_path/'package';package.mkdir();manifest=fixture(package)
    with zipfile.ZipFile(tmp_path/'package.zip','w') as archive:
        for path in sorted(package.iterdir()):
            info=zipfile.ZipInfo(path.name);info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,path.read_bytes())
    raw=(tmp_path/'package.zip').read_bytes()
    task={'package_sha256':sha256(raw).hexdigest(),'package_size_bytes':len(raw)}
    module.verify_archive(tmp_path,task,None,manifest)
    with pytest.raises(ValueError):module.verify_archive(tmp_path,{**task,'package_sha256':'0'*64},None,manifest)
    manifest['classes']=['forged class'];(package/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):module.verify_archive(tmp_path,task,None,manifest)
