"""Synthetic contract tests; deliberately do not import or execute native ML."""
import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[1] / 'app' / 'real_export_diagnostic.py'
spec = importlib.util.spec_from_file_location('real_export_diagnostic_test', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_guard_fails_before_loading_boundary_or_runtime(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(module, 'load_boundary', lambda *a: calls.append(a))
    with pytest.raises(ValueError):
        module.guard(root=tmp_path, environ={})
    assert calls == []


def test_guard_requires_profile_and_private_root(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(module, 'load_boundary', lambda *a: calls.append(a) or object())
    expected = {'EDGEVISION_EXPORT_COMPARE_PROFILE': 'v1',
                'PLATFORM_DATA_ROOT': '/opt/edgevision/private/real-platform'}
    with pytest.raises(ValueError):
        module.guard(root=Path('/opt/edgevision'), environ={**expected, 'PLATFORM_DATA_ROOT':'/tmp'})
    assert calls == []
    env = {'EDGEVISION_EXPORT_COMPARE_PROFILE':'v1', 'PLATFORM_DATA_ROOT':'/opt/edgevision/private/real-platform'}
    class Boundary:
        def verify_boundary(self, netns): calls.append(('verified', netns))
    monkeypatch.setattr(module, 'load_boundary', lambda root: Boundary())
    module.guard(root=Path('/opt/edgevision'), environ=env)
    assert calls == [('verified', '')]
    calls.clear()
    with pytest.raises(ValueError):
        module.guard(root=Path('/opt/edgevision'), environ={**expected, 'EDGEVISION_EXPORT_COMPARE_PROFILE':'v2'})
    assert calls == []


def test_arm_settings_are_closed_and_fixed():
    assert module.arm_settings('A') == {'fuse': False, 'constant_folding': True}
    assert module.arm_settings('B') == {'fuse': False, 'constant_folding': False}
    assert module.arm_settings('C') == {'fuse': True, 'constant_folding': True}
    for arm in ('a', 'D', None, True):
        with pytest.raises(ValueError): module.arm_settings(arm)


def test_proof_uses_null_for_unexecuted_and_requires_complete_pass():
    proof = module.empty_proof('C')
    assert proof['checks']['source_bn'] is None
    assert proof['checks']['reference_ort_match'] == {'zeros': None, 'gradient': None, 'pattern': None}
    with pytest.raises(ValueError): module.validate_proof({**proof, 'status':'passed'})
    proof['checks'].update(source_bn=False, onnx_batchnorm=False, pt_repeat_pre=True,
        pt_repeat_post=True, source_unchanged=True, network_unchanged=True, fused_reference_match=True,
        reference_ort_match={'zeros':True,'gradient':True,'pattern':True})
    proof['status'] = 'passed'; proof['failure_code'] = None
    from test_export_compare_report import with_metrics
    with_metrics(proof)
    assert module.validate_proof(proof) is proof


def test_failed_comparison_proof_can_retain_all_three_samples():
    proof = module.empty_proof('A')
    proof['status'] = 'failed'; proof['failure_code'] = 'ONNX_MISMATCH'
    proof['checks'].update(source_bn=True, onnx_batchnorm=True, pt_repeat_pre=True,
        pt_repeat_post=True, source_unchanged=True, network_unchanged=True,
        reference_ort_match={'zeros':True,'gradient':False,'pattern':True})
    from test_export_compare_report import with_metrics
    with_metrics(proof)
    assert module.validate_proof(proof) is proof
    proof['checks']['reference_ort_match'].pop('pattern')
    with pytest.raises(ValueError): module.validate_proof(proof)


def test_network_state_snapshot_detects_buffer_or_parameter_change():
    class Tensor:
        dtype = 'float32'; shape = (1,)
        def __init__(self, value): self.value = value
        def detach(self): return self
        def cpu(self): return self
        def clone(self): return Tensor(self.value)
    class Network:
        def __init__(self): self.parameter = Tensor(1); self.buffer = Tensor(2)
        def named_parameters(self): return iter([('weight', self.parameter)])
        def named_buffers(self): return iter([('running', self.buffer)])
    class Torch:
        @staticmethod
        def equal(left, right): return left.value == right.value
    network = Network(); before = module._snapshot_network(network)
    assert module._network_unchanged(Torch, network, before)
    network.buffer.value = 3
    assert not module._network_unchanged(Torch, network, before)


def test_sample_comparisons_continue_after_numerical_mismatch_but_not_runtime_error():
    visited = []
    class Mismatch(Exception): pass
    def compare(name):
        visited.append(name)
        if name == 'gradient': raise Mismatch()
    values, incomplete = module.collect_samples(compare, Mismatch)
    assert visited == ['zeros', 'gradient', 'pattern']
    assert values == {'zeros':True, 'gradient':False, 'pattern':True} and not incomplete
    visited.clear()
    def runtime(name):
        visited.append(name)
        if name == 'gradient': raise OSError('private runtime detail')
    values, incomplete = module.collect_samples(runtime, Mismatch)
    assert visited == ['zeros', 'gradient']
    assert values == {'zeros':True, 'gradient':None, 'pattern':None} and incomplete


def test_non_c_fused_check_must_be_null_and_unknown_keys_rejected():
    proof = module.empty_proof('B')
    proof['checks']['fused_reference_match'] = False
    with pytest.raises(ValueError): module.validate_proof(proof)


def test_run_input_accepts_only_fixed_arm_and_source_export_mapping():
    value = {'schema_version':1, 'job_id':'job', 'run_id':'run',
        'kind':'real_export_diagnostic', 'arm':'B', 'source_export':{'kind':'export_onnx'}}
    assert module._model_input(value, 'job', 'run') == ('B', {'kind':'export_onnx'})
    value['source_export_input'] = value.pop('source_export')
    with pytest.raises(ValueError): module._model_input(value, 'job', 'run')


def test_worker_kind_is_fixed_and_selects_diagnostic_child():
    source = (Path(__file__).resolve().parents[1] / 'app' / 'task_process.py').read_text()
    assert 'elif kind == "real_export_diagnostic":' in source
    assert 'from .real_export_diagnostic import probe_child as run' in source
    proof = module.empty_proof('A'); proof['private'] = 'secret'
    with pytest.raises(ValueError): module.validate_proof(proof)


def test_swallowed_policy_failure_cannot_write_complete_proof(monkeypatch, tmp_path):
    writes = []
    monkeypatch.setattr(module, '_write', lambda *args: writes.append(args))
    proof = module.empty_proof('A')
    with pytest.raises(module.DiagnosticFailure) as failure:
        module.write_observations(tmp_path, proof, ['NETWORK_ATTEMPT'])
    assert failure.value.code == 'POLICY_FAILED'
    assert failure.value.exit_code == 68
    assert writes == []
    module.write_observations(tmp_path, proof, [])
    assert writes == [(tmp_path, proof)]


def test_observation_does_not_publish_statistics_when_comparator_errors():
    class Mismatch(Exception):pass
    def error():raise RuntimeError('private failure')
    with pytest.raises(RuntimeError):module.compare_observation(lambda:{'private':'stats'},error,Mismatch)
    def mismatch():raise Mismatch()
    assert module.compare_observation(lambda:{'closed':True},mismatch,Mismatch)==({'closed':True},False)
    assert module.compare_observation(lambda:{'closed':True},lambda:None,Mismatch)==({'closed':True},True)


def test_last_fused_sample_runtime_error_preserves_null_suffix():
    class Mismatch(Exception):pass
    proof=module.empty_proof('C')
    from test_export_compare_report import with_metrics
    completed=module.empty_proof('C');completed['checks']['fused_reference_match']=True
    with_metrics(completed)
    for sample in ('zeros','gradient'):
        stats,match=module.compare_observation(lambda:completed['metrics']['original_fused'][sample],lambda:None,Mismatch)
        proof['metrics']['original_fused'][sample]=stats
    def fail():raise RuntimeError('private failure')
    with pytest.raises(RuntimeError):
        stats,match=module.compare_observation(lambda:completed['metrics']['original_fused']['pattern'],fail,Mismatch)
        proof['metrics']['original_fused']['pattern']=stats
    proof['failure_code']='RUNTIME_FAILED'
    assert proof['metrics']['original_fused']['pattern'] is None
    module.validate_proof(proof)
