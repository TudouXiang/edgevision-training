"""Operator-only dual-mode probe. Uses the existing shared lock/recovery protocol."""
import argparse
from hashlib import sha256
import json
import math
import os
import struct
import subprocess
from uuid import uuid4
from .config import data_root
from .database import transaction
from .dataset_storage import resolve_storage_file
from .inference_assets import runtime_identity
from .inference_inputs import model_snapshot
from .inference_files import copy_stored, verified_file, write_bytes
from .inference_probe_contract import ProbePair, ProbeInput, InferenceProbeProof, InferenceProbeRecord
from .inference_errors import ImageInferenceError, error_exit, inference_boundary
from .run_files import atomic_json, read_json, fingerprint, run_directory
from .training_assets import digest_json
from .delivery_infer import synthetic_png, match_detections


def sources(connection, artifact_id):
    row = connection.execute("SELECT * FROM artifacts WHERE id=? AND kind='onnx'", (artifact_id,)).fetchone()
    if not row: raise ValueError('operator must select a successful platform ONNX artifact')
    onnx = model_snapshot(connection, row['project_id'], artifact_id, 'onnx')
    pt = model_snapshot(connection, row['project_id'], onnx['export_input']['source_artifact_id'], 'pt')
    return ProbePair.model_validate({'pt': pt, 'onnx': onnx}).model_dump(mode='json')


def verify_pair(pair):
    with transaction() as connection:
        connection.execute('BEGIN')
        current = sources(connection, pair['onnx']['source_artifact_id'])
    if current != pair: raise ValueError('probe source pair changed')


def probe_child(job_id, run_id):
    directory = run_directory(job_id, run_id)
    try: task = ProbeInput.model_validate(read_json(directory/'input.json')).model_dump(mode='json')
    except ValueError: return 65
    if (task['job_id'], task['run_id']) != (job_id, run_id): return 65
    with inference_boundary('runtime'): before = runtime_identity()
    if task['runtime_binding'] != digest_json(before) or task['code_version'] != digest_json(before['adapter']): return 67
    pair = task['pair']
    with inference_boundary('source'): verify_pair(pair)
    model = pair[task['backend']]
    image = synthetic_png()
    if (len(image), sha256(image).hexdigest()) != (task['image_size_bytes'], task['image_sha256']): return 66
    with inference_boundary('source'):
        model_path = copy_stored(model['source_key'], model['source_size_bytes'], model['source_sha256'], 128*1024**2, directory/('model.'+task['backend']))
    image_path = directory/'image.png'; write_bytes(image_path, image, 50*1024**2)
    from .inference_runtime import execute_image
    from .training_runtime import TrainingPolicyError
    try:
        output, raw, preview = execute_image(directory, model_path, image_path, 'png', task['backend'], model['source_metadata']['classes'], .25, .45)
    except ImageInferenceError as exc: return error_exit(exc)
    except TrainingPolicyError: return 91
    with inference_boundary('source'): verify_pair(pair)
    with inference_boundary('runtime'):
        if before != runtime_identity(): return 67
    with inference_boundary('source'):
        with verified_file(model_path, model['source_size_bytes'], model['source_sha256'], 128*1024**2): pass
        with verified_file(image_path, task['image_size_bytes'], task['image_sha256'], 50*1024**2): pass
    write_bytes(directory/'raw.f32le', raw, 33_734_400)
    write_bytes(directory/'preview.png', preview, 8*1024**2)
    proof = InferenceProbeProof.model_validate({'schema_version': 1, 'protocol': 'detection-image-v1', 'job_id': job_id, 'run_id': run_id,
        'project_id': model['project_id'], 'model_artifact_id': model['source_artifact_id'], 'parent_pt_artifact_id': pair['pt']['source_artifact_id'],
        'model_sha256': model['source_sha256'], 'pair_sha256': task['pair_sha256'], 'image_sha256': task['image_sha256'],
        'image_size_bytes': task['image_size_bytes'], 'runtime_binding': task['runtime_binding'], 'code_version': task['code_version'],
        'output': output, 'raw_size_bytes': len(raw), 'raw_sha256': sha256(raw).hexdigest(), 'receipt_sha256': None}).model_dump(mode='json')
    atomic_json(directory/'probe-result.json', proof)
    return 0


def compare_raw(first, second):
    """Both sources are already drained; hash and compare bounded open descriptors."""
    if first['raw_size_bytes'] != second['raw_size_bytes']: raise ValueError('raw sizes differ')
    paths = [run_directory(v['job_id'], v['run_id'])/'raw.f32le' for v in (first, second)]
    size = first['raw_size_bytes']; count = 0; maximum = 0.; ratio = 0.
    with verified_file(paths[0], size, first['raw_sha256'], 33_734_400) as left, verified_file(paths[1], size, second['raw_sha256'], 33_734_400) as right:
        hashes = [sha256(), sha256()]
        remaining = size
        while remaining:
            length = min(64*1024, remaining); a, b = left.read(length), right.read(length)
            if len(a) != length or len(b) != length or length % 4: raise ValueError('raw comparison truncated')
            hashes[0].update(a); hashes[1].update(b)
            for (reference,), (actual,) in zip(struct.iter_unpack('<f', a), struct.iter_unpack('<f', b)):
                if not math.isfinite(reference) or not math.isfinite(actual): raise ValueError('nonfinite raw comparison')
                delta = abs(actual-reference); tolerance = 1e-4 + 1e-4*abs(reference)
                if delta > tolerance: raise ValueError('raw tolerance exceeded')
                maximum = max(maximum, delta); ratio = max(ratio, delta/tolerance); count += 1
            remaining -= length
        if left.read(1) or right.read(1) or [h.hexdigest() for h in hashes] != [first['raw_sha256'], second['raw_sha256']] or count*4 != size:
            raise ValueError('raw comparison fingerprint changed')
    return {'elements': count, 'max_absolute_error': maximum, 'max_tolerance_ratio': ratio, 'atol': 1e-4, 'rtol': 1e-4, 'detections_matched': True}


