"""Closed managed-image exit protocol; arbitrary native exception text stays private."""
from .delivery_infer import ImageInferenceError

INFERENCE_EXIT_ERRORS = dict(enumerate((
    'IMAGE_DECODE_FAILED', 'IMAGE_FORMAT_MISMATCH', 'IMAGE_MULTIFRAME', 'IMAGE_PIXEL_LIMIT',
    'IMAGE_MODE_UNSUPPORTED', 'PT_LOAD_REJECTED', 'ORT_DEPENDENCY_MISSING', 'ORT_MODEL_INVALID',
    'ORT_PROVIDER_MISMATCH', 'ORT_EXECUTION_FAILED', 'INFERENCE_OUTPUT_INVALID', 'INFERENCE_POLICY_FAILED'), 80))
INFERENCE_ERROR_EXITS = {value: key for key, value in INFERENCE_EXIT_ERRORS.items()}
INFERENCE_ERROR_EXITS.update(INPUT_CHANGED=66, RUNTIME_CHANGED=67, OUTPUT_CAPACITY_LIMIT=71)


def error_exit(error):
    if not isinstance(error, ImageInferenceError) or error.code not in INFERENCE_ERROR_EXITS:
        return 72
    return INFERENCE_ERROR_EXITS[error.code]


from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError


@contextmanager
def inference_boundary(stage):
    """Storage errors remain 70; only expected integrity/identity errors are mapped."""
    if stage not in {'source', 'runtime'}: raise ValueError('unknown inference boundary')
    try:
        yield
    except ImageInferenceError:
        raise
    except OSError:
        raise
    except PackageNotFoundError as exc:
        code = 'ORT_DEPENDENCY_MISSING' if exc.name in {'onnx', 'onnxruntime'} else 'RUNTIME_CHANGED'
        raise ImageInferenceError(code) from exc
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        raise ImageInferenceError('INPUT_CHANGED' if stage == 'source' else 'RUNTIME_CHANGED') from exc
