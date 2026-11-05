"""Fixed managed training entry, frozen inputs and bounded metric journal."""
from pathlib import Path
import shutil
import os
from .dataset_runner import log
from .dataset_storage import resolve_storage_file
from .run_files import atomic_json, fingerprint, read_json, run_directory
from .training_assets import BASE_KEY, digest_json, runtime_identity
from .training_contract import TrainingInput, MAX_METRIC_BYTES
from .training_inputs import verify_input, copy_input


def run(job_id, run_id):
    directory = run_directory(job_id, run_id)
    task = TrainingInput.model_validate(read_json(directory / "input.json")).model_dump(mode="json")
    if task["job_id"] != job_id or task["run_id"] != run_id: return 65
    frozen = verify_input(task["input"])
    if digest_json(runtime_identity()) != frozen["runtime_binding"]: return 67
    copy_input(frozen, directory)
    shutil.copyfile(resolve_storage_file(BASE_KEY), directory / "yolo11n.pt")
    log("Training input verified")
    count = 0
    journal = directory / "metrics.jsonl"
    from .job_service import canonical
    with journal.open("xb", buffering=0) as sink:
        def emit(epoch, name, value):
            nonlocal count
            count += 1
            event = {"schema_version": 1, "job_id": job_id, "run_id": run_id, "seq": count, "epoch": epoch, "name": name, "value": value}
            raw = (canonical(event) + "\n").encode()
            if count > 1000 or sink.tell() + len(raw) > MAX_METRIC_BYTES: raise ValueError("metric capacity exceeded")
            sink.write(raw)
            os.fsync(sink.fileno())
        from .training_runtime import train, TrainingPolicyError
        try:
            paths, runtime = train(directory, frozen["params"], frozen["classes"], frozen["files"], emit)
        except TrainingPolicyError:
            log("Training safety validation failed", "error")
            return 68
    verify_input(frozen)
    for entry in frozen["files"]:
        if entry["path"] != "data.yaml" and fingerprint(directory / "dataset" / entry["path"]) != (entry["size_bytes"], entry["sha256"]): return 66
    bundle = directory / "bundle"
    bundle.mkdir(mode=0o700)
    outputs = []
    for path in paths:
        destination = bundle / path.name
        shutil.copyfile(path, destination)
        size, digest = fingerprint(destination)
        outputs.append({"path": path.name, "size_bytes": size, "sha256": digest})
    metadata = {"schema_version": 1, "job_id": job_id, "run_id": run_id, "classes": frozen["classes"], "runtime": runtime,
                "input_sha256": digest_json(frozen), "metrics_size_bytes": fingerprint(journal)[0], "metrics_sha256": fingerprint(journal)[1], "metric_count": count}
    atomic_json(bundle / "metadata.json", metadata)
    size, digest = fingerprint(bundle / "metadata.json")
    outputs.append({"path": "metadata.json", "size_bytes": size, "sha256": digest})
    atomic_json(directory / "evidence.json", {"schema_version": 1, "job_id": job_id, "run_id": run_id,
        "input_sha256": digest_json(frozen), "outputs": outputs, "metric_count": count,
        "completed_epochs": runtime["completed_epochs"], "optimizer_steps": runtime["optimizer_steps"]})
    log("Training checkpoints verified")
    return 0
