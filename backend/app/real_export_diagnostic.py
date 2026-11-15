"""Fixed A/D export-backend control, diagnostic only.

No native imports occur until the exact container/network/profile guard has
passed. Arm A exports once with MKLDNN enabled; arm D consumes A's strict
private handoff and only disables MKLDNN. Neither arm publishes artifacts.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = '/opt/edgevision/private/real-platform'
PROFILE = 'v1'
_spec = importlib.util.spec_from_file_location('export_compare_metrics', ROOT / 'scripts' / 'export_compare_metrics.py')
metrics = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(metrics)
ARMS = ('A', 'D')
SAMPLES = ('zeros', 'gradient', 'pattern')
FAILURE_CODES = ('POLICY_FAILED', 'SOURCE_INVALID', 'GRAPH_INVALID', 'PT_REPEAT_MISMATCH', 'BACKEND_MISMATCH', 'SOURCE_CHANGED', 'ONNX_MISMATCH', 'RUNTIME_FAILED', 'UNKNOWN')
CHECKS = {'source_bn', 'onnx_batchnorm', 'pt_repeat_pre', 'pt_repeat_post', 'source_unchanged', 'network_unchanged', 'reference_ort_match', 'backend_reference_match', 'shared_input_unchanged'}


def load_boundary(root: Path):
    path = root / 'scripts' / 'isolated_ml_entry.py'
    spec = importlib.util.spec_from_file_location('real_export_isolated_ml_entry', path)
    if spec is None or spec.loader is None:
        raise ValueError('container boundary unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard(*, root: Path | None = None, environ=None) -> None:
    root = ROOT if root is None else Path(root)
    env = os.environ if environ is None else environ
    if root != Path('/opt/edgevision'):
        raise ValueError('container checkout required')
    if env.get('EDGEVISION_EXPORT_COMPARE_PROFILE') != PROFILE:
        raise ValueError('comparison profile required')
    if env.get('PLATFORM_DATA_ROOT') != DATA_ROOT:
        raise ValueError('private platform root required')
    load_boundary(root).verify_boundary(env.get('EDGEVISION_ISOLATED_HOST_NETNS', ''))


def arm_settings(arm):
    if type(arm) is not str or arm not in ARMS:
        raise ValueError('unknown comparison arm')
    return {'export': arm == 'A', 'disable_mkldnn': arm == 'D'}


class DiagnosticFailure(Exception):
    def __init__(self, code, exit_code):
        if type(code) is not str or code not in FAILURE_CODES or type(exit_code) is not int:
            raise ValueError('invalid diagnostic failure')
        self.code, self.exit_code = code, exit_code
        super().__init__('export backend diagnostic failed')


def empty_proof(arm):
    arm_settings(arm)
    return {'schema_version': 3, 'arm': arm, 'status': 'failed',
        'checks': {'source_bn': None, 'onnx_batchnorm': None,
            'pt_repeat_pre': None, 'pt_repeat_post': None, 'source_unchanged': None,
            'network_unchanged': None, 'reference_ort_match': {name: None for name in SAMPLES},
            'backend_reference_match': None, 'shared_input_unchanged': None},
        'failure_code': 'UNKNOWN', 'metrics': metrics.empty_matrix(arm), 'precision': None}


def validate_proof(value):
    if type(value) is not dict or set(value) != {'schema_version', 'arm', 'status', 'checks', 'failure_code', 'metrics', 'precision'}:
        raise ValueError('diagnostic proof schema invalid')
    if type(value['schema_version']) is not int or value['schema_version'] != 3:
        raise ValueError('diagnostic proof version invalid')
    arm_settings(value['arm'])
    if value['status'] not in ('passed', 'failed'):
        raise ValueError('diagnostic proof status invalid')
    if value['failure_code'] is not None and (type(value['failure_code']) is not str or value['failure_code'] not in FAILURE_CODES):
        raise ValueError('diagnostic failure code invalid')
    if value['precision'] is not None:
        metrics.validate_precision(value['precision'], value['arm'])
    checks = value['checks']
    if type(checks) is not dict or set(checks) != CHECKS:
        raise ValueError('diagnostic checks invalid')
    for name in CHECKS - {'reference_ort_match'}:
        if name == 'backend_reference_match' and value['arm'] == 'A':
            if checks[name] is not None: raise ValueError('A backend comparison not applicable')
        elif checks[name] is not None and type(checks[name]) is not bool:
            raise ValueError('diagnostic check type invalid')
    matches = checks['reference_ort_match']
    if type(matches) is not dict or set(matches) != set(SAMPLES) or any(x is not None and type(x) is not bool for x in matches.values()):
        raise ValueError('diagnostic sample checks invalid')
    if value['status'] == 'passed':
        required = ('source_bn', 'onnx_batchnorm', 'pt_repeat_pre', 'pt_repeat_post', 'source_unchanged', 'network_unchanged', 'shared_input_unchanged')
        if any(type(checks[name]) is not bool for name in required):
            raise ValueError('completed diagnostic checks missing')
        if (checks['source_unchanged'] is not True or checks['shared_input_unchanged'] is not True
                or checks['pt_repeat_pre'] is not True or checks['pt_repeat_post'] is not True
                or checks['network_unchanged'] is not True or any(v is not True for v in matches.values())
                or value['precision'] is None or value['failure_code'] is not None):
            raise ValueError('incomplete or failed proof cannot pass')
        if value['arm'] == 'D' and checks['backend_reference_match'] is not True:
            raise ValueError('D backend comparison did not pass')
    elif type(value['failure_code']) is not str:
        raise ValueError('failed proof needs a closed failure code')
    metrics.validate_matrix(value['metrics'], value['arm'], checks)
    if value['status'] == 'passed':
        if not metrics.complete(value['metrics'], value['arm']):
            raise ValueError('numeric observations incomplete')
        if any(not metrics.matches(groups) for block in value['metrics'].values() if block is not None for groups in block.values()):
            raise ValueError('numeric comparisons did not all match')
    return value


def _model_input(value, job_id, run_id):
    if type(value) is not dict or set(value) != {'schema_version', 'job_id', 'run_id', 'kind', 'arm', 'source_export', 'backend_source'}:
        raise ValueError('diagnostic input schema invalid')
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['kind'] != 'real_export_diagnostic':
        raise ValueError('diagnostic input identity invalid')
    if value['job_id'] != job_id or value['run_id'] != run_id:
        raise ValueError('diagnostic run binding invalid')
    arm_settings(value['arm'])
    if type(value['source_export']) is not dict:
        raise ValueError('frozen export input required')
    if value['arm'] == 'A' and value['backend_source'] is not None:
        raise ValueError('A must not receive a handoff')
    if value['arm'] == 'D' and type(value['backend_source']) is not dict:
        raise ValueError('D requires the fixed A handoff')
    return value['arm'], value['source_export'], value['backend_source']


def _outputs(torch, network, tensors):
    import numpy as np
    values = {}
    with torch.inference_mode():
        for name in SAMPLES:
            result = network(torch.from_numpy(tensors[name]))
            if not isinstance(result, torch.Tensor) or tuple(result.shape) != (1, 6, 8400):
                raise ValueError('fixed PT output schema invalid')
            values[name] = result.detach().cpu().numpy().copy()
    return values


def _same_outputs(np, left, right):
    return all(np.array_equal(left[name], right[name], equal_nan=True) for name in SAMPLES)


def _snapshot_network(network):
    result = {}
    for category, values in (('parameter', network.named_parameters()), ('buffer', network.named_buffers())):
        for name, value in values:
            key = f'{category}:{name}'
            if key in result: raise ValueError('duplicate network state name')
            tensor = value.detach().cpu().clone()
            result[key] = (str(tensor.dtype), tuple(tensor.shape), tensor)
    return result


def _network_unchanged(torch, network, before):
    after = _snapshot_network(network)
    if set(after) != set(before): return False
    return all(before[key][0] == after[key][0] and before[key][1] == after[key][1]
               and torch.equal(before[key][2], after[key][2]) for key in before)


def compare_observation(measure, compare, mismatch_type):
    """Return one atomic observation only after a completed comparison."""
    statistics = measure()
    try:
        compare()
    except mismatch_type:
        return statistics, False
    return statistics, True


def collect_samples(compare_one, mismatch_type):
    """Continue after complete numerical mismatches; runtime errors stay null."""
    results = {name: None for name in SAMPLES}
    for name in SAMPLES:
        try:
            matched = compare_one(name)
        except mismatch_type:
            results[name] = False
        except Exception:
            return results, True
        else:
            results[name] = matched is not False
    return results, False


def _contains_batchnorm(model_proto):
    stack = [model_proto]
    while stack:
        message = stack.pop()
        if getattr(message, 'op_type', None) == 'BatchNormalization': return True
        for field, value in message.ListFields():
            if field.message_type is not None:
                stack.extend(value if field.is_repeated else [value])
    return False


def _write(directory, proof):
    from .run_files import atomic_json
    atomic_json(directory / 'diagnostic-proof.json', validate_proof(proof))


def write_observations(directory, proof, fatal):
    # Native dependencies can swallow a policy exception, not its audit marker.
    if fatal:
        raise DiagnosticFailure('POLICY_FAILED', 68)
    _write(directory, proof)


def _set_head_export(network, Detect):
    heads = [module for module in network.modules() if isinstance(module, Detect)]
    if len(heads) != 1 or heads[0].nc != 2 or getattr(heads[0], 'end2end', False):
        raise ValueError('fixed detection head invalid')
    for head in heads: head.export, head.format, head.dynamic = True, 'onnx', False


def _ort_session(ort, graph_bytes):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session = ort.InferenceSession(graph_bytes, sess_options=options, providers=['CPUExecutionProvider'])
    session.disable_fallback()
    if session.get_providers() != ['CPUExecutionProvider']:
        raise RuntimeError('CPU provider mismatch')
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if (len(inputs) != 1 or len(outputs) != 1
            or (inputs[0].name, inputs[0].type, inputs[0].shape) != ('images', 'tensor(float)', [1, 3, 640, 640])
            or (outputs[0].name, outputs[0].type, outputs[0].shape) != ('output0', 'tensor(float)', [1, 6, 8400])):
        raise RuntimeError('fixed ORT interface mismatch')
    return session


def _raw_array(raw, np):
    if len(raw) != 201600: raise ValueError('fixed handoff tensor size invalid')
    value = np.frombuffer(raw, dtype='<f4').reshape((1, 6, 8400)).copy()
    if not np.isfinite(value).all(): raise ValueError('fixed handoff tensor nonfinite')
    return value


def _array_bytes(value, np):
    if value.shape != (1, 6, 8400) or value.dtype != np.float32 or not np.isfinite(value).all():
        raise DiagnosticFailure('RUNTIME_FAILED', 72)
    raw = value.astype('<f4', copy=False).tobytes(order='C')
    if len(raw) != 201600: raise DiagnosticFailure('RUNTIME_FAILED', 72)
    return raw


def _compare_one(metrics_module, typed_compare, mismatch_type, np, reference, actual, name):
    # Save grouped statistics atomically, while retaining the production typed
    # shape/dtype/finite/tolerance comparator as the validity authority. Only a
    # fully computed numeric mismatch is retained as observations.
    groups = metrics_module.measure_arrays(np, reference, actual)
    try:
        typed_compare(np, reference, actual, name)
    except mismatch_type as exc:
        if getattr(exc, 'diagnostic', None) not in {'compare_tolerance', 'compare_nonfinite'}:
            raise
    return groups


def _set_failure(proof, code):
    proof['status'] = 'failed'; proof['failure_code'] = code


def probe_child(job_id, run_id):
    # Strict guard is before any app/native runtime imports.
    guard()
    from .run_files import run_directory, read_json, fingerprint
    from .export_contract import ExportInput, INPUT_SHAPE, TENSOR_NAMES, tensor_bytes
    from .export_inputs import verify_input, copy_input
    from .training_runtime import prepare_environment, initialize, TrainingPolicyError
    from .ml_privacy import load_ort
    from .export_runtime import read_model_bytes, guard_graph, compare_arrays
    from .export_errors import ExportGraphError
    from .export_backend_handoff import (
        verify as verify_handoff, copy_to as copy_handoff,
        _read_fixed_file, _write_exclusive,
    )
    import stat

    directory = run_directory(job_id, run_id)
    proof = empty_proof('A')
    try:
        raw_input = read_json(directory / 'input.json', 1024 * 1024)
        arm, source_raw, backend_source = _model_input(raw_input, job_id, run_id)
        proof = empty_proof(arm)
        source_export = ExportInput.model_validate(source_raw)
        if (source_export.kind != 'export_onnx' or str(source_export.job_id) != job_id
                or str(source_export.run_id) != run_id):
            raise ValueError('source export identity invalid')
        frozen = verify_input(source_export.input.model_dump(mode='json'))
        source = copy_input(frozen, directory)
        if source.is_symlink() or not stat.S_ISREG(source.lstat().st_mode): raise ValueError('source checkpoint type invalid')
        source_before = fingerprint(source)

        copied_handoff = None
        current_outputs = None
        current_raws = None
        if arm == 'D':
            verify_handoff(backend_source, frozen)
            copied_handoff = copy_handoff(backend_source, frozen, directory)
            current_raws = {name: _read_fixed_file(copied_handoff[f'current-{name}.f32'].parent, f'current-{name}.f32') for name in SAMPLES}
            graph_bytes = _read_fixed_file(copied_handoff['model.onnx'].parent, 'model.onnx')

        prepare_environment(directory)
        torch, torchvision, YOLO, DetectionModel, fail, fatal, loads = initialize(directory, {source})
        from .export_backend_handoff import precision_snapshot as get_precision
        try:
            precision_start = get_precision(torch)
        except Exception as exc:
            raise TrainingPolicyError('PRECISION_CONTROLS_UNAVAILABLE') from exc
        if arm == 'A':
            if precision_start['mkldnn_enabled'] is not True: raise TrainingPolicyError('MKLDNN_NOT_ENABLED')
            proof['precision'] = precision_start
        else:
            a_precision = backend_source['precision']
            precision_start = get_precision(torch)
            if precision_start['mkldnn_enabled'] is not True or any(precision_start[k] != a_precision[k] for k in ('global', 'backend', 'conv', 'matmul')):
                raise TrainingPolicyError('PRECISION_PROFILE_CHANGED')
            # Exactly one A/D perturbation; do not use mkldnn.flags() context.
            torch.backends.mkldnn.enabled = False
            precision_after_toggle = get_precision(torch)
            expected_precision = {**a_precision, 'mkldnn_enabled': False}
            if precision_after_toggle != expected_precision: raise TrainingPolicyError('PRECISION_TOGGLE_CHANGED_OTHER_SETTING')
            proof['precision'] = precision_after_toggle

        ort = load_ort()
        import onnx
        import numpy as np
        import ultralytics
        if arm == 'D':
            current_outputs = {name: _raw_array(current_raws[name], np) for name in SAMPLES}
        if (torch.__version__ != '2.15.0+cpu' or torchvision.__version__ != '0.29.2+cpu'
                or ultralytics.__version__ != '8.4.202' or onnx.__version__ != '1.23.2'
                or ort.__version__ != '1.31.1' or torch.version.cuda is not None
                or torch.version.hip is not None or torch.cuda.is_available()):
            raise TrainingPolicyError('RUNTIME_VERSION_MISMATCH')
        # initialize() already installs the fixed 2 intra / 1 inter thread limits.
        model = YOLO(str(source), task='detect')
        if not isinstance(model.model, DetectionModel) or model.task != 'detect': raise TrainingPolicyError('SOURCE_STRUCTURE_INVALID')
        classes = source_export.input.source_metadata.classes
        actual_classes = [model.names[index] for index in range(len(model.names))]
        if classes != actual_classes or classes is None or len(classes) != 2: raise TrainingPolicyError('SOURCE_CLASSES_CHANGED')
        if model.ckpt.get('optimizer') is not None or model.ckpt.get('ema') is not None or model.ckpt.get('epoch') != -1:
            raise TrainingPolicyError('SOURCE_CHECKPOINT_NOT_FINALIZED')
        network = model.model.cpu().float().eval()
        for parameter in network.parameters():
            parameter.requires_grad_(False)
            if not torch.isfinite(parameter).all(): raise TrainingPolicyError('SOURCE_NONFINITE')
        from ultralytics.nn.modules.head import Detect
        _set_head_export(network, Detect)
        try:
            precision_at_compare = get_precision(torch)
        except Exception as exc:
            raise TrainingPolicyError('PRECISION_CONTROLS_UNAVAILABLE') from exc
        if precision_at_compare != proof['precision']:
            raise TrainingPolicyError('PRECISION_CHANGED_BEFORE_COMPARISON')
        proof['checks']['source_bn'] = any(isinstance(module, torch.nn.BatchNorm2d) for module in network.modules())
        network_before = _snapshot_network(network)
        tensors = {name: np.frombuffer(tensor_bytes(name), dtype='<f4').reshape(INPUT_SHAPE).copy() for name in TENSOR_NAMES}
        if arm == 'A':
            references = _outputs(torch, network, tensors)
            repeated = _outputs(torch, network, tensors)
            proof['checks']['pt_repeat_pre'] = _same_outputs(np, references, repeated)
            output_records = {}
            for name in SAMPLES:
                raw = _array_bytes(references[name], np)
                path = directory / f'current-{name}.f32'
                _write_exclusive(path, raw)
                output_records[path.name] = __import__('hashlib').sha256(raw).hexdigest()
            candidate = directory / 'model.onnx'
            if candidate.exists() or candidate.is_symlink(): raise ValueError('export target already exists')
            try:
                torch.onnx.export(network, torch.from_numpy(tensors['zeros']), str(candidate),
                    export_params=True, opset_version=18, do_constant_folding=True,
                    input_names=['images'], output_names=['output0'], dynamic_axes=None,
                    dynamo=False, external_data=False, verbose=False)
            except Exception as exc:
                raise DiagnosticFailure('RUNTIME_FAILED', 72) from exc
            try:
                graph_bytes = read_model_bytes(candidate)
                model_proto = onnx.load_model_from_string(graph_bytes)
                from .export_runtime import guard_graph
                guard_graph(model_proto, onnx, classes)
                onnx.checker.check_model(graph_bytes, full_check=True)
            except Exception as exc:
                raise DiagnosticFailure('GRAPH_INVALID', 74) from exc
            proof['checks']['onnx_batchnorm'] = _contains_batchnorm(model_proto)
            shared_outputs = references
        else:
            assert current_outputs is not None and copied_handoff is not None
            try:
                model_proto = onnx.load_model_from_string(graph_bytes)
                from .export_runtime import guard_graph
                guard_graph(model_proto, onnx, classes)
                onnx.checker.check_model(graph_bytes, full_check=True)
            except Exception as exc:
                raise DiagnosticFailure('GRAPH_INVALID', 74) from exc
            proof['checks']['onnx_batchnorm'] = _contains_batchnorm(model_proto)
            shared_outputs = current_outputs
            references = _outputs(torch, network, tensors)
            repeated = _outputs(torch, network, tensors)
            proof['checks']['pt_repeat_pre'] = _same_outputs(np, references, repeated)
            disabled_outputs = references
            for name in SAMPLES:
                proof['metrics']['current_disabled'][name] = _compare_one(metrics, compare_arrays, ExportGraphError, np, shared_outputs[name], disabled_outputs[name], name)
            proof['checks']['backend_reference_match'] = all(metrics.matches(proof['metrics']['current_disabled'][name]) for name in SAMPLES)
            output_records = None

        try:
            session = _ort_session(ort, graph_bytes)
        except Exception as exc:
            raise DiagnosticFailure('RUNTIME_FAILED', 72) from exc
        runtime_error = False
        for name in SAMPLES:
            try:
                values = session.run(['output0'], {'images': tensors[name]})
                if len(values) != 1: raise RuntimeError('ORT output count invalid')
                if arm == 'A':
                    current_ort = _compare_one(metrics, compare_arrays, ExportGraphError, np, references[name], values[0], name)
                    proof['metrics']['current_ort'][name] = current_ort
                else:
                    current_ort = _compare_one(metrics, compare_arrays, ExportGraphError, np, shared_outputs[name], values[0], name)
                    disabled_ort = _compare_one(metrics, compare_arrays, ExportGraphError, np, disabled_outputs[name], values[0], name)
                    proof['metrics']['current_ort'][name] = current_ort
                    proof['metrics']['disabled_ort'][name] = disabled_ort
                proof['checks']['reference_ort_match'][name] = metrics.matches(proof['metrics']['current_ort'][name])
            except Exception:
                # A failed ORT invocation/schema is incomplete, not an observed numeric mismatch.
                runtime_error = True
                break

        proof['checks']['network_unchanged'] = _network_unchanged(torch, network, network_before)
        if arm == 'D':
            post = _outputs(torch, network, tensors)
            proof['checks']['pt_repeat_post'] = _same_outputs(np, disabled_outputs, post)
        else:
            post = _outputs(torch, network, tensors)
            proof['checks']['pt_repeat_post'] = _same_outputs(np, references, post)

        try:
            source_ok = fingerprint(source) == source_before
        except Exception:
            source_ok = False
        try:
            verify_input(frozen)
        except Exception:
            source_ok = False
        proof['checks']['source_unchanged'] = source_ok
        if arm == 'A':
            try:
                from .export_backend_handoff import _read_fixed_file
                proof['checks']['shared_input_unchanged'] = all(
                    __import__('hashlib').sha256(_read_fixed_file(directory, name)).hexdigest() == digest
                    for name, digest in output_records.items()) and __import__('hashlib').sha256(_read_fixed_file(directory, 'model.onnx')).hexdigest() == __import__('hashlib').sha256(graph_bytes).hexdigest()
            except Exception:
                proof['checks']['shared_input_unchanged'] = False
        else:
            try:
                verify_handoff(backend_source, frozen)
                proof['checks']['shared_input_unchanged'] = all(
                    __import__('hashlib').sha256(_read_fixed_file(path.parent, name)).hexdigest() == backend_source['files'][name]['sha256']
                    for name, path in copied_handoff.items())
            except Exception:
                proof['checks']['shared_input_unchanged'] = False

        try:
            precision_end = get_precision(torch)
        except Exception as exc:
            raise TrainingPolicyError('PRECISION_CONTROLS_UNAVAILABLE') from exc
        if precision_end != proof['precision']:
            raise TrainingPolicyError('PRECISION_CHANGED_DURING_COMPARISON')
        if fatal: raise TrainingPolicyError('RUNTIME_POLICY_FATAL')
        if not proof['checks']['source_unchanged'] or not proof['checks']['shared_input_unchanged']:
            _set_failure(proof, 'SOURCE_CHANGED')
        elif not proof['checks']['network_unchanged']:
            _set_failure(proof, 'SOURCE_CHANGED')
        elif runtime_error:
            _set_failure(proof, 'RUNTIME_FAILED')
        elif not proof['checks']['pt_repeat_pre'] or not proof['checks']['pt_repeat_post']:
            _set_failure(proof, 'PT_REPEAT_MISMATCH')
        elif arm == 'D' and not proof['checks']['backend_reference_match']:
            _set_failure(proof, 'BACKEND_MISMATCH')
        elif any(value is not True for value in proof['checks']['reference_ort_match'].values()):
            _set_failure(proof, 'ONNX_MISMATCH')
        elif not metrics.complete(proof['metrics'], arm) or any(
                not metrics.matches(groups) for block in proof['metrics'].values() if block is not None for groups in block.values()):
            _set_failure(proof, 'ONNX_MISMATCH')
        else:
            proof['status'] = 'passed'; proof['failure_code'] = None
        write_observations(directory, proof, fatal)
        if proof['status'] == 'passed': return 0
        if proof['failure_code'] == 'SOURCE_CHANGED': return 68
        if proof['failure_code'] == 'RUNTIME_FAILED': return 72
        return 74
    except DiagnosticFailure as exc:
        _set_failure(proof, exc.code); _write(directory, proof); return exc.exit_code
    except TrainingPolicyError:
        _set_failure(proof, 'POLICY_FAILED'); _write(directory, proof); return 68
    except (ValueError, OSError, TypeError):
        _set_failure(proof, 'SOURCE_INVALID'); _write(directory, proof); return 65
    except Exception:
        _set_failure(proof, 'UNKNOWN'); _write(directory, proof); return 72
