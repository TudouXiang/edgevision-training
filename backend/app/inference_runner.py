"""Managed infer runner: source copies, actual native execution, three-file seal."""
from .dataset_runner import log
from .run_files import read_json, run_directory, atomic_json, fingerprint
from .inference_contract import InferenceInput, InferenceEvidence, MAX_INFERENCE_JSON_BYTES, MAX_PREVIEW_BYTES
from .inference_inputs import verify_input, copy_input
from .inference_files import verified_file, write_bytes
from .inference_assets import runtime_identity
from .inference_service import provenance
from .inference_errors import ImageInferenceError, error_exit, INFERENCE_EXIT_ERRORS, inference_boundary
from .schemas import InferenceDocument, InferenceResultMetadata
from .training_assets import digest_json


def run(job_id, run_id):
    directory = run_directory(job_id, run_id)
    try: task = InferenceInput.model_validate(read_json(directory / 'input.json')).model_dump(mode='json')
    except ValueError: return 65
    if task['job_id'] != job_id or task['run_id'] != run_id: return 65
    with inference_boundary('source'): frozen = verify_input(task['input'])
    with inference_boundary('runtime'):
        identity = runtime_identity()
        if digest_json(identity) != frozen['runtime_binding'] or digest_json(identity['adapter']) != frozen['code_version']: return 67
    with inference_boundary('source'): model_path, image_path = copy_input(frozen, directory)
    log('Inference immutable sources verified')
    from .inference_runtime import execute_image
    from .training_runtime import TrainingPolicyError
    model, image, params = frozen['model'], frozen['image'], frozen['params']
    try:
        fields, _, preview = execute_image(directory, model_path, image_path, image['metadata']['declared_format'],
            params['backend'], model['source_metadata']['classes'], params['confidence'], params['iou'])
    except ImageInferenceError as exc:
        code = error_exit(exc); log(INFERENCE_EXIT_ERRORS.get(code, 'Inference failed'), 'error'); return code
    except TrainingPolicyError:
        log('Inference safety policy failed', 'error'); return 91
    with inference_boundary('source'): verify_input(frozen)
    with inference_boundary('runtime'):
        if digest_json(runtime_identity()) != frozen['runtime_binding']: return 67
    for path, size, digest, limit in ((model_path, model['source_size_bytes'], model['source_sha256'], 128*1024**2), (image_path, image['image_size_bytes'], image['image_sha256'], 50*1024**2)):
        with inference_boundary('source'):
            with verified_file(path, size, digest, limit): pass
    document = InferenceDocument.model_validate({'schema_version': 1, 'protocol': 'detection-image-v1',
        'provenance': provenance(frozen, job_id, run_id), 'params': params, **fields}).model_dump(mode='json')
    bundle = directory / 'bundle'; bundle.mkdir(mode=0o700)
    write_bytes(bundle / 'preview.png', preview, MAX_PREVIEW_BYTES)
    atomic_json(bundle / 'result.json', document)
    size, digest = fingerprint(bundle / 'result.json')
    if size > MAX_INFERENCE_JSON_BYTES: return 71
    metadata = InferenceResultMetadata.model_validate({'schema_version': 1, 'protocol': 'detection-image-v1',
        'provenance': document['provenance'], 'result_sha256': digest, 'result_size_bytes': size,
        'preview': document['preview'], 'validation_scope': 'real_single_image_inference'}).model_dump(mode='json')
    atomic_json(bundle / 'metadata.json', metadata)
    outputs = []
    for name in ('result.json', 'metadata.json', 'preview.png'):
        size, digest = fingerprint(bundle / name)
        if size > (MAX_PREVIEW_BYTES if name == 'preview.png' else MAX_INFERENCE_JSON_BYTES): return 71
        outputs.append({'path': name, 'size_bytes': size, 'sha256': digest})
    evidence = InferenceEvidence.model_validate({'schema_version': 1, 'job_id': job_id, 'run_id': run_id,
        'frozen_input_sha256': digest_json(frozen), 'outputs': outputs}).model_dump(mode='json')
    atomic_json(directory / 'evidence.json', evidence)
    log('Real image inference result sealed')
    return 0
