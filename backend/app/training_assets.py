"""Fixed asset supply and lightweight runtime bindings; never import Torch here."""
from hashlib import sha256
from importlib import metadata
import json
import platform
from pathlib import Path
import sys
from .config import data_root
from .dataset_storage import resolve_storage_file
from .job_service import canonical
from .run_files import fingerprint, read_json

BASE_MANIFEST = {
    "schema_version": 1, "model": "yolo11n.pt", "architecture": "yolo11n", "task": "detection",
    "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    "release": "v8.3.0", "asset_id": 196201276, "size_bytes": 5613764,
    "sha256": "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1",
    "license": "AGPL-3.0", "license_url": "https://docs.ultralytics.com/models/yolo11/",
    "publisher_digest": None,
}
BASE_KEY = "models/base/yolo11n.pt"
MANIFEST_KEY = "models/base/manifest.json"

def digest_json(value):
    return sha256(canonical(value).encode()).hexdigest()

def verify_asset():
    manifest = read_json(resolve_storage_file(MANIFEST_KEY), 16384)
    if manifest != BASE_MANIFEST or fingerprint(resolve_storage_file(BASE_KEY)) != (manifest["size_bytes"], manifest["sha256"]):
        raise ValueError("fixed base asset is unavailable or changed")
    return manifest

def runtime_identity():
    lock = Path(__file__).resolve().parents[1] / "requirements-ml-linux-cpu.lock"
    packages = {}
    for line in lock.read_text().splitlines():
        if not line or line.startswith("#"): continue
        name, version = line.split(" --hash=")[0].split("==")
        dist = metadata.distribution(name)
        if dist.version != version: raise ValueError("installed distribution version mismatch")
        record = dist.read_text("RECORD")
        if not record: raise ValueError("installed distribution record unavailable")
        packages[name] = {"version": version, "record_sha256": sha256(record.encode()).hexdigest()}
    source = {}
    for name in ("ml_privacy.py", "python_launch.py", "training_runtime.py", "training_runner.py", "training_assets.py", "training_contract.py", "training_inputs.py", "training_probe.py", "schemas.py", "task_process.py"):
        source[name] = fingerprint(Path(__file__).parent / name)[1]
    return {"python": platform.python_version(), "platform": sys.platform, "machine": platform.machine(),
            "executable": str(Path(sys.executable).absolute()), "executable_sha256": fingerprint(Path(sys.executable).resolve())[1],
            "lock_sha256": fingerprint(lock)[1], "packages": packages, "adapter": source}

def capability():
    try:
        manifest = verify_asset()
        identity = runtime_identity()
        record = read_json(data_root() / "training-capability.json", 65536)
        expected = {"schema_version", "available", "runtime_binding", "manifest_sha256", "versions", "device"}
        if set(record) != expected or record["schema_version"] != 1 or record["available"] is not True or record["device"] != "cpu" or record["runtime_binding"] != digest_json(identity) or record["manifest_sha256"] != digest_json(manifest):
            raise ValueError("stale probe")
        return {"available": True, "reason_code": None, "reason": None, "detected_version": record["versions"]["ultralytics"]}
    except (OSError, ValueError, KeyError, TypeError, metadata.PackageNotFoundError):
        return {"available": False, "reason_code": "TRAINING_SETUP_REQUIRED", "reason": "Fixed CPU runtime, trusted weights and a current operator probe are required", "detected_version": None}
