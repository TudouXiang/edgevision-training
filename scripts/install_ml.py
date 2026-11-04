"""Explicit opt-in Linux CPU environment; does not modify backend/.venv."""
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv
ROOT=Path(__file__).resolve().parents[1]
if sys.platform!='linux' or platform.machine()!='x86_64' or sys.version_info[:2]!=(3,12):
    raise SystemExit('Verified ML lock requires Linux x86_64 Python 3.12; other targets are unverified')
environment=ROOT/'backend'/'.venv-ml'
venv.EnvBuilder(with_pip=True).create(environment)
python=environment/'bin'/'python'
subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--only-binary=:all:','--require-hashes',
    '--index-url','https://pypi.org/simple','--extra-index-url','https://download.pytorch.org/whl/cpu',
    '-r',str(ROOT/'backend'/'requirements-ml-linux-cpu.lock')],check=True)
subprocess.run([str(python),'-m','pip','check'],check=True)
print('Optional environment installed. Run API and Worker using backend/.venv-ml/bin/python; provision the fixed asset with app.training_probe before training.')
