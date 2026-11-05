"""CI-only real HTTP/API-process restart probe; independent from browser claims.

Run explicitly with the isolated backend interpreter. Network tests are not
silently skipped; unavailable loopback networking makes this command fail.
"""
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic import command
from alembic.config import Config
from test_dataset_api import setup_admin, upload, headers, BACKEND
from test_worker_api import submit
from test_worker_process import start, run_path, wait_marker, wait_until, stop_and_reap, record
from app.config import SESSION_COOKIE_NAME
from app.process_identity import exited
from app.python_launch import python_child


def main():
    api = worker = None
    receipt_directory = None
    temporary = tempfile.mkdtemp(prefix="edgevision-http-restart-")
    cleanup_safe = False
    try:
        root = Path(temporary)
        os.environ["PLATFORM_DATA_ROOT"] = temporary
        os.environ["EDGEVISION_ALLOWED_ORIGINS"] = "http://127.0.0.1:5173"
        os.environ["EDGEVISION_COOKIE_SECURE"] = "false"
        configuration = Config(str(BACKEND / "alembic.ini"))
        configuration.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(configuration, "head")
        client, project = setup_admin(root)
        task = submit(client, upload(client, project).json()["id"])
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        url = f"http://127.0.0.1:{port}/api/v1/jobs/{task}"
        cookie = f"{SESSION_COOKIE_NAME}={client.cookies.get(SESSION_COOKIE_NAME)}"
        def request():
            try:
                with urlopen(Request(url, headers={"Cookie": cookie}), timeout=1) as response:
                    import json
                    return json.load(response)
            except OSError:
                return None
        def launch_api():
            args, environment = python_child([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"])
            return subprocess.Popen(args, env=environment,
                                    cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            worker = start("tree")
            directory = run_path(task)
            receipt_directory = directory
            identities = [wait_marker(directory, name) for name in ("started.json", "child.json", "grandchild.json")]
            api = launch_api()
            assert wait_until(request)["state"] == "running"
            first_pid = api.pid
            api.terminate()
            api.wait(timeout=10)
            assert worker.poll() is None and record(task)["status"] == "running"
            api = launch_api()
            assert api.pid != first_pid
            assert wait_until(request)["state"] == "running"
            assert worker.poll() is None
            client.post(f"/api/v1/jobs/{task}/cancel", headers=headers(client))
            assert worker.wait(timeout=15) == 0
            assert wait_until(request)["state"] == "cancelled"
            assert all(exited(value) for value in identities)
            print("http_api_restart=passed independent_worker=passed tree_exit=passed")
        finally:
            if api:
                stop_and_reap(api)
            if worker:
                stop_and_reap(worker)
            if receipt_directory and receipt_directory.exists():
                # Worker EOF owns cleanup even if the probe itself failed.
                receipt = wait_marker(receipt_directory, "drained.json")
                wait_until(lambda: exited(receipt["guardian"]))
            cleanup_safe = True
    finally:
        if cleanup_safe or worker is None:
            shutil.rmtree(temporary)
        else:
            print("http_api_restart cleanup failed: isolated runtime retained", file=sys.stderr)


if __name__ == "__main__":
    main()
