"""Full trusted ONNX lineage reused without loading or executing model code."""
from contextlib import closing
import sqlite3
from .config import db_path
from .inference_inputs import model_snapshot, model_binding
from .inference_files import copy_stored
from .package_contract import FrozenPackage


def freeze_source(connection, project_id: str, onnx_artifact_id: str) -> dict:
    return model_snapshot(connection, project_id, onnx_artifact_id, 'onnx')


def verify_input(value: dict, connection=None) -> dict:
    frozen = FrozenPackage.model_validate(value).model_dump(mode='json')
    if connection is None:
        with closing(sqlite3.connect(f'file:{db_path()}?mode=ro', uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            return verify_input(frozen, connection)
    actual = freeze_source(connection, frozen['project_id'], frozen['params']['onnx_artifact_id'])
    if actual != frozen['model']:
        raise ValueError('frozen package source changed')
    return frozen


def source_binding(connection, frozen: dict) -> dict:
    return model_binding(connection, frozen['model'])


def copy_input(frozen: dict, directory):
    frozen = verify_input(frozen)
    model = frozen['model']
    path = copy_stored(model['source_key'], model['source_size_bytes'], model['source_sha256'],
                       128 * 1024**2, directory / 'model.onnx')
    verify_input(frozen)
    return path
