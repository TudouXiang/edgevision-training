"""detection-image-v1, the sole portable image/geometry implementation.

No platform or model-framework imports. Future deployment copies this source
unchanged. All model-native execution stays in lazy adapters, never API import.
"""
from array import array
from hashlib import sha256
from io import BytesIO
import math
import struct
import sys
import warnings

PROTOCOL = 'detection-image-v1'
MAX_IMAGE_BYTES = 50 * 1024**2
MAX_PIXELS = 30_000_000
MAX_PREVIEW_BYTES = 8 * 1024**2
MAX_CANDIDATES = 3000
MAX_RESULTS = 300


class ImageInferenceError(ValueError):
    """Closed codes only; upstream exception text is never user-facing."""
    def __init__(self, code):
        allowed = {'IMAGE_DECODE_FAILED', 'IMAGE_FORMAT_MISMATCH', 'IMAGE_MULTIFRAME', 'IMAGE_PIXEL_LIMIT',
                   'IMAGE_MODE_UNSUPPORTED', 'PT_LOAD_REJECTED', 'ORT_DEPENDENCY_MISSING', 'ORT_MODEL_INVALID',
                   'ORT_PROVIDER_MISMATCH', 'ORT_EXECUTION_FAILED', 'INFERENCE_OUTPUT_INVALID',
                   'INFERENCE_POLICY_FAILED', 'INPUT_CHANGED', 'RUNTIME_CHANGED', 'OUTPUT_CAPACITY_LIMIT'}
        if type(code) is not str or code not in allowed: raise ValueError('unknown image failure code')
        self.code = code
        super().__init__(code)


def fail(code):
    raise ImageInferenceError(code)


def letterbox_record(width, height):
    if type(width) is not int or type(height) is not int or min(width, height) <= 0 or width * height > MAX_PIXELS:
        fail('IMAGE_PIXEL_LIMIT')
    ratio = min(640 / width, 640 / height)
    rw, rh = (max(1, min(640, math.floor(v * ratio + .5))) for v in (width, height))
    left, top = (640 - rw) // 2, (640 - rh) // 2
    return {'image_width': width, 'image_height': height, 'resized_width': rw, 'resized_height': rh,
            'left': left, 'right': 640 - rw - left, 'top': top, 'bottom': 640 - rh - top,
            'scale_x': rw / width, 'scale_y': rh / height,
            'target_width': 640, 'target_height': 640, 'padding': 114, 'resampling': 'pillow_bilinear',
            'layout': 'NCHW', 'dtype': 'float32', 'color': 'RGB', 'normalization': 'divide_255'}


