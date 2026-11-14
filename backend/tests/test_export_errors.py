"""Lightweight failures, never native ML evidence or production test switches."""
from importlib.metadata import PackageNotFoundError
import json
from pathlib import Path
import subprocess
import sys
import pytest
from app.export_errors import ExportFailure, EXPORT_EXIT_ERRORS, export_boundary, unsupported_operator
from app.database import transaction
from app.run_files import run_directory, atomic_json
from app.worker import claim, get_job
from test_export import export_ready, post, IDENTITY
from test_training import ready
from test_dataset_api import data_root


@pytest.mark.parametrize('stage,error,code', [
    ('dependency', PackageNotFoundError('private-test-marker'), 73),
    ('dependency', ModuleNotFoundError('private-test-marker'), 73),
    ('runtime', ImportError('private-test-marker'), 73),
    ('graph', ValueError('private-test-marker'), 74),
    ('runtime', RuntimeError('private-test-marker'), 76),
    ('graph', unsupported_operator(), 75),
])
def test_fixed_codes_without_upstream_text(stage, error, code):
    with pytest.raises(ExportFailure) as caught:
        with export_boundary(stage): raise error
    assert caught.value.exit_code == code
    assert str(caught.value) == EXPORT_EXIT_ERRORS[code]
    assert 'private-test-marker' not in str(caught.value)


@pytest.mark.parametrize('module,name,code', [
    ('onnxruntime.capi.onnxruntime_pybind11_state', 'NotImplemented', 75),
    ('torch.onnx.errors', 'UnsupportedOperatorError', 75),
    ('not.a.native.module', 'NotImplemented', 76),
])
def test_exact_native_error_identity_only(module, name, code):
    error_type = type(name, (Exception,), {'__module__': module})
    with pytest.raises(ExportFailure) as caught:
        with export_boundary('runtime'): raise error_type('private-test-marker')
    assert caught.value.exit_code == code


@pytest.mark.parametrize('error', [OSError('storage'), KeyboardInterrupt(), SystemExit(9)])
def test_storage_and_control_failures_are_not_reclassified(error):
    with pytest.raises(type(error)) as caught:
        with export_boundary('runtime'): raise error
    assert caught.value is error


@pytest.mark.parametrize('stage', ['dependency', 'graph', 'runtime'])
def test_existing_training_policy_exception_is_preserved(stage):
    from app.training_runtime import TrainingPolicyError
    error = TrainingPolicyError('NETWORK_ATTEMPT')
    with pytest.raises(TrainingPolicyError) as caught:
        with export_boundary(stage, passthrough=(TrainingPolicyError,)): raise error
    assert caught.value is error


@pytest.mark.parametrize('value', [0, 72, 77, True, '73'])
def test_unrecognized_codes_cannot_be_published(value):
    with pytest.raises(ValueError): ExportFailure(value)


@pytest.mark.parametrize('code', sorted(EXPORT_EXIT_ERRORS))
def test_real_runner_failure_never_creates_bundle(export_ready, monkeypatch, code):
    from app import export_runner, export_runtime
    result = post(export_ready)
    job_id = result.json()['job_id']
    _, run_id = claim('error-fixture', None)
    directory = run_directory(job_id, run_id, create=True)
    frozen = json.loads(get_job(job_id)['input_snapshot_json'])
    atomic_json(directory / 'input.json', {'schema_version': 1, 'job_id': job_id, 'run_id': run_id, 'kind': 'export_onnx', 'input': frozen})
    monkeypatch.setattr(export_runner, 'verify_input', lambda value: value)
    monkeypatch.setattr(export_runner, 'runtime_identity', lambda: IDENTITY)
    monkeypatch.setattr(export_runner, 'copy_input', lambda *args: directory / 'source.pt')
    calls = []
    def fail(*args, **kwargs):
        calls.append('only-export-call')
        raise ExportFailure(code)
    monkeypatch.setattr(export_runtime, 'export_and_validate', fail)
    assert export_runner.run(job_id, run_id) == code
    assert calls == ['only-export-call']
    assert not (directory / 'bundle').exists() and not (directory / 'evidence.json').exists()
    with transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?', (job_id,)).fetchone()[0] == 0


