"""Fixed bootstrap: gate before importing any adapter or decoding its inputs."""
import sys


def main() -> int:
    if len(sys.argv) != 3 or sys.stdin.buffer.readline(16) != b"GO\n":
        return 125
    return execute(sys.argv[1], sys.argv[2])


def execute(job_id: str, run_id: str) -> int:
    # No user-controlled module, command or model is imported.
    from .dataset_runner import log, run
    from .run_files import read_json, run_directory
    kind = read_json(run_directory(job_id, run_id) / "input.json").get("kind")
    if kind == "train":
        from .training_runner import run
    elif kind == "export_onnx":
        from .export_runner import run
    elif kind == "export_probe":
        from .export_probe import probe_child as run
    elif kind == "ml_probe":
        from .training_probe import probe_child as run
    elif kind != "dataset_check":
        return 65
    from .run_files import OutputLimitError
    try:
        return run(job_id, run_id)
    except OutputLimitError:
        log("Validation report exceeds supported size", "error")
        return 71
    except OSError:
        log("Runner storage is unavailable", "error")
        return 70
    except Exception:
        log("Runner infrastructure failed", "error")
        return 72


if __name__ == "__main__":
    raise SystemExit(main())
