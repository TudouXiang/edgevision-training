"""Current image runtime identity without any native imports."""
from pathlib import Path
from importlib import metadata
from .export_assets import runtime_identity as export_identity
from .run_files import fingerprint, read_json
from .training_assets import digest_json
from .config import data_root


def runtime_identity():
    from .delivery_infer import ImageInferenceError
    try:
        value = export_identity()
    except metadata.PackageNotFoundError as exc:
        code = 'ORT_DEPENDENCY_MISSING' if exc.name in {'onnx', 'onnxruntime'} else 'RUNTIME_CHANGED'
        raise ImageInferenceError(code) from exc
    for name in ('delivery_infer.py', 'inference_contract.py', 'inference_files.py', 'image_storage.py',
                 'inference_inputs.py', 'inference_service.py', 'inference_assets.py', 'inference_runtime.py',
                 'inference_runner.py', 'inference_publication.py', 'inference_download.py', 'inference_errors.py',
                 'inference_probe.py', 'inference_probe_contract.py', 'main.py', 'schemas.py', 'security.py', 'services.py'):
        value['adapter'][name] = fingerprint(Path(__file__).parent / name)[1]
    value['image_protocol'] = 'detection-image-v1'
    return value


def capability():
    try:
        from .inference_probe_contract import InferenceProbeRecord
        identity = runtime_identity()
        record = InferenceProbeRecord.model_validate(read_json(data_root() / 'inference-capability.json', 1024**2))
        if record.runtime_binding != digest_json(identity) or record.code_version != digest_json(identity['adapter']) or record.synthetic_source_sha256 != identity['adapter']['delivery_infer.py']:
            raise ValueError('image probe stale')
        return {'available': True, 'reason_code': None, 'reason': None, 'detected_version': 'detection-image-v1'}
    except (OSError, ValueError, KeyError, TypeError, ImportError, metadata.PackageNotFoundError):
        return {'available': False, 'reason_code': 'INFERENCE_SETUP_REQUIRED', 'reason': 'A current managed PT and ONNX image probe is required', 'detected_version': None}
