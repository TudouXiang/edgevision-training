"""Lightweight package identity and fail-closed independent validation gate.

The gate intentionally cannot become available until the managed, genuinely
standalone probe writer and strict proof validator are implemented together.
An I probe or an arbitrary JSON file is not P proof.
"""
from pathlib import Path
from .inference_assets import runtime_identity as inference_identity
from .package_bundle import template_identity
from .run_files import fingerprint


def runtime_identity():
    value = inference_identity()
    for path in sorted(Path(__file__).parent.glob('package_*.py')):
        value['adapter'][path.name] = fingerprint(path)[1]
    value['package_template'] = template_identity()
    return value


def validated_template():
    raise ValueError('independent package validation not implemented')


def capability():
    return {'available': False, 'reason_code': 'PACKAGE_SETUP_REQUIRED',
            'reason': 'Independent package runtime validation is not yet available', 'detected_version': None}