def decode_image(path, declared_format):
    """Read bounded local copy; classify decoder OSError separately from storage."""
    from PIL import Image, ImageOps, ImageFile, __version__
    if __version__ != '12.3.0': fail('RUNTIME_CHANGED')
    if declared_format not in {'jpeg', 'png'}: fail('IMAGE_FORMAT_MISMATCH')
    # Actual filesystem failures occur before the decoder exception boundary.
    with open(path, 'rb') as source:
        content = source.read(MAX_IMAGE_BYTES + 1)
    if not content or len(content) > MAX_IMAGE_BYTES: fail('IMAGE_DECODE_FAILED')
    # Pillow silently reduces 16-bit RGB/RGBA PNG to mode RGB/RGBA. Inspect the
    # encoded IHDR before mode conversion; verify() below still checks its CRC.
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        if declared_format != 'png': fail('IMAGE_FORMAT_MISMATCH')
        if len(content) < 33 or content[8:16] != b'\x00\x00\x00\x0dIHDR': fail('IMAGE_DECODE_FAILED')
        if content[24] > 8: fail('IMAGE_MODE_UNSUPPORTED')
    old_limit, old_truncated = Image.MAX_IMAGE_PIXELS, ImageFile.LOAD_TRUNCATED_IMAGES
    Image.MAX_IMAGE_PIXELS, ImageFile.LOAD_TRUNCATED_IMAGES = MAX_PIXELS, False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(BytesIO(content)) as check:
                if check.format != {'jpeg': 'JPEG', 'png': 'PNG'}[declared_format]: fail('IMAGE_FORMAT_MISMATCH')
                if getattr(check, 'n_frames', 1) != 1: fail('IMAGE_MULTIFRAME')
                width, height = check.size
                if min(width, height) <= 0 or width * height > MAX_PIXELS: fail('IMAGE_PIXEL_LIMIT')
                if check.mode not in {'RGB', 'L', 'RGBA', 'LA', 'P'}: fail('IMAGE_MODE_UNSUPPORTED')
                check.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
                orientation = image.getexif().get(274, 1)
                if type(orientation) is not int or orientation not in range(1, 9): fail('IMAGE_DECODE_FAILED')
                corrected = ImageOps.exif_transpose(image)
                if corrected.mode in {'RGBA', 'LA'} or 'transparency' in corrected.info:
                    rgba = corrected.convert('RGBA')
                    # Explicit integer compositing, independent of implicit Pillow modes.
                    data = rgba.tobytes()
                    pixels = bytearray(len(data) // 4 * 3)
                    for offset in range(0, len(data), 4):
                        alpha = data[offset + 3]
                        output = offset // 4 * 3
                        for channel in range(3):
                            pixels[output + channel] = (data[offset + channel] * alpha + 114 * (255 - alpha) + 127) // 255
                    rgb = Image.frombytes('RGB', rgba.size, bytes(pixels))
                else:
                    converted = corrected.convert('RGB')
                    rgb = Image.frombytes('RGB', converted.size, converted.tobytes())
    except ImageInferenceError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageInferenceError('IMAGE_PIXEL_LIMIT') from exc
    except (OSError, ValueError, SyntaxError, Warning) as exc:
        raise ImageInferenceError('IMAGE_DECODE_FAILED') from exc
    finally:
        Image.MAX_IMAGE_PIXELS, ImageFile.LOAD_TRUNCATED_IMAGES = old_limit, old_truncated
    return rgb, {'encoded_width': width, 'encoded_height': height, 'image_width': rgb.width,
                 'image_height': rgb.height, 'orientation': orientation, 'format': declared_format,
                 'rgb_sha256': sha256(rgb.tobytes()).hexdigest()}


def preprocess(rgb):
    from PIL import Image
    record = letterbox_record(rgb.width, rgb.height)
    resized = rgb.resize((record['resized_width'], record['resized_height']), Image.Resampling.BILINEAR)
    padded = Image.new('RGB', (640, 640), (114, 114, 114))
    padded.paste(resized, (record['left'], record['top']))
    pixels = padded.tobytes()
    values = array('f', (pixels[offset] / 255 for channel in range(3) for offset in range(channel, len(pixels), 3)))
    if sys.byteorder != 'little': values.byteswap()
    tensor = values.tobytes()
    record['tensor_sha256'] = sha256(tensor).hexdigest()
    return tensor, record


def preview_png(rgb):
    from PIL import Image
    ratio = min(1., 1280 / max(rgb.size))
    size = tuple(max(1, math.floor(v * ratio + .5)) for v in rgb.size)
    image = rgb.resize(size, Image.Resampling.BILINEAR) if size != rgb.size else rgb
    # A newly constructed object cannot carry EXIF/ICC/tRNS/comment metadata.
    clean = Image.frombytes('RGB', size, image.tobytes())
    sink = BytesIO()
    clean.save(sink, format='PNG', compress_level=6, optimize=False)
    content = sink.getvalue()
    if len(content) > MAX_PREVIEW_BYTES: fail('OUTPUT_CAPACITY_LIMIT')
    return content, size


def synthetic_png():
    from PIL import Image
    pixels = bytes(value for y in range(193) for x in range(257)
                   for value in ((3*x+y) % 256, (x+5*y) % 256, (7*x+11*y) % 256))
    return preview_png(Image.frombytes('RGB', (257, 193), pixels))[0]


def box_iou(first, second):
    intersection = max(0., min(first[2], second[2]) - max(first[0], second[0])) * max(0., min(first[3], second[3]) - max(first[1], second[1]))
    union = (first[2]-first[0])*(first[3]-first[1]) + (second[2]-second[0])*(second[3]-second[1]) - intersection
    return intersection / union if union > 0 else 0.


def postprocess(raw, classes, geometry, confidence, iou):
    nc = len(classes)
    if not 1 <= nc <= 1000 or len(raw) != (4 + nc) * 8400 * 4: fail('INFERENCE_OUTPUT_INVALID')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in (confidence, iou)):
        fail('INFERENCE_OUTPUT_INVALID')
    values = array('f'); values.frombytes(raw)
    if sys.byteorder != 'little': values.byteswap()
    if any(not math.isfinite(value) for value in values): fail('INFERENCE_OUTPUT_INVALID')
    if any(not 0 <= value <= 1 for value in values[4 * 8400:]): fail('INFERENCE_OUTPUT_INVALID')
    candidates = []
    for anchor in range(8400):
        # array indexing returns Python float: geometry/NMS use float64, not FP32.
        class_id = 0; score = values[4 * 8400 + anchor]
        for cls in range(1, nc):
            other = values[(4 + cls) * 8400 + anchor]
            if other > score: class_id, score = cls, other
        cx, cy, width, height = (values[channel * 8400 + anchor] for channel in range(4))
        if score <= confidence or width <= 0 or height <= 0: continue
        candidates.append((score, class_id, anchor, (cx-width/2, cy-height/2, cx+width/2, cy+height/2)))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    count = len(candidates); candidates = candidates[:MAX_CANDIDATES]
    kept = []
    for item in candidates:
        if not any(other[1] == item[1] and box_iou(item[3], other[3]) > iou for other in kept): kept.append(item)
    limited = kept[:MAX_RESULTS]
    detections = []; removed = 0
    for score, cls, _, box in limited:
        x1, y1, x2, y2 = box
        x1, x2 = (min(float(geometry['image_width']), max(0., (x-geometry['left'])/geometry['scale_x'])) for x in (x1, x2))
        y1, y2 = (min(float(geometry['image_height']), max(0., (y-geometry['top'])/geometry['scale_y'])) for y in (y1, y2))
        if x1 >= x2 or y1 >= y2: removed += 1; continue
        detections.append({'class_id': cls, 'score': score, 'xyxy': [x1, y1, x2, y2]})
    return {'detections': detections, 'counts': {'candidates': count, 'candidate_truncated': max(0, count-MAX_CANDIDATES),
            'nms_kept': len(kept), 'result_truncated': max(0, len(kept)-MAX_RESULTS), 'clip_removed': removed}}


