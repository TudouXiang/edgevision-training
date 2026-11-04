"""Verify dependency preparation without installing or importing ML."""
import importlib.util
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
