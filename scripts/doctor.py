"""Read-only, short environment inventory. Does not import optional ML libraries."""

import importlib.metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import sys


def command_version(binary: str, option: str) -> str:
    path = shutil.which(binary)
    if not path:
        return "MISSING"
    result = subprocess.run([path, option], text=True, capture_output=True, timeout=3, check=False)
    return (result.stdout or result.stderr).strip().splitlines()[0] if result.returncode == 0 else f"ERROR {result.returncode}"


def module_status(name: str) -> str:
    if importlib.util.find_spec(name) is None:
        return "MISSING"
    try:
        return f"INSTALLED {importlib.metadata.version(name)}; runtime NOT_VERIFIED"
    except importlib.metadata.PackageNotFoundError:
        return "FOUND; version/runtime NOT_VERIFIED"


if __name__ == "__main__":
    print(f"python: {sys.version.split()[0]} / {sys.executable}")
    print(f"platform: {platform.system()} {platform.release()} {platform.machine()}")
    for binary, option in (("uv", "--version"), ("node", "--version"), ("npm", "--version"), ("git", "--version")):
        print(f"{binary}: {command_version(binary, option)}")
    for package in ("fastapi", "sqlalchemy", "alembic", "pytest", "httpx", "pydantic", "torch", "ultralytics", "onnx", "onnxruntime"):
        print(f"{package}: {module_status(package)}")
    print(f"PLATFORM_DATA_ROOT: {'SET' if os.environ.get('PLATFORM_DATA_ROOT') else 'NOT_SET (local default)'}")
