"""Explicit optional CPU installation. Importing this module never installs or imports ML."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def install_plan(root: Path, delivery: bool):
    environment = root/'backend'/('.venv-delivery' if delivery else '.venv-ml')
    python = environment/'bin/python'
    lock = root/'backend'/('requirements-delivery-linux-cpu.lock' if delivery else 'requirements-ml-linux-cpu.lock')
    commands = [
        [str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
         '--require-hashes', '--index-url', 'https://pypi.org/simple', '--extra-index-url',
         'https://download.pytorch.org/whl/cpu', '-r', str(lock)],
        [str(python), '-m', 'pip', 'check'],
    ]
    return environment, commands


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--delivery', action='store_true', help='Prepare the separate joint ONNX CPU environment')
    parser.add_argument('--check', action='store_true', help='Validate the plan only; do not create or install anything')
    args = parser.parse_args(argv)
    if sys.platform != 'linux' or platform.machine() != 'x86_64' or sys.version_info[:2] != (3, 12):
        parser.error('Fixed ML locks require Linux x86_64 Python 3.12; other targets are unverified')
    environment, commands = install_plan(ROOT, args.delivery)
    if args.check:
        print('Optional CPU installation plan checked; installation and runtime NOT_RUN')
        return 0
    venv.EnvBuilder(with_pip=True).create(environment)
    for command in commands:
        subprocess.run(command, check=True)
    print('Optional environment installed; runtime NOT_VERIFIED. Actual probes require an approved execution boundary.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
