"""Managed export child: verify, copy, execute fixed adapter, seal complete bundle."""
import shutil
from .dataset_runner import log
from .run_files import atomic_json, read_json, fingerprint, run_directory
from .export_contract import ExportInput, MAX_EXPORT_JSON_BYTES
from .export_assets import runtime_identity
from .export_inputs import verify_input, copy_input
from .export_service import provenance
from .training_assets import digest_json
from .schemas import OnnxArtifactMetadata


def run(job_id, run_id):
    directory = run_directory(job_id, run_id)
    task = ExportInput.model_validate(read_json(directory / 'input.json')).model_dump(mode='json')
    if task['job_id'] != job_id or task['run_id'] != run_id: return 65
    frozen = verify_input(task['input'])
    if digest_json(runtime_identity()) != frozen['runtime_binding']: return 67
    source = copy_input(frozen, directory)
    log('Export input verified')
    from .export_runtime import export_and_validate
    from .training_runtime import TrainingPolicyError
    try:
        model, validation = export_and_validate(directory, source, frozen['source_metadata']['classes'],
            job_id=job_id, run_id=run_id, input_sha256=digest_json(frozen), source_sha256=frozen['source_sha256'])
    except TrainingPolicyError:
        log('Export safety validation failed', 'error')
        return 68
    verify_input(frozen)
    if digest_json(runtime_identity()) != frozen['runtime_binding'] or fingerprint(source) != (frozen['source_size_bytes'], frozen['source_sha256']): return 66
    bundle = directory / 'bundle'
    bundle.mkdir(mode=0o700)
    shutil.copyfile(model, bundle / 'model.onnx')
    atomic_json(bundle / 'validation.json', validation)
    metadata = OnnxArtifactMetadata.model_validate({'schema_version': 1, 'task': 'detection', 'architecture': 'yolo11n',
        'classes': frozen['source_metadata']['classes'], 'provenance': provenance(frozen, job_id, run_id),
        'validation': validation, 'validation_sha256': fingerprint(bundle / 'validation.json')[1],
        'validation_scope': 'checker_ort_raw_tensor_equivalence'}).model_dump(mode='json')
    atomic_json(bundle / 'metadata.json', metadata)
    outputs = []
    for name in ('model.onnx', 'metadata.json', 'validation.json'):
        size, digest = fingerprint(bundle / name)
        if name != 'model.onnx' and size > MAX_EXPORT_JSON_BYTES: return 71
        outputs.append({'path': name, 'size_bytes': size, 'sha256': digest})
    atomic_json(directory / 'evidence.json', {'schema_version': 1, 'job_id': job_id, 'run_id': run_id,
        'input_sha256': digest_json(frozen), 'outputs': outputs})
    log('Export graph and fixed tensor comparisons verified')
    return 0
