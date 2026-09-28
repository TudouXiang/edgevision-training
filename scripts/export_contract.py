"""Generate/check FastAPI OpenAPI and TypeScript from the same app routes.

Run from the repository via scripts/dev.py. No network or model import.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # Script is invoked from scripts/, app package lives under backend/.
SCHEMA = ROOT / "contracts" / "openapi.json"
TYPES = ROOT / "contracts" / "generated" / "openapi.ts"
GENERATOR = ROOT / "web" / "node_modules" / "openapi-typescript" / "bin" / "cli.js"


def render(schema_path: Path, type_path: Path) -> None:
    from app.main import app

    schema_path.parent.mkdir(parents=True, exist_ok=True)
    type_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(app.openapi(), sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not GENERATOR.is_file():
        raise RuntimeError("Missing project-local openapi-typescript; run cd web && npm ci first")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is missing from PATH")
    subprocess.run([node, str(GENERATOR), str(schema_path), "-o", str(type_path)], check=True, cwd=ROOT, timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Compare without modifying tracked generated files")
    options = parser.parse_args()
    if options.check and (not SCHEMA.is_file() or not TYPES.is_file()):
        print("Contract artifacts missing; run contract-generate first", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        schema = Path(tmp) / "openapi.json"
        types = Path(tmp) / "openapi.ts"
        try:
            render(schema, types)
        except ModuleNotFoundError as exc:
            if exc.name not in {"fastapi", "starlette", "sqlalchemy"}:
                raise
            print(f"Missing project-local Python dependency: {exc.name}; run cd backend && uv sync --extra dev", file=sys.stderr)
            return 2
        if options.check:
            if schema.read_bytes() != SCHEMA.read_bytes() or types.read_bytes() != TYPES.read_bytes():
                print("OpenAPI or TypeScript contract drift", file=sys.stderr)
                return 1
        else:
            SCHEMA.parent.mkdir(parents=True, exist_ok=True)
            TYPES.parent.mkdir(parents=True, exist_ok=True)
            SCHEMA.write_bytes(schema.read_bytes())
            TYPES.write_bytes(types.read_bytes())
    if options.check:
        print("contract artifacts match live FastAPI/Pydantic schema")
    else:
        print(f"generated {SCHEMA.relative_to(ROOT)} and {TYPES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
