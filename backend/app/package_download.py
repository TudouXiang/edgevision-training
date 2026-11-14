"""Historical package download verifies frozen lineage, not today's runtime."""
import json
from fastapi import HTTPException
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask
from .database import transaction
from .dataset_storage import resolve_storage_file
from .job_service import artifact_public
from .package_contract import FrozenPackage,MAX_PACKAGE_BYTES
from .inference_files import verified_file
from .package_publication import bundle_documents
from .package_service import provenance
from .schemas import PackageArtifactPublic

def verified_result(row):
    try:
        public = PackageArtifactPublic.model_validate(artifact_public(row)).model_dump(mode='json')
        with transaction() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='package' AND status='succeeded'", (row['job_id'], row['project_id'])).fetchone()
        if not job: raise ValueError('successful package missing')
        frozen = FrozenPackage.model_validate_json(job['input_snapshot_json']).model_dump(mode='json')
        if frozen['project_id'] != row['project_id'] or frozen['params'] != json.loads(job['payload_json']) or frozen['code_version'] != job['code_version'] or row['parent_id'] != frozen['model']['source_artifact_id']:
            raise ValueError('historical job binding changed')
        intent = json.loads(job['publication_json']); key = f"packages/{job['id']}/{job['run_id']}"
        if set(intent) != {'schema_version', 'run_id', 'bundle_key', 'outputs'} or type(intent['schema_version']) is not int or intent['schema_version'] != 1 or intent['run_id'] != job['run_id'] or intent['bundle_key'] != key or row['storage_key'] != key+'/package.zip':
            raise ValueError('package publication intent changed')
        if intent['outputs']['package.zip'] != {'path': 'package.zip', 'size_bytes': row['size_bytes'], 'sha256': row['sha256']}:
            raise ValueError('result row fingerprint changed')
        metadata, validation = bundle_documents(resolve_storage_file(row['storage_key']).parent, intent['outputs'], frozen)
        if metadata != public['metadata'] or metadata['provenance'] != provenance(frozen, job['id'], job['run_id']):
            raise ValueError('historical package provenance changed')
        return metadata, intent
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        raise HTTPException(409, {'code': 'ARTIFACT_UNAVAILABLE', 'message': 'Package publication is unavailable or changed'}) from exc


def download(row):
    _, intent = verified_result(row)
    name = 'package.zip'; entry = intent['outputs'][name]
    try:
        context = verified_file(resolve_storage_file(intent['bundle_key']+'/'+name), entry['size_bytes'], entry['sha256'], MAX_PACKAGE_BYTES)
        source = context.__enter__()
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, {'code': 'ARTIFACT_UNAVAILABLE', 'message': 'Package file changed'}) from exc
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
    headers['Content-Disposition'] = f'attachment; filename="edgevision-{row["id"]}.zip"'
    return VerifiedStream(chunks(), media_type='application/zip', headers=headers, background=BackgroundTask(close))
