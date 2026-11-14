"""Explicit, isolated CPU package runtime preparation; importing never installs ML."""
import argparse
import importlib.util
from importlib import metadata
from pathlib import Path
import platform
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    'pillow': '12.3.0', 'numpy': '2.5.4', 'onnx': '1.23.2',
    'onnxruntime': '1.31.1', 'protobuf': '7.36.2', 'ml-dtypes': '0.6.0',
    'flatbuffers': '25.12.19', 'packaging': '26.3', 'typing-extensions': '4.16.0',
}


def install_plan(root: Path):
    environment = root / 'backend' / '.venv-package'
    lock = root / 'backend' / 'requirements-package-linux-cpu.lock'
    command = [str(environment / 'bin/python'), '-I', '-m', 'pip', 'install',
               '--disable-pip-version-check', '--only-binary=:all:', '--require-hashes', '--no-compile',
               '--index-url', 'https://pypi.org/simple', '-r', str(lock)]
    return environment, [command, [str(environment / 'bin/python'), '-I', '-m', 'pip', 'check']]


def verify_record_files(dist, environment):
    """Verify actual runtime distribution bytes, not only the RECORD manifest."""
    import base64,csv,hashlib,io,os,stat
    root=environment.resolve(strict=True)
    site=root/'lib/python3.12/site-packages'
    record=dist.read_text('RECORD')
    if not record or len(record)>16*1024**2:raise ValueError('invalid RECORD')
    seen=set();total=0
    for row in csv.reader(io.StringIO(record)):
        if len(row)!=3 or not row[0] or row[0] in seen or len(seen)>=50000:raise ValueError('invalid RECORD entry')
        seen.add(row[0]);name,encoded,size=row
        if Path(name).is_absolute() or '\\' in name or '\x00' in name:raise ValueError('invalid RECORD path')
        original=site/name;path=original.resolve()
        if not path.is_relative_to(root) or any(parent.is_symlink() for parent in (original,*original.parents)):raise ValueError('RECORD path escapes prefix')
        if not encoded and not size:
            if path==Path(dist._path).resolve()/'RECORD':continue
            if path.suffix=='.pyc' and not path.exists():continue
            raise ValueError('unhashed installed code')
        if not encoded.startswith('sha256=') or not size.isdecimal():raise ValueError('unsupported RECORD digest')
        declared=int(size);total+=declared
        if declared>256*1024**2 or total>2*1024**3:raise ValueError('RECORD size limit')
        expected=base64.urlsafe_b64decode(encoded[7:]+'='*(-len(encoded[7:])%4))
        if len(expected)!=32:raise ValueError('invalid RECORD digest')
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size!=declared:raise ValueError('installed file size changed')
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor,'rb') as source:
            opened=os.fstat(source.fileno())
            if (opened.st_dev,opened.st_ino,opened.st_size)!=(before.st_dev,before.st_ino,declared):raise ValueError('installed file identity changed')
            digest=hashlib.sha256();remaining=declared
            while remaining:
                block=source.read(min(1024**2,remaining))
                if not block:raise ValueError('installed file truncated')
                digest.update(block);remaining-=len(block)
            if source.read(1) or digest.digest()!=expected:raise ValueError('installed file hash changed')


def verify_environment(environment: Path):
    """Verify only the locked runtime set plus pip bootstrap and RECORD presence."""
    cfg = {}
    for line in (environment / 'pyvenv.cfg').read_text().splitlines():
        key, separator, value = line.partition('=')
        key = key.strip().lower()
        if not separator or not key or key in cfg:
            raise ValueError('invalid or duplicate virtualenv configuration')
        cfg[key] = value.strip()
    if cfg.get('include-system-site-packages', '').lower() != 'false':
        raise ValueError('system site packages must be disabled')
    base = Path(getattr(sys, '_base_executable', sys.executable)).resolve(strict=True)
    if Path(cfg.get('home', '/missing')).resolve() != base.parent or Path(cfg.get('executable', '/missing')).resolve() != base:
        raise ValueError('virtualenv base interpreter changed')
    found = {}
    seen = set()
    for dist in metadata.distributions(path=[str(environment / 'lib/python3.12/site-packages')]):
        name = (dist.metadata.get('Name') or '').lower().replace('_', '-')
        if name in seen:
            raise ValueError(f'duplicate installed distribution: {name}')
        seen.add(name)
        if name == 'pip':
            continue
        found[name] = dist
    if set(found) != set(PACKAGES):
        raise ValueError(f'unexpected package set: {sorted(set(found) ^ set(PACKAGES))}')
    for name, version in PACKAGES.items():
        dist = found[name]
        if dist.version != version:
            raise ValueError(f'unexpected version for {name}: {dist.version}')
        if not dist.read_text('RECORD'):
            raise ValueError(f'missing RECORD for {name}')
        verify_record_files(dist, environment)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Check plan without creating/installing')
    args = parser.parse_args(argv)
    libc, libc_version = platform.libc_ver()
    try:
        glibc = tuple(int(part) for part in libc_version.split('.')[:2])
    except ValueError:
        glibc = ()
    if (sys.platform != 'linux' or platform.machine() != 'x86_64' or sys.version_info[:2] != (3, 12)
            or libc.lower() != 'glibc' or glibc < (2, 28)):
        parser.error('Package lock requires Linux x86_64 CPython 3.12 and glibc >= 2.28')
    environment, commands = install_plan(ROOT)
    if args.check:
        print('Package installation plan checked; installation and runtime NOT_RUN')
        return 0
    if environment.exists() or environment.is_symlink():
        parser.error('Package preparation requires a fresh environment')
    spec = importlib.util.spec_from_file_location('package_install_ml_security', ROOT/'scripts/install_ml.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load shared installer security checks')
    security = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(security)
    reject_path_overrides, reject_startup_hooks = security.reject_path_overrides, security.reject_startup_hooks
    reject_startup_hooks(Path(sys.base_prefix))
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
    reject_startup_hooks(environment)
    for command in commands:
        reject_startup_hooks(environment)
        reject_startup_hooks(Path(sys.base_prefix))
        subprocess.run(command, check=True)
        reject_startup_hooks(environment)
        reject_startup_hooks(Path(sys.base_prefix))
    reject_path_overrides(environment)
    reject_path_overrides(Path(sys.base_prefix))
    verify_environment(environment)
    print('Package environment installed and verified; native runtime NOT_VERIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
