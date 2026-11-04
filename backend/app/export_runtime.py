"""Fixed native export adapter. Imported only in a managed child after GO.

This module itself imports no ML. Runtime invocation requires a separately
reviewed network-isolated execution boundary; Python hooks are not a sandbox.
"""
from hashlib import sha256
import os
from pathlib import Path
import stat
from .export_contract import MAX_ONNX_BYTES, INPUT_SHAPE, TENSOR_NAMES, tensor_bytes
from .run_files import fingerprint
from .schemas import ExportValidation


def read_model_bytes(path):
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= MAX_ONNX_BYTES:
        raise ValueError('model size or type rejected before parsing')
    with path.open('rb') as source:
        raw = source.read(MAX_ONNX_BYTES + 1)
    if len(raw) != details.st_size or len(raw) > MAX_ONNX_BYTES:
        raise ValueError('model changed or exceeds parse bound')
    return raw


def guard_graph(model, onnx, classes):
    """Recursively visit protobuf messages, including nested graph attributes."""
    if model.ir_version != 8 or model.functions or model.training_info or model.metadata_props:
        raise ValueError('unsupported ONNX model contract')
    if [(item.domain, item.version) for item in model.opset_import] != [('', 18)]:
        raise ValueError('unsupported ONNX opset')
    if len(model.graph.input) != 1 or len(model.graph.output) != 1:
        raise ValueError('unexpected graph interface')
    for value, name, shape in ((model.graph.input[0], 'images', INPUT_SHAPE), (model.graph.output[0], 'output0', (1, 4 + len(classes), 8400))):
        if value.name != name or value.type.WhichOneof('value') != 'tensor_type':
            raise ValueError('unexpected graph interface type')
        tensor = value.type.tensor_type
        if tensor.elem_type != onnx.TensorProto.FLOAT or any(d.WhichOneof('value') != 'dim_value' for d in tensor.shape.dim) or tuple(d.dim_value for d in tensor.shape.dim) != shape:
            raise ValueError('unexpected graph shape or dtype')
    stack, count = [(model, 0)], 0
    while stack:
        message, depth = stack.pop()
        count += 1
        if depth > 64 or count > 200000:
            raise ValueError('graph complexity limit exceeded')
        kind = message.DESCRIPTOR.name
        if kind in {'SparseTensorProto', 'FunctionProto', 'TrainingInfoProto'}:
            raise ValueError('sparse, local function or training graph rejected')
        if kind == 'TensorProto' and (message.external_data or message.data_location != onnx.TensorProto.DEFAULT):
            raise ValueError('external tensor rejected')
        if kind == 'NodeProto':
            if message.domain or not onnx.defs.has(message.op_type, 18, ''):
                raise ValueError('custom or unknown operator rejected')
        if kind == 'GraphProto' and message.sparse_initializer:
            raise ValueError('sparse graph rejected')
        for field, value in message.ListFields():
            if field.message_type is not None:
                values = value if field.is_repeated else [value]
                stack.extend((item, depth + 1) for item in values)


def compare_arrays(np, reference, actual, name):
    if reference.shape != actual.shape or reference.dtype != np.float32 or actual.dtype != np.float32:
        raise ValueError('raw output shape or dtype mismatch')
    if not np.isfinite(reference).all() or not np.isfinite(actual).all():
        raise ValueError('raw output contains nonfinite values')
    # Float64 arithmetic prevents overflow/cancellation in the validator itself.
    delta = np.abs(actual.astype(np.float64) - reference.astype(np.float64))
    allowed = 1e-4 + 1e-4 * np.abs(reference.astype(np.float64))
    if not np.all(delta <= allowed):
        raise ValueError('fixed raw tensor equivalence threshold exceeded')
    return {'name': name, 'input_sha256': sha256(tensor_bytes(name)).hexdigest(),
        'pt_sha256': sha256(reference.astype('<f4', copy=False).tobytes(order='C')).hexdigest(),
        'ort_sha256': sha256(actual.astype('<f4', copy=False).tobytes(order='C')).hexdigest(),
        'max_absolute_error': float(delta.max()), 'max_tolerance_ratio': float((delta / allowed).max()),
        'elements': int(reference.size), 'passed': True}


