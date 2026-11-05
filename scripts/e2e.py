"""Run the real T020–T060 browser suite against disposable local services.

The harness owns its temporary database and generated credentials. It never
loads a developer database, changes the production startup path, or writes
credentials to command lines, reports, or the repository.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from io import BytesIO
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"


def create_dataset_fixture(path: Path, invalid: bool = False) -> None:
    """Create a deterministic tiny synthetic dataset inside the disposable runtime."""
    from PIL import Image

    def raster(format_name: str) -> bytes:
        output = BytesIO()
        Image.new("RGB", (8, 8), (30, 100, 150)).save(output, format=format_name)
        return output.getvalue()

    values = {
        "data.yaml": b"train: images/train\nval: images/val\nnames: [object]\nnc: 1\n",
        "images/train/a.png": raster("PNG"),
        "labels/train/a.txt": b"9 0.5 0.5 0.5 0.5\n" if invalid else b"0 0.5 0.5 0.5 0.5\n",
        "images/val/b.jpg": raster("JPEG"),
        "labels/val/b.txt": b"",
    }
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in values.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)


def backend_python() -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    environment = ".venv-delivery" if "--delivery" in sys.argv else ".venv-ml" if "--ml" in sys.argv else ".venv"
    return BACKEND / environment / relative


def ensure_backend_python() -> None:
    expected = backend_python()
    if not expected.is_file():
        raise RuntimeError("selected backend environment is missing; install the matching locked environment first")
    if os.environ.get("EDGEVISION_E2E_REEXEC") == "1":
        return
    environment = {**os.environ, "EDGEVISION_E2E_REEXEC": "1"}
    os.execve(str(expected), [str(expected), str(Path(__file__).resolve()), *sys.argv[1:]], environment)


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for(url: str, process: subprocess.Popen[bytes], deadline_seconds: int = 30) -> None:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"service exited before readiness (code {code})")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError("service readiness deadline expired")


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def stop_owned(processes: tuple[subprocess.Popen[bytes] | None, ...]) -> bool:
    """Attempt every owned root even if an earlier stop cannot be confirmed."""
    confirmed = True
    for process in processes:
        try:
            stop(process)
        except (OSError, subprocess.TimeoutExpired):
            confirmed = False
    return confirmed


def start_process(args: list[str], cwd: Path, environment: dict[str, str]) -> subprocess.Popen[bytes]:
    if os.name == "nt" and os.path.normcase(args[0]) == os.path.normcase(sys.executable):
        # main already re-executed in backend/.venv; Node is not transformed.
        from app.python_launch import python_child
        args, environment = python_child(args, environment)
    return subprocess.Popen(
        args,
        cwd=cwd,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def interrupt_for_cleanup(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def safe_summary(report_dir: Path, stage: str, status: str) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    # A harness fallback is not a reporter receipt. Unknown discovery/counts
    # must not be replaced with zero or a successful browser claim.
    payload = {"schema_version": 2, "stage": stage, "status": status,
               "browser_status": "UNKNOWN" if stage == "browser" else "NOT_RUN",
               "evidence_available": False, "discovered": None, "counts": None,
               "outcomes": None, "attempts": None, "cases": []}
    (report_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (report_dir / "summary.md").write_text(
        f"# EdgeVision isolated browser validation\n\n- Stage: `{stage}`\n- Status: `{status}`\n- Browser status: `{payload['browser_status']}`\n- Reporter evidence unavailable; counts unknown.\n- Credentials, cookies, traces, screenshots, service logs, uploaded fixtures and database files are excluded.\n",
        encoding="utf-8",
    )


def valid_browser_receipt(payload: object) -> bool:
    """Check the closed anonymous schema and rebuild all aggregates from attempts."""
    statuses = ("passed", "failed", "timedOut", "interrupted", "skipped")
    outcome_names = ("expected", "unexpected", "flaky", "skipped", "NOT_RUN")

    def natural(value: object) -> bool:
        return type(value) is int and value >= 0

    def numeric_map(value: object, expected: dict) -> bool:
        return (isinstance(value, dict) and set(value) == set(expected)
                and all(natural(item) for item in value.values()) and value == expected)

    keys = {"schema_version", "stage", "status", "browser_status", "evidence_available",
            "discovered", "counts", "outcomes", "attempts", "reporter_errors", "cases"}
    if not (isinstance(payload, dict) and set(payload) == keys
            and type(payload["schema_version"]) is int and payload["schema_version"] == 2
            and payload["stage"] == "browser" and payload["evidence_available"] is True
            and payload["status"] in ("passed", "failed", "timedout", "interrupted")
            and natural(payload["discovered"]) and natural(payload["reporter_errors"])
            and isinstance(payload["cases"], list) and len(payload["cases"]) == payload["discovered"]):
        return False
    counts = dict.fromkeys((*statuses, "NOT_RUN", "executed", "expected_skipped", "unexpected_skipped"), 0)
    attempts = dict.fromkeys((*statuses, "total", "executed"), 0)
    outcomes = dict.fromkeys(outcome_names, 0)
    for number, case in enumerate(payload["cases"], 1):
        if not (isinstance(case, dict) and set(case) == {"case_number", "status", "outcome", "executed", "attempts"}
                and type(case["case_number"]) is int and case["case_number"] == number
                and type(case["executed"]) is bool and isinstance(case["attempts"], list)):
            return False
        results = case["attempts"]
        for retry, attempt in enumerate(results):
            if not (isinstance(attempt, dict) and set(attempt) == {"status", "expected_status", "retry", "duration_ms"}
                    and attempt["status"] in statuses and attempt["expected_status"] in statuses
                    and natural(attempt["retry"]) and attempt["retry"] == retry and natural(attempt["duration_ms"])):
                return False
            attempts[attempt["status"]] += 1
            attempts["total"] += 1
            attempts["executed"] += int(attempt["status"] != "skipped")
        final_status = results[-1]["status"] if results else "NOT_RUN"
        executed = any(attempt["status"] != "skipped" for attempt in results)
        # Playwright 1.64 computes outcome against the case's final expectedStatus,
        # ignores interrupted attempts, and separates expected/unexpected skips.
        outcome = "NOT_RUN"
        if results:
            expected_status = results[-1]["expected_status"]
            expected = sum(attempt["status"] == expected_status for attempt in results
                           if attempt["status"] not in ("skipped", "interrupted"))
            unexpected = sum(attempt["status"] != expected_status for attempt in results
                             if attempt["status"] not in ("skipped", "interrupted"))
            expected_skips = expected_status == "skipped" and any(attempt["status"] == "skipped" for attempt in results)
            outcome = ("skipped" if expected == unexpected == 0 else "expected" if unexpected == 0
                       else "unexpected" if expected == 0 and not expected_skips else "flaky")
        if case["status"] != final_status or case["executed"] != executed or case["outcome"] != outcome:
            return False
        counts[final_status] += 1
        counts["executed"] += int(executed)
        outcomes[outcome] += 1
        if final_status == "skipped":
            counts["expected_skipped" if results[-1]["expected_status"] == "skipped" else "unexpected_skipped"] += 1
    return (numeric_map(payload["counts"], counts) and numeric_map(payload["attempts"], attempts)
            and numeric_map(payload["outcomes"], outcomes)
            and payload["browser_status"] == (payload["status"] if counts["executed"] else "NOT_RUN")
            and (payload["status"] != "passed" or (outcomes["unexpected"] == 0 and payload["reporter_errors"] == 0)))


def browser_exit_code(report_dir: Path, returncode: int, require_all_passed: bool = False) -> int:
    """Require a valid receipt; opted-in ML must execute every discovered case."""
    try:
        # Bound untrusted input before decoding/parsing; never echo its contents.
        with (report_dir / "summary.json").open("rb") as receipt:
            raw = receipt.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("receipt too large")
        payload = json.loads(raw.decode("utf-8"))
        valid = valid_browser_receipt(payload)
    except (OSError, ValueError, RecursionError):
        valid = False
    if not valid:
        safe_summary(report_dir, "browser", "failed")
        return returncode or 2
    counts = payload["counts"]
    all_passed = (counts["executed"] > 0 and counts["passed"] == counts["executed"] == payload["discovered"]
                  and payload["reporter_errors"] == 0 and payload["outcomes"]["unexpected"] == 0
                  and payload["outcomes"]["flaky"] == 0)
    # Keep the actual receipt when the stricter mode rejects observed skips.
    if require_all_passed and not all_passed:
        return returncode or 2
    return returncode or (0 if payload["status"] == "passed" else 2)


def record_cleanup(report_dir: Path, status: str) -> None:
    """Keep the actual browser outcome even when later cleanup fails."""
    try:
        payload = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("summary must be an object")
    except (OSError, ValueError):
        payload = {"schema_version": 2, "stage": "cleanup", "status": "failed", "browser_status": "UNKNOWN", "evidence_available": False}
    payload["cleanup_status"] = status
    if status != "passed":
        payload["status"] = "failed"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with (report_dir / "summary.md").open("a", encoding="utf-8") as summary:
        summary.write(f"\n- Isolated runtime cleanup: {status}.\n")


def main(argv: list[str]) -> int:
    signal.signal(signal.SIGTERM, interrupt_for_cleanup)
    parser = argparse.ArgumentParser(description="Run isolated EdgeVision browser end-to-end tests")
    parser.add_argument("--report-dir", type=Path, default=WEB / "playwright-report")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ml", action="store_true", help="Run verified optional Linux CPU training browser scenario")
    mode.add_argument("--delivery", action="store_true", help="Run one-epoch training and ONNX export in the separately authorized isolated delivery environment")
    parser.add_argument("--ml-asset", type=Path, help="Separately downloaded fixed official YOLO11n asset")
    parser.add_argument("--list", action="store_true", help="discover tests without launching a browser")
    options = parser.parse_args(argv)
    training = options.ml or options.delivery
    playwright_args = ["--list"] if options.list else []
    run_stage = "discovery" if options.list else "browser"
    report_dir = options.report_dir.expanduser().resolve()
    safe_summary(report_dir, "bootstrap", "running")

    # Discovery is read-only: no Python environment, services, dataset or credentials.
    if options.list:
        npm = shutil.which("npm")
        if npm is None:
            safe_summary(report_dir, "discovery", "failed")
            return 2
        result = subprocess.run(
            [npm, "run", "test:e2e:list"], cwd=WEB,
            env={**os.environ, "EDGEVISION_E2E_REPORT_DIR": str(report_dir)}, check=False,
        )
        if result.returncode:
            safe_summary(report_dir, "discovery", "failed")
        return result.returncode
    if training and (options.ml_asset is None or not options.ml_asset.is_file()):
        safe_summary(report_dir, "bootstrap", "failed")
        print("browser_e2e bootstrap_failed: training/delivery requires an existing --ml-asset", file=sys.stderr)
        return 2

    try:
        ensure_backend_python()
    except RuntimeError as exc:
        safe_summary(report_dir, "bootstrap", "failed")
        print(f"browser_e2e bootstrap_failed: {exc}", file=sys.stderr)
        return 2

    python = backend_python()
    npm = shutil.which("npm")
    node = shutil.which("node")
    if npm is None or node is None:
        safe_summary(report_dir, "bootstrap", "failed")
        print("browser_e2e bootstrap_failed: Node.js/npm is missing", file=sys.stderr)
        return 2

    api_process: subprocess.Popen[bytes] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    worker_process: subprocess.Popen[bytes] | None = None
    runtime: Path | None = None
    managed_probe_started = False
    try:
        runtime = Path(tempfile.mkdtemp(prefix="edgevision-e2e-"))
        data_root = runtime / "data"
        data_root.mkdir()
        output_dir = runtime / "playwright-output"
        dataset_fixture = runtime / "tiny-dataset.zip"
        create_dataset_fixture(dataset_fixture)
        training_fixture = runtime / "training-dataset.zip"
        if training:
            from PIL import Image, ImageDraw
            with ZipFile(training_fixture, "w", ZIP_DEFLATED) as archive:
                archive.writestr("data.yaml", "train: images/train\nval: images/val\nnames: [object]\nnc: 1\n")
                for split in ("train", "val"):
                    for index in range(4):
                        image = Image.new("RGB", (64, 64), (20 + index * 10, 40, 80))
                        ImageDraw.Draw(image).rectangle((16, 16, 48, 48), fill=(220, 100, 40))
                        output = BytesIO(); image.save(output, format="PNG")
                        archive.writestr(f"images/{split}/{index}.png", output.getvalue())
                        archive.writestr(f"labels/{split}/{index}.txt", "0 0.5 0.5 0.5 0.5\n")
        invalid_fixture = runtime / "invalid-dataset.zip"
        create_dataset_fixture(invalid_fixture, invalid=True)
        api_port, web_port = available_port(), available_port()
        while web_port == api_port:
            web_port = available_port()
        origin = f"http://127.0.0.1:{web_port}"
        service_environment = {
            **os.environ,
            "ORT_DISABLE_TELEMETRY": "1",
            "PLATFORM_DATA_ROOT": str(data_root),
            "EDGEVISION_ALLOWED_ORIGINS": origin,
            "EDGEVISION_COOKIE_SECURE": "false",
            "EDGEVISION_DEV_API_PORT": str(api_port),
            "EDGEVISION_DEV_WEB_PORT": str(web_port),
            "PYTHONPATH": str(BACKEND),
        }

        migration = subprocess.run(
            [str(python), "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=service_environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if migration.returncode:
            raise RuntimeError(f"migration failed (code {migration.returncode})")

        os.environ.update({
            "ORT_DISABLE_TELEMETRY": "1",
            "PLATFORM_DATA_ROOT": str(data_root),
            "EDGEVISION_ALLOWED_ORIGINS": origin,
            "EDGEVISION_COOKIE_SECURE": "false",
        })
        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from app.admin_cli import create_admin

        run_id = uuid4().hex[:10]
        admin_username = f"e2e-admin-{run_id}"
        admin_password = f"E2e-{secrets.token_urlsafe(24)}-Aa1!"
        user_username = f"e2e-user-{run_id}"
        user_password = f"E2e-{secrets.token_urlsafe(24)}-Bb2!"
        rotated_password = f"E2e-{secrets.token_urlsafe(24)}-Cc3!"
        create_admin(admin_username, admin_password)

        if training:
            assert options.ml_asset is not None
            probes = [[str(python), "-m", "app.training_probe", "--asset", str(options.ml_asset.resolve())]]
            if options.delivery:
                probes.append([str(python), "-m", "app.export_probe"])
            for probe in probes:
                managed_probe_started = True
                result = subprocess.run(probe, cwd=BACKEND, env=service_environment, check=False,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=360)
                if result.returncode:
                    raise RuntimeError("managed capability probe failed; browser was not started")
        api_process = start_process(
            [
                str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                "--port", str(api_port), "--no-access-log",
            ],
            BACKEND,
            service_environment,
        )
        wait_for(f"http://127.0.0.1:{api_port}/api/v1/health/ready", api_process)

        worker_process = start_process([str(python), "-m", "app.worker"], BACKEND, service_environment)

        web_process = start_process(
            [node, str(WEB / "node_modules" / "vite" / "bin" / "vite.js"), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
            WEB,
            service_environment,
        )
        wait_for(f"{origin}/api/v1/health/ready", web_process)

        browser_environment = {
            **service_environment,
            "EDGEVISION_E2E_BASE_URL": origin,
            "EDGEVISION_E2E_ADMIN_USERNAME": admin_username,
            "EDGEVISION_E2E_ADMIN_PASSWORD": admin_password,
            "EDGEVISION_E2E_USER_USERNAME": user_username,
            "EDGEVISION_E2E_USER_PASSWORD": user_password,
            "EDGEVISION_E2E_ROTATED_PASSWORD": rotated_password,
            "EDGEVISION_E2E_REPORT_DIR": str(report_dir),
            "EDGEVISION_E2E_OUTPUT_DIR": str(output_dir),
            "EDGEVISION_E2E_DATASET_ZIP": str(dataset_fixture),
            "EDGEVISION_E2E_ML": "1" if training else "0",
            "EDGEVISION_E2E_DELIVERY": "1" if options.delivery else "0",
            "EDGEVISION_E2E_TRAINING_ZIP": str(training_fixture),
            "EDGEVISION_E2E_INVALID_DATASET_ZIP": str(invalid_fixture),
        }
        safe_summary(report_dir, run_stage, "running")
        result = subprocess.run(
            [npm, "run", "test:e2e", "--", *playwright_args],
            cwd=WEB,
            env=browser_environment,
            check=False,
        )
        return browser_exit_code(report_dir, result.returncode, require_all_passed=training)
    except KeyboardInterrupt:
        safe_summary(report_dir, run_stage, "interrupted")
        return 130
    except subprocess.TimeoutExpired:
        safe_summary(report_dir, "bootstrap", "failed")
        print("browser_e2e bootstrap_failed: managed capability probe timed out", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        safe_summary(report_dir, "bootstrap", "failed")
        print(f"browser_e2e bootstrap_failed: {exc}", file=sys.stderr)
        return 2
    finally:
        cleanup_safe = stop_owned((web_process, api_process, worker_process))
        if runtime is not None and (worker_process is not None or managed_probe_started):
            try:
                from app.worker import recover, worker_lock
                from app.training_probe import recover_probe
                with worker_lock(runtime / "data"):
                    cleanup_safe = recover_probe() and (not recover()) and cleanup_safe
            except Exception:
                cleanup_safe = False
        if not cleanup_safe:
            print("browser_e2e cleanup_blocked: service or task exit is unconfirmed; isolated runtime retained", file=sys.stderr)
            record_cleanup(report_dir, "failed")
            return 4
        if runtime is not None and cleanup_safe:
            try:
                shutil.rmtree(runtime)
            except OSError:
                time.sleep(0.2)
                try:
                    shutil.rmtree(runtime)
                except OSError:
                    record_cleanup(report_dir, "failed")
                    print("browser_e2e filesystem_cleanup_failed: isolated runtime retained", file=sys.stderr)
                    return 4
            if runtime.exists():
                record_cleanup(report_dir, "failed")
                return 4
            record_cleanup(report_dir, "passed")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
