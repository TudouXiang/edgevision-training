"""Synthetic diagnostic contracts only; no native model execution."""
import json
import pytest
from app import export_errors as errors
from app import export_runner


@pytest.mark.parametrize('code', ['graph_read','graph_parse','graph_guard','graph_checker','final_integrity'])
def test_graph_boundary_attaches_only_fixed_code(code):
    with pytest.raises(errors.ExportFailure) as caught:
        with errors.export_boundary('graph', diagnostic=code):
            raise ValueError('private path and tensor')
    assert caught.value.exit_code == 74
    assert caught.value.diagnostic == code
    assert str(caught.value) == 'ONNX_MODEL_INVALID'


@pytest.mark.parametrize('code', ['compare_shape_dtype','compare_nonfinite','compare_tolerance'])
def test_compare_failure_preserves_message_and_category(code):
    error = errors.ExportGraphError('original message', code)
    assert str(error) == 'original message'
    with pytest.raises(errors.ExportFailure) as caught:
        with errors.export_boundary('graph'):
            raise error
    assert caught.value.diagnostic == code
    assert caught.value.exit_code == 74


def test_unknown_and_passthrough():
    with pytest.raises(ValueError):
        with errors.export_boundary('graph', diagnostic='secret'): pass
    original = OSError('private')
    with pytest.raises(OSError) as caught:
        with errors.export_boundary('graph', diagnostic='graph_read'): raise original
    assert caught.value is original
    with pytest.raises(errors.ExportFailure) as caught:
        with errors.export_boundary('graph', diagnostic='graph_guard'): raise errors.unsupported_operator()
    assert caught.value.exit_code == 75
    assert caught.value.diagnostic == 'unknown'


def test_private_sidecar_is_closed_and_write_failure_is_best_effort(tmp_path, monkeypatch):
    error = errors.ExportFailure(74, diagnostic='compare_tolerance')
    export_runner.write_failure_diagnostic(tmp_path, error)
    assert json.loads((tmp_path/'export-failure.json').read_text()) == {'schema_version':1,'code':'compare_tolerance'}
    error.diagnostic = 'private arbitrary payload'
    export_runner.write_failure_diagnostic(tmp_path, error)
    assert json.loads((tmp_path/'export-failure.json').read_text())['code'] == 'unknown'
    def fail(*args): raise OSError('secret')
    monkeypatch.setattr(export_runner, 'atomic_json', fail)
    export_runner.write_failure_diagnostic(tmp_path, error)
    assert error.exit_code == 74


@pytest.mark.parametrize('case,code', [('shape','compare_shape_dtype'),('nonfinite','compare_nonfinite'),('tolerance','compare_tolerance')])
def test_actual_compare_branch_with_synthetic_array_facade(case, code):
    # Tiny facade exercises control flow only; not NumPy/ML numerical evidence.
    from types import SimpleNamespace
    from app.export_runtime import compare_arrays
    class Array:
        dtype = 'f32'
        shape = (1,)
        def __init__(self, value): self.value = value
        def astype(self, dtype): return self.value
    reference, actual = Array(0.0), Array(1.0)
    if case == 'shape': actual.shape = (2,)
    np = SimpleNamespace(float32='f32', float64='f64',
        isfinite=lambda value: SimpleNamespace(all=lambda: case != 'nonfinite'),
        abs=abs, all=lambda value: value)
    with pytest.raises(errors.ExportFailure) as caught:
        with errors.export_boundary('graph'):
            compare_arrays(np, reference, actual, 'zeros')
    assert caught.value.exit_code == 74
    assert caught.value.diagnostic == code


def test_success_and_non_graph_error_do_not_create_sidecar(tmp_path):
    with errors.export_boundary('graph', diagnostic='graph_guard'):
        pass
    for code in (73, 75, 76):
        export_runner.write_failure_diagnostic(tmp_path, errors.ExportFailure(code))
    assert list(tmp_path.iterdir()) == []


def test_sidecar_never_suppresses_safety_signal(tmp_path, monkeypatch):
    from app.training_runtime import TrainingPolicyError
    def fail(*args):raise TrainingPolicyError('synthetic safety signal')
    monkeypatch.setattr(export_runner,'atomic_json',fail)
    with pytest.raises(TrainingPolicyError):
        export_runner.write_failure_diagnostic(tmp_path, errors.ExportFailure(74))
