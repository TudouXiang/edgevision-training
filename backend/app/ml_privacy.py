"""Pre-import opt-out for the planned pinned ORT adapter, not a network sandbox."""
import importlib
from importlib import metadata
import os
import sys

_prepared = False


def prepare_ort_privacy():
    global _prepared
    if not _prepared and any(name == 'onnxruntime' or name.startswith('onnxruntime.') for name in sys.modules):
        raise RuntimeError('ORT was imported before privacy initialization')
    os.environ['ORT_DISABLE_TELEMETRY'] = '1'
    _prepared = True


def load_ort():
    prepare_ort_privacy()
    if metadata.version('onnxruntime') != '1.31.1':
        raise RuntimeError('Unverified ORT telemetry configuration version')
    ort = importlib.import_module('onnxruntime')
    ort.disable_telemetry_events()
    return ort
