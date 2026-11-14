"""Lightweight guards for opt-in I evidence. No native adapter is executed."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name, folder=HERE):
    spec = importlib.util.spec_from_file_location(name, folder / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


http = load('inference_http_probe')
policy = load('inference_policy_probe')


@pytest.fixture
def opted_root(tmp_path, monkeypatch):
    monkeypatch.setenv('PLATFORM_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('EDGEVISION_INFERENCE_HTTP_ROOT', str(tmp_path))
    for name in ('first-result.json', 'export-result.json', 'export-artifact.json', 'smoke-session.json'):
        (tmp_path / name).write_text('{}')
    return tmp_path


def test_same_fresh_root_required_without_launch(opted_root, monkeypatch):
    monkeypatch.setattr(http.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    assert http.prerequisites() == opted_root
    monkeypatch.delenv('EDGEVISION_INFERENCE_HTTP_ROOT')
    with pytest.raises(ValueError):
        http.prerequisites()
    monkeypatch.setenv('EDGEVISION_INFERENCE_HTTP_ROOT', str(opted_root / 'other'))
    with pytest.raises(ValueError):
        http.prerequisites()


@pytest.mark.parametrize('name', ['first-result.json', 'export-result.json', 'export-artifact.json', 'smoke-session.json'])
def test_missing_lineage_or_session_rejected(opted_root, name):
    (opted_root / name).unlink()
    with pytest.raises(ValueError):
        http.prerequisites()


@pytest.mark.parametrize('name', ['inference-capability.json', 'inference-http-started.json', 'inference-http-result.json'])
def test_previous_probe_or_partial_attempt_not_reused(opted_root, name):
    (opted_root / name).write_text('{}')
    with pytest.raises(ValueError):
        http.prerequisites()


def test_http_missing_opt_in_emits_only_fixed_failure(monkeypatch, capsys):
    monkeypatch.delenv('EDGEVISION_INFERENCE_HTTP_ROOT', raising=False)
    monkeypatch.setenv('PLATFORM_DATA_ROOT', '/SECRET/private/path')
    monkeypatch.setattr(http, 'run', lambda *a: pytest.fail('must not run'))
    assert http.main() == 1
    captured = capsys.readouterr()
    assert captured.out == 'FAIL real managed image prerequisites\n' and not captured.err


def test_native_helper_rejects_case_and_root_before_app_import(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match='unknown'):
        policy.main('untrusted', str(tmp_path))
    monkeypatch.delenv('EDGEVISION_INFERENCE_POLICY_ROOT', raising=False)
    with pytest.raises(ValueError, match='same-root'):
        policy.main('corrupt_onnx', str(tmp_path))


def test_probe_module_imports_do_not_launch_or_import_native():
    script = """
import importlib.util, pathlib, subprocess, sys
subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not launch'))
for name in ('inference_http_probe', 'inference_policy_probe'):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path('tests') / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
assert not {'torch', 'numpy', 'onnx', 'onnxruntime', 'ultralytics'}.intersection(sys.modules)
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=HERE.parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_cases_are_explicit_closed_codes_and_separate_interpreters():
    assert policy.CASES == {
        'corrupt_onnx': 'ORT_MODEL_INVALID', 'missing_ort': 'ORT_DEPENDENCY_MISSING',
        'provider_mismatch': 'ORT_PROVIDER_MISMATCH', 'execution_failure': 'ORT_EXECUTION_FAILED',
        'nonfinite_output': 'INFERENCE_OUTPUT_INVALID'}
    source = (HERE / 'test_inference_runtime_policy.py').read_text()
    assert 'EDGEVISION_INFERENCE_POLICY_ROOT' in source and 'subprocess.run' in source
    assert 'inference_policy_probe.py' in source


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    return load('inference_e2e', ROOT / 'scripts')


def test_browser_has_no_arbitrary_root_or_cli_reuse(browser, monkeypatch, capsys):
    monkeypatch.setattr(browser, 'boundary', lambda: pytest.fail('arguments must fail first'))
    assert browser.main(['--reuse-root', '/SECRET']) == 2
    captured = capsys.readouterr()
    assert 'SECRET' not in captured.out + captured.err
    assert captured.out == 'FAIL real isolated image browser; private diagnostics retained\n'


def test_browser_cannot_execute_from_development_checkout(browser, monkeypatch):
    monkeypatch.setattr(browser, 'run', lambda *a: pytest.fail('must not start'))
    assert browser.main([]) == 2


def test_browser_private_inputs_go_only_to_browser_environment(browser, monkeypatch, tmp_path):
    cookies = {'edgevision_session': 'SECRET_SESSION', 'edgevision_csrf': 'SECRET_CSRF'}
    pair = {'pt': {'project_id': 'project', 'source_artifact_id': 'pt'}, 'onnx': {'source_artifact_id': 'onnx'}}
    monkeypatch.setenv('EDGEVISION_E2E_ADMIN_PASSWORD', 'UNRELATED')
    service, private = browser.environments('http://127.0.0.1:5000', 4000, 5000, pair, cookies, tmp_path / 'image.png')
    assert not any(name.startswith('EDGEVISION_E2E_') for name in service)
    assert private['EDGEVISION_E2E_INFERENCE'] == '1'
    assert 'SECRET_SESSION' in private['EDGEVISION_E2E_INFERENCE_SESSION']
    assert 'EDGEVISION_E2E_ADMIN_PASSWORD' not in private
    assert private['EDGEVISION_E2E_INFERENCE_PROJECT_ID'] == 'project'
    assert service['PLATFORM_DATA_ROOT'] == '/opt/edgevision/private/http'
    assert service['ORT_DISABLE_TELEMETRY'] == '1'