def match_detections(first, second):
    """Deterministic maximum bipartite matching, not a greedy nearest-box check."""
    if len(first) != len(second): return False
    edges = [[j for j, other in enumerate(second) if item['class_id'] == other['class_id']
              and abs(item['score']-other['score']) <= .001 and box_iou(item['xyxy'], other['xyxy']) >= .99
              and all(abs(x-y) <= .5 for x, y in zip(item['xyxy'], other['xyxy']))] for item in first]
    matched = {}
    def augment(i, seen):
        for j in edges[i]:
            if j in seen: continue
            seen.add(j)
            if j not in matched or augment(matched[j], seen): matched[j] = i; return True
        return False
    return all(augment(i, set()) for i in range(len(first)))


def guard_onnx_graph(model, onnx, classes):
    """Portable graph contract; no external tensors, custom operators or dynamic IO."""
    if model.ir_version != 8 or model.functions or model.training_info or model.metadata_props:
        fail('ORT_MODEL_INVALID')
    if [(v.domain, v.version) for v in model.opset_import] != [('', 18)]: fail('ORT_MODEL_INVALID')
    if len(model.graph.input) != 1 or len(model.graph.output) != 1: fail('ORT_MODEL_INVALID')
    for value, name, shape in ((model.graph.input[0], 'images', (1, 3, 640, 640)), (model.graph.output[0], 'output0', (1, 4+len(classes), 8400))):
        if value.name != name or value.type.WhichOneof('value') != 'tensor_type': fail('ORT_MODEL_INVALID')
        tensor = value.type.tensor_type
        if tensor.elem_type != onnx.TensorProto.FLOAT or any(d.WhichOneof('value') != 'dim_value' for d in tensor.shape.dim) or tuple(d.dim_value for d in tensor.shape.dim) != shape:
            fail('ORT_MODEL_INVALID')
    stack, count = [(model, 0)], 0
    while stack:
        message, depth = stack.pop(); count += 1
        if depth > 64 or count > 200000: fail('ORT_MODEL_INVALID')
        kind = message.DESCRIPTOR.name
        if kind in {'SparseTensorProto', 'FunctionProto', 'TrainingInfoProto'}: fail('ORT_MODEL_INVALID')
        if kind == 'TensorProto' and (message.external_data or message.data_location != onnx.TensorProto.DEFAULT): fail('ORT_MODEL_INVALID')
        if kind == 'NodeProto' and (message.domain or not onnx.defs.has(message.op_type, 18, '')): fail('ORT_MODEL_INVALID')
        if kind == 'GraphProto' and message.sparse_initializer: fail('ORT_MODEL_INVALID')
        for field, value in message.ListFields():
            if field.message_type is not None:
                stack.extend((item, depth+1) for item in (value if field.is_repeated else [value]))


