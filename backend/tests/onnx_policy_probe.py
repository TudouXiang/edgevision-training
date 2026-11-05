"""Explicit native faults; never imported by the API or default pytest suite."""
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(case, source_root):
    root = Path(source_root)
    os.environ['PLATFORM_DATA_ROOT'] = str(root)
    from app.database import transaction
    from app.run_files import run_directory
    from app.export_runtime import guard_graph, read_model_bytes, compare_arrays, export_and_validate
    from app.training_runtime import prepare_environment
    from app.ml_privacy import load_ort
    artifact = json.loads((root / 'export-artifact.json').read_text())
    with transaction() as c:
        row = c.execute('SELECT storage_key FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()
        source = c.execute('SELECT storage_key FROM artifacts WHERE id=?', (artifact['metadata']['provenance']['parent_artifact_id'],)).fetchone()
    job, run = str(uuid4()), str(uuid4())
    directory = run_directory(job, run, create=True)
    source_path = directory / 'source.pt'
    shutil.copyfile(root / source['storage_key'], source_path)
    raw = read_model_bytes(root / row['storage_key'])
    if case == 'no_fallback':
        from app import ml_privacy
        real_load = ml_privacy.load_ort
        class InjectedOrtFailure(Exception): pass
        def fail_load():
            ort = real_load()
            def fail_session(*args, **kwargs): raise InjectedOrtFailure('explicit ORT failure')
            ort.InferenceSession = fail_session
            return ort
        ml_privacy.load_ort = fail_load
        try:
            export_and_validate(directory, source_path, artifact['metadata']['classes'], job_id=job, run_id=run,
                input_sha256='a' * 64, source_sha256=artifact['metadata']['provenance']['source_sha256'])
        except InjectedOrtFailure: return
        raise AssertionError('ORT failure silently fell back')
    prepare_environment(directory)
    load_ort()
    import onnx
    import numpy as np
    if case == 'numeric':
        expected = np.zeros((1, 5, 8400), dtype=np.float32)
        try: compare_arrays(np, expected, np.full_like(expected, .001), 'zeros')
        except ValueError: return
        raise AssertionError('numerical mismatch was accepted')
    if case == 'corrupt':
        try: onnx.load_model_from_string(b'not-a-protobuf-model')
        except Exception: return
        raise AssertionError('corrupt graph parsed')
    model = onnx.load_model_from_string(raw)
    if case == 'external':
        tensor = model.graph.initializer[0]
        tensor.data_location = onnx.TensorProto.EXTERNAL
        entry = tensor.external_data.add(); entry.key, entry.value = 'location', 'outside.bin'
    elif case == 'custom': model.graph.node[0].domain = 'untrusted.custom'
    elif case == 'sparse': model.graph.sparse_initializer.add()
    else: raise ValueError('unknown native policy case')
    try: guard_graph(model, onnx, artifact['metadata']['classes'])
    except ValueError: return
    raise AssertionError('unsupported graph was accepted')


if __name__ == '__main__':
    main(*sys.argv[1:])
    print('PASS native ONNX policy case')
