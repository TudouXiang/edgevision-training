"""Fail-closed package gate: current strict three-stage standalone proof only."""
from pathlib import Path
from .inference_assets import runtime_identity as inference_identity
from .package_bundle import template_identity
from .package_launch import environment_identity,source_hashes,ROOT
from .package_probe_contract import PackageProbeRecord
from .run_files import fingerprint,read_json
from .training_assets import digest_json
from .config import data_root


def runtime_identity():
    value=inference_identity()
    reference_binding=digest_json(value);reference_code=digest_json(value['adapter'])
    for path in sorted(Path(__file__).parent.glob('package_*.py')):
        value['adapter'][path.name]=fingerprint(path)[1]
    for name in ('package_standalone.py','install_package.py'):
        value['adapter'][name]=fingerprint(ROOT/'scripts'/name)[1]
    value.update(package_template=template_identity(),package_environment=environment_identity(),
        reference_runtime_binding=reference_binding,reference_code_version=reference_code)
    return value


def validated_template():
    # Reject absent/incomplete proof before expensive runtime hashing. A valid
    # proof still requires every current environment and source check below.
    record=PackageProbeRecord.model_validate(read_json(data_root()/'package-capability.json',1024**2)).model_dump(mode='json')
    identity=runtime_identity()
    expected={'runtime_binding':digest_json(identity),'code_version':digest_json(identity['adapter']),
        'template':identity['package_template'],'environment_sha256':digest_json(identity['package_environment']),
        'reference_runtime_binding':identity['reference_runtime_binding'],'reference_code_version':identity['reference_code_version']}
    if any(record[k]!=v for k,v in expected.items()):raise ValueError('package proof is stale')
    for name in ('raw_task','cli_task'):
        if any(record[name][k]!=v for k,v in source_hashes().items()):raise ValueError('package proof entry changed')
    return {'template':record['template'],'record_sha256':digest_json(record)}


def capability():
    try:
        validated_template()
        return {'available':True,'reason_code':None,'reason':None,'detected_version':'edgevision-python-onnx-v1'}
    except (OSError,ValueError,KeyError,TypeError,ImportError):
        return {'available':False,'reason_code':'PACKAGE_SETUP_REQUIRED',
            'reason':'A current independent managed package template probe is required','detected_version':None}
