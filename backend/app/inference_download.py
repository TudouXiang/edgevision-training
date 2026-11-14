"""Historical inference verification, independent of current runtime capability."""
import json
from fastapi import HTTPException
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask
from .database import transaction
from .dataset_storage import resolve_storage_file
from .job_service import artifact_public
from .inference_contract import FrozenInference, MAX_INFERENCE_JSON_BYTES, MAX_PREVIEW_BYTES
from .inference_files import verified_file
from .inference_publication import bundle_documents
from .inference_service import provenance
from .schemas import InferenceResultArtifactPublic


def verified_result(row):
    try:
        public = InferenceResultArtifactPublic.model_validate(artifact_public(row)).model_dump(mode='json')
        with transaction() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='infer' AND status='succeeded'", (row['job_id'], row['project_id'])).fetchone()
        if not job: raise ValueError('successful inference missing')
        frozen = FrozenInference.model_validate_json(job['input_snapshot_json']).model_dump(mode='json')
        if frozen['project_id'] != row['project_id'] or frozen['params'] != json.loads(job['payload_json']) or frozen['code_version'] != job['code_version'] or row['parent_id'] != frozen['model']['source_artifact_id']:
            raise ValueError('historical job binding changed')
        intent = json.loads(job['publication_json']); key = f"inferences/{job['id']}/{job['run_id']}"
        if set(intent) != {'schema_version', 'run_id', 'bundle_key', 'outputs'} or type(intent['schema_version']) is not int or intent['schema_version'] != 1 or intent['run_id'] != job['run_id'] or intent['bundle_key'] != key or row['storage_key'] != key+'/result.json':
            raise ValueError('inference publication intent changed')
        if intent['outputs']['result.json'] != {'path': 'result.json', 'size_bytes': row['size_bytes'], 'sha256': row['sha256']}:
            raise ValueError('result row fingerprint changed')
        document, metadata = bundle_documents(resolve_storage_file(row['storage_key']).parent, intent['outputs'])
        if metadata != public['metadata'] or document['provenance'] != provenance(frozen, job['id'], job['run_id']) or document['classes'] != frozen['model']['source_metadata']['classes'] or document['params'] != frozen['params'] or document['image']['format'] != frozen['image']['metadata']['declared_format']:
            raise ValueError('historical inference provenance changed')
        return document, intent
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        raise HTTPException(409, {'code': 'ARTIFACT_UNAVAILABLE', 'message': 'Inference publication is unavailable or changed'}) from exc


def result(row):
    document, _ = verified_result(row)
    return {**document, 'artifact_id': row['id'], 'image_url': f"/api/v1/inferences/{row['id']}/image"}


def download(row, *, preview=False):
    _, intent = verified_result(row)
    name = 'preview.png' if preview else 'result.json'; entry = intent['outputs'][name]
    try:
        context = verified_file(resolve_storage_file(intent['bundle_key']+'/'+name), entry['size_bytes'], entry['sha256'], MAX_PREVIEW_BYTES if preview else MAX_INFERENCE_JSON_BYTES)
        source = context.__enter__()
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, {'code': 'ARTIFACT_UNAVAILABLE', 'message': 'Inference file changed'}) from exc
    def close(): context.__exit__(None, None, None)
    def chunks():
        try:
            remaining = entry['size_bytes']
            while remaining:
                chunk = source.read(min(1024**2, remaining))
                if not chunk: return
                remaining -= len(chunk); yield chunk
        finally: close()
    class VerifiedStream(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try: await super().__call__(scope, receive, send)
            finally: close()
    headers = {'Content-Length': str(entry['size_bytes']), 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
    if not preview: headers['Content-Disposition'] = f'attachment; filename="inference-{row["id"]}.json"'
    return VerifiedStream(chunks(), media_type='image/png' if preview else 'application/json', headers=headers, background=BackgroundTask(close))
