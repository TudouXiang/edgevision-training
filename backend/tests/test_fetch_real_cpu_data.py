import hashlib
import importlib.util
import io
from pathlib import Path
import pytest


def load():
    path=Path(__file__).resolve().parents[2]/'scripts/fetch_real_cpu_data.py'
    assert path.is_file(),'fixed public archive downloader absent'
    spec=importlib.util.spec_from_file_location('fetch_real_data',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_fixed_url_hash_new_destination(tmp_path,monkeypatch):
    m=load();raw=b'public';calls=[]
    monkeypatch.setattr(m,'PINS',{'images':(len(raw),hashlib.sha256(raw).hexdigest())})
    def open_url(url,timeout):calls.append(url);return io.BytesIO(raw)
    monkeypatch.setattr(m.urllib.request,'urlopen',open_url)
    m.fetch('images',tmp_path/'images.tar.gz')
    assert calls==['https://thor.robots.ox.ac.uk/~vgg/data/pets/images.tar.gz']
    assert (tmp_path/'images.tar.gz').read_bytes()==raw
    with pytest.raises(ValueError):m.fetch('images',tmp_path/'images.tar.gz')
    with pytest.raises(ValueError):m.fetch('https://bad',tmp_path/'bad')

@pytest.mark.parametrize('raw',[b'',b'wrong',b'excesssize'])
def test_mismatch_never_publishes(tmp_path,monkeypatch,raw):
    m=load();monkeypatch.setattr(m,'PINS',{'images':(5,hashlib.sha256(b'right').hexdigest())})
    monkeypatch.setattr(m.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(raw))
    with pytest.raises(ValueError):m.fetch('images',tmp_path/'images.tar.gz')
    assert not (tmp_path/'images.tar.gz').exists()
