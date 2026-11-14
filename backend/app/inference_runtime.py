"""Native image adapter invoked only in a fresh managed child after GO."""
from hashlib import sha256
import os
from pathlib import Path
import sys
import time
from .delivery_infer import (ImageInferenceError, decode_image, preprocess, postprocess,
                             preview_png, load_onnx, canonical_raw, fail)


def install_policy(root):
    from .training_runtime import TrainingPolicyError
    def denied(): raise TrainingPolicyError("INFERENCE_POLICY_FAILED")
    def check_write(path):
        if isinstance(path, int): return
        try: target = Path(os.fsdecode(path)).resolve()
        except TypeError: return
        if target != root and root not in target.parents: denied()
    def audit(event, args):
        if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.sendto', 'socket.bind',
                     'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.posix_spawnp', 'os.exec', 'os.fork', 'os.forkpty', 'os.spawn'}:
            denied()
        if event == 'open':
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)): check_write(path)
        if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.chown', 'os.truncate', 'os.utime'}: check_write(args[0])
        if event in {'os.rename', 'os.link', 'os.symlink'}: check_write(args[0]); check_write(args[1])
    sys.addaudithook(audit)


def load_pt(root, path, classes):
    from .training_runtime import initialize, TrainingPolicyError
    try:
        torch, torchvision, YOLO, DetectionModel, reject, fatal, loads = initialize(root, {path})
        import numpy as np
        import ultralytics
        if np.__version__ != '2.5.4': fail('RUNTIME_CHANGED')
        model = YOLO(str(path), task='detect')
        if not isinstance(model.model, DetectionModel) or model.task != 'detect' or [model.names[i] for i in range(len(model.names))] != classes:
            fail('PT_LOAD_REJECTED')
        if model.ckpt.get('optimizer') is not None or model.ckpt.get('ema') is not None or model.ckpt.get('epoch') != -1:
            fail('PT_LOAD_REJECTED')
        network = model.model.cpu().float().eval()
        for parameter in network.parameters():
            parameter.requires_grad_(False)
            if not torch.isfinite(parameter).all(): fail('PT_LOAD_REJECTED')
        from ultralytics.nn.modules.head import Detect
        heads = [module for module in network.modules() if isinstance(module, Detect)]
        if len(heads) != 1 or heads[0].nc != len(classes) or getattr(heads[0], 'end2end', False): fail('PT_LOAD_REJECTED')
        heads[0].export, heads[0].format, heads[0].dynamic = True, 'onnx', False
    except ImageInferenceError: raise
    except TrainingPolicyError as exc: raise ImageInferenceError('INFERENCE_POLICY_FAILED') from exc
    except Exception as exc: raise ImageInferenceError('PT_LOAD_REJECTED') from exc
    def infer(tensor):
        try:
            with torch.inference_mode():
                value = network(torch.from_numpy(np.frombuffer(tensor, dtype='<f4').reshape(1,3,640,640).copy()))
            if fatal or not isinstance(value, torch.Tensor): fail('INFERENCE_OUTPUT_INVALID')
            return canonical_raw(value.cpu().numpy(), len(classes))
        except ImageInferenceError: raise
        except TrainingPolicyError as exc: raise ImageInferenceError('INFERENCE_POLICY_FAILED') from exc
        except Exception as exc: raise ImageInferenceError('INFERENCE_OUTPUT_INVALID') from exc
    return infer, {'pillow': '12.3.0', 'numpy': np.__version__, 'torch': torch.__version__,
        'torchvision': torchvision.__version__, 'ultralytics': ultralytics.__version__, 'onnx': None, 'onnxruntime': None}


def execute_image(root, model_path, image_path, declared_format, backend, classes, confidence, iou):
    from .training_runtime import prepare_environment
    prepare_environment(root)
    install_policy(root)
    began = time.monotonic()
    rgb, image = decode_image(image_path, declared_format); decoded = time.monotonic()
    tensor, geometry = preprocess(rgb); prepared = time.monotonic()
    infer, versions = load_pt(root, model_path, classes) if backend == 'pt' else load_onnx(model_path, classes)
    loaded = time.monotonic()
    raw = infer(tensor); inferred = time.monotonic()
    result = postprocess(raw, classes, geometry, confidence, iou)
    preview, size = preview_png(rgb); finished = time.monotonic()
    return {'image_width': rgb.width, 'image_height': rgb.height, 'backend': backend,
        'provider': 'pytorch_cpu' if backend == 'pt' else 'CPUExecutionProvider', 'classes': classes,
        'image': image, 'preprocess': geometry,
        'runtime': {'backend': backend, 'provider': 'pytorch_cpu' if backend == 'pt' else 'CPUExecutionProvider',
                    'device': 'cpu', 'threads': 2, 'interop_threads': 1, 'warmup_runs': 0, 'versions': versions,
                    'raw_sha256': sha256(raw).hexdigest(), 'raw_elements': len(raw)//4},
        'preview': {'width': size[0], 'height': size[1], 'size_bytes': len(preview), 'sha256': sha256(preview).hexdigest(), 'format': 'png'},
        'counts': result['counts'], 'detections': result['detections'],
        'timings': {'unit': 'ms', 'decode': (decoded-began)*1000, 'preprocess': (prepared-decoded)*1000,
                    'load': (loaded-prepared)*1000, 'infer': (inferred-loaded)*1000, 'postprocess': (finished-inferred)*1000,
                    'total': (finished-began)*1000}}, raw, preview
