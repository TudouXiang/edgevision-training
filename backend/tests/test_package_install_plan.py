"""Plan and security checks for the explicit package-only installer."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def installer():
    spec = importlib.util.spec_from_file_location('package_installer', ROOT/'scripts/install_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_is_exact_delivery_subset():
    delivery = {line.split('==', 1)[0].lower().replace('_', '-'): line
                for line in (ROOT/'backend/requirements-delivery-linux-cpu.lock').read_text().splitlines()}
    lock = (ROOT/'backend/requirements-package-linux-cpu.lock').read_text().splitlines()
    assert len(lock) == 9
    assert all(delivery[line.split('==', 1)[0].lower().replace('_', '-')] == line for line in lock)
    assert {line.split('==', 1)[0].lower().replace('_', '-') for line in lock} == set(installer().PACKAGES)


def test_plan_is_linux_only_pypi_hash_locked_and_checked():
    env, commands = installer().install_plan(ROOT)
    assert env.name == '.venv-package'
    assert len(commands) == 2
    assert commands[0][1:5] == ['-I', '-m', 'pip', 'install']
    assert '--require-hashes' in commands[0] and '--only-binary=:all:' in commands[0]
    assert commands[0][commands[0].index('--index-url') + 1] == 'https://pypi.org/simple'
    assert commands[1][-2:] == ['pip', 'check']
    assert not any('--extra-index-url' in command for command in commands)


def test_check_mode_does_not_create_or_install(monkeypatch):
    module = installer()
    from types import SimpleNamespace
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', version_info=(3, 12, 9)))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: pytest.fail('venv created'))
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: pytest.fail('child started'))
    assert module.main(['--check']) == 0


def test_rejects_non_312_and_no_user_overrides(monkeypatch):
    module = installer()
    from types import SimpleNamespace
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', version_info=(3, 11, 9)))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    with pytest.raises(SystemExit): module.main(['--check'])
    assert '--defer-check' not in module.__doc__


@pytest.mark.parametrize('libc, version, expected', [
    ('glibc', '2.28', 0), ('glibc', '2.27', 2), ('musl', '1.2.5', 2),
])
def test_glibc_floor_is_enforced(monkeypatch, libc, version, expected):
    module = installer()
    from types import SimpleNamespace
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', version_info=(3, 12, 9)))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(module.platform, 'libc_ver', lambda: (libc, version))
    if expected:
        with pytest.raises(SystemExit): module.main(['--check'])
    else:
        assert module.main(['--check']) == expected


def test_verify_exact_environment_rejects_unexpected_or_mismatched_packages(tmp_path, monkeypatch):
    module = installer()
    class Dist:
        def __init__(self, name, version): self.metadata = {'Name': name}; self.version = version
        def read_text(self, name): return 'record' if name == 'RECORD' else None
    (tmp_path/'pyvenv.cfg').write_text('include-system-site-packages = false\nhome = '+str(Path(sys._base_executable).resolve().parent)+'\nexecutable = '+str(Path(sys._base_executable).resolve())+'\n')
    monkeypatch.setattr(module, 'verify_record_files', lambda *args: None)
    monkeypatch.setattr(module.metadata, 'distributions', lambda path: [Dist(n, v) for n, v in module.PACKAGES.items()])
    module.verify_environment(tmp_path)
    monkeypatch.setattr(module.metadata, 'distributions', lambda path: [Dist('torch', '1')])
    with pytest.raises(ValueError): module.verify_environment(tmp_path)


def test_verify_rejects_system_site_packages_and_duplicate_pip(tmp_path, monkeypatch):
    module = installer()
    class Dist:
        metadata = {'Name': 'pip'}
        version = '25.0'
        def read_text(self, name): return 'record'
    (tmp_path/'pyvenv.cfg').write_text('include-system-site-packages = true\n')
    with pytest.raises(ValueError, match='system site'):
        module.verify_environment(tmp_path)
    (tmp_path/'pyvenv.cfg').write_text('include-system-site-packages = false\nhome = '+str(Path(sys._base_executable).resolve().parent)+'\nexecutable = '+str(Path(sys._base_executable).resolve())+'\n')
    monkeypatch.setattr(module.metadata, 'distributions', lambda path: [Dist(), Dist()])
    with pytest.raises(ValueError, match='duplicate'):
        module.verify_environment(tmp_path)


def test_each_installer_command_is_bracketed_by_startup_checks(tmp_path, monkeypatch):
    module = installer()
    from types import SimpleNamespace
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    base = tmp_path/'base'; base.mkdir()
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', version_info=(3, 12, 9), base_prefix=str(base)))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(module.platform, 'libc_ver', lambda: ('glibc', '2.28'))
    checks = []
    def load(_module):
        _module.reject_startup_hooks = lambda path: checks.append(path)
        _module.reject_path_overrides = lambda path: None
    monkeypatch.setattr(module.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(loader=SimpleNamespace(exec_module=load)))
    monkeypatch.setattr(module.importlib.util, 'module_from_spec', lambda spec: SimpleNamespace())
    target = tmp_path/'backend/.venv-package'
    def create(path):
        path.mkdir(parents=True)
        (path/'lib/python3.12/site-packages').mkdir(parents=True)
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: SimpleNamespace(create=create))
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(module, 'verify_environment', lambda p: None)
    module.main([])
    assert checks.count(target) >= 4
    assert checks.count(base) >= 3



def test_venv_configuration_cannot_redirect_fixed_base(tmp_path, monkeypatch):
    module=installer()
    class Dist:
        def __init__(self,name,version):self.metadata={'Name':name};self.version=version
        def read_text(self,name):return 'record'
    monkeypatch.setattr(module.metadata,'distributions',lambda path:[Dist(n,v) for n,v in module.PACKAGES.items()])
    (tmp_path/'pyvenv.cfg').write_text('include-system-site-packages = false\nhome = /untrusted/python\nexecutable = /untrusted/python/bin/python\n')
    with pytest.raises(ValueError):module.verify_environment(tmp_path)


def test_record_verification_binds_actual_module_bytes(tmp_path):
    module=installer()
    import base64,hashlib
    from types import SimpleNamespace
    site=tmp_path/'lib/python3.12/site-packages';site.mkdir(parents=True)
    info=site/'demo.dist-info';info.mkdir()
    code=site/'demo.py';code.write_bytes(b'original module')
    encoded=base64.urlsafe_b64encode(hashlib.sha256(code.read_bytes()).digest()).decode().rstrip('=')
    record=f'demo.py,sha256={encoded},{code.stat().st_size}\ndemo.dist-info/RECORD,,\n'
    (info/'RECORD').write_text(record)
    dist=SimpleNamespace(read_text=lambda name:record,_path=info)
    module.verify_record_files(dist,tmp_path)
    code.write_bytes(b'changed module!')
    with pytest.raises(ValueError):module.verify_record_files(dist,tmp_path)


def test_record_cannot_escape_prefix_or_run_unhashed_bytecode(tmp_path):
    module=installer()
    from types import SimpleNamespace
    info=tmp_path/'lib/python3.12/site-packages/demo.dist-info';info.mkdir(parents=True)
    for record in ('../../../../outside,sha256=AAAA,1\n','demo.py,,\n'):
        dist=SimpleNamespace(read_text=lambda name:record,_path=info)
        with pytest.raises(ValueError):module.verify_record_files(dist,tmp_path)


def test_duplicate_venv_configuration_is_rejected(tmp_path):
    module=installer()
    (tmp_path/'pyvenv.cfg').write_text('include-system-site-packages = false\ninclude-system-site-packages = true\n')
    with pytest.raises(ValueError):module.verify_environment(tmp_path)
