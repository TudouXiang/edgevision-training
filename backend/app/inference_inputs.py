"""Trusted same-project sources; repeat full lineage and byte checks at boundaries."""
from contextlib import closing
import json
import sqlite3
import stat
from .config import db_path
from .dataset_storage import resolve_storage_file
from .export_inputs import source_snapshot as pt_snapshot, verify_input as verify_export_input, source_binding as pt_binding
from .export_download import verify_published_onnx
from .inference_contract import FrozenInference, FrozenImage, TrustedPT, TrustedOnnx
from .inference_files import check_stored, copy_stored
from .job_service import artifact_public
from .schemas import InferenceInputArtifactPublic
from .training_assets import digest_json


def check_bundle(key, entries, limits):
    parent = resolve_storage_file(key + '/' + next(iter(limits))).parent
    if not stat.S_ISDIR(parent.lstat().st_mode) or set(entries) != set(limits): raise ValueError('source bundle invalid')
    if {p.name for p in parent.iterdir()} != set(limits): raise ValueError('source bundle members changed')
    for name, limit in limits.items():
        entry = entries[name]
        if set(entry) != {'path', 'size_bytes', 'sha256'} or entry['path'] != name: raise ValueError('source entry invalid')
        check_stored(key + '/' + name, entry['size_bytes'], entry['sha256'], limit)


def model_snapshot(connection, project_id, artifact_id, backend):
    row = connection.execute('SELECT * FROM artifacts WHERE id=? AND project_id=?', (artifact_id, project_id)).fetchone()
    if not row or row['validation_status'] != 'passed' or row['metadata_schema_version'] != 1:
        raise ValueError('model source is not passed')
    if backend == 'pt':
        value = pt_snapshot(connection, project_id, artifact_id)
        job = connection.execute('SELECT * FROM jobs WHERE id=?', (row['job_id'],)).fetchone()
        intent = json.loads(job['publication_json'])
        check_bundle(intent['bundle_key'], intent['outputs'], {'best.pt': 128*1024**2, 'last.pt': 128*1024**2, 'metadata.json': 65536})
        return TrustedPT.model_validate({'backend': 'pt', **value}).model_dump(mode='json')
    if backend != 'onnx' or row['kind'] != 'onnx' or row['format'] != 'onnx': raise ValueError('source model format mismatch')
    job, frozen, metadata, intent = verify_published_onnx(row, connection)
    verify_export_input(frozen, connection)  # Historical E capability is deliberately irrelevant.
    # Revalidate the parent's full train bundle, not just its selected checkpoint.
    model_snapshot(connection, project_id, frozen['source_artifact_id'], 'pt')
    check_bundle(intent['bundle_key'], intent['outputs'], {'model.onnx': 128*1024**2, 'metadata.json': 1024**2, 'validation.json': 1024**2})
    return TrustedOnnx.model_validate({'backend': 'onnx', 'project_id': project_id,
        'source_artifact_id': artifact_id, 'source_job_id': job['id'], 'source_key': row['storage_key'],
        'source_sha256': row['sha256'], 'source_size_bytes': row['size_bytes'], 'source_metadata': metadata,
        'source_metadata_sha256': digest_json(metadata), 'export_input': frozen}).model_dump(mode='json')


def image_snapshot(connection, project_id, artifact_id):
    row = connection.execute('SELECT * FROM artifacts WHERE id=? AND project_id=?', (artifact_id, project_id)).fetchone()
    if not row or row['parent_id'] is not None: raise ValueError('image source missing')
    public = InferenceInputArtifactPublic.model_validate(artifact_public(row)).model_dump(mode='json')
    extension = 'png' if public['format'] == 'png' else 'jpg'
    if row['storage_key'] != f'images/{artifact_id}/source.{extension}': raise ValueError('image source key changed')
    check_stored(row['storage_key'], row['size_bytes'], row['sha256'], 50*1024**2)
    return FrozenImage.model_validate({'artifact_id': artifact_id, 'project_id': project_id, 'key': row['storage_key'],
        'image_sha256': row['sha256'], 'image_size_bytes': row['size_bytes'], 'metadata': public['metadata']}).model_dump(mode='json')


def verify_input(value, connection=None):
    frozen = FrozenInference.model_validate(value).model_dump(mode='json')
    if connection is None:
        with closing(sqlite3.connect(f'file:{db_path()}?mode=ro', uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row; connection.execute('PRAGMA query_only=ON'); connection.execute('BEGIN')
            return verify_input(frozen, connection)
    model = model_snapshot(connection, frozen['project_id'], frozen['params']['model_artifact_id'], frozen['params']['backend'])
    image = image_snapshot(connection, frozen['project_id'], frozen['params']['image_artifact_id'])
    if frozen['model'] != model or frozen['image'] != image: raise ValueError('frozen inference source changed')
    return frozen


def model_binding(connection, model):
    root = model if model['backend'] == 'pt' else model['export_input']
    result = pt_binding(connection, root)
    for label, table, identifier in [('model', 'artifacts', model['source_artifact_id']), ('model_job', 'jobs', model['source_job_id'])]:
        row = connection.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if not row: raise ValueError('source row disappeared')
        result[label] = dict(row)
    return result


def source_binding(connection, frozen):
    result = model_binding(connection, frozen['model'])
    row = connection.execute('SELECT * FROM artifacts WHERE id=?', (frozen['image']['artifact_id'],)).fetchone()
    if not row: raise ValueError('image row disappeared')
    result['image'] = dict(row)
    return result


def copy_input(frozen, directory):
    frozen = verify_input(frozen)
    model, image = frozen['model'], frozen['image']
    model_path = copy_stored(model['source_key'], model['source_size_bytes'], model['source_sha256'], 128*1024**2, directory / ('model.' + model['backend']))
    image_path = copy_stored(image['key'], image['image_size_bytes'], image['image_sha256'], 50*1024**2, directory / ('image.' + image['metadata']['declared_format']))
    verify_input(frozen)
    return model_path, image_path
