"""Complete image bundle validation and witnessed intent/rename/CAS publication."""
import json
import os
import stat
from uuid import uuid4
from .config import data_root
from .database import transaction
from .dataset_storage import safe_directory
from .job_service import canonical, transition
from .run_files import read_json, run_directory, relative_file
from .security import timestamp
from .inference_contract import FrozenInference, InferenceEvidence, MAX_INFERENCE_JSON_BYTES, MAX_PREVIEW_BYTES
from .inference_inputs import verify_input, source_binding
from .inference_files import verified_file
from .inference_assets import runtime_identity
from .inference_service import provenance
from .training_assets import digest_json
from .schemas import InferenceDocument, InferenceResultMetadata


def bundle_documents(bundle, entries):
    limits = {'result.json': MAX_INFERENCE_JSON_BYTES, 'metadata.json': MAX_INFERENCE_JSON_BYTES, 'preview.png': MAX_PREVIEW_BYTES}
    if not stat.S_ISDIR(bundle.lstat().st_mode) or set(entries) != set(limits): raise ValueError('inference bundle invalid')
    if {item.name for item in bundle.iterdir()} != set(limits): raise ValueError('inference bundle members changed')
    documents = {}
    for name, limit in limits.items():
        entry = entries[name]
        if set(entry) != {'path', 'size_bytes', 'sha256'} or entry['path'] != name: raise ValueError('inference member invalid')
        path = relative_file(bundle, name)
        with verified_file(path, entry['size_bytes'], entry['sha256'], limit) as source:
            if name.endswith('.json'):
                content = source.read(entry['size_bytes']+1)
                from hashlib import sha256
                if len(content) != entry['size_bytes'] or sha256(content).hexdigest() != entry['sha256']: raise ValueError('document changed')
                documents[name] = json.loads(content)
    document = InferenceDocument.model_validate(documents['result.json']).model_dump(mode='json')
    metadata = InferenceResultMetadata.model_validate(documents['metadata.json']).model_dump(mode='json')
    if metadata['provenance'] != document['provenance'] or metadata['preview'] != document['preview']:
        raise ValueError('image document metadata mismatch')
    if (metadata['result_size_bytes'], metadata['result_sha256']) != (entries['result.json']['size_bytes'], entries['result.json']['sha256']):
        raise ValueError('result fingerprint mismatch')
    if (document['preview']['size_bytes'], document['preview']['sha256']) != (entries['preview.png']['size_bytes'], entries['preview.png']['sha256']):
        raise ValueError('preview fingerprint mismatch')
    # Verify public dimensions without decoding untrusted bytes in API/Worker.
    with verified_file(relative_file(bundle, 'preview.png'), entries['preview.png']['size_bytes'], entries['preview.png']['sha256'], MAX_PREVIEW_BYTES) as source:
        header = source.read(33)
    import struct
    if len(header) != 33 or header[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR' or header[24:29] != b'\x08\x02\x00\x00\x00' or struct.unpack('>II', header[16:24]) != (document['preview']['width'], document['preview']['height']):
        raise ValueError('preview encoded geometry mismatch')
    return document, metadata


def verify(job, bundle=None, connection=None):
    directory = run_directory(job['id'], job['run_id'])
    frozen = verify_input(json.loads(job['input_snapshot_json']), connection)
    if job['kind'] != 'infer' or frozen['project_id'] != job['project_id'] or frozen['params'] != json.loads(job['payload_json']) or frozen['code_version'] != job['code_version']:
        raise ValueError('inference job changed')
    if digest_json(runtime_identity()) != frozen['runtime_binding']: raise ValueError('image runtime changed')
    if read_json(directory / 'input.json') != {'schema_version': 1, 'job_id': job['id'], 'run_id': job['run_id'], 'kind': 'infer', 'input': frozen}:
        raise ValueError('managed input file changed')
    model, image = frozen['model'], frozen['image']
    for path, size, digest, limit in ((directory / ('model.'+model['backend']), model['source_size_bytes'], model['source_sha256'], 128*1024**2),
                                   (directory / ('image.'+image['metadata']['declared_format']), image['image_size_bytes'], image['image_sha256'], 50*1024**2)):
        with verified_file(path, size, digest, limit): pass
    evidence = InferenceEvidence.model_validate(read_json(directory / 'evidence.json', MAX_INFERENCE_JSON_BYTES))
    if (str(evidence.job_id), str(evidence.run_id), evidence.frozen_input_sha256) != (job['id'], job['run_id'], digest_json(frozen)):
        raise ValueError('inference evidence changed')
    entries = {entry.path: entry.model_dump(mode='json') for entry in evidence.outputs}
    document, metadata = bundle_documents(bundle or directory / 'bundle', entries)
    if document['provenance'] != provenance(frozen, job['id'], job['run_id']) or document['params'] != frozen['params'] or document['classes'] != frozen['model']['source_metadata']['classes'] or document['image']['format'] != frozen['image']['metadata']['declared_format']:
        raise ValueError('inference provenance changed')
    return frozen, metadata, entries, document


def publish(job):
    from .worker import drain_receipt
    receipt = drain_receipt(job)
    if not receipt or receipt['reason'] != 'completed' or receipt['exit_code'] != 0 or not receipt['logs_complete'] or not receipt['started']:
        raise ValueError('successful tree exit unconfirmed')
    frozen, metadata, entries, document = verify(job)
    key = f"inferences/{job['id']}/{job['run_id']}"
    intent = {'schema_version': 1, 'run_id': job['run_id'], 'bundle_key': key, 'outputs': entries}
    with transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("UPDATE jobs SET publication_json=? WHERE id=? AND run_id=? AND status='running'", (canonical(intent), job['id'], job['run_id'])).rowcount != 1: return False
    parent = safe_directory(data_root(), 'inferences', job['id']); destination = parent / job['run_id']
    if destination.exists(): raise ValueError('immutable result destination exists')
    os.rename(run_directory(job['id'], job['run_id']) / 'bundle', destination)
    if os.name != 'nt':
        descriptor = os.open(parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    with transaction() as connection:
        connection.execute('BEGIN')
        frozen, metadata, entries, document = verify(job, destination, connection)
        binding = source_binding(connection, frozen)
    with transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        current = connection.execute('SELECT * FROM jobs WHERE id=? AND run_id=?', (job['id'], job['run_id'])).fetchone()
        if not current or current['status'] != 'running': return False
        if any(current[k] != job[k] for k in ('project_id', 'kind', 'run_id', 'input_snapshot_json', 'payload_json', 'code_version')) or current['publication_json'] != canonical(intent):
            raise ValueError('inference job changed before publication')
        if source_binding(connection, frozen) != binding: raise ValueError('source changed before publication')
        entry, now = entries['result.json'], timestamp()
        connection.execute('INSERT INTO artifacts(id,project_id,job_id,parent_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at,validated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (str(uuid4()), job['project_id'], job['id'], frozen['model']['source_artifact_id'], 'inference_result', 'json', key+'/result.json', entry['sha256'], entry['size_bytes'], 'passed', canonical(metadata), now, now))
        connection.execute('UPDATE jobs SET environment_json=? WHERE id=?', (canonical(document['runtime']), job['id']))
        if not transition(connection, job['id'], 'running', 'succeeded', run_id=job['run_id'], process_exited=True, evidence_verified=True):
            raise RuntimeError('inference publication CAS lost')
    return True
