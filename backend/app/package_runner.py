"""Managed package construction: integrity only, no model/native execution."""
from .dataset_runner import log
from .run_files import read_json, run_directory, atomic_json, fingerprint
from .package_contract import PackageInput, PackageEvidence, PackageValidation
from .package_inputs import verify_input
from .package_bundle import build_bundle
from .package_assets import runtime_identity, validated_template
from .package_service import provenance
from .schemas import PackageArtifactMetadata
from .training_assets import digest_json


def check_runtime(frozen, identity, proof):
    if (digest_json(identity) != frozen['runtime_binding'] or digest_json(identity['adapter']) != frozen['code_version']
        or identity['package_template'] != frozen['template'] or proof['template'] != frozen['template']
        or proof['record_sha256'] != frozen['template_validation_sha256']):
        raise ValueError('package runtime or validation changed')


def run(job_id, run_id):
    directory = run_directory(job_id,run_id)
    try:
        task = PackageInput.model_validate(read_json(directory/'input.json')).model_dump(mode='json')
        if task['job_id'] != job_id or task['run_id'] != run_id: return 65
        frozen = verify_input(task['input'])
    except (ValueError,KeyError,TypeError): return 65
    try: check_runtime(frozen,runtime_identity(),validated_template())
    except (ValueError,KeyError,TypeError,ImportError): return 67
    bundle = directory/'bundle';bundle.mkdir(mode=0o700)
    result = build_bundle(frozen,bundle)
    verify_input(frozen)
    check_runtime(frozen,runtime_identity(),validated_template())
    metadata = PackageArtifactMetadata.model_validate({'schema_version':1,'protocol':'edgevision-python-onnx-v1',
        'provenance':provenance(frozen,job_id,run_id),'template':frozen['template'],
        'package_sha256':result['sha256'],'package_size_bytes':result['size_bytes'],
        'manifest_sha256':result['manifest_sha256'],'manifest_size_bytes':result['manifest_size_bytes'],
        'template_validation_sha256':frozen['template_validation_sha256'],
        'validation_scope':'trusted_model_fixed_package_integrity','standalone_execution':'not_run_for_this_artifact'}).model_dump(mode='json')
    validation = PackageValidation.model_validate({'schema_version':1,'metadata':metadata,'manifest':result['manifest']}).model_dump(mode='json')
    atomic_json(bundle/'metadata.json',metadata);atomic_json(bundle/'validation.json',validation)
    outputs=[]
    for name in ('package.zip','metadata.json','validation.json'):
        size,digest=fingerprint(bundle/name);outputs.append({'path':name,'size_bytes':size,'sha256':digest})
    evidence=PackageEvidence.model_validate({'schema_version':1,'job_id':job_id,'run_id':run_id,'input_sha256':digest_json(frozen),'outputs':outputs}).model_dump(mode='json')
    atomic_json(directory/'evidence.json',evidence)
    log('Package integrity sealed; per-artifact standalone execution not performed')
    return 0
