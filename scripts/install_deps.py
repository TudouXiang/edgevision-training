"""Install only the project's lightweight development dependencies.

Run with Python 3.11+ on Linux or Windows. Training/ONNX extras are separate.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"


def prerequisites(backend: bool, web: bool) -> dict[str, str]:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required")
    binaries = ("uv",) if backend and not web else ("npm", "node") if web and not backend else ("uv", "node", "npm")
    found = {}
    for binary in binaries:
        path = shutil.which(binary)
        if not path:
            raise RuntimeError(f"{binary} is missing from PATH; install it before running this script")
        found[binary] = path
    versions = {}
    for binary, path in found.items():
        versions[binary] = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    if web:
        version = versions["node"]
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
        if not match or tuple(map(int, match.groups())) < (22, 13, 0):
            raise RuntimeError(f"Node 22.13+ is required; found {version!r}")
        if not (WEB / "package-lock.json").is_file():
            raise RuntimeError("web/package-lock.json is missing; npm ci needs the existing lockfile")
    if backend and not (BACKEND / "pyproject.toml").is_file():
        raise RuntimeError("backend/pyproject.toml is missing")
    return found


def install_steps(binaries: dict[str, str], backend: bool, web: bool) -> list[tuple[Path, list[str]]]:
    steps = []
    if backend:
        uv = [binaries["uv"], "sync", "--extra", "dev", "--python", sys.executable, "--no-managed-python", "--no-python-downloads"]
        if (BACKEND / "uv.lock").is_file():
            uv.append("--locked")
        steps.append((BACKEND, uv))
    if web:
        steps.append((WEB, [binaries["npm"], "ci", "--no-audit", "--no-fund"]))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Install backend/.venv and web/node_modules without installing system tools or ML packages")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backend-only", action="store_true")
    group.add_argument("--web-only", action="store_true")
    parser.add_argument("--check", action="store_true", help="Validate prerequisites and print steps without installing")
    args = parser.parse_args()
    backend, web = not args.web_only, not args.backend_only
    try:
        binaries = prerequisites(backend, web)
        steps = install_steps(binaries, backend, web)
        env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(BACKEND / ".venv")}
        for cwd, command in steps:
            print(f"{cwd.relative_to(ROOT)}: {' '.join(command)}", flush=True)
            if not args.check:
                result = subprocess.run(command, cwd=cwd, env=env, check=False)
                if result.returncode:
                    return result.returncode
        if args.check:
            print("Prerequisites found; installation NOT_RUN")
        else:
            print("Requested lightweight dependencies installed; application runtime NOT_VERIFIED")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Dependency installation stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