def test_default_workflow_and_dev_check_clear_all_image_opt_ins(monkeypatch):
    import yaml
    workflow = yaml.load((ROOT / '.github/workflows/t020-ci.yml').read_text(), Loader=yaml.BaseLoader)
    for job in ('checks', 'windows-process'):
        for key in ('EDGEVISION_INFERENCE_HTTP_ROOT', 'EDGEVISION_INFERENCE_POLICY_ROOT', 'EDGEVISION_E2E_INFERENCE'):
            assert workflow['jobs'][job]['env'][key] == ''
    assert workflow['jobs']['linux-training']['timeout-minutes'] == '20'
    dev = load('dev', ROOT / 'scripts')
    for key in dev.NATIVE_OPT_INS:
        monkeypatch.setenv(key, 'must-not-reach-default-check')
    calls = []
    monkeypatch.setattr(dev, 'backend_python', lambda: '/light/python')
    monkeypatch.setattr(dev, 'run', lambda *args, **kwargs: calls.append((args, kwargs)) or 0)
    assert dev.main(['check']) == 0
    assert len(calls) == 6
    for _, kwargs in calls:
        assert all(key not in kwargs['env'] for key in dev.NATIVE_OPT_INS)
    # A check does not mutate the operator's surrounding environment.
    assert all(dev.os.environ[key] == 'must-not-reach-default-check' for key in dev.NATIVE_OPT_INS)


@pytest.mark.parametrize('failure', ['none', 'web_start', 'browser_wait', 'tree_unconfirmed', 'receipt_rejected', 'cleanup_write'])
def test_browser_owns_cleanup_and_never_masks_unconfirmed_tree(browser, monkeypatch, tmp_path, failure):
    from io import StringIO
    from app import delivery_infer
    monkeypatch.setattr(browser, 'PRIVATE', tmp_path)
    monkeypatch.setattr(browser, 'REPORT', tmp_path / 'report')
    monkeypatch.setattr(delivery_infer, 'synthetic_png', lambda: b'private synthetic bytes')
    pair = {'pt': {'project_id': 'project', 'source_artifact_id': 'pt'}, 'onnx': {'source_artifact_id': 'onnx'}}
    monkeypatch.setattr(browser, 'inputs', lambda: (pair, {'edgevision_session': 'private', 'edgevision_csrf': 'private'}))
    settlements = []
    def settle():
        settlements.append(True)
        return not (failure == 'tree_unconfirmed' and len(settlements) > 1)
    monkeypatch.setattr(browser, 'settle', settle)
    monkeypatch.setattr(browser.shutil, 'which', lambda name: '/locked/' + name)
    ports = iter([4000, 5000])
    monkeypatch.setattr(browser, 'available_port', lambda: next(ports))
    started = []
    class Process:
        def poll(self): return None
        def wait(self, **kwargs):
            if failure == 'browser_wait': raise subprocess.TimeoutExpired('private browser', 150)
            return 0
    def start(*args):
        process = Process()
        started.append(process)
        return process
    monkeypatch.setattr(browser, 'start_process', start)
    waits = []
    def wait_for(*args):
        waits.append(True)
        if failure == 'web_start' and len(waits) == 2: raise RuntimeError('private readiness')
    monkeypatch.setattr(browser, 'wait_for', wait_for)
    monkeypatch.setattr(browser.subprocess, 'Popen', lambda *a, **k: start())
    if failure == 'cleanup_write':
        original_write = browser.Path.write_text
        def write(path, *args, **kwargs):
            if path.name == 'cleanup.json':
                raise OSError('SECRET cleanup path')
            return original_write(path, *args, **kwargs)
        monkeypatch.setattr(browser.Path, 'write_text', write)
    stopped = []
    monkeypatch.setattr(browser, 'stop_owned', lambda processes: stopped.extend(processes) or True)
    monkeypatch.setattr(browser, 'browser_exit_code', lambda *a, **kw: 2 if failure == 'receipt_rejected' else 0)
    if failure == 'cleanup_write':
        with pytest.raises(OSError):
            browser.run(StringIO())
        assert browser.CURRENT_PHASE == 'cleanup'
        return
    if failure in {'web_start', 'browser_wait'}:
        with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
            browser.run(StringIO())
    else:
        assert browser.run(StringIO()) == {'none': 0, 'tree_unconfirmed': 4, 'receipt_rejected': 2}[failure]
    assert stopped == list(reversed(started))
    assert len(settlements) == 2
    import json
    cleanup = json.loads((tmp_path / 'cleanup.json').read_text())
    assert cleanup['status'] == ('failed' if failure == 'tree_unconfirmed' else 'passed')


def test_browser_stale_or_undrained_input_stops_before_services(browser, monkeypatch, tmp_path):
    monkeypatch.setattr(browser, 'settle', lambda: False)
    monkeypatch.setattr(browser, 'inputs', lambda: pytest.fail('must not read private session'))
    monkeypatch.setattr(browser, 'start_process', lambda *args: pytest.fail('must not start'))
    with pytest.raises(RuntimeError, match='unconfirmed'):
        browser.run(None)


def test_browser_failure_receipt_is_closed_and_has_no_exception(browser, monkeypatch, tmp_path, capsys):
    import json
    monkeypatch.setattr(browser, 'PRIVATE', tmp_path / 'browser')
    monkeypatch.setattr(browser, 'boundary', lambda: None)
    def fail(_diagnostic):
        browser.CURRENT_PHASE = 'inputs'
        raise ValueError('SECRET cookie /home/user/input.png')
    monkeypatch.setattr(browser, 'run', fail)
    assert browser.main([]) == 2
    receipt = json.loads((browser.PRIVATE / 'failure.json').read_text())
    assert receipt == {'phase': 'inputs'}
    assert 'SECRET' not in capsys.readouterr().out
