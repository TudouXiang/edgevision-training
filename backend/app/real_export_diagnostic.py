"""Fixed, one-arm diagnostic for real CPU ONNX export behavior.

No ML imports occur until the strict container/network/root guard passes. This
module is not an HTTP job or product exporter and never publishes artifacts.
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
ARMS = ('A', 'B', 'C')
SAMPLES = ('zeros', 'gradient', 'pattern')
FAILURE_CODES = ('POLICY_FAILED', 'SOURCE_INVALID', 'GRAPH_INVALID', 'PT_REPEAT_MISMATCH', 'FUSED_MISMATCH', 'ONNX_MISMATCH', 'SOURCE_CHANGED', 'RUNTIME_FAILED', 'UNKNOWN')


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
    return {'fuse': arm == 'C', 'constant_folding': arm != 'B'}


class DiagnosticFailure(Exception):
    def __init__(self, code, exit_code):
        if type(code) is not str or code not in FAILURE_CODES or type(exit_code) is not int:
            raise ValueError('invalid diagnostic failure')
        self.code, self.exit_code = code, exit_code
        super().__init__('real export diagnostic failed')


def empty_proof(arm):
    arm_settings(arm)
    return {'schema_version': 2, 'metrics': metrics.empty_matrix(arm), 'arm': arm, 'status': 'failed',
        'checks': {'source_bn': None, 'onnx_batchnorm': None,
            'pt_repeat_pre': None, 'pt_repeat_post': None, 'source_unchanged': None,
            'network_unchanged': None,
            'reference_ort_match': {name: None for name in SAMPLES},
            'fused_reference_match': None if arm != 'C' else None},
        'failure_code': 'UNKNOWN'}


def validate_proof(value):
    if type(value) is not dict or set(value) != {'schema_version', 'arm', 'status', 'checks', 'failure_code', 'metrics'}:
        raise ValueError('diagnostic proof schema invalid')
    if type(value['schema_version']) is not int or value['schema_version'] != 2:
        raise ValueError('diagnostic proof version invalid')
    settings = arm_settings(value['arm'])
    if value['status'] not in ('passed', 'failed'):
        raise ValueError('diagnostic proof status invalid')
    if value['failure_code'] is not None and (type(value['failure_code']) is not str or value['failure_code'] not in FAILURE_CODES):
        raise ValueError('diagnostic failure code invalid')
    checks = value['checks']
    expected = {'source_bn', 'onnx_batchnorm', 'pt_repeat_pre', 'pt_repeat_post', 'source_unchanged', 'network_unchanged', 'reference_ort_match', 'fused_reference_match'}
    if type(checks) is not dict or set(checks) != expected:
        raise ValueError('diagnostic checks invalid')
    for key in ('source_bn', 'onnx_batchnorm', 'pt_repeat_pre', 'pt_repeat_post', 'source_unchanged', 'network_unchanged'):
        if checks[key] is not None and type(checks[key]) is not bool:
            raise ValueError('diagnostic check type invalid')
    samples = checks['reference_ort_match']
    if type(samples) is not dict or set(samples) != set(SAMPLES) or any(x is not None and type(x) is not bool for x in samples.values()):
        raise ValueError('diagnostic sample checks invalid')
    fused = checks['fused_reference_match']
    if settings['fuse']:
        if fused is not None and type(fused) is not bool:
            raise ValueError('diagnostic fused check invalid')
    elif fused is not None:
        raise ValueError('fused check not applicable')
    if value['status'] == 'passed':
        if type(checks['source_bn']) is not bool or type(checks['onnx_batchnorm']) is not bool:
            raise ValueError('completed BN observations are required')
            # BN presence is descriptive evidence; fused exports may legitimately have none.
        required = [checks[k] for k in ('pt_repeat_pre', 'pt_repeat_post', 'source_unchanged', 'network_unchanged')]
        required.extend(samples[name] for name in SAMPLES)
        if settings['fuse']:
            required.append(fused)
        if any(type(x) is not bool for x in required) or checks['source_unchanged'] is not True or any(x is not True for x in required) or value['failure_code'] is not None:
            raise ValueError('incomplete or failed proof cannot pass')
    elif type(value['failure_code']) is not str:
        raise ValueError('failed proof needs a closed failure code')
    metrics.validate_matrix(value['metrics'], value['arm'], checks)
    if value['status'] == 'passed' and not metrics.complete(value['metrics'], value['arm']):
        raise ValueError('numeric observations incomplete')
    return value


def _model_input(value, job_id, run_id):
    if type(value) is not dict or set(value) != {'schema_version', 'job_id', 'run_id', 'kind', 'arm', 'source_export'}:
        raise ValueError('diagnostic input schema invalid')
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['kind'] != 'real_export_diagnostic':
        raise ValueError('diagnostic input identity invalid')
    if value['job_id'] != job_id or value['run_id'] != run_id:
        raise ValueError('diagnostic run binding invalid')
    arm_settings(value['arm'])
    if type(value['source_export']) is not dict:
        raise ValueError('frozen export input required')
    return value['arm'], value['source_export']


def _outputs(torch, np, network, tensors, classes):
    values = {}
    with torch.inference_mode():
        for name in SAMPLES:
            result = network(torch.from_numpy(tensors[name]))
            if not isinstance(result, torch.Tensor) or tuple(result.shape) != (1, 4 + len(classes), 8400):
                raise ValueError('fixed PT output schema invalid')
            values[name] = result.detach().cpu().numpy().copy()
    return values


def _snapshot_network(network):
    """Clone state tensors participating in the selected export arm."""
    result = {}
    for category, values in (('parameter', network.named_parameters()), ('buffer', network.named_buffers())):
        for name, value in values:
            key = f'{category}:{name}'
            if key in result:
                raise ValueError('duplicate network state name')
            tensor = value.detach().cpu().clone()
            result[key] = (str(tensor.dtype), tuple(tensor.shape), tensor)
    return result


def _network_unchanged(torch, network, before):
    after = _snapshot_network(network)
    if set(after) != set(before):
        return False
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
    """Retain all fixed comparisons after mismatches, but not runtime failures."""
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
    from google.protobuf.message import Message
    stack = [model_proto]
    while stack:
        message = stack.pop()
        if getattr(message, 'op_type', None) == 'BatchNormalization':
            return True
        for field, value in message.ListFields():
            if field.message_type is not None:
                stack.extend(value if field.is_repeated else [value])
    return False


def _write(directory, proof):
    from .run_files import atomic_json
    atomic_json(directory / 'diagnostic-proof.json', validate_proof(proof))


def write_observations(directory, proof, fatal):
    # A native dependency may catch a policy exception; its persistent audit
    # marker remains authoritative and must prevent complete observations.
    if fatal:
        raise DiagnosticFailure('POLICY_FAILED', 68)
    _write(directory, proof)


def probe_child(job_id, run_id):
    # Container/network/profile checks precede all app and native runtime imports.
    guard()
    from .run_files import run_directory, read_json, atomic_json, fingerprint
    from .export_contract import ExportInput, INPUT_SHAPE, TENSOR_NAMES, tensor_bytes
    from .export_inputs import verify_input, copy_input
    from .training_runtime import prepare_environment, initialize, TrainingPolicyError
    from .ml_privacy import load_ort
    from .export_runtime import read_model_bytes, guard_graph, compare_arrays
    from .export_errors import ExportGraphError
    import copy
    import stat

    directory = run_directory(job_id, run_id)
    proof = empty_proof('A')
    try:
        raw_input = read_json(directory / 'input.json', 1024 * 1024)
        arm, export_raw = _model_input(raw_input, job_id, run_id)
        proof = empty_proof(arm)
        export_input = ExportInput.model_validate(export_raw)
        if export_input.kind != 'export_onnx':
            raise ValueError('source export required')
        frozen = verify_input(export_input.input.model_dump(mode='json'))
        source = copy_input(frozen, directory)
        if source.is_symlink() or not stat.S_ISREG(source.lstat().st_mode):
            raise ValueError('frozen source file rejected')
        source_before = fingerprint(source)

        prepare_environment(directory)
        torch, torchvision, YOLO, DetectionModel, fail, fatal, loads = initialize(directory, {source})
        ort = load_ort()
        import onnx
        import numpy as np
        import ultralytics
        if (torch.__version__ != '2.15.0+cpu' or torchvision.__version__ != '0.29.2+cpu'
                or ultralytics.__version__ != '8.4.202' or onnx.__version__ != '1.23.2'
                or ort.__version__ != '1.31.1' or torch.version.cuda is not None
                or torch.version.hip is not None or torch.cuda.is_available()):
            raise TrainingPolicyError('RUNTIME_VERSION_MISMATCH')
        # initialize() applies the fixed 2 intra / 1 inter thread limits.
        before = fingerprint(source)
        model = YOLO(str(source), task='detect')
        if not isinstance(model.model, DetectionModel) or model.task != 'detect':
            raise TrainingPolicyError('SOURCE_STRUCTURE_INVALID')
        classes = export_input.input.source_metadata.classes
        actual_classes = [model.names[index] for index in range(len(model.names))]
        if classes != actual_classes or not 1 <= len(classes) <= 1000:
            raise TrainingPolicyError('SOURCE_CLASSES_CHANGED')
        if model.ckpt.get('optimizer') is not None or model.ckpt.get('ema') is not None or model.ckpt.get('epoch') != -1:
            raise TrainingPolicyError('SOURCE_CHECKPOINT_NOT_FINALIZED')
        original = model.model.cpu().float().eval()
        for parameter in original.parameters():
            parameter.requires_grad_(False)
            if not torch.isfinite(parameter).all():
                raise TrainingPolicyError('SOURCE_NONFINITE')
        from ultralytics.nn.modules.head import Detect
        heads = [module for module in original.modules() if isinstance(module, Detect)]
        if len(heads) != 1 or heads[0].nc != len(classes):
            raise TrainingPolicyError('SOURCE_HEAD_INVALID')
        if getattr(heads[0], 'end2end', False):
            raise TrainingPolicyError('SOURCE_HEAD_INVALID')
        proof['checks']['source_bn'] = any(isinstance(module, torch.nn.BatchNorm2d) for module in original.modules())
        for head in heads:
            head.export, head.format, head.dynamic = True, 'onnx', False
        tensors = {name: np.frombuffer(tensor_bytes(name), dtype='<f4').reshape(INPUT_SHAPE).copy() for name in TENSOR_NAMES}
        references = _outputs(torch, np, original, tensors, classes)
        repeated = _outputs(torch, np, original, tensors, classes)
        proof['checks']['pt_repeat_pre'] = all(np.array_equal(references[n], repeated[n], equal_nan=True) for n in SAMPLES)

        settings = arm_settings(arm)
        export_network = original
        fused_outputs = None
        if settings['fuse']:
            export_network = copy.deepcopy(original)
            export_network.fuse()
            export_network.eval()
            for parameter in export_network.parameters(): parameter.requires_grad_(False)
            for head in (m for m in export_network.modules() if isinstance(m, Detect)):
                head.export, head.format, head.dynamic = True, 'onnx', False
            fused_outputs = _outputs(torch, np, export_network, tensors, classes)
            fused = True
            for name in SAMPLES:
                statistics, matched = compare_observation(
                    lambda: metrics.measure_arrays(np, references[name], fused_outputs[name]),
                    lambda: compare_arrays(np, references[name], fused_outputs[name], name), ExportGraphError)
                proof['metrics']['original_fused'][name] = statistics
                fused = fused and matched
            proof['checks']['fused_reference_match'] = fused

        # Snapshot the actual network handed to torch.onnx.export, not the original
        # reference network when arm C exports its explicit fused copy.
        network_before = _snapshot_network(export_network)

        candidate = directory / 'model.onnx'
        try:
            torch.onnx.export(export_network, torch.from_numpy(tensors['zeros']), str(candidate),
                export_params=True, opset_version=18, do_constant_folding=settings['constant_folding'],
                input_names=['images'], output_names=['output0'], dynamic_axes=None,
                dynamo=False, external_data=False, verbose=False)
        except Exception as exc:
            raise DiagnosticFailure('RUNTIME_FAILED', 72) from exc
        try:
            graph_bytes = read_model_bytes(candidate)
            model_proto = onnx.load_model_from_string(graph_bytes)
            guard_graph(model_proto, onnx, classes)
            onnx.checker.check_model(graph_bytes, full_check=True)
        except Exception as exc:
            raise DiagnosticFailure('GRAPH_INVALID', 74) from exc
        proof['checks']['onnx_batchnorm'] = _contains_batchnorm(model_proto)
        options = ort.SessionOptions(); options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(graph_bytes, sess_options=options, providers=['CPUExecutionProvider'])
        session.disable_fallback()
        if session.get_providers() != ['CPUExecutionProvider']:
            raise TrainingPolicyError('ORT_PROVIDER_MISMATCH')
        ins, outs = session.get_inputs(), session.get_outputs()
        expected_out = [1, 4 + len(classes), 8400]
        if len(ins) != 1 or len(outs) != 1 or (ins[0].name, ins[0].type, ins[0].shape) != ('images', 'tensor(float)', list(INPUT_SHAPE)) or (outs[0].name, outs[0].type, outs[0].shape) != ('output0', 'tensor(float)', expected_out):
            raise TrainingPolicyError('ORT_INTERFACE_MISMATCH')
        # Complete the fixed three-input matrix even after an individual mismatch/error.
        def compare_one(name):
            outputs = session.run(['output0'], {'images': tensors[name]})
            if len(outputs) != 1: raise ValueError('ORT output schema invalid')
            statistics, matched = compare_observation(
                lambda: (metrics.measure_arrays(np, references[name], outputs[0]),
                         metrics.measure_arrays(np, fused_outputs[name], outputs[0]) if arm == 'C' else None),
                lambda: compare_arrays(np, references[name], outputs[0], name), ExportGraphError)
            proof['metrics']['original_ort'][name] = statistics[0]
            if arm == 'C': proof['metrics']['fused_ort'][name] = statistics[1]
            return matched
        # Comparison mismatches are false but do not short-circuit the other two
        # inputs. Runtime/protocol errors stay null and preserve only the prefix.
        matches, incomplete_runtime = collect_samples(compare_one, ExportGraphError)
        proof['checks']['reference_ort_match'] = matches
        proof['checks']['network_unchanged'] = _network_unchanged(torch, export_network, network_before)
        post = _outputs(torch, np, original, tensors, classes)
        proof['checks']['pt_repeat_post'] = all(np.array_equal(references[n], post[n], equal_nan=True) for n in SAMPLES)
        proof['checks']['source_unchanged'] = fingerprint(source) == source_before
        verify_input(frozen)

        checks = proof['checks']
        all_ok = (checks['pt_repeat_pre'] is True and checks['pt_repeat_post'] is True
                  and checks['source_unchanged'] is True and checks['network_unchanged'] is True
                  and type(checks['source_bn']) is bool and type(checks['onnx_batchnorm']) is bool
                  and all(checks['reference_ort_match'][name] is True for name in SAMPLES)
                  and (arm != 'C' or checks['fused_reference_match'] is True))
        if all_ok:
            proof['status'] = 'passed'; proof['failure_code'] = None
        elif incomplete_runtime:
            proof['status'] = 'failed'; proof['failure_code'] = 'RUNTIME_FAILED'
        else:
            proof['status'] = 'failed'
            if checks['source_unchanged'] is not True: proof['failure_code'] = 'SOURCE_CHANGED'
            elif checks['pt_repeat_pre'] is not True or checks['pt_repeat_post'] is not True: proof['failure_code'] = 'PT_REPEAT_MISMATCH'
            elif arm == 'C' and checks['fused_reference_match'] is not True: proof['failure_code'] = 'FUSED_MISMATCH'
            elif any(checks['reference_ort_match'][name] is not True for name in SAMPLES): proof['failure_code'] = 'ONNX_MISMATCH'
            else: proof['failure_code'] = 'UNKNOWN'
        if checks['network_unchanged'] is not True:
            proof['status'] = 'failed'; proof['failure_code'] = 'SOURCE_CHANGED'
        write_observations(directory, proof, fatal)
        if proof['failure_code'] == 'SOURCE_CHANGED':
            return 68
        if proof['failure_code'] == 'RUNTIME_FAILED':
            return 72
        return 0 if proof['status'] == 'passed' else 74
    except DiagnosticFailure as exc:
        proof['status'] = 'failed'; proof['failure_code'] = exc.code
        _write(directory, proof)
        return exc.exit_code
    except TrainingPolicyError:
        proof['status'] = 'failed'; proof['failure_code'] = 'POLICY_FAILED'
        _write(directory, proof)
        return 68
    except (ValueError, OSError, TypeError):
        proof['status'] = 'failed'; proof['failure_code'] = 'SOURCE_INVALID'
        _write(directory, proof)
        return 65
    except Exception:
        proof['status'] = 'failed'; proof['failure_code'] = 'UNKNOWN'
        _write(directory, proof)
        return 72
