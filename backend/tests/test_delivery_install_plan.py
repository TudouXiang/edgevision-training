"""Verify dependency preparation without installing or importing ML."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def installer():
    spec = importlib.util.spec_from_file_location('delivery_installer', ROOT/'scripts/install_ml.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_lock_preserves_every_base_pin():
    base = (ROOT/'backend/requirements-ml-linux-cpu.lock').read_text().splitlines()
    joint = (ROOT/'backend/requirements-delivery-linux-cpu.lock').read_text().splitlines()
    assert joint[:len(base)] == base
    assert len(base) == 62 and len(joint) == 67
    assert len({line.split('==')[0] for line in joint}) == 67
    assert all(' --hash=sha256:' in line for line in joint)


def test_delivery_environment_and_lock_are_separate():
    module = installer()
    ordinary, ordinary_commands = module.install_plan(ROOT, False)
    joint, joint_commands = module.install_plan(ROOT, True)
    assert ordinary.name == '.venv-ml' and joint.name == '.venv-delivery'
    assert ordinary_commands[0][-1].endswith('requirements-ml-linux-cpu.lock')
    assert joint_commands[0][-1].endswith('requirements-delivery-linux-cpu.lock')
    assert '--require-hashes' in joint_commands[0]
    assert '--only-binary=:all:' in joint_commands[0]


def test_check_mode_does_not_create_environment_or_run_commands(monkeypatch):
    module = installer()
    def forbidden(*args, **kwargs): raise AssertionError('Preparation check must be read-only')
    from types import SimpleNamespace
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', version_info=(3, 12, 14)))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(module.venv, 'EnvBuilder', forbidden)
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    assert module.main(['--delivery', '--check']) == 0


import pytest


def deferred_installer(tmp_path, monkeypatch):
    from types import SimpleNamespace
    module = installer()
    prefix = tmp_path / 'python'
    prefix.mkdir()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', version_info=(3, 12, 14), base_prefix=str(prefix)))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    return module


def test_deferred_plan_has_one_isolated_hash_locked_install():
    _, commands = installer().install_plan(ROOT, True, defer_check=True)
    assert len(commands) == 1
    assert commands[0][1:5] == ['-I', '-m', 'pip', 'install']
    assert '--require-hashes' in commands[0] and '--only-binary=:all:' in commands[0]
    assert '-S' not in commands[0]  # Python 3.12 venv prefix requires site.


def test_deferred_check_requires_delivery(tmp_path, monkeypatch):
    module = deferred_installer(tmp_path, monkeypatch)
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: pytest.fail('venv created'))
    with pytest.raises(SystemExit): module.main(['--defer-check'])


def test_deferred_check_plan_is_still_read_only(tmp_path, monkeypatch):
    module = deferred_installer(tmp_path, monkeypatch)
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: pytest.fail('venv created'))
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: pytest.fail('child started'))
    assert module.main(['--delivery', '--defer-check', '--check']) == 0


@pytest.mark.parametrize('existing', ['directory', 'file', 'dangling_link'])
def test_deferred_preparation_rejects_existing_target_before_venv(tmp_path, monkeypatch, existing):
    module = deferred_installer(tmp_path, monkeypatch)
    target = tmp_path / 'backend/.venv-delivery'
    target.parent.mkdir()
    if existing == 'directory': target.mkdir()
    elif existing == 'file': target.write_text('existing')
    else: target.symlink_to(tmp_path / 'missing')
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: pytest.fail('existing venv modified'))
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: pytest.fail('child started'))
    with pytest.raises(SystemExit): module.main(['--delivery', '--defer-check'])


@pytest.mark.parametrize('relative', [
    'lib/python3.12/sitecustomize.py', 'lib/python3.12/usercustomize.pyc',
    'lib/python3.12/sitecustomize/__init__.py',
    'lib/python3.12/lib-dynload/sitecustomize.cpython-312-x86_64-linux-gnu.so',
    'lib/python3.12/site-packages/path-only.pth', 'lib/python3.12/site-packages/executable.pth',
    'lib64/python3.12/site-packages/usercustomize.py', 'bin/python._pth', 'lib/libpython3.12._pth',
])
def test_bootstrap_rejects_active_startup_hooks_without_import(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('/untrusted/path\n')
    with pytest.raises(ValueError): installer().reject_startup_hooks(tmp_path)


@pytest.mark.parametrize('member', ['sitecustomize.py', 'usercustomize.pyc', 'sitecustomize/__init__.py'])
def test_bootstrap_rejects_archive_hooks(tmp_path, member):
    import zipfile
    archive = tmp_path / 'lib/python312.zip'
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, 'w') as zipped: zipped.writestr(member, 'never executed')
    with pytest.raises(ValueError): installer().reject_startup_hooks(tmp_path)


def test_bootstrap_rejects_bad_archive_and_escape(tmp_path):
    import zipfile
    prefix = tmp_path / 'prefix'
    (prefix / 'lib').mkdir(parents=True)
    (prefix / 'lib/python312.zip').write_text('not a zip')
    with pytest.raises(zipfile.BadZipFile): installer().reject_startup_hooks(prefix)
    (prefix / 'lib/python312.zip').unlink()
    (prefix / 'lib/python3.12').symlink_to(tmp_path)
    with pytest.raises(ValueError): installer().reject_startup_hooks(prefix)


def test_bootstrap_ignores_nonimportable_fixture_hooks(tmp_path):
    fixture = tmp_path / 'lib/python3.12/test/fixtures/sitecustomize.py'
    fixture.parent.mkdir(parents=True)
    fixture.write_text('never imported')
    (fixture.parent / 'sample.pth').write_text('test fixture')
    installer().reject_startup_hooks(tmp_path)


def test_deferred_build_never_restarts_python_after_wheels(tmp_path, monkeypatch):
    module = deferred_installer(tmp_path, monkeypatch)
    from types import SimpleNamespace
    target = tmp_path / 'backend/.venv-delivery'
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: SimpleNamespace(
        create=lambda path: (path / 'lib/python3.12/site-packages').mkdir(parents=True)))
    calls = []
    def install(command, **kwargs):
        calls.append(command)
        assert kwargs == {'check': True}
        (target / 'lib/python3.12/site-packages/installed-wheel.pth').write_text('import never_run\n')
    monkeypatch.setattr(module.subprocess, 'run', install)
    assert module.main(['--delivery', '--defer-check']) == 0
    assert len(calls) == 1 and 'check' not in calls[0]


def test_bootstrap_hook_is_rejected_before_any_install(tmp_path, monkeypatch):
    module = deferred_installer(tmp_path, monkeypatch)
    from types import SimpleNamespace
    def create(path):
        root = path / 'lib/python3.12/site-packages'
        root.mkdir(parents=True)
        (root / 'unexpected.pth').write_text('/untrusted/path\n')
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: SimpleNamespace(create=create))
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: pytest.fail('child started'))
    with pytest.raises(ValueError): module.main(['--delivery', '--defer-check'])


@pytest.mark.skipif(sys.platform != 'linux', reason='Fixed Linux Python startup layout')
def test_parent_no_site_flags_do_not_protect_a_child(tmp_path):
    """Harmless stdlib-only reproduction: write a marker, never ML/network."""
    import subprocess
    import sys
    import venv
    environment = tmp_path / 'venv'
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / 'bin/python'
    marker = tmp_path / 'marker'
    site = next((environment / 'lib').glob('python*/site-packages'))
    (site / 'marker.pth').write_text(f'import pathlib; pathlib.Path({str(marker)!r}).write_text("hook")\n')
    parent = 'import subprocess; subprocess.run(' + repr([str(python), '-I', '-c', 'pass']) + ', check=True)'
    subprocess.run([sys.executable, '-I', '-S', '-c', parent], check=True)
    assert marker.read_text() == 'hook'


@pytest.mark.parametrize('relative', ['bin/python._pth', 'lib/libpython3.12._pth', 'base/bin/python3._pth'])
def test_postinstall_path_override_rejected_without_new_child(tmp_path, monkeypatch, relative):
    module = deferred_installer(tmp_path, monkeypatch)
    from types import SimpleNamespace
    target = tmp_path / 'backend/.venv-delivery'
    monkeypatch.setattr(module.venv, 'EnvBuilder', lambda **kw: SimpleNamespace(
        create=lambda path: path.mkdir(parents=True)))
    calls = []
    def install(command, **kwargs):
        calls.append(command)
        path = (Path(module.sys.base_prefix) / relative.removeprefix('base/')
                if relative.startswith('base/') else target / relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('import site\n')
    monkeypatch.setattr(module.subprocess, 'run', install)
    with pytest.raises(ValueError, match='path override'):
        module.main(['--delivery', '--defer-check'])
    assert len(calls) == 1


@pytest.mark.skipif(sys.platform != 'linux', reason='Fixed Linux Python startup layout')
def test_path_override_can_defeat_no_site_flags(tmp_path):
    """Harmless stdlib-only proof for the postinstall ._pth rejection."""
    import subprocess
    import sysconfig
    import venv
    environment = tmp_path / 'venv'
    venv.EnvBuilder(with_pip=False).create(environment)
    site = next((environment / 'lib').glob('python*/site-packages'))
    marker = tmp_path / 'marker'
    (site / 'marker.pth').write_text(f'import pathlib; pathlib.Path({str(marker)!r}).write_text("hook")\n')
    stdlib = Path(sysconfig.get_path('stdlib'))
    (environment / 'bin/python._pth').write_text(f'{stdlib}\n{stdlib / "lib-dynload"}\n{site}\nimport site\n')
    result = subprocess.run([str(environment / 'bin/python'), '-I', '-S', '-c',
                             'import sys; print(sys.flags.no_site)'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == '0'
    assert marker.read_text() == 'hook'