def canonical_raw(value, nc):
    import numpy as np
    if value.dtype != np.float32 or value.shape != (1, 4+nc, 8400) or not np.isfinite(value).all():
        fail('INFERENCE_OUTPUT_INVALID')
    return value.astype('<f4', copy=False).tobytes(order='C')


def load_onnx(path, classes):
    """Independent fixed ORT entry, copied unchanged into future packages."""
    import os
    from importlib import metadata
    import stat
    if any(name == 'onnxruntime' or name.startswith('onnxruntime.') for name in sys.modules):
        fail('INFERENCE_POLICY_FAILED')  # This invocation owns the pre-import gate.
    os.environ['ORT_DISABLE_TELEMETRY'] = '1'
    try:
        if metadata.version('onnxruntime') != '1.31.1': fail('RUNTIME_CHANGED')
        import onnxruntime as ort
        ort.disable_telemetry_events()
        import onnx
        import numpy as np
    except (ImportError, metadata.PackageNotFoundError) as exc:
        raise ImageInferenceError('ORT_DEPENDENCY_MISSING') from exc
    if onnx.__version__ != '1.23.2' or np.__version__ != '2.5.4': fail('RUNTIME_CHANGED')
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= 128*1024**2: fail('ORT_MODEL_INVALID')
    with path.open('rb') as source: raw = source.read(128*1024**2+1)
    if len(raw) != details.st_size: fail('ORT_MODEL_INVALID')
    try:
        model = onnx.load_model_from_string(raw)
        guard_onnx_graph(model, onnx, classes)
        onnx.checker.check_model(raw, full_check=True)
    except ImageInferenceError: raise
    except Exception as exc: raise ImageInferenceError('ORT_MODEL_INVALID') from exc
    try:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(raw, sess_options=options, providers=['CPUExecutionProvider'])
        session.disable_fallback()
        if session.get_providers() != ['CPUExecutionProvider']: fail('ORT_PROVIDER_MISMATCH')
        ins, outs = session.get_inputs(), session.get_outputs()
        if len(ins) != 1 or len(outs) != 1 or (ins[0].name, ins[0].type, ins[0].shape) != ('images', 'tensor(float)', [1,3,640,640]) or (outs[0].name, outs[0].type, outs[0].shape) != ('output0', 'tensor(float)', [1,4+len(classes),8400]):
            fail('ORT_MODEL_INVALID')
    except ImageInferenceError: raise
    except Exception as exc: raise ImageInferenceError('ORT_EXECUTION_FAILED') from exc
    def infer(tensor):
        try:
            value = np.frombuffer(tensor, dtype='<f4').reshape((1,3,640,640)).copy()
            outputs = session.run(['output0'], {'images': value})
        except Exception as exc: raise ImageInferenceError('ORT_EXECUTION_FAILED') from exc
        if session.get_providers() != ['CPUExecutionProvider']: fail('ORT_PROVIDER_MISMATCH')
        if len(outputs) != 1: fail('INFERENCE_OUTPUT_INVALID')
        return canonical_raw(outputs[0], len(classes))
    return infer, {'pillow': '12.3.0', 'numpy': np.__version__, 'torch': None, 'torchvision': None,
                   'ultralytics': None, 'onnx': onnx.__version__, 'onnxruntime': ort.__version__}
