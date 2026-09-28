"""Offline checks for project-local install/startup commands."""

import contextlib
import importlib.util
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallCommandTests(unittest.TestCase):
    def test_installer_targets_local_env_and_locked_web(self):
        install = load_script("install_deps")
        steps = install.install_steps({"uv": "/tools/uv", "npm": "/tools/npm.cmd"}, True, True)
        self.assertEqual(steps[0][0], ROOT / "backend")
        self.assertEqual(steps[1], (ROOT / "web", ["/tools/npm.cmd", "ci", "--no-audit", "--no-fund"]))
        self.assertIn("--no-python-downloads", steps[0][1])
        self.assertEqual(steps[0][1][steps[0][1].index("--python") + 1], sys.executable)

    def test_old_node_is_rejected_before_install(self):
        install = load_script("install_deps")
        with patch.object(install.shutil, "which", return_value="/tools/node"), patch.object(
            install.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v20.0.0\n")
        ):
            with self.assertRaisesRegex(RuntimeError, "Node 22.13"):
                install.prerequisites(False, True)

    def test_check_never_installs(self):
        install = load_script("install_deps")
        with patch.object(install, "prerequisites", return_value={"uv": "/tools/uv", "npm": "/tools/npm.cmd"}), patch.object(
            install.subprocess, "run"
        ) as runner, patch.object(sys, "argv", ["install_deps.py", "--check"]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(install.main(), 0)
        runner.assert_not_called()
        self.assertIn("NOT_RUN", output.getvalue())

    def test_backend_install_failure_stops_before_web(self):
        install = load_script("install_deps")
        with patch.object(install, "prerequisites", return_value={"uv": "/tools/uv", "npm": "/tools/npm.cmd"}), patch.object(
            install.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)
        ) as runner, patch.object(sys, "argv", ["install_deps.py"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install.main(), 7)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["cwd"], ROOT / "backend")
        self.assertEqual(runner.call_args.kwargs["env"]["UV_PROJECT_ENVIRONMENT"], str(ROOT / "backend" / ".venv"))

    def test_web_command_resolves_windows_style_executable_without_shell(self):
        dev = load_script("dev")
        with patch.object(dev.shutil, "which", return_value="C:\\Node\\npm.cmd"), patch.object(
            dev.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as runner:
            self.assertEqual(dev.main(["web"]), 0)
        args, kwargs = runner.call_args
        self.assertEqual(args[0], ["C:\\Node\\npm.cmd", "run", "dev"])
        self.assertEqual(kwargs["cwd"], ROOT / "web")
        self.assertFalse(kwargs.get("shell", False))


class WorkerLockTests(unittest.TestCase):
    def test_second_worker_cannot_hold_lock(self):
        from app.worker import worker_lock

        with tempfile.TemporaryDirectory() as directory:
            with worker_lock(Path(directory)):
                with self.assertRaises(BlockingIOError):
                    with worker_lock(Path(directory)):
                        pass

    def test_unsupported_job_exits_failed_and_orphan_stops_claims(self):
        job_id = str(uuid4())
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "platform.db"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE alembic_version (version_num TEXT)")
                db.execute("INSERT INTO alembic_version VALUES ('0002_foundation')")
                db.execute("CREATE TABLE jobs (id TEXT, status TEXT, created_at TEXT, started_at TEXT, heartbeat_at TEXT, worker_pid INTEGER, run_id TEXT, worker_instance TEXT, host_boot_id TEXT, child_pid INTEGER, child_pgid INTEGER, finished_at TEXT, error_code TEXT, error_message TEXT)")
                db.execute("CREATE TABLE job_events (job_id TEXT, seq INTEGER, kind TEXT, payload_json TEXT, created_at TEXT)")
                db.execute("INSERT INTO jobs (id,status,created_at) VALUES (?,?,?)", (job_id, "queued", "2026-09-28T00:00:00Z"))
            environment = {**os.environ, "PLATFORM_DATA_ROOT": directory}
            first = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=ROOT / "backend", env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            with sqlite3.connect(db_path) as db:
                self.assertEqual(db.execute("SELECT status,error_code FROM jobs WHERE id=?", (job_id,)).fetchone(), ("failed", "UNSUPPORTED_JOB"))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0], 2)
                db.execute("INSERT INTO jobs (id,status,created_at) VALUES (?,?,?)", (str(uuid4()), "running", "2026-09-28T00:00:01Z"))
            second = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=ROOT / "backend", env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(second.returncode, 4, second.stderr)


if __name__ == "__main__":
    unittest.main()
