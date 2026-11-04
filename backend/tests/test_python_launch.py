"""Native PID/venv regression, including an early Windows CI structural probe."""
import json
import ntpath
import os
import subprocess
import sys
import time
from types import SimpleNamespace
import pytest
from app import python_launch
from app.process_identity import identity
from app.run_files import read_json


@pytest.mark.parametrize("platform,base,direct", [("posix", "/base/python", False), ("nt", r"C:\venv\python.exe", False), ("nt", r"C:\base\python.exe", True)])
def test_child_environment_is_private_and_current_interpreter_only(monkeypatch, platform, base, direct):
    executable = r"C:\venv\python.exe"
    parent = {"UNCHANGED": "yes"}
    explicit = {"CHILD_ONLY": "yes"}
    with monkeypatch.context() as patch:
        patch.setattr(python_launch, "os", SimpleNamespace(name=platform, path=ntpath, environ=parent))
        patch.setattr(python_launch, "sys", SimpleNamespace(executable=executable, _base_executable=base))
        command = [executable, "-m", "app.guardian", "job", "run"]
        args, env = python_launch.python_child(command, explicit)
        assert args[0] == (base if direct else executable)
        assert command[0] == executable
        assert env == ({**explicit, "__PYVENV_LAUNCHER__": executable} if direct else explicit)
        inherited_args, inherited_env = python_launch.python_child(command)
        assert inherited_args == args
        assert inherited_env == ({**parent, "__PYVENV_LAUNCHER__": executable} if direct else None)
        with pytest.raises(ValueError):
            python_launch.python_child([r"C:\unrelated\python.exe"])
    assert parent == {"UNCHANGED": "yes"} and explicit == {"CHILD_ONLY": "yes"}


def test_native_owned_pid_and_venv_are_preserved(tmp_path):
    # Output is only PID/booleans. Never print paths, env, credentials or argv.
    source = """
import json, os, sys
import fastapi, PIL, pydantic
print(json.dumps({"pid": os.getpid(), "prefix_matches": os.path.normcase(sys.prefix) == os.path.normcase(sys.argv[1]), "executable_matches": os.path.normcase(sys.executable) == os.path.normcase(sys.argv[2]), "dependencies_importable": True}))
"""
    command = [sys.executable, "-c", source, sys.prefix, sys.executable]
    raw = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        raw_output, _ = raw.communicate(timeout=15)
        assert raw.returncode == 0
        raw_pid_matches = json.loads(raw_output)["pid"] == raw.pid
    finally:
        if raw.poll() is None:
            raw.kill()
            raw.wait(timeout=5)
    marker = tmp_path / "native-identity.json"
    held_source = """
import json, os, sys
from pathlib import Path
import fastapi, PIL, pydantic
from app.process_identity import identity
from app.run_files import atomic_json
atomic_json(Path(sys.argv[3]), {"identity": identity(os.getpid()), "prefix_matches": os.path.normcase(sys.prefix) == os.path.normcase(sys.argv[1]), "executable_matches": os.path.normcase(sys.executable) == os.path.normcase(sys.argv[2]), "dependencies_importable": True})
raise SystemExit(0 if sys.stdin.buffer.readline(16) == b"GO\\n" else 125)
"""
    args, environment = python_launch.python_child([sys.executable, "-c", held_source, sys.prefix, sys.executable, str(marker)])
    child = subprocess.Popen(args, env=environment, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "native interpreter did not reach the identity gate"
        result = read_json(marker)
        flags = {"raw_pid_matches": raw_pid_matches, "direct_pid_matches": result["identity"]["pid"] == child.pid,
                 "birth_identity_matches": result["identity"] == identity(child.pid),
                 "prefix_matches": result["prefix_matches"], "executable_matches": result["executable_matches"],
                 "dependencies_importable": result["dependencies_importable"], "windows": os.name == "nt"}
        print("python_launch_probe=" + json.dumps(flags, sort_keys=True))
        assert all(flags[key] for key in ("direct_pid_matches", "birth_identity_matches", "prefix_matches", "executable_matches", "dependencies_importable"))
        child.communicate(input=b"GO\n", timeout=10)
        assert child.returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        if child.stdin and not child.stdin.closed:
            child.stdin.close()
