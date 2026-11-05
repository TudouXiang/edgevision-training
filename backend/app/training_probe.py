"""Explicit operator provision/probe. Never invoked from an HTTP request."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4
from .config import data_root
from .dataset_storage import safe_directory, resolve_storage_file
from .run_files import atomic_json, fingerprint, read_json, run_directory
from .training_assets import BASE_MANIFEST, BASE_KEY, MANIFEST_KEY, digest_json, runtime_identity, verify_asset


def probe_child(job_id, run_id):
    directory = run_directory(job_id, run_id)
    before = runtime_identity()
    verify_asset()
    shutil.copyfile(resolve_storage_file(BASE_KEY), directory / "yolo11n.pt")
    from .training_runtime import prepare_environment, initialize, TrainingPolicyError
    prepare_environment(directory)
    try:
        torch, torchvision, YOLO, DetectionModel, fail, fatal, loads = initialize(directory, {directory / "yolo11n.pt"})
        if (torch.tensor([[1., 2.]]) @ torch.tensor([[3.], [4.]])).item() != 11: fail("NATIVE_TORCH_FAILED")
        if torchvision.ops.nms(torch.tensor([[0., 0., 1., 1.]]), torch.tensor([1.]), .5).tolist() != [0]: fail("NATIVE_NMS_FAILED")
        model = YOLO(str(directory / "yolo11n.pt"), task="detect")
        if not isinstance(model.model, DetectionModel) or len(model.names) != 80 or fatal: fail("BASE_MODEL_INVALID")
        import ultralytics
        atomic_json(directory / "probe-result.json", {"schema_version": 1, "available": True, "device": "cpu", "runtime_binding": digest_json(before),
            "manifest_sha256": digest_json(BASE_MANIFEST), "versions": {"torch": torch.__version__, "torchvision": torchvision.__version__, "ultralytics": ultralytics.__version__}})
        return 0
    except TrainingPolicyError:
        return 68


def recover_probe():
    path = data_root() / "training-probe-active.json"
    if not path.exists(): return True
    from .worker import drain_receipt
    value = read_json(path, 16384)
    row = {"id": value["job_id"], "run_id": value["run_id"], "process_identity_json": json.dumps({"guardian": value.get("guardian")})}
    return drain_receipt(row, wait_seconds=20) is not None


def provision(source):
    path = Path(source)
    if fingerprint(path) != (BASE_MANIFEST["size_bytes"], BASE_MANIFEST["sha256"]): raise ValueError("Only the fixed verified official asset is accepted")
    directory = safe_directory(data_root(), "models", "base")
    target = directory / "yolo11n.pt"
    if target.exists():
        if fingerprint(target) != fingerprint(path): raise ValueError("Existing asset differs")
    else:
        with path.open("rb") as inp, target.open("xb") as out: shutil.copyfileobj(inp, out)
    atomic_json(directory / "manifest.json", BASE_MANIFEST)


def run_probe():
    from .worker import worker_lock, guardian_command, drain_receipt
    from .python_launch import python_child
    from .process_identity import identity
    root = data_root(); root.mkdir(parents=True, exist_ok=True)
    with worker_lock(root):
        if not recover_probe(): raise RuntimeError("Previous probe exit is unconfirmed")
        from .worker import recover
        if recover(): raise RuntimeError("Existing task exit is unconfirmed")
        atomic_json(root / "training-capability.json", {"schema_version": 1, "available": False})
        verify_asset()
        job_id, run_id = str(uuid4()), str(uuid4())
        directory = run_directory(job_id, run_id, create=True)
        atomic_json(directory / "input.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id, "kind": "ml_probe"})
        active = {"job_id": job_id, "run_id": run_id, "guardian": None}
        atomic_json(root / "training-probe-active.json", active)
        command, env = python_child(guardian_command(job_id, run_id))
        child = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=os.name != "nt")
        active["guardian"] = identity(child.pid)
        atomic_json(root / "training-probe-active.json", active)
        try:
            child.stdin.write(b"GO\n"); child.stdin.flush()
            try: child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                child.stdin.write(b"STOP\n"); child.stdin.flush()
                child.wait(timeout=25)
        finally:
            if child.stdin: child.stdin.close()
        row = {"id": job_id, "run_id": run_id, "process_identity_json": json.dumps({"guardian": active["guardian"]})}
        receipt = drain_receipt(row, wait_seconds=2)
        if not receipt or receipt["reason"] != "completed" or receipt["exit_code"] != 0: raise RuntimeError("Fixed CPU probe failed or exit is unconfirmed")
        record = read_json(directory / "probe-result.json", 65536)
        if record["runtime_binding"] != digest_json(runtime_identity()): raise RuntimeError("Probe runtime changed")
        atomic_json(root / "training-capability.json", record)


def main():
    parser = argparse.ArgumentParser(description="Provision only the fixed official YOLO11n asset and verify this interpreter's CPU runtime")
    parser.add_argument("--asset", help="Operator-owned local copy of the fixed official asset, exact hash required")
    args = parser.parse_args()
    if args.asset: provision(args.asset)
    run_probe()
    print("Fixed CPU runtime and asset verified; training capability record saved")

if __name__ == "__main__": main()
