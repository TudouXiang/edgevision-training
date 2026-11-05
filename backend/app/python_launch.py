"""Launch the current Python directly while preserving its virtual environment.

Windows venv python.exe may be a redirector whose PID is not the interpreter's.
Use CPython's multiprocessing/popen_spawn_win32.py protocol for owned Popen
handles. This only configures a child environment, never the parent environment.
"""
from __future__ import annotations
import os
import sys


def python_child(command: list[str], environment: dict[str, str] | None = None) -> tuple[list[str], dict[str, str] | None]:
    if not command or os.path.normcase(command[0]) != os.path.normcase(sys.executable):
        raise ValueError("Owned Python children must use the current interpreter")
    args = list(command)
    child_environment = dict(os.environ if environment is None else environment)
    child_environment["ORT_DISABLE_TELEMETRY"] = "1"
    if os.name != "nt":
        return args, child_environment
    base = getattr(sys, "_base_executable", None)
    if not base or not os.path.isabs(base):
        raise RuntimeError("Direct Windows Python interpreter is unavailable")
    if os.path.normcase(base) == os.path.normcase(sys.executable):
        return args, child_environment
    child_environment["__PYVENV_LAUNCHER__"] = sys.executable
    args[0] = base
    return args, child_environment
