"""No native execution: opt-in and fresh-lineage boundary only."""
from pathlib import Path
import importlib.util
import pytest


def load():
    path=Path(__file__).with_name('package_http_probe.py')
    spec=importlib.util.spec_from_file_location('package_http_probe_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_package_http_requires_matching_opt_in(monkeypatch,tmp_path):
    probe=load();monkeypatch.setenv('PLATFORM_DATA_ROOT',str(tmp_path))
    monkeypatch.delenv('EDGEVISION_PACKAGE_HTTP_ROOT',raising=False)
    with pytest.raises(ValueError):probe.prerequisites()
    monkeypatch.setenv('EDGEVISION_PACKAGE_HTTP_ROOT',str(tmp_path/'other'))
    with pytest.raises(ValueError):probe.prerequisites()


def test_package_http_requires_fresh_lineage(monkeypatch,tmp_path):
    probe=load()
    for key in ('PLATFORM_DATA_ROOT','EDGEVISION_PACKAGE_HTTP_ROOT'):monkeypatch.setenv(key,str(tmp_path))
    with pytest.raises(ValueError):probe.prerequisites()
    for name in ('first-result.json','export-result.json','export-artifact.json','smoke-session.json','inference-http-result.json','inference-capability.json'):
        (tmp_path/name).write_text('{}')
    assert probe.prerequisites()==tmp_path
    (tmp_path/'package-capability.json').write_text('{}')
    with pytest.raises(ValueError):probe.prerequisites()
