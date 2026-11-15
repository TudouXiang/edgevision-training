"""Synthetic files only: validate the exact model copy before native loading."""
import importlib.util
from pathlib import Path
from hashlib import sha256
import pytest


def load():
    p=Path(__file__).resolve().parents[2]/'scripts/pt_eval_binding.py'
    assert p.is_file(),'PT measurement binding missing'
    spec=importlib.util.spec_from_file_location('pt_binding',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_copy_is_verified_before_use_and_never_overwrites(tmp_path):
    m=load();source=tmp_path/'source';source.write_bytes(b'model')
    binding={'sha256':sha256(b'model').hexdigest(),'size_bytes':5};target=tmp_path/'copy'
    m.copy_verified(source,target,binding);assert m.verify_file(target,binding) is True
    with pytest.raises(FileExistsError):m.copy_verified(source,target,binding)
    target.write_bytes(b'other')
    with pytest.raises(ValueError):m.verify_file(target,binding)


@pytest.mark.parametrize('fault',['hash','size','bool','unknown','symlink','fifo'])
def test_bad_model_binding_rejected_without_loading(tmp_path,fault):
    import os
    m=load();source=tmp_path/'source';source.write_bytes(b'model')
    binding={'sha256':sha256(b'model').hexdigest(),'size_bytes':5}
    if fault=='hash':binding['sha256']='0'*64
    if fault=='size':binding['size_bytes']=6
    if fault=='bool':binding['size_bytes']=True
    if fault=='unknown':binding['path']='secret'
    if fault=='symlink':
        source=tmp_path/'link';source.symlink_to(tmp_path/'source')
    if fault=='fifo':
        source=tmp_path/'fifo';os.mkfifo(source)
    with pytest.raises(ValueError):m.copy_verified(source,tmp_path/'copy',binding)
    assert not (tmp_path/'copy').exists()


def test_measurement_pt_only_requires_binding_and_validates_actual_copy(tmp_path,monkeypatch):
    import sys,json
    scripts=Path(__file__).resolve().parents[2]/'scripts';monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('measure_test',scripts/'real_cpu_measure.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert hasattr(m,'prepare_model'),'measurement must bind actual private copy'
    private=tmp_path/'private';private.mkdir();work=private/'measure-pt';work.mkdir()
    (private/'trained.pt').write_bytes(b'model')
    with pytest.raises((ValueError,OSError)):m.prepare_model(private,work,'pt',pt_only=True)
    binding={'sha256':sha256(b'model').hexdigest(),'size_bytes':5}
    (private/'pt-eval-model.json').write_text(json.dumps(binding))
    with pytest.raises(ValueError):m.prepare_model(private,work,'onnx',pt_only=True)
    model,actual=m.prepare_model(private,work,'pt',pt_only=True)
    assert model==work/'model.pt' and actual==binding
    assert model.read_bytes()==b'model'