def stage(pair, backend, before, image):
    from .worker import guardian_command, drain_receipt, send_control
    from .python_launch import python_child
    from .process_identity import identity
    job_id, run_id = str(uuid4()), str(uuid4()); directory = run_directory(job_id, run_id, create=True)
    task = ProbeInput.model_validate({'schema_version': 1, 'kind': 'inference_probe', 'protocol': 'detection-image-v1',
        'job_id': job_id, 'run_id': run_id, 'pair': pair, 'backend': backend, 'pair_sha256': digest_json(pair),
        'image_sha256': sha256(image).hexdigest(), 'image_size_bytes': len(image), 'runtime_binding': digest_json(before),
        'code_version': digest_json(before['adapter'])}).model_dump(mode='json')
    atomic_json(directory/'input.json', task)
    active = {'job_id': job_id, 'run_id': run_id, 'guardian': None}
    atomic_json(data_root()/'training-probe-active.json', active)
    command, env = python_child(guardian_command(job_id, run_id)); child = None
    try:
        child = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, start_new_session=os.name != 'nt')
        active['guardian'] = identity(child.pid); atomic_json(data_root()/'training-probe-active.json', active)
        send_control(child.stdin, b'GO\n')
        try: child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            send_control(child.stdin, b'STOP\n'); child.wait(timeout=25)
    finally:
        if child is not None and child.stdin:
            try: child.stdin.close()
            except BrokenPipeError: pass
    row = {'id': job_id, 'run_id': run_id, 'process_identity_json': json.dumps({'guardian': active['guardian']})}
    receipt = drain_receipt(row, wait_seconds=2)
    if not receipt or receipt['reason'] != 'completed' or receipt['exit_code'] != 0 or not receipt['logs_complete'] or not receipt['started']:
        raise ValueError('image probe tree exit or execution failed')
    proof = InferenceProbeProof.model_validate(read_json(directory/'probe-result.json', 1024**2)).model_dump(mode='json')
    model = pair[backend]
    expected = {'job_id': job_id, 'run_id': run_id, 'project_id': model['project_id'], 'model_artifact_id': model['source_artifact_id'],
        'parent_pt_artifact_id': pair['pt']['source_artifact_id'], 'model_sha256': model['source_sha256'],
        'pair_sha256': digest_json(pair), 'image_sha256': sha256(image).hexdigest(), 'image_size_bytes': len(image),
        'runtime_binding': digest_json(before), 'code_version': digest_json(before['adapter']), 'receipt_sha256': None}
    if any(proof[key] != value for key, value in expected.items()) or proof['output']['backend'] != backend or proof['output']['classes'] != model['source_metadata']['classes']:
        raise ValueError('probe execution proof changed')
    for name, size, digest, limit in [('model.'+backend, model['source_size_bytes'], model['source_sha256'], 128*1024**2),
        ('image.png', len(image), sha256(image).hexdigest(), 50*1024**2), ('raw.f32le', proof['raw_size_bytes'], proof['raw_sha256'], 33_734_400),
        ('preview.png', proof['output']['preview']['size_bytes'], proof['output']['preview']['sha256'], 8*1024**2)]:
        with verified_file(directory/name, size, digest, limit): pass
    verify_pair(pair)
    if runtime_identity() != before: raise ValueError('probe runtime changed')
    proof['receipt_sha256'] = digest_json(receipt)
    return proof


def run_probe(artifact_id):
    from .worker import worker_lock, recover
    from .training_probe import recover_probe
    root = data_root(); root.mkdir(parents=True, exist_ok=True)
    with worker_lock(root):
        atomic_json(root/'inference-capability.json', {'schema_version': 1, 'available': False})
        if not recover_probe(): raise RuntimeError('Previous shared probe exit is unconfirmed')
        if recover(): raise RuntimeError('Existing task exit is unconfirmed')
        with transaction() as connection:
            connection.execute('BEGIN'); pair = sources(connection, artifact_id)
        before = runtime_identity(); image = synthetic_png()
        pt = stage(pair, 'pt', before, image)
        onnx = stage(pair, 'onnx', before, image)
        comparison = compare_raw(pt, onnx)
        if not match_detections(pt['output']['detections'], onnx['output']['detections']): raise ValueError('probe detection comparison failed')
        verify_pair(pair)
        if runtime_identity() != before: raise ValueError('probe runtime changed')
        record = InferenceProbeRecord.model_validate({'schema_version': 1, 'available': True, 'protocol': 'detection-image-v1',
            'runtime_binding': digest_json(before), 'code_version': digest_json(before['adapter']),
            'synthetic_source_sha256': before['adapter']['delivery_infer.py'], 'pt': pt, 'onnx': onnx, 'comparison': comparison}).model_dump(mode='json')
        atomic_json(root/'inference-capability.json', record)


def main():
    parser = argparse.ArgumentParser(description='Verify both actual image backends from a successful platform ONNX Artifact and its parent PT')
    parser.add_argument('--onnx-artifact-id', type=lambda value: str(__import__('uuid').UUID(value)), required=True)
    args = parser.parse_args()
    try: run_probe(args.onnx_artifact_id)
    except Exception:
        print('Image probe failed; capability remains unavailable'); return 1
    print('Managed PT and ONNX image probe passed for the current runtime'); return 0


if __name__ == '__main__': raise SystemExit(main())
