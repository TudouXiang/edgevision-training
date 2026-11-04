"""Witnessed-exit, complete-bundle, intent/rename/CAS export publication."""
import json
import os
import stat
from uuid import uuid4
from .config import data_root
from .database import transaction
from .dataset_storage import safe_directory
from .job_service import canonical, transition
from .run_files import fingerprint, read_json, relative_file, run_directory
from .security import timestamp
from .training_assets import digest_json
from .export_assets import runtime_identity
from .export_contract import ExportEvidence, MAX_ONNX_BYTES, MAX_EXPORT_JSON_BYTES, tensor_hashes
from .export_inputs import verify_input, source_binding
from .export_service import provenance
from .schemas import ExportValidation, OnnxArtifactMetadata


def verify(job, bundle=None, connection=None):
    directory = run_directory(job['id'], job['run_id'])
    frozen = verify_input(json.loads(job['input_snapshot_json']), connection)
    if frozen['project_id'] != job['project_id'] or frozen['params'] != json.loads(job['payload_json']) or frozen['code_version'] != job['code_version']:
        raise ValueError('job input binding mismatch')
    if digest_json(runtime_identity()) != frozen['runtime_binding']:
        raise ValueError('export runtime changed')
    evidence = ExportEvidence.model_validate(read_json(directory / 'evidence.json', MAX_EXPORT_JSON_BYTES))
    if (str(evidence.job_id), str(evidence.run_id), evidence.input_sha256) != (job['id'], job['run_id'], digest_json(frozen)):
        raise ValueError('export evidence binding mismatch')
    bundle = bundle or directory / 'bundle'
    expected = {'model.onnx', 'metadata.json', 'validation.json'}
    if not stat.S_ISDIR(bundle.lstat().st_mode): raise ValueError('bundle directory invalid')
    actual = set()
    for item in bundle.rglob('*'):
        if not stat.S_ISREG(item.lstat().st_mode): raise ValueError('unexpected bundle file type')
        actual.add(item.relative_to(bundle).as_posix())
    if actual != expected or {entry.path for entry in evidence.outputs} != expected:
        raise ValueError('incomplete export bundle')
    entries = {}
    for entry in evidence.outputs:
        limit = MAX_ONNX_BYTES if entry.path == 'model.onnx' else MAX_EXPORT_JSON_BYTES
        path = relative_file(bundle, entry.path)
        if not 0 < entry.size_bytes <= limit or path.stat().st_size != entry.size_bytes or fingerprint(path) != (entry.size_bytes, entry.sha256):
            raise ValueError('export bundle fingerprint mismatch')
        entries[entry.path] = entry.model_dump()
    validation = ExportValidation.model_validate(read_json(bundle / 'validation.json', MAX_EXPORT_JSON_BYTES)).model_dump(mode='json')
    metadata = OnnxArtifactMetadata.model_validate(read_json(bundle / 'metadata.json', MAX_EXPORT_JSON_BYTES)).model_dump(mode='json')
    if metadata['provenance'] != provenance(frozen, job['id'], job['run_id']) or metadata['classes'] != frozen['source_metadata']['classes']:
        raise ValueError('metadata provenance mismatch')
    if metadata['validation'] != validation or metadata['validation_sha256'] != entries['validation.json']['sha256']:
        raise ValueError('validation document mismatch')
    if validation['model_sha256'] != entries['model.onnx']['sha256'] or validation['model_size_bytes'] != entries['model.onnx']['size_bytes']:
        raise ValueError('model validation fingerprint mismatch')
    if {sample['name']: sample['input_sha256'] for sample in validation['samples']} != tensor_hashes():
        raise ValueError('deterministic tensor protocol mismatch')
    return frozen, metadata, entries


def publish(job):
    # Defense in depth: callers cannot bypass witnessed tree exit.
    from .worker import drain_receipt
    receipt = drain_receipt(job)
    if not receipt or receipt['reason'] != 'completed' or receipt['exit_code'] != 0 or not receipt['logs_complete'] or not receipt['started']:
        raise ValueError('successful whole-tree exit is not proven')
    frozen, metadata, entries = verify(job)
    directory = run_directory(job['id'], job['run_id'])
    bundle_key = f"exports/{job['id']}/{job['run_id']}"
    intent = {'schema_version': 1, 'run_id': job['run_id'], 'bundle_key': bundle_key, 'outputs': entries}
    with transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        changed = connection.execute("UPDATE jobs SET publication_json=? WHERE id=? AND run_id=? AND status='running'", (canonical(intent), job['id'], job['run_id'])).rowcount
        if changed != 1: return False
    parent = safe_directory(data_root(), 'exports', job['id'])
    destination = parent / job['run_id']
    if destination.exists(): raise ValueError('immutable export publication already exists')
    os.rename(directory / 'bundle', destination)
    if os.name != 'nt':
        descriptor = os.open(parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    # Recheck the exact destination after rename, then serialize with cancellation.
    with transaction() as connection:
        connection.execute('BEGIN')
        frozen, metadata, entries = verify(job, destination, connection)
        binding = source_binding(connection, frozen)
    with transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        current = connection.execute('SELECT * FROM jobs WHERE id=? AND run_id=?', (job['id'], job['run_id'])).fetchone()
        if not current or current['status'] != 'running': return False
        if any(current[key] != job[key] for key in ('project_id', 'kind', 'run_id', 'input_snapshot_json', 'payload_json', 'code_version')) or current['publication_json'] != canonical(intent):
            raise ValueError('export job changed before publication')
        if source_binding(connection, frozen) != binding:
            raise ValueError('source records changed before publication')
        now = timestamp()
        entry = entries['model.onnx']
        connection.execute('INSERT INTO artifacts(id,project_id,job_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at,validated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (str(uuid4()), job['project_id'], job['id'], 'onnx', 'onnx', bundle_key + '/model.onnx', entry['sha256'], entry['size_bytes'], 'passed', canonical(metadata), now, now))
        connection.execute('UPDATE jobs SET environment_json=? WHERE id=?', (canonical(metadata['validation']['runtime']), job['id']))
        if not transition(connection, job['id'], 'running', 'succeeded', run_id=job['run_id'], process_exited=True, evidence_verified=True, fields={'launch_phase': 'finished'}):
            raise RuntimeError('export publication CAS failed')
    return True
