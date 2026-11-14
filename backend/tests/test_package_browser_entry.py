"""Package browser harness guards; no native model is executed here."""
from pathlib import Path
import importlib.util
import pytest
from test_inference_validation_entry import test_browser_owns_cleanup_and_never_masks_unconfirmed_tree, test_browser_stale_or_undrained_input_stops_before_services
ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def browser(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    spec=importlib.util.spec_from_file_location('package_e2e',ROOT/'scripts/package_e2e.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_package_browser_is_container_only_and_rejects_external_inputs(browser,monkeypatch,capsys):
    monkeypatch.setattr(browser,'run',lambda *args:pytest.fail('must not run'))
    assert browser.main(['--reuse-root','SECRET'])==2
    assert browser.main([])==2
    assert 'SECRET' not in capsys.readouterr().out


def test_package_browser_credentials_are_private_child_only(browser,monkeypatch,tmp_path):
    monkeypatch.setenv('EDGEVISION_E2E_ADMIN_PASSWORD','UNRELATED')
    pair={'pt':{'project_id':'project'},'onnx':{'source_artifact_id':'onnx'}}
    service,private=browser.environments('http://127.0.0.1:5000',4000,5000,pair,{'edgevision_session':'SECRET','edgevision_csrf':'CSRF'},tmp_path/'unused')
    assert not any(k.startswith('EDGEVISION_E2E_') for k in service)
    assert private['EDGEVISION_E2E_PACKAGE']=='1'
    assert 'SECRET' in private['EDGEVISION_E2E_PACKAGE_SESSION']
    assert 'EDGEVISION_E2E_ADMIN_PASSWORD' not in private
    assert 'EDGEVISION_E2E_INFERENCE' not in private
    assert private['EDGEVISION_E2E_PACKAGE_ONNX_ID']=='onnx'


@pytest.mark.parametrize('raw',['{}','{"schema_version":1,"status":"failed"}'])
def test_browser_rejects_missing_http_proof_before_capability(browser,monkeypatch,tmp_path,raw):
    import inference_e2e
    from app import package_assets
    monkeypatch.setattr(inference_e2e,'inputs',lambda:({'onnx':{},'pt':{}},{}))
    monkeypatch.setattr(browser,'DATA',tmp_path)
    (tmp_path/'package-http-result.json').write_text(raw)
    monkeypatch.setattr(package_assets,'validated_template',lambda:pytest.fail('must reject first'))
    with pytest.raises(ValueError):browser.inputs()


def test_browser_missing_private_http_evidence_cannot_be_reused(browser,monkeypatch,tmp_path):
    import inference_e2e
    monkeypatch.setattr(inference_e2e,'inputs',lambda:({},{}))
    monkeypatch.setattr(browser,'DATA',tmp_path)
    with pytest.raises(OSError):browser.inputs()