def export_and_validate(root, source, classes, *, job_id, run_id, input_sha256, source_sha256):
    from .training_runtime import prepare_environment, initialize
    prepare_environment(root)
    torch, torchvision, YOLO, DetectionModel, fail, fatal, loads = initialize(root, {source})
    # ORT must only enter through this pre-import privacy gate, before any exporter.
    from .ml_privacy import load_ort
    ort = load_ort()
    import onnx
    import numpy as np
    import ultralytics
    if onnx.__version__ != '1.23.2' or ort.__version__ != '1.31.1':
        fail('DELIVERY_VERSION_MISMATCH')
    before = fingerprint(source)
    if before[1] != source_sha256: fail('SOURCE_CHANGED')
    model = YOLO(str(source), task='detect')
    if not isinstance(model.model, DetectionModel) or model.task != 'detect': fail('SOURCE_STRUCTURE_INVALID')
    actual_classes = [model.names[index] for index in range(len(model.names))]
    if classes is None: classes = actual_classes  # Only the fixed official-asset probe uses this.
    if classes != actual_classes or not 1 <= len(classes) <= 1000: fail('SOURCE_CLASSES_CHANGED')
    if model.ckpt.get('optimizer') is not None or model.ckpt.get('ema') is not None or model.ckpt.get('epoch') != -1:
        fail('SOURCE_CHECKPOINT_NOT_FINALIZED')
    network = model.model.cpu().float().eval()
    for parameter in network.parameters():
        parameter.requires_grad_(False)
        if not torch.isfinite(parameter).all(): fail('SOURCE_NONFINITE')
    from ultralytics.nn.modules.head import Detect
    heads = [module for module in network.modules() if isinstance(module, Detect)]
    if len(heads) != 1 or heads[0].nc != len(classes): fail('SOURCE_HEAD_INVALID')
    head = heads[0]
    head.export, head.format, head.dynamic = True, 'onnx', False
    if getattr(head, 'end2end', False): fail('SOURCE_HEAD_INVALID')
    inputs = {name: np.frombuffer(tensor_bytes(name), dtype='<f4').reshape(INPUT_SHAPE).copy() for name in TENSOR_NAMES}
    references = {}
    with torch.inference_mode():
        for name in TENSOR_NAMES:
            value = network(torch.from_numpy(inputs[name]))
            if not isinstance(value, torch.Tensor) or tuple(value.shape) != (1, 4 + len(classes), 8400): fail('PT_OUTPUT_SCHEMA_INVALID')
            references[name] = value.cpu().numpy().copy()
    candidate = root / 'model.onnx'
    # Legacy exporter emits the original graph; no upstream metadata, simplifier,
    # IR rewrite, external-data conversion, auto-install, or fallback is invoked.
    torch.onnx.export(network, torch.from_numpy(inputs['zeros']), str(candidate),
        export_params=True, opset_version=18, do_constant_folding=True,
        input_names=['images'], output_names=['output0'], dynamic_axes=None,
        dynamo=False, external_data=False, verbose=False)
    raw = read_model_bytes(candidate)  # Bound BEFORE any protobuf parsing.
    model_proto = onnx.load_model_from_string(raw)
    guard_graph(model_proto, onnx, classes)
    onnx.checker.check_model(raw, full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session = ort.InferenceSession(raw, sess_options=options, providers=['CPUExecutionProvider'])
    session.disable_fallback()
    if session.get_providers() != ['CPUExecutionProvider']: fail('ORT_PROVIDER_MISMATCH')
    ins, outs = session.get_inputs(), session.get_outputs()
    if len(ins) != 1 or len(outs) != 1 or (ins[0].name, ins[0].type, ins[0].shape) != ('images', 'tensor(float)', list(INPUT_SHAPE)) or (outs[0].name, outs[0].type, outs[0].shape) != ('output0', 'tensor(float)', [1, 4 + len(classes), 8400]):
        fail('ORT_INTERFACE_MISMATCH')
    samples = []
    for name in TENSOR_NAMES:
        outputs = session.run(['output0'], {'images': inputs[name]})
        if len(outputs) != 1: fail('ORT_OUTPUT_SCHEMA_INVALID')
        samples.append(compare_arrays(np, references[name], outputs[0], name))
    if fatal or fingerprint(source) != before or read_model_bytes(candidate) != raw: fail('EXPORT_INPUT_OR_GRAPH_CHANGED')
    runtime = {'versions': {'torch': torch.__version__, 'torchvision': torchvision.__version__, 'ultralytics': ultralytics.__version__, 'onnx': onnx.__version__, 'onnxruntime': ort.__version__},
        'provider': 'CPUExecutionProvider', 'device': 'cpu', 'threads': 2, 'opset': 18, 'ir_version': 8,
        'precision': 'fp32', 'dynamic': False, 'simplify': False, 'nms': False}
    digest = sha256(raw).hexdigest()
    validation = ExportValidation.model_validate({'schema_version': 1, 'job_id': job_id, 'run_id': run_id,
        'input_sha256': input_sha256, 'source_sha256': source_sha256, 'original_graph_sha256': digest,
        'model_sha256': digest, 'model_size_bytes': len(raw), 'classes': classes, 'input_name': 'images',
        'input_shape': INPUT_SHAPE, 'output_name': 'output0', 'output_shape': [1, 4 + len(classes), 8400],
        'dtype': 'float32', 'tensor_protocol': 'rgb-fixed-v1', 'atol': 1e-4, 'rtol': 1e-4,
        'checker_passed': True, 'runtime': runtime, 'samples': samples}).model_dump(mode='json')
    return candidate, validation
