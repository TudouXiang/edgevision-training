"""Test-only native I faults in a fresh interpreter, never a production selector.

Requires the successful private I HTTP root. Mutations affect only a fresh local
copy or test-only import adapter, never the trusted source or capability record.
"""
import builtins
import os
from pathlib import Path
import sys
from uuid import uuid4

CASES = {
    'corrupt_onnx': 'ORT_MODEL_INVALID',
    'missing_ort': 'ORT_DEPENDENCY_MISSING',
    'provider_mismatch': 'ORT_PROVIDER_MISMATCH',
    'execution_failure': 'ORT_EXECUTION_FAILED',
    'nonfinite_output': 'INFERENCE_OUTPUT_INVALID',
}


def main(case, source_root):
    if case not in CASES:
        raise ValueError('unknown image policy case')
    root = Path(source_root).resolve()
    if any(not os.environ.get(name) or Path(os.environ[name]).resolve() != root
           for name in ('PLATFORM_DATA_ROOT', 'EDGEVISION_INFERENCE_POLICY_ROOT')):
        raise ValueError('explicit same-root image policy opt-in required')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import transaction
    from app.inference_probe import sources
    from app.inference_files import copy_stored, write_bytes
    from app.run_files import read_json, run_directory
    from app.delivery_infer import synthetic_png, ImageInferenceError
    from app import inference_runtime
    from app.inference_assets import capability
    evidence = read_json(root / 'inference-http-result.json', 1024**2)
    assert evidence['status'] == 'passed' and capability()['available']
    artifact = read_json(root / 'export-artifact.json', 1024**2)
    with transaction() as connection:
        connection.execute('BEGIN')
        pair = sources(connection, artifact['id'])
    source = pair['onnx']
    directory = run_directory(str(uuid4()), str(uuid4()), create=True)
    model = copy_stored(source['source_key'], source['source_size_bytes'], source['source_sha256'], 128*1024**2, directory / 'model.onnx')
    image = directory / 'image.png'
    write_bytes(image, synthetic_png(), 50*1024**2)
    if case == 'corrupt_onnx':
        model.write_bytes(b'not a protobuf model')

    observed = {'import': False, 'session': False, 'run': False, 'fallback': False}
    original_import = builtins.__import__
    importing_ort = False

    def intercept(name, globals=None, locals=None, fromlist=(), level=0):
        nonlocal importing_ort
        if name != 'onnxruntime' or importing_ort:
            return original_import(name, globals, locals, fromlist, level)
        observed['import'] = True
        if case == 'missing_ort':
            # Simulate the import boundary, not a real package uninstall.
            raise ModuleNotFoundError('explicit isolated dependency fault', name='onnxruntime')
        importing_ort = True
        try:
            ort = original_import(name, globals, locals, fromlist, level)
        finally:
            importing_ort = False
        if case in {'provider_mismatch', 'execution_failure', 'nonfinite_output'}:
            original_session = ort.InferenceSession
            class FaultSession(original_session):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    observed['session'] = True
                def get_providers(self):
                    actual = super().get_providers()
                    assert actual == ['CPUExecutionProvider']
                    return ['UnexpectedExecutionProvider'] if case == 'provider_mismatch' else actual
                def run(self, *args, **kwargs):
                    observed['run'] = True
                    if case == 'execution_failure':
                        raise RuntimeError('explicit isolated ORT execution fault')
                    outputs = super().run(*args, **kwargs)
                    if case == 'nonfinite_output':
                        outputs[0].flat[0] = float('nan')
                    return outputs
            ort.InferenceSession = FaultSession
        return ort

    def forbidden_pt(*args, **kwargs):
        observed['fallback'] = True
        raise AssertionError('ONNX failure attempted PT fallback')

    inference_runtime.load_pt = forbidden_pt
    builtins.__import__ = intercept
    try:
        try:
            inference_runtime.execute_image(directory, model, image, 'png', 'onnx', source['source_metadata']['classes'], .25, .45)
        except ImageInferenceError as exc:
            assert exc.code == CASES[case]
        else:
            raise AssertionError('native image fault returned success')
    finally:
        builtins.__import__ = original_import
    assert observed['import'] and not observed['fallback']
    assert not {'torch', 'ultralytics'}.intersection(sys.modules)
    if case in {'provider_mismatch', 'execution_failure', 'nonfinite_output'}:
        assert observed['session']
    if case in {'execution_failure', 'nonfinite_output'}:
        assert observed['run']
    assert not (directory / 'evidence.json').exists() and not (directory / 'bundle').exists()
    print('PASS native image policy case')


if __name__ == '__main__':
    main(*sys.argv[1:])
