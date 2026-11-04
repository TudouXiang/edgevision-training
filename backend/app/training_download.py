"""Hash and stream the same bounded open model descriptor."""
from hashlib import sha256
import os
import stat
from fastapi import HTTPException
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask
from .dataset_storage import resolve_storage_file
from .training_contract import MAX_PT_BYTES


def download_pt(row, artifact_id):
    source = None
    try:
        if row["validation_status"] != "passed" or not 0 < row["size_bytes"] <= MAX_PT_BYTES: raise ValueError("model unverified")
        path = resolve_storage_file(row["storage_key"])
        source = path.open("rb")
        details = os.fstat(source.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size != row["size_bytes"]: raise ValueError("model size changed")
        digest = sha256(); size = 0
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_PT_BYTES: raise ValueError("model bound exceeded")
            digest.update(chunk)
        if size != row["size_bytes"] or digest.hexdigest() != row["sha256"]: raise ValueError("model changed")
        source.seek(0)
    except (OSError, ValueError, RuntimeError) as exc:
        if source: source.close()
        raise HTTPException(409, {"code": "ARTIFACT_UNAVAILABLE", "message": "Model is missing or its fingerprint changed"}) from exc
    def chunks():
        try:
            remaining = row["size_bytes"]
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk: return
                remaining -= len(chunk)
                yield chunk
        finally: source.close()
    class VerifiedStream(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                source.close()
    return VerifiedStream(chunks(), media_type="application/octet-stream", background=BackgroundTask(source.close), headers={"Content-Length": str(row["size_bytes"]), "Content-Disposition": f'attachment; filename="{row["kind"]}-{artifact_id}.pt"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
