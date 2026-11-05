"""Authorized-ID download validates complete bindings, then streams one descriptor."""
import json
from fastapi import HTTPException
from .database import transaction
from .schemas import ArtifactPublic, OnnxArtifactMetadata, ExportValidation
from .job_service import artifact_public
from .training_download import download_model
from .export_contract import MAX_ONNX_BYTES, MAX_EXPORT_JSON_BYTES, FrozenExport, tensor_hashes
from .export_service import provenance
from .dataset_storage import resolve_storage_file
from .run_files import read_json, fingerprint


def download_onnx(row, artifact_id):
    try:
        public = ArtifactPublic.model_validate(artifact_public(row)).model_dump(mode='json')
        with transaction() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='export_onnx' AND status='succeeded'", (row['job_id'], row['project_id'])).fetchone()
        if not job: raise ValueError('successful export missing')
        frozen = FrozenExport.model_validate_json(job['input_snapshot_json']).model_dump(mode='json')
        if frozen['project_id'] != row['project_id'] or frozen['params'] != json.loads(job['payload_json']) or frozen['code_version'] != job['code_version']:
            raise ValueError('export job binding changed')
        intent = json.loads(job['publication_json'])
        key = f"exports/{job['id']}/{job['run_id']}"
        if set(intent) != {'schema_version', 'run_id', 'bundle_key', 'outputs'} or intent['schema_version'] != 1 or intent['run_id'] != job['run_id'] or intent['bundle_key'] != key or row['storage_key'] != key + '/model.onnx' or set(intent['outputs']) != {'model.onnx', 'metadata.json', 'validation.json'}:
            raise ValueError('publication intent mismatch')
        documents = {}
        for name in ('metadata.json', 'validation.json'):
            path = resolve_storage_file(key + '/' + name)
            entry = intent['outputs'][name]
            if entry['path'] != name or not 0 < entry['size_bytes'] <= MAX_EXPORT_JSON_BYTES or path.stat().st_size != entry['size_bytes'] or fingerprint(path) != (entry['size_bytes'], entry['sha256']):
                raise ValueError('published document changed')
            documents[name] = read_json(path, MAX_EXPORT_JSON_BYTES)
        metadata = OnnxArtifactMetadata.model_validate(documents['metadata.json']).model_dump(mode='json')
        validation = ExportValidation.model_validate(documents['validation.json']).model_dump(mode='json')
        if metadata != public['metadata'] or metadata['provenance'] != provenance(frozen, job['id'], job['run_id']) or metadata['validation'] != validation or metadata['validation_sha256'] != intent['outputs']['validation.json']['sha256']:
            raise ValueError('published provenance changed')
        if {sample['name']: sample['input_sha256'] for sample in validation['samples']} != tensor_hashes():
            raise ValueError('published tensor protocol mismatch')
        if intent['outputs']['model.onnx'] != {'path': 'model.onnx', 'size_bytes': row['size_bytes'], 'sha256': row['sha256']}:
            raise ValueError('published model binding changed')
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        raise HTTPException(409, {'code': 'ARTIFACT_UNAVAILABLE', 'message': 'Export validation or successful provenance is unavailable'}) from exc
    return download_model(row, artifact_id, limit=MAX_ONNX_BYTES, extension='onnx')
