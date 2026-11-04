"""Explicit managed delivery probe, sharing the training probe/Worker exclusion slot."""
import json
import os
import shutil
import subprocess
from uuid import uuid4
from .config import data_root
from .dataset_storage import resolve_storage_file
from .export_assets import runtime_identity
from .run_files import atomic_json, read_json, fingerprint, run_directory
from .training_assets import BASE_KEY, BASE_MANIFEST, verify_asset, digest_json
from .schemas import ExportValidation


def probe_child(job_id, run_id):
    directory = run_directory(job_id, run_id)
    before = runtime_identity()
    manifest = verify_asset()
    source = directory / 'yolo11n.pt'
    shutil.copyfile(resolve_storage_file(BASE_KEY), source)
    from .export_runtime import export_and_validate
    from .training_runtime import TrainingPolicyError
    try:
        _, validation = export_and_validate(directory, source, None, job_id=job_id, run_id=run_id,
            input_sha256=digest_json({'manifest': manifest, 'runtime': before}), source_sha256=manifest['sha256'])
    except TrainingPolicyError:
        return 68
    if runtime_identity() != before or fingerprint(source) != (manifest['size_bytes'], manifest['sha256']): return 67
    atomic_json(directory / 'probe-result.json', {'schema_version': 1, 'available': True, 'runtime_binding': digest_json(before),
        'manifest_sha256': digest_json(manifest), 'source_sha256': manifest['sha256'], 'validation': validation})
    return 0


def run_probe():
    from .worker import worker_lock, guardian_command, drain_receipt, recover
    from .training_probe import recover_probe
    from .python_launch import python_child
    from .process_identity import identity
    root = data_root(); root.mkdir(parents=True, exist_ok=True)
    with worker_lock(root):
        if not recover_probe(): raise RuntimeError('Previous shared probe exit is unconfirmed')
        if recover(): raise RuntimeError('Existing task exit is unconfirmed')
        atomic_json(root / 'delivery-capability.json', {'schema_version': 1, 'available': False})
        verify_asset()
        before = runtime_identity()
        job_id, run_id = str(uuid4()), str(uuid4())
        directory = run_directory(job_id, run_id, create=True)
        atomic_json(directory / 'input.json', {'schema_version': 1, 'job_id': job_id, 'run_id': run_id, 'kind': 'export_probe'})
        # Persist ambiguous launch before Popen. The common recovery path blocks
        # both training/export probes and Worker if the drain cannot be proven.
        active = {'job_id': job_id, 'run_id': run_id, 'guardian': None}
        atomic_json(root / 'training-probe-active.json', active)
        command, env = python_child(guardian_command(job_id, run_id))
        child = None
        try:
            child = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, start_new_session=os.name != 'nt')
            active['guardian'] = identity(child.pid)
            atomic_json(root / 'training-probe-active.json', active)
            child.stdin.write(b'GO\n'); child.stdin.flush()
            try: child.wait(timeout=300)
            except subprocess.TimeoutExpired:
                child.stdin.write(b'STOP\n'); child.stdin.flush()
                child.wait(timeout=25)
        finally:
            if child is not None and child.stdin:
                try: child.stdin.close()
                except BrokenPipeError: pass
        row = {'id': job_id, 'run_id': run_id, 'process_identity_json': json.dumps({'guardian': active['guardian']})}
        receipt = drain_receipt(row, wait_seconds=2)
        if not receipt or receipt['reason'] != 'completed' or receipt['exit_code'] != 0 or not receipt['logs_complete'] or not receipt['started']:
            raise RuntimeError('Delivery probe failed or exit is unconfirmed')
        record = read_json(directory / 'probe-result.json', 65536)
        proof = ExportValidation.model_validate(record['validation'])
        if set(record) != {'schema_version', 'available', 'runtime_binding', 'manifest_sha256', 'source_sha256', 'validation'} or record['schema_version'] != 1 or record['available'] is not True or record['manifest_sha256'] != digest_json(BASE_MANIFEST) or record['source_sha256'] != BASE_MANIFEST['sha256'] or proof.input_sha256 != digest_json({'manifest': BASE_MANIFEST, 'runtime': before}) or record['runtime_binding'] != digest_json(before) or before != runtime_identity() or str(proof.job_id) != job_id or str(proof.run_id) != run_id or proof.source_sha256 != BASE_MANIFEST['sha256']:
            raise RuntimeError('Delivery probe binding changed')
        if fingerprint(directory / 'model.onnx') != (proof.model_size_bytes, proof.model_sha256):
            raise RuntimeError('Delivery probe graph changed after drain')
        atomic_json(root / 'delivery-capability.json', record)


def main():
    try:
        run_probe()
    except Exception:
        print('Delivery probe unavailable; capability remains disabled')
        return 1
    print('Managed delivery probe passed; current capability saved')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
