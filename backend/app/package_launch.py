"""One fixed independent interpreter/bootstrap and a closed child environment."""
from hashlib import sha256
import importlib.util
from importlib import metadata
import os
from pathlib import Path
import sys
from .run_files import run_directory,read_json
from .package_probe_contract import StandaloneInput
from .training_assets import digest_json

ROOT=Path(__file__).resolve().parents[2]
PYTHON=ROOT/'backend/.venv-package/bin/python'
BOOTSTRAP=ROOT/'scripts/package_standalone.py'


def installer():
    spec=importlib.util.spec_from_file_location('edgevision_fixed_package_installer',ROOT/'scripts/install_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def check_environment():
    if sys.platform!='linux' or sys.version_info[:2]!=(3,12):raise ValueError('standalone target unsupported')
    if PYTHON.resolve(strict=True)!=Path(sys.executable).resolve(strict=True):raise ValueError('standalone interpreter is not the fixed base Python')
    prefix=PYTHON.parent.parent
    spec=importlib.util.spec_from_file_location('edgevision_fixed_install_security',ROOT/'scripts/install_ml.py')
    security=importlib.util.module_from_spec(spec);spec.loader.exec_module(security)
    security.reject_startup_hooks(prefix);security.reject_startup_hooks(Path(sys.base_prefix))
    installer().verify_environment(prefix)


def environment_identity():
    check_environment()
    packages={}
    site=PYTHON.parent.parent/'lib/python3.12/site-packages'
    for dist in metadata.distributions(path=[str(site)]):
        name=(dist.metadata.get('Name') or '').lower().replace('_','-')
        if name=='pip':continue
        packages[name]={'version':dist.version,'record_sha256':sha256(dist.read_text('RECORD').encode()).hexdigest()}
    return {'python_version':list(sys.version_info[:3]),'python_sha256':sha256(PYTHON.resolve().read_bytes()).hexdigest(),
        'venv_config_sha256':sha256((PYTHON.parent.parent/'pyvenv.cfg').read_bytes()).hexdigest(),'packages':packages,
        'lock_sha256':sha256((ROOT/'backend/requirements-package-linux-cpu.lock').read_bytes()).hexdigest()}


def source_hashes():
    return {'cli_sha256':sha256((ROOT/'backend/app/package_cli.py').read_bytes()).hexdigest(),
            'bootstrap_sha256':sha256(BOOTSTRAP.read_bytes()).hexdigest()}


def launch(job_id,run_id):
    directory=run_directory(job_id,run_id)
    raw=read_json(directory/'input.json',1024**2)
    task=StandaloneInput.model_validate(raw).model_dump(mode='json')
    if (task['job_id'],task['run_id'])!=(job_id,run_id):raise ValueError('standalone run identity mismatch')
    if any(task[key]!=value for key,value in source_hashes().items()):raise ValueError('standalone source changed')
    check_environment()
    environment={'HOME':str(directory/'home'),'TMPDIR':str(directory/'tmp'),
        'PATH':str(PYTHON.parent)+':/usr/bin:/bin','LD_LIBRARY_PATH':str(Path(sys.base_prefix)/'lib'),
        'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'Etc/UTC','ORT_DISABLE_TELEMETRY':'1',
        'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','PYTHONNOUSERSITE':'1',
        'EDGEVISION_PACKAGE_RUN_DIR':str(directory),'EDGEVISION_PACKAGE_INPUT_SHA256':digest_json(task)}
    return [str(PYTHON),'-I','-B',str(BOOTSTRAP),job_id,run_id],environment
