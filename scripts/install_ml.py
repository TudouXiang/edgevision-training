"""Explicit optional CPU installation. Importing this module never installs or imports ML."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def install_plan(root: Path, delivery: bool, *, defer_check: bool = False):
    environment = root/'backend'/('.venv-delivery' if delivery else '.venv-ml')
    python = environment/'bin/python'
    lock = root/'backend'/('requirements-delivery-linux-cpu.lock' if delivery else 'requirements-ml-linux-cpu.lock')
    commands = [
        [str(python), '-I', '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
         '--require-hashes', '--index-url', 'https://pypi.org/simple', '--extra-index-url',
         'https://download.pytorch.org/whl/cpu', '-r', str(lock)],
    ]
    if not defer_check:
        commands.append([str(python), '-I', '-m', 'pip', 'check'])
    return environment, commands


def reject_path_overrides(root: Path) -> None:
    # Reuse this standard-library scan in the same installer process after pip,
    # without starting an interpreter that an installed ._pth could reconfigure.
    base = root.resolve(strict=True)
    for path in root.rglob('*'):
        if path.name.lower().endswith('._pth'):
            raise ValueError('Python path override rejected')
        if path.is_symlink() and path.is_dir() and not path.resolve(strict=True).is_relative_to(base):
            raise ValueError('Python prefix directory link escapes its root')


def reject_startup_hooks(root: Path) -> None:
    """Inspect only fixed Linux 3.12 startup locations, without importing them.

    -I ignores cwd, PYTHONPATH and user sites; -S cannot be used for pip because
    Python 3.12 needs site to initialize the virtualenv prefix. Reject path hooks
    as well as executable hooks: a plain .pth path can expose sitecustomize.
    The official interpreter and its bundled ensurepip remain trusted inputs.
    """
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Python prefix must be an owned directory')
    base = root.resolve(strict=True)

    def checked(path: Path) -> Path:
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(base):
            raise ValueError('Python startup path escapes its prefix')
        return path

    def hook(name: str) -> bool:
        name = name.lower()
        return (name.endswith(('.pth', '._pth')) or name in {'sitecustomize', 'usercustomize'}
                or name.startswith(('sitecustomize.', 'usercustomize.')))

    # ._pth can override interpreter startup flags, so reject it anywhere in the
    # copied prefix. The host copy check does this before starting that Python.
    reject_path_overrides(root)
    for library in ('lib', 'lib64'):
        directory = checked(root / library)
        if not directory.exists():
            continue
        stdlib = checked(directory / 'python3.12')
        for startup in (stdlib, stdlib / 'lib-dynload', stdlib / 'site-packages'):
            checked(startup)
            if not startup.exists():
                continue
            if not startup.is_dir():
                raise ValueError('Invalid Python startup directory')
            if any(hook(path.name) for path in startup.iterdir()):
                raise ValueError('Python startup hook rejected before online preparation')
        archive = checked(directory / 'python312.zip')
        if archive.exists():
            # Invalid/unreadable archives fail closed, never silently skip them.
            with zipfile.ZipFile(archive) as zipped:
                if any(hook(name.split('/')[0]) for name in zipped.namelist()):
                    raise ValueError('Python archive startup hook rejected')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--delivery', action='store_true', help='Prepare the separate joint ONNX CPU environment')
    parser.add_argument('--check', action='store_true', help='Validate the plan only; do not create or install anything')
    parser.add_argument('--defer-check', action='store_true',
                        help='Fresh delivery image only: run pip check after the kernel isolation boundary')
    args = parser.parse_args(argv)
    if sys.platform != 'linux' or platform.machine() != 'x86_64' or sys.version_info[:2] != (3, 12):
        parser.error('Fixed ML locks require Linux x86_64 Python 3.12; other targets are unverified')
    if args.defer_check and not args.delivery:
        parser.error('--defer-check requires --delivery')
    environment, commands = install_plan(ROOT, args.delivery, defer_check=args.defer_check)
    if args.check:
        print('Optional CPU installation plan checked; installation and runtime NOT_RUN')
        return 0
    if args.defer_check:
        if environment.exists() or environment.is_symlink():
            parser.error('Deferred-check preparation requires a fresh environment')
        reject_startup_hooks(Path(sys.base_prefix))
    venv.EnvBuilder(with_pip=True).create(environment)
    if args.defer_check:
        # ensurepip has only installed the trusted interpreter's bundled pip.
        # Abort before pip starts if the fresh environment gained a startup hook.
        reject_startup_hooks(environment)
    for command in commands:
        subprocess.run(command, check=True)
    if args.defer_check:
        reject_path_overrides(environment)
        reject_path_overrides(Path(sys.base_prefix))
        print('Environment installed; dependency check DEFERRED to kernel-isolated execution. Runtime NOT_VERIFIED.')
    else:
        print('Optional environment installed; runtime NOT_VERIFIED. Actual probes require an approved execution boundary.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
