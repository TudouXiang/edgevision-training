"""Offline checks for project-local install/startup commands."""

import contextlib
import copy
import importlib.util
import io
import json
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

    def test_api_and_web_port_overrides_keep_local_entrypoints(self):
        dev = load_script("dev")
        with patch.dict(os.environ, {"EDGEVISION_DEV_API_PORT": "18000", "EDGEVISION_DEV_WEB_PORT": "15173"}), patch.object(
            dev, "backend_python", return_value="C:\\backend\\python.exe"
        ), patch.object(dev, "run", return_value=0) as runner:
            self.assertEqual(dev.main(["api"]), 0)
            self.assertEqual(runner.call_args.args[-2:], ("--port", "18000"))
            self.assertEqual(dev.main(["web"]), 0)
            self.assertEqual(runner.call_args.args[-4:], ("--", "--port", "15173", "--strictPort"))

    def test_invalid_port_stops_before_launch(self):
        dev = load_script("dev")
        with patch.dict(os.environ, {"EDGEVISION_DEV_API_PORT": "18000 --reload"}), patch.object(
            dev, "backend_python", return_value="C:\\backend\\python.exe"
        ), patch.object(dev, "run") as runner, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dev.main(["api"]), 2)
            runner.assert_not_called()


class BrowserCleanupTests(unittest.TestCase):
    @staticmethod
    def receipt(status="passed", skipped=0):
        return {"schema_version": 2, "stage": "browser", "status": status,
                "browser_status": status if skipped < 5 else "NOT_RUN", "evidence_available": True, "discovered": 5,
                "reporter_errors": 0,
                "counts": {"passed": 5 - skipped, "failed": 0, "timedOut": 0, "interrupted": 0,
                           "skipped": skipped, "NOT_RUN": 0, "executed": 5 - skipped,
                           "expected_skipped": skipped, "unexpected_skipped": 0},
                "outcomes": {"expected": 5 - skipped, "unexpected": 0, "flaky": 0, "skipped": skipped, "NOT_RUN": 0},
                "attempts": {"passed": 5 - skipped, "failed": 0, "timedOut": 0, "interrupted": 0,
                             "skipped": skipped, "total": 5, "executed": 5 - skipped},
                "cases": [{"case_number": i + 1, "status": "skipped" if i < skipped else "passed",
                           "outcome": "skipped" if i < skipped else "expected", "executed": i >= skipped,
                           "attempts": [{"status": "skipped" if i < skipped else "passed",
                                         "expected_status": "skipped" if i < skipped else "passed",
                                         "retry": 0, "duration_ms": 12}]} for i in range(5)]}

    def test_closed_receipt_rejects_missing_unknown_and_contradictory_fields(self):
        script = load_script("e2e")
        mutations = [
            (("cases",), [None] * 5), (("cases", 0), {"case_number": 1}),
            (("cases", 0, "case_number"), 2), (("cases", 0, "case_number"), True),
            (("cases", 0, "status"), "skipped"), (("cases", 0, "outcome"), "flaky"),
            (("cases", 0, "executed"), False), (("cases", 0, "executed"), 1),
            (("cases", 0, "attempts"), []), (("cases", 0, "attempts"), [None]),
            (("cases", 0, "attempts", 0, "status"), "UNKNOWN"),
            (("cases", 0, "attempts", 0, "expected_status"), "failed"),
            (("cases", 0, "attempts", 0, "retry"), 1),
            (("cases", 0, "attempts", 0, "duration_ms"), -1),
            (("cases", 0, "attempts", 0, "duration_ms"), True),
            (("cases", 0, "attempts", 0, "duration_ms"), float("nan")),
            (("attempts", "passed"), 4), (("attempts", "executed"), 4),
            (("outcomes", "expected"), 4), (("reporter_errors",), 1),
            (("reporter_errors",), True), (("counts", "passed"), True),
            (("cases", 0, "title"), "PRIVATE-SENTINEL"),
            (("cases", 0, "attempts", 0, "stack"), "PRIVATE-SENTINEL"),
            (("raw_error",), "PRIVATE-SENTINEL"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, value in mutations:
                with self.subTest(path=path):
                    payload = self.receipt()
                    target = payload
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = value
                    (root / "summary.json").write_text(json.dumps(payload))
                    self.assertEqual(script.browser_exit_code(root, 0, require_all_passed=True), 2)
                    self.assertEqual(json.loads((root / "summary.json").read_text())["browser_status"], "UNKNOWN")
                    self.assertNotIn("PRIVATE-SENTINEL", (root / "summary.json").read_text() + (root / "summary.md").read_text())
            for path in (("outcomes",), ("attempts",), ("reporter_errors",), ("cases", 0, "status"),
                         ("cases", 0, "attempts", 0, "expected_status")):
                payload = self.receipt()
                target = payload
                for key in path[:-1]:
                    target = target[key]
                del target[path[-1]]
                self.assertFalse(script.valid_browser_receipt(payload))

    def test_oversized_invalid_encoding_and_deep_json_fail_anonymously(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in (b" " * (1024 * 1024 + 1), b"\xff", b"[" * 2000 + b"]" * 2000):
                (root / "summary.json").write_bytes(raw)
                self.assertEqual(script.browser_exit_code(root, 17, require_all_passed=True), 17)
                self.assertEqual(json.loads((root / "summary.json").read_text())["browser_status"], "UNKNOWN")

    def test_recomputed_retry_skip_failure_and_not_run_outcomes(self):
        script = load_script("e2e")
        base = self.receipt()
        # Keep four ordinary passed cases, vary the fifth with explicit expected aggregates.
        scenarios = [
            ([], "NOT_RUN", "NOT_RUN", False),
            ([("failed", "passed")], "failed", "unexpected", True),
            ([("timedOut", "passed")], "timedOut", "unexpected", True),
            ([("interrupted", "passed")], "interrupted", "skipped", True),
            ([("failed", "failed")], "failed", "expected", True),
            ([("skipped", "passed")], "skipped", "skipped", False),
            ([("failed", "passed"), ("passed", "passed")], "passed", "flaky", True),
            ([("failed", "passed"), ("skipped", "skipped")], "skipped", "flaky", True),
            ([("failed", "passed"), ("skipped", "passed")], "skipped", "unexpected", True),
        ]
        for results, status, outcome, executed in scenarios:
            with self.subTest(status=status, outcome=outcome, results=results):
                payload = copy.deepcopy(base)
                payload["status"] = payload["browser_status"] = "failed"
                case = payload["cases"][-1]
                case.update(status=status, outcome=outcome, executed=executed,
                            attempts=[{"status": actual, "expected_status": expected, "retry": i, "duration_ms": 1}
                                      for i, (actual, expected) in enumerate(results)])
                payload["counts"]["passed"] -= 1
                payload["counts"][status] += 1
                payload["counts"]["executed"] += int(executed) - 1
                if status == "skipped":
                    payload["counts"]["expected_skipped" if results[-1][1] == "skipped" else "unexpected_skipped"] += 1
                payload["outcomes"]["expected"] -= 1
                payload["outcomes"][outcome] += 1
                payload["attempts"]["passed"] -= 1
                payload["attempts"]["total"] += len(results) - 1
                payload["attempts"]["executed"] += sum(actual != "skipped" for actual, _ in results) - 1
                for actual, _ in results:
                    payload["attempts"][actual] += 1
                self.assertTrue(script.valid_browser_receipt(payload))
                payload["cases"][-1]["outcome"] = "expected" if outcome != "expected" else "unexpected"
                self.assertFalse(script.valid_browser_receipt(payload))

    def test_opted_in_ml_rejects_valid_flaky_pass_receipt(self):
        script = load_script("e2e")
        payload = self.receipt()
        case = payload["cases"][0]
        case["attempts"][0]["retry"] = 1
        case["attempts"].insert(0, {"status": "failed", "expected_status": "passed", "retry": 0, "duration_ms": 1})
        case["outcome"] = "flaky"
        payload["outcomes"].update(expected=4, flaky=1)
        payload["attempts"].update(failed=1, total=6, executed=6)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "summary.json").write_text(json.dumps(payload))
            self.assertEqual(script.browser_exit_code(root, 0), 0)
            self.assertEqual(script.browser_exit_code(root, 0, require_all_passed=True), 2)
            self.assertEqual(json.loads((root / "summary.json").read_text()), payload)

    def test_opted_in_ml_rejects_skips_but_default_allows_them(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for skipped in (0, 1):
                original = self.receipt(skipped=skipped)
                (root / "summary.json").write_text(json.dumps(original))
                self.assertEqual(script.browser_exit_code(root, 0), 0)
                self.assertEqual(script.browser_exit_code(root, 0, require_all_passed=True), 2 if skipped else 0)
                self.assertEqual(script.browser_exit_code(root, 7, require_all_passed=True), 7)
                self.assertEqual(json.loads((root / "summary.json").read_text()), original)

    def test_invalid_count_receipts_are_unknown(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for field, value in (("counts", None), ("discovered", True), ("cases", []), ("status", [])):
                original = self.receipt()
                original[field] = value
                (root / "summary.json").write_text(json.dumps(original))
                self.assertEqual(script.browser_exit_code(root, 0, require_all_passed=True), 2)
                self.assertEqual(json.loads((root / "summary.json").read_text())["browser_status"], "UNKNOWN")
            original = self.receipt()
            original["counts"]["executed"] = 6
            (root / "summary.json").write_text(json.dumps(original))
            self.assertEqual(script.browser_exit_code(root, 9, require_all_passed=True), 9)

    def test_harness_fallback_does_not_invent_browser_execution(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for stage, browser_status in (("bootstrap", "NOT_RUN"), ("discovery", "NOT_RUN"), ("browser", "UNKNOWN")):
                script.safe_summary(root, stage, "failed")
                result = json.loads((root / "summary.json").read_text())
                self.assertEqual(result["schema_version"], 2)
                self.assertEqual(result["browser_status"], browser_status)
                self.assertFalse(result["evidence_available"])
                self.assertIsNone(result["discovered"])
                self.assertIsNone(result["counts"])
                self.assertIsNone(result["attempts"])

    def test_missing_receipt_during_cleanup_is_unknown_not_not_run(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script.record_cleanup(root, "failed")
            result = json.loads((root / "summary.json").read_text())
            self.assertEqual(result["browser_status"], "UNKNOWN")
            self.assertFalse(result["evidence_available"])

    def test_process_success_without_terminal_receipt_is_not_success(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for content in (None, "{", "[]", '{"status": "passed"}',
                            '{"schema_version": 2, "stage": "browser", "status": "running"}'):
                receipt = root / "summary.json"
                if content is None:
                    receipt.unlink(missing_ok=True)
                else:
                    receipt.write_text(content)
                self.assertEqual(script.browser_exit_code(root, 0), 2)
                self.assertEqual(json.loads(receipt.read_text())["browser_status"], "UNKNOWN")

    def test_reporter_outcome_and_process_exit_both_must_pass(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status, process_code, expected in (("passed", 0, 0), ("failed", 0, 2), ("passed", 7, 7)):
                original = self.receipt(status=status)
                (root / "summary.json").write_text(json.dumps(original))
                self.assertEqual(script.browser_exit_code(root, process_code), expected)
                self.assertEqual(json.loads((root / "summary.json").read_text()), original)

    def test_every_owned_service_is_stopped_after_one_failure(self):
        script = load_script("e2e")
        processes = (object(), object(), object())
        with patch.object(script, "stop", side_effect=[OSError("isolated stop fault"), None, None]) as stop:
            self.assertFalse(script.stop_owned(processes))
        self.assertEqual([call.args[0] for call in stop.call_args_list], list(processes))

    def test_cleanup_failure_preserves_real_browser_evidence(self):
        script = load_script("e2e")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = {"schema_version": 1, "stage": "browser", "status": "passed", "browser_status": "passed", "discovered": 4, "counts": {"passed": 4}, "cases": [{"title": "synthetic", "status": "passed"}]}
            (root / "summary.json").write_text(json.dumps(original), encoding="utf-8")
            script.record_cleanup(root, "failed")
            result = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["cleanup_status"], "failed")
            for field in ("browser_status", "discovered", "counts", "cases"):
                self.assertEqual(result[field], original[field])


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
            with contextlib.closing(sqlite3.connect(db_path)) as db, db:
                db.execute("CREATE TABLE alembic_version (version_num TEXT)")
                db.execute("INSERT INTO alembic_version VALUES ('0003_worker')")
                db.execute("CREATE TABLE jobs (id TEXT, status TEXT, created_at TEXT, started_at TEXT, heartbeat_at TEXT, worker_pid INTEGER, run_id TEXT, worker_instance TEXT, host_boot_id TEXT, child_pid INTEGER, child_pgid INTEGER, finished_at TEXT, error_code TEXT, error_message TEXT, launch_phase TEXT DEFAULT 'unverified', kind TEXT DEFAULT 'package', environment_json TEXT, process_identity_json TEXT DEFAULT '{}')")
                db.execute("CREATE TABLE datasets (status TEXT, validation_job_id TEXT)")
                db.execute("CREATE TABLE job_events (job_id TEXT, seq INTEGER, kind TEXT, payload_json TEXT, created_at TEXT)")
                db.execute("INSERT INTO jobs (id,status,created_at) VALUES (?,?,?)", (job_id, "queued", "2026-09-28T00:00:00Z"))
            environment = {**os.environ, "PLATFORM_DATA_ROOT": directory}
            first = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=ROOT / "backend", env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            with contextlib.closing(sqlite3.connect(db_path)) as db, db:
                self.assertEqual(db.execute("SELECT status,error_code FROM jobs WHERE id=?", (job_id,)).fetchone(), ("failed", "UNSUPPORTED_JOB"))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM job_events WHERE job_id=?", (job_id,)).fetchone()[0], 2)
                db.execute("INSERT INTO jobs (id,status,created_at) VALUES (?,?,?)", (str(uuid4()), "running", "2026-09-28T00:00:01Z"))
            second = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=ROOT / "backend", env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(second.returncode, 4, second.stderr)


if __name__ == "__main__":
    unittest.main()
