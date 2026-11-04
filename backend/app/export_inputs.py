"""Repeat source ownership, terminal-state, metadata and byte checks at every boundary."""
import json
import shutil
import sqlite3
from contextlib import closing
from .config import db_path
from .dataset_storage import resolve_storage_file
from .export_contract import FrozenExport, MAX_ONNX_BYTES
from .run_files import fingerprint, read_json
from .training_assets import digest_json
from .training_contract import FrozenTraining
from .training_inputs import verify_input as verify_training_input
from .training_service import provenance as training_provenance
from .schemas import TrainingArtifactMetadata


def source_snapshot(connection, project_id, artifact_id):
    row = connection.execute("SELECT * FROM artifacts WHERE id=? AND project_id=?", (artifact_id, project_id)).fetchone()
    if not row or row['kind'] not in {'pt_best', 'pt_last'} or row['format'] != 'pt' or row['validation_status'] != 'passed' or row['metadata_schema_version'] != 1:
        raise ValueError('source is not a passed platform checkpoint')
    job = connection.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='train' AND status='succeeded'", (row['job_id'], project_id)).fetchone()
    if not job:
        raise ValueError('source training did not succeed in this project')
    # A database row and replacement bytes alone cannot impersonate a published PT.
    intent = json.loads(job['publication_json'])
    expected_key = f"trained/{job['id']}/{job['run_id']}"
    filename = 'best.pt' if row['kind'] == 'pt_best' else 'last.pt'
    if set(intent) != {'schema_version', 'run_id', 'bundle_key', 'outputs'} or intent['schema_version'] != 1 or intent['run_id'] != job['run_id'] or intent['bundle_key'] != expected_key or row['storage_key'] != expected_key + '/' + filename or set(intent['outputs']) != {'best.pt', 'last.pt', 'metadata.json'}:
        raise ValueError('source publication binding changed')
    if intent['outputs'][filename] != {'path': filename, 'size_bytes': row['size_bytes'], 'sha256': row['sha256']}:
        raise ValueError('source publication fingerprint changed')
    meta_entry = intent['outputs']['metadata.json']
    meta_path = resolve_storage_file(expected_key + '/metadata.json')
    if meta_entry['path'] != 'metadata.json' or not 0 < meta_entry['size_bytes'] <= 65536 or meta_path.stat().st_size != meta_entry['size_bytes'] or fingerprint(meta_path) != (meta_entry['size_bytes'], meta_entry['sha256']):
        raise ValueError('source published metadata changed')
    original_metadata = read_json(meta_path, 65536)
    metadata = TrainingArtifactMetadata.model_validate_json(row['metadata_json']).model_dump(mode='json')
    training = FrozenTraining.model_validate_json(job['input_snapshot_json']).model_dump(mode='json')
    if metadata['provenance'] != training_provenance(training) or metadata['classes'] != training['classes'] or metadata['runtime'] != json.loads(job['environment_json']):
        raise ValueError('source training metadata mismatch')
    if original_metadata.get('job_id') != job['id'] or original_metadata.get('run_id') != job['run_id'] or original_metadata.get('input_sha256') != digest_json(training) or original_metadata.get('classes') != training['classes'] or original_metadata.get('runtime') != metadata['runtime']:
        raise ValueError('source original metadata mismatch')
    if metadata['runtime']['completed_epochs'] != training['params']['epochs']:
        raise ValueError('source training epoch mismatch')
    dataset = connection.execute("SELECT * FROM datasets WHERE id=? AND project_id=? AND status='ready'", (training['dataset_id'], project_id)).fetchone()
    report = connection.execute("SELECT * FROM artifacts WHERE id=? AND project_id=? AND kind='dataset_report' AND validation_status='passed'", (training['report_artifact_id'], project_id)).fetchone()
    if not dataset or not report or dataset['version'] != training['dataset_version'] or dataset['sha256'] != training['archive_sha256'] or dataset['snapshot_key'] != training['snapshot_key'] or dataset['report_key'] != training['report_key'] or json.loads(dataset['classes_json']) != training['classes'] or json.loads(dataset['counts_json']) != training['counts']:
        raise ValueError('source dataset binding mismatch')
    if (report['storage_key'], report['size_bytes'], report['sha256']) != (training['report_key'], training['report_size_bytes'], training['report_sha256']):
        raise ValueError('source report binding mismatch')
    path = resolve_storage_file(row['storage_key'])
    if not 0 < row['size_bytes'] <= MAX_ONNX_BYTES or path.stat().st_size != row['size_bytes'] or fingerprint(path) != (row['size_bytes'], row['sha256']):
        raise ValueError('source checkpoint changed')
    verify_training_input(training)
    return {'project_id': project_id, 'source_artifact_id': artifact_id, 'source_job_id': job['id'],
        'source_key': row['storage_key'], 'source_sha256': row['sha256'], 'source_size_bytes': row['size_bytes'],
        'source_metadata': metadata, 'source_metadata_sha256': digest_json(metadata), 'training_input': training,
        'source_training_input_sha256': digest_json(training)}


def verify_input(value, connection=None):
    frozen = FrozenExport.model_validate(value).model_dump(mode='json')
    if connection is None:
        with closing(sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            return verify_input(frozen, connection)
    current = source_snapshot(connection, frozen['project_id'], frozen['source_artifact_id'])
    if any(frozen[key] != value for key, value in current.items()):
        raise ValueError('frozen source binding changed')
    return frozen


def copy_input(frozen, directory):
    frozen = verify_input(frozen)
    if shutil.disk_usage(directory).free < frozen['source_size_bytes'] + 512 * 1024**2:
        raise OSError('insufficient export disk budget')
    target = directory / 'source.pt'
    with resolve_storage_file(frozen['source_key']).open('rb') as source, target.open('xb') as sink:
        # The bounded copy rejects growth and never copies arbitrary external files.
        remaining = frozen['source_size_bytes']
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk: raise ValueError('source truncated')
            sink.write(chunk)
            remaining -= len(chunk)
        if source.read(1): raise ValueError('source grew')
    if fingerprint(target) != (frozen['source_size_bytes'], frozen['source_sha256']):
        raise ValueError('copied source changed')
    verify_input(frozen)
    return target


def source_binding(connection, frozen):
    """Small number of immutable DB rows, with no filesystem/runtime work.

    Capture under the same read snapshot used for full validation; compare under
    the final writer lock. Raw JSON strings preserve exact frozen row bindings.
    """
    references = (
        ('artifact', 'artifacts', frozen['source_artifact_id']),
        ('training', 'jobs', frozen['source_job_id']),
        ('dataset', 'datasets', frozen['training_input']['dataset_id']),
        ('report', 'artifacts', frozen['training_input']['report_artifact_id']),
    )
    result = {}
    for label, table, identifier in references:
        row = connection.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if row is None: raise ValueError('source binding disappeared')
        result[label] = dict(row)
    return result
