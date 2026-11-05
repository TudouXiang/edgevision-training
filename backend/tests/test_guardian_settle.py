"""Deterministic supervisor control/accounting tests; not native OS evidence."""
import sys
from types import SimpleNamespace
import pytest
from app import guardian


def simulate(monkeypatch, tmp_path, *, converges_at=None, clears_on_stop=False, control=None, windows=True):
    clock = {"now": 100.0, "queue": None, "sent": False}
    writes, stops = {}, []

    class Tree:
        output = None
        record = {"test": True}
        root_code = 71
        def __init__(self, _command):
            pass
        def start(self):
            pass
        def go(self):
            pass
        def poll(self):
            return self.root_code
        def empty(self):
            return bool((clears_on_stop and stops) or (converges_at is not None and clock["now"] >= 100 + converges_at))
        def stop(self, force=False):
            stops.append((clock["now"] - 100, force))
        def close(self):
            pass

    class Thread:
        def __init__(self, target, args, **_kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
        def join(self, **_kwargs):
            pass
        def is_alive(self):
            return False

    def read_control(commands):
        clock["queue"] = commands
        commands.put("GO")

    def sleep(seconds):
        clock["now"] += seconds
        if control and not clock["sent"]:
            clock["queue"].put(control)
            clock["sent"] = True

    monkeypatch.setattr(guardian, "os", SimpleNamespace(name="nt" if windows else "posix", getpid=lambda: 123, set_inheritable=lambda *_: None))
    monkeypatch.setattr(guardian, "time", SimpleNamespace(monotonic=lambda: clock["now"], sleep=sleep))
    monkeypatch.setattr(guardian, "signal", SimpleNamespace(SIGTERM=15, SIGINT=2, SIGCHLD=17, SIG_DFL=0, signal=lambda *_: None))
    monkeypatch.setattr(guardian, "threading", SimpleNamespace(Thread=Thread))
    monkeypatch.setitem(sys.modules, "app.process_windows" if windows else "app.process_linux", SimpleNamespace(ProcessTree=Tree))
    monkeypatch.setattr(guardian, "read_control", read_control)
    monkeypatch.setattr(guardian, "capture_output", lambda _source, _path, result: result.update(complete=True))
    monkeypatch.setattr(guardian, "identity", lambda _pid: {"test": True})
    monkeypatch.setattr(guardian, "run_directory", lambda *_: tmp_path)
    monkeypatch.setattr(guardian, "atomic_json", lambda path, value: writes.update({path.name: value}))
    # No wall-clock wait: every poll advances a deterministic clock.
    result = guardian.supervise("job", "run")
    return result, writes.get("drained.json"), stops


def test_windows_transient_accounting_completes_without_termination(monkeypatch, tmp_path):
    result, receipt, stops = simulate(monkeypatch, tmp_path, converges_at=0.15)
    assert result == 0 and stops == []
    assert receipt["reason"] == "completed" and receipt["exit_code"] == 71
    assert receipt["tree_exited"] is True and receipt["logs_complete"] is True


def test_windows_remaining_members_are_drained_but_not_success(monkeypatch, tmp_path):
    result, receipt, stops = simulate(monkeypatch, tmp_path, clears_on_stop=True)
    assert result == 0 and 0.25 <= stops[0][0] <= 0.31
    assert receipt["reason"] == "remaining_job_members_after_settle"
    assert receipt["tree_exited"] is True


def test_windows_nonzero_count_never_becomes_exit_proof(monkeypatch, tmp_path):
    result, receipt, stops = simulate(monkeypatch, tmp_path)
    assert result == 4 and receipt is None
    assert 0.25 <= stops[0][0] <= 0.31 and any(force for _, force in stops)


@pytest.mark.parametrize("control,reason", [("STOP", "cancelled"), ("EOF", "worker_lost")])
def test_control_preempts_windows_settle(monkeypatch, tmp_path, control, reason):
    result, receipt, stops = simulate(monkeypatch, tmp_path, clears_on_stop=True, control=control)
    assert result == 0 and stops[0][0] < 0.1
    assert receipt["reason"] == reason


def test_linux_keeps_immediate_post_root_cleanup(monkeypatch, tmp_path):
    result, receipt, stops = simulate(monkeypatch, tmp_path, clears_on_stop=True, windows=False)
    assert result == 0 and stops[0][0] == 0
    assert receipt["reason"] == "descendants_after_root_exit"
