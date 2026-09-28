"""Portable development commands. Dependencies are installed separately."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"
COMMANDS = ("doctor", "migrate", "api", "worker", "web", "contract-generate", "contract-check", "check")


def backend_python() -> str | None:
    executable = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        print("Missing backend/.venv; run scripts/install_deps.py first", file=sys.stderr)
        return None
    return str(executable)


def run(cwd: Path, program: str, *args: str, env: dict[str, str] | None = None) -> int:
    executable = shutil.which(program) if program in ("uv", "npm") else program
    if not executable:
        print(f"Missing {program}; see README.md installation steps", file=sys.stderr)
        return 127
    try:
        return subprocess.run([executable, *args], cwd=cwd, env=env, check=False).returncode
    except OSError as exc:
        print(f"Cannot start {program}: {exc}", file=sys.stderr)
        return 127


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(f"Usage: {Path(sys.argv[0]).name} {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    action = argv[0]
    if action == "doctor":
        return run(ROOT, backend_python() or sys.executable, str(ROOT / "scripts" / "doctor.py"))
    if action == "web":
        return run(WEB, "npm", "run", "dev")
    python = backend_python()
    if not python:
        return 127
    if action == "check":
        env = {**os.environ, "PYTHONPATH": str(BACKEND)}
        for pattern in ("test_contracts_unit.py", "test_dev_scripts_unit.py"):
            result = run(ROOT, python, "-m", "unittest", "discover", "-s", "backend/tests", "-p", pattern, env=env)
            if result:
                return result
    if action == "migrate":
        return run(BACKEND, python, "-m", "alembic", "upgrade", "head")
    if action == "api":
        return run(BACKEND, python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
    if action == "worker":
        return run(BACKEND, python, "-m", "app.worker")
    if action in ("contract-generate", "contract-check"):
        args = ("--check",) if action == "contract-check" else ()
        return run(BACKEND, python, "../scripts/export_contract.py", *args)
    return (
        run(BACKEND, python, "-m", "pytest")
        or run(WEB, "npm", "run", "build")
        or main(["contract-check"])
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