@pytest.mark.parametrize('fault,code', [
    ('onnx_dependency', 'ONNX_DEPENDENCY_UNAVAILABLE'),
    ('onnx_invalid', 'ONNX_MODEL_INVALID'),
    ('onnx_operator', 'ONNX_OPERATOR_UNSUPPORTED'),
    ('onnx_runtime', 'ONNX_RUNTIME_FAILED'),
])
def test_managed_failure_drains_and_publishes_specific_code(export_ready, fault, code):
    result = post(export_ready)
    job_id = result.json()['job_id']
    subprocess.run([sys.executable, str(Path(__file__).with_name('process_fixture.py')), 'worker', 'export_' + fault], check=True, timeout=60, capture_output=True)
    client = export_ready[0][0]
    actual = client.get('/api/v1/jobs/' + job_id).json()
    assert actual['state'] == 'failed' and actual['error_code'] == code
    assert post(export_ready).json() == {'job_id': job_id, 'state': 'failed'}
    job = get_job(job_id)
    directory = run_directory(job_id, job['run_id'])
    receipt = json.loads((directory / 'drained.json').read_text())
    assert receipt['tree_exited'] is True and receipt['started'] is True
    assert receipt['reason'] == 'completed' and receipt['exit_code'] in EXPORT_EXIT_ERRORS
    assert 'private-test-marker' not in json.dumps(actual)
    assert 'private-test-marker' not in client.get('/api/v1/jobs/' + job_id + '/logs').text
    with transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM artifacts WHERE job_id=?', (job_id,)).fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM jobs WHERE kind='export_onnx'").fetchone()[0] == 1


def test_error_modules_are_lightweight():
    result = subprocess.run([sys.executable, '-c', "import app.export_errors,app.export_runner,app.export_runtime,app.task_process,sys; assert not {'torch','onnx','onnxruntime','ultralytics','numpy'}.intersection(sys.modules)"], capture_output=True)
    assert result.returncode == 0


def test_production_ort_loader_fails_with_actual_absent_distribution():
    # A stdlib-only interpreter has no third-party distributions. This is actual
    # absence, not an uninstall and not an otherwise complete native ML stack.
    backend = str(Path(__file__).resolve().parents[1])
    code = '''
import sys
from importlib import metadata
sys.path.insert(0, sys.argv[1])
from app.ml_privacy import load_ort
try:
    metadata.version('onnxruntime')
except metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError('expected an isolated stdlib-only interpreter')
try:
    load_ort()
except metadata.PackageNotFoundError:
    pass
else:
    raise AssertionError('missing ORT accepted')
assert not {'torch','numpy','onnx','onnxruntime','ultralytics'}.intersection(sys.modules)
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code, backend], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_native_calls_remain_in_classified_boundaries():
    # Structural regression, separate from the actual lightweight failure tests.
    # No native function is imported or executed by this assertion.
    import ast
    source = Path(__file__).parents[1] / 'app/export_runtime.py'
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'export_and_validate')
    expected = {
        'read_model_bytes': 'graph', 'onnx.load_model_from_string': 'graph',
        'guard_graph': 'graph', 'onnx.checker.check_model': 'graph',
        'ort.SessionOptions': 'runtime', 'ort.InferenceSession': 'runtime',
        'session.disable_fallback': 'runtime', 'session.get_providers': 'runtime',
        'session.get_inputs': 'runtime', 'session.get_outputs': 'runtime',
        'session.run': 'runtime', 'compare_arrays': 'graph',
    }
    seen = set()
    def visit(node, boundary=None):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and ast.unparse(call.func) == 'export_boundary':
                    boundary = ast.literal_eval(call.args[0])
                    passthrough = next(k.value for k in call.keywords if k.arg == 'passthrough')
                    assert ast.unparse(passthrough) == '(TrainingPolicyError,)'
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in expected:
                assert boundary == expected[name], name
                seen.add(name)
        for child in ast.iter_child_nodes(node): visit(child, boundary)
    visit(function)
    assert seen == set(expected)


@pytest.mark.parametrize('fault', ['empty', 'directory'])
def test_actual_invalid_model_file_gets_graph_code(tmp_path, fault):
    from app.export_runtime import read_model_bytes
    model = tmp_path / 'model.onnx'
    if fault == 'empty': model.write_bytes(b'')
    else: model.mkdir()
    with pytest.raises(ExportFailure) as caught:
        with export_boundary('graph'): read_model_bytes(model)
    assert caught.value.exit_code == 74
