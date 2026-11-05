"""Run the real T020/T030/T040 browser suite against disposable local services.

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
    return BACKEND / ".venv" / relative


def ensure_backend_python() -> None:
    expected = backend_python()
    if not expected.is_file():
        raise RuntimeError("backend/.venv is missing; run scripts/install_deps.py first")
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
    payload = {"schema_version": 1, "stage": stage, "status": status}
    if stage != "browser":
        payload["browser_status"] = "NOT_RUN"
    (report_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (report_dir / "summary.md").write_text(
        f"# T020/T030/T040 browser validation\n\n- Stage: `{stage}`\n- Status: `{status}`\n- Credentials, cookies, traces, screenshots, service logs, uploaded fixtures and database files are excluded.\n",
        encoding="utf-8",
    )


def record_cleanup(report_dir: Path, status: str) -> None:
    """Keep the actual browser outcome even when later cleanup fails."""
    try:
        payload = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("summary must be an object")
    except (OSError, ValueError):
        payload = {"schema_version": 1, "stage": "cleanup", "status": "failed", "browser_status": "NOT_RUN"}
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
    parser.add_argument("--list", action="store_true", help="discover tests without launching a browser")
    options = parser.parse_args(argv)
    playwright_args = ["--list"] if options.list else []
    run_stage = "discovery" if options.list else "browser"
    report_dir = options.report_dir.expanduser().resolve()
    safe_summary(report_dir, "bootstrap", "running")

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
    try:
        runtime = Path(tempfile.mkdtemp(prefix="edgevision-e2e-"))
        data_root = runtime / "data"
        data_root.mkdir()
        output_dir = runtime / "playwright-output"
        dataset_fixture = runtime / "tiny-dataset.zip"
        create_dataset_fixture(dataset_fixture)
        invalid_fixture = runtime / "invalid-dataset.zip"
        create_dataset_fixture(invalid_fixture, invalid=True)
        api_port, web_port = available_port(), available_port()
        while web_port == api_port:
            web_port = available_port()
        origin = f"http://127.0.0.1:{web_port}"
        service_environment = {
            **os.environ,
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
            "EDGEVISION_E2E_INVALID_DATASET_ZIP": str(invalid_fixture),
        }
        safe_summary(report_dir, run_stage, "running")
        result = subprocess.run(
            [npm, "run", "test:e2e", "--", *playwright_args],
            cwd=WEB,
            env=browser_environment,
            check=False,
        )
        try:
            recorded_status = json.loads((report_dir / "summary.json").read_text(encoding="utf-8")).get("status")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            recorded_status = None
        if recorded_status == "running" or recorded_status is None:
            fallback_status = "listed" if run_stage == "discovery" and result.returncode == 0 else ("passed" if result.returncode == 0 else "failed")
            safe_summary(report_dir, run_stage, fallback_status)
        return result.returncode
    except KeyboardInterrupt:
        safe_summary(report_dir, run_stage, "interrupted")
        return 130
    except (OSError, RuntimeError) as exc:
        safe_summary(report_dir, "bootstrap", "failed")
        print(f"browser_e2e bootstrap_failed: {exc}", file=sys.stderr)
        return 2
    finally:
        cleanup_safe = stop_owned((web_process, api_process, worker_process))
        if worker_process is not None and runtime is not None:
            try:
                from app.worker import recover, worker_lock
                with worker_lock(runtime / "data"):
                    cleanup_safe = (not recover()) and cleanup_safe
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
