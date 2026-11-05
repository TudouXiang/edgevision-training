"""Delivery runtime identity and managed-probe freshness without importing ML."""
from importlib import metadata
from pathlib import Path
from .config import data_root
from .run_files import fingerprint, read_json
from .training_assets import runtime_identity as training_identity, digest_json, verify_asset
from .schemas import ExportValidation


def runtime_identity():
    value = training_identity()
    lock = Path(__file__).resolve().parents[1] / 'requirements-delivery-linux-cpu.lock'
    # Parent supplies the independently verified full joint lock. Its absence fails closed.
    from hashlib import sha256
    packages = {}
    for line in lock.read_text().splitlines():
        if not line or line.startswith('#'): continue
        name, version = line.split(' --hash=')[0].split('==')
        dist = metadata.distribution(name)
        if dist.version != version: raise ValueError('delivery distribution version mismatch')
        record = dist.read_text('RECORD')
        if not record: raise ValueError('delivery distribution record unavailable')
        packages[name] = {'version': version, 'record_sha256': sha256(record.encode()).hexdigest()}
    if any(packages.get(name, {}).get('version') != version for name, version in {'onnx': '1.23.2', 'onnxruntime': '1.31.1'}.items()):
        raise ValueError('fixed delivery runtime missing')
    if any(packages.get(name) != record for name, record in value['packages'].items()):
        raise ValueError('delivery lock does not preserve training environment')
    for name in ('export_assets.py', 'export_contract.py', 'export_inputs.py', 'export_runtime.py', 'export_runner.py', 'export_probe.py', 'export_publication.py', 'export_service.py', 'export_download.py', 'training_download.py', 'training_inputs.py', 'training_service.py', 'worker.py', 'guardian.py', 'run_files.py', 'job_service.py', 'database.py', 'config.py', 'dataset_storage.py', 'process_identity.py', 'process_linux.py', 'process_windows.py'):
        value['adapter'][name] = fingerprint(Path(__file__).parent / name)[1]
    value.update(delivery_lock_sha256=fingerprint(lock)[1], delivery_packages=packages)
    return value


def capability():
    try:
        identity = runtime_identity()
        manifest = verify_asset()
        record = read_json(data_root() / 'delivery-capability.json', 65536)
        if set(record) != {'schema_version', 'available', 'runtime_binding', 'manifest_sha256', 'validation', 'source_sha256'} or record['schema_version'] != 1 or record['available'] is not True or record['runtime_binding'] != digest_json(identity) or record['manifest_sha256'] != digest_json(manifest) or record['source_sha256'] != manifest['sha256']:
            raise ValueError('delivery probe missing or stale')
        proof = ExportValidation.model_validate(record['validation'])
        if proof.source_sha256 != manifest['sha256'] or proof.input_sha256 != digest_json({'manifest': manifest, 'runtime': identity}):
            raise ValueError('probe source or input mismatch')
        from .export_contract import tensor_hashes
        if {sample.name: sample.input_sha256 for sample in proof.samples} != tensor_hashes():
            raise ValueError('probe tensor protocol changed')
        return {'available': True, 'reason_code': None, 'reason': None, 'detected_version': proof.runtime.versions.onnxruntime}
    except (OSError, ValueError, KeyError, TypeError, metadata.PackageNotFoundError):
        return {'available': False, 'reason_code': 'DELIVERY_SETUP_REQUIRED', 'reason': 'Fixed delivery runtime and a current managed export probe are required', 'detected_version': None}
