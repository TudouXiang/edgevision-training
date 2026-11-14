"""Fixed package ZIP tests: synthetic model bytes and no ML execution."""
from copy import deepcopy
from hashlib import sha256
import io
import zipfile
import pytest
from test_package_inputs import frozen
from test_inference import inference_ready
from test_export import export_ready
from test_training import ready
from test_dataset_api import data_root


def candidate(context):
    from app.package_bundle import template_identity
    value=frozen(context);value['template']=template_identity();return value


def test_builds_reproducible_exact_fixed_archive(inference_ready,tmp_path):
    from app.package_bundle import build_bundle,verify_bundle
    from app.package_cli import MEMBERS
    value=candidate(inference_ready)
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    first=build_bundle(value,a);second=build_bundle(value,b)
    assert (a/'package.zip').read_bytes()==(b/'package.zip').read_bytes()
    assert first==second
    result=verify_bundle(a/'package.zip',value)
    assert result==first
    with zipfile.ZipFile(a/'package.zip') as z:
        assert sorted(z.namelist())==sorted([*MEMBERS,'manifest.json'])
        assert all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist())
        assert z.read('delivery_infer.py')==__import__('pathlib').Path('app/delivery_infer.py').read_bytes()
        assert z.read('run.py')==__import__('pathlib').Path('app/package_cli.py').read_bytes()
        assert b'torch==' not in z.read('requirements.lock') and b'fastapi==' not in z.read('requirements.lock')
        assert b'GNU AFFERO GENERAL PUBLIC LICENSE' in z.read('LICENSE')


@pytest.mark.parametrize('fault',['prefix','suffix','truncated','corrupt','wrong_source','wrong_template'])
def test_rejects_malformed_or_cross_bound_archive(inference_ready,tmp_path,fault):
    from app.package_bundle import build_bundle,verify_bundle
    value=candidate(inference_ready);build_bundle(value,tmp_path);path=tmp_path/'package.zip';raw=path.read_bytes()
    if fault=='prefix':path.write_bytes(b'junk'+raw)
    elif fault=='suffix':path.write_bytes(raw+b'junk')
    elif fault=='truncated':path.write_bytes(raw[:-1])
    elif fault=='corrupt':path.write_bytes(raw[:100]+bytes([raw[100]^1])+raw[101:])
    elif fault=='wrong_source':value['model']['source_sha256']='0'*64
    elif fault=='wrong_template':value['template']['template_sha256']='0'*64
    with pytest.raises((ValueError,OSError,zipfile.BadZipFile)):verify_bundle(path,value)


def test_refuses_changed_template_or_existing_destination(inference_ready,tmp_path):
    from app.package_bundle import build_bundle
    value=candidate(inference_ready);value['template']['core_sha256']='0'*64
    with pytest.raises(ValueError):build_bundle(value,tmp_path)
    assert not (tmp_path/'package.zip').exists()
    value=candidate(inference_ready);(tmp_path/'package.zip').write_bytes(b'keep')
    with pytest.raises(FileExistsError):build_bundle(value,tmp_path)
    assert (tmp_path/'package.zip').read_bytes()==b'keep'


@pytest.mark.parametrize('fault', ['symlink', 'oversized'])
def test_rechecks_private_copy_before_read(inference_ready, tmp_path, monkeypatch, fault):
    from app import package_bundle as bundle
    value = candidate(inference_ready)
    original = bundle.copy_input
    def changed(frozen_value, directory):
        path = original(frozen_value, directory)
        if fault == 'symlink':
            target = directory/'replacement'; path.rename(target); path.symlink_to(target)
        else:
            with path.open('ab') as sink: sink.write(b'changed')
        return path
    monkeypatch.setattr(bundle, 'copy_input', changed)
    with pytest.raises(ValueError): bundle.build_bundle(value, tmp_path)
    assert not (tmp_path/'package.zip').exists()


@pytest.mark.parametrize('fault', ['duplicate', 'symlink', 'deflate', 'local_name', 'declared_size'])
def test_zip_structure_faults_with_consistent_crcs(inference_ready, tmp_path, fault):
    import stat, struct
    from app.package_bundle import build_bundle, verify_bundle
    value = candidate(inference_ready); build_bundle(value, tmp_path); path = tmp_path/'package.zip'
    original = path.read_bytes()
    if fault in {'duplicate','symlink','deflate'}:
        with zipfile.ZipFile(io.BytesIO(original)) as source:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as target:
                for index, info in enumerate(source.infolist()):
                    content = source.read(info)
                    if index == 0 and fault == 'symlink': info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    if index == 0 and fault == 'deflate': info.compress_type = zipfile.ZIP_DEFLATED
                    target.writestr(info, content)
                    if index == 0 and fault == 'duplicate':
                        with pytest.warns(UserWarning): target.writestr(info, content)
            raw = buffer.getvalue()
    else:
        raw = bytearray(original)
        if fault == 'local_name': raw[30] ^= 1
        else: struct.pack_into('<L', raw, 22, 0x7fffffff)
    path.write_bytes(raw)
    with pytest.raises((ValueError, zipfile.BadZipFile)): verify_bundle(path, value)
