"""No ML imports: mock the import boundary and inspect environment handling."""
import os
import sys
from types import SimpleNamespace
import pytest
from app import ml_privacy


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ml_privacy, '_prepared', False)
    monkeypatch.delenv('ORT_DISABLE_TELEMETRY', raising=False)
    monkeypatch.setattr(ml_privacy.metadata, 'version', lambda name: '1.31.1')


def test_opt_out_is_set_before_import_and_event_disable(monkeypatch):
    events = []
    def imported(name):
        assert name == 'onnxruntime'
        assert os.environ['ORT_DISABLE_TELEMETRY'] == '1'
        events.append('import')
        return SimpleNamespace(disable_telemetry_events=lambda: events.append('disable'))
    monkeypatch.setattr(ml_privacy.importlib, 'import_module', imported)
    ml_privacy.load_ort()
    assert events == ['import', 'disable']


@pytest.mark.parametrize('name', ['onnxruntime', 'onnxruntime.capi'])
def test_unprepared_prior_import_is_rejected(monkeypatch, name):
    monkeypatch.setitem(sys.modules, name, SimpleNamespace())
    with pytest.raises(RuntimeError, match='before privacy'):
        ml_privacy.prepare_ort_privacy()
    assert ml_privacy._prepared is False


def test_opt_out_is_forced_and_restored(monkeypatch):
    monkeypatch.setenv('ORT_DISABLE_TELEMETRY', '0')
    ml_privacy.prepare_ort_privacy()
    monkeypatch.delenv('ORT_DISABLE_TELEMETRY')
    ml_privacy.prepare_ort_privacy()
    assert os.environ['ORT_DISABLE_TELEMETRY'] == '1'


def test_missing_disable_api_fails_closed(monkeypatch):
    monkeypatch.setattr(ml_privacy.importlib, 'import_module', lambda name: SimpleNamespace())
    with pytest.raises(AttributeError): ml_privacy.load_ort()


def test_environment_rebuild_keeps_opt_out(monkeypatch, tmp_path):
    from app import config, training_runtime
    monkeypatch.setattr(os, 'environ', {'INHERITED_VALUE': 'discard', 'ORT_DISABLE_TELEMETRY': '0'})
    monkeypatch.setattr(config, 'data_root', lambda: tmp_path/'platform')
    monkeypatch.setattr(sys, 'dont_write_bytecode', sys.dont_write_bytecode)
    training_runtime.prepare_environment(tmp_path)
    assert os.environ['ORT_DISABLE_TELEMETRY'] == '1'
    assert 'INHERITED_VALUE' not in os.environ


def test_rebuild_workflow_never_automatically_executes_ml():
    from pathlib import Path
    import yaml
    workflow = yaml.load((Path(__file__).resolve().parents[2]/'.github/workflows/t020-ci.yml').read_text(), Loader=yaml.BaseLoader)
    assert workflow['jobs']['linux-training']['if'] == "${{ github.event_name == 'workflow_dispatch' && inputs.run_isolated_ml == true }}"
    assert workflow['on']['workflow_dispatch']['inputs']['run_isolated_ml']['default'] == 'false'
    for name in ('checks', 'windows-process'):
        assert workflow['jobs'][name]['env']['EDGEVISION_ML_POLICY_ROOT'] == ''
        assert workflow['jobs'][name]['env']['EDGEVISION_ONNX_POLICY_ROOT'] == ''


def test_other_runtime_version_is_rejected_before_import(monkeypatch):
    monkeypatch.setattr(ml_privacy.metadata, 'version', lambda name: 'unverified')
    monkeypatch.setattr(ml_privacy.importlib, 'import_module', lambda name: pytest.fail('Must not import unverified runtime'))
    with pytest.raises(RuntimeError, match='Unverified ORT'):
        ml_privacy.load_ort()
