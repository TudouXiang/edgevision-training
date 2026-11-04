"""Explicit opt-in local-Docker orchestration, not an authorization to run ML.

All CLI subprocess output is private. Public output is reconstructed from a
closed schema. No Docker, dependency installation or ML runs at module import.
"""
from __future__ import annotations

import argparse
from hashlib import sha1, sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON_PREFIX = Path('/opt/hostedtoolcache/Python/3.12.14/x64')
NODE_PREFIX = Path('/opt/hostedtoolcache/node/24.22.1/x64')
CONTAINER_PYTHON = '/opt/edgevision/backend/.venv-delivery/bin/python'
ENTRY = '/opt/edgevision/scripts/isolated_ml_entry.py'
LOCAL_ENDPOINT = 'unix:///var/run/docker.sock'
OWNER_LABEL = 'org.edgevision.isolated-ml-owner'
BUILD_TIMEOUT = 600
EXECUTION_TIMEOUT = 480
CLEANUP_TIMEOUT = 30
STAGES = ('isolation', 'training_http', 'export_http', 'onnx_policy', 'training_policy', 'browser_delivery')
PUBLIC_STAGES = ('preparation', 'build', 'create', 'inspect', 'execution', 'cleanup', 'cleanup_unknown', 'complete')
IMAGE_ID = re.compile(r'sha256:[a-f0-9]{64}')
CONTAINER_ID = re.compile(r'[a-f0-9]{64}')
BLOCKED_OVERRIDES = (
    'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
    'DOCKER_CONFIG', 'BUILDX_BUILDER', 'BUILDKIT_HOST', 'DOCKER_BUILDKIT',
)
BASE_ENV = {
    'PATH': '/opt/edgevision/backend/.venv-delivery/bin:/opt/hostedtoolcache/Python/3.12.14/x64/bin:'
            '/opt/hostedtoolcache/node/24.22.1/x64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'LD_LIBRARY_PATH': '/opt/hostedtoolcache/Python/3.12.14/x64/lib',
    'HOME': '/home/edgevision', 'CI': 'true', 'ORT_DISABLE_TELEMETRY': '1',
    'PLAYWRIGHT_BROWSERS_PATH': '/ms-playwright', 'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD': '1',
    'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1', 'PYTHONNOUSERSITE': '1',
    'PIP_NO_CACHE_DIR': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
    'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'Etc/UTC', 'DEBIAN_FRONTEND': 'noninteractive',
}


class IsolationError(RuntimeError):
    """Only fixed stage/status values, never the exception text, may be published."""


class PrivateCommandError(IsolationError):
    def __init__(self, output: Path):
        super().__init__('private command failed')
        self.output = output


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise IsolationError('arguments rejected')


def interrupt_for_cleanup(_signal, _frame):
    raise KeyboardInterrupt


def before_deadline(deadline: float, maximum: float = 10) -> float:
    remaining = deadline - time.monotonic()
    require(remaining > 0)
    return min(maximum, remaining)


def require(condition: bool) -> None:
    if not condition:
        raise IsolationError('isolated validation rejected')


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def decode_json(value: str):
    return json.loads(value, object_pairs_hook=unique_object)


def validate_summary(value: str) -> dict:
    require(len(value) <= 8192)
    result = decode_json(value)
    require(isinstance(result, dict) and set(result) == {'schema_version', 'stage', 'status', 'stages'})
    require(type(result['schema_version']) is int and result['schema_version'] == 1)
    require(result['stage'] == 'isolated_ml' and result['status'] in ('passed', 'failed'))
    rows = result['stages']
    require(isinstance(rows, list) and len(rows) == len(STAGES))
    for name, row in zip(STAGES, rows, strict=True):
        require(isinstance(row, dict) and set(row) == {'stage', 'status'})
        require(row['stage'] == name and row['status'] in ('passed', 'failed', 'NOT_RUN', 'unverified'))
    all_passed = all(row['status'] == 'passed' for row in rows)
    require((result['status'] == 'passed') == all_passed)
    # Return freshly built known fields; never relay arbitrary Docker output.
    return {'schema_version': 1, 'stage': 'isolated_ml', 'status': result['status'],
            'stages': [{'stage': name, 'status': row['status']} for name, row in zip(STAGES, rows, strict=True)]}


def public_summary(stage: str, passed: bool, result: dict | None = None) -> dict:
    require(stage in PUBLIC_STAGES)
    rows = [{'stage': name, 'status': 'NOT_RUN'} for name in STAGES]
    if result is not None:
        rows = validate_summary(json.dumps(result))['stages']
    require(not passed or (stage == 'complete' and all(row['status'] == 'passed' for row in rows)))
    return {'schema_version': 1, 'stage': stage, 'status': 'passed' if passed else 'failed', 'stages': rows}


def failed_outer(stage: str, previous: dict) -> dict:
    # Cleanup/reporting faults cannot erase already verified child outcomes.
    rows = previous['stages']
    evidence = {'schema_version': 1, 'stage': 'isolated_ml',
                'status': 'passed' if all(row['status'] == 'passed' for row in rows) else 'failed',
                'stages': rows}
    return public_summary(stage, False, evidence)


def reject_overrides(environment: dict[str, str]) -> None:
    require(not any(key in environment for key in BLOCKED_OVERRIDES))


def verify_hosted_workflow(environment: dict[str, str], expected_commit: str) -> None:
    # Accident-prevention gate, not authentication against a malicious owner who
    # can forge env vars or edit this program. Trust the reviewed hosted workflow.
    require(environment.get('GITHUB_ACTIONS') == 'true')
    require(environment.get('RUNNER_ENVIRONMENT') == 'github-hosted')
    require(environment.get('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    require(environment.get('GITHUB_WORKFLOW') == 'EdgeVision feature checks')
    require(environment.get('EDGEVISION_RUN_ISOLATED_ML') == 'true')
    require(environment.get('GITHUB_SHA') == expected_commit)
    require(environment.get('GITHUB_WORKFLOW_SHA') == expected_commit)
    repository = environment.get('GITHUB_REPOSITORY', '')
    require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)))
    require(environment.get('GITHUB_WORKFLOW_REF', '').startswith(
        repository + '/.github/workflows/t020-ci.yml@refs/heads/'))


class PrivateCommands:
    """No inherited credentials/proxies, remote builders or public subprocess stderr."""
    def __init__(self, private: Path):
        self.private = private
        self.sequence = 0
        config = private / 'docker-config'
        config.mkdir(mode=0o700)
        (config / 'config.json').write_text('{"auths":{},"proxies":{}}\n')
        self.environment = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                            'HOME': str(private), 'DOCKER_CONFIG': str(config),
                            'DOCKER_BUILDKIT': '1', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                            'ORT_DISABLE_TELEMETRY': '1',
                            'LD_LIBRARY_PATH': str(PYTHON_PREFIX / 'lib')}
        self.docker_binary = shutil.which('docker', path=self.environment['PATH'])
        require(self.docker_binary is not None)

    def command(self, args: list[str], *, timeout: float, capture: bool = True,
                cwd: Path | None = None) -> str:
        self.sequence += 1
        path = self.private / f'command-{self.sequence}.log'
        with path.open('xb') as output:
            completed = subprocess.run(args, cwd=cwd, env=self.environment, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        if completed.returncode != 0:
            raise PrivateCommandError(path)
        if not capture:
            return ''
        require(path.stat().st_size <= 1024 * 1024)
        return path.read_bytes().decode('utf-8')

    def docker(self, args: list[str], *, timeout: float = 10, capture: bool = True) -> str:
        return self.command([self.docker_binary, '--context', 'default', *args],
                            timeout=timeout, capture=capture)


def verify_local_endpoint(commands: PrivateCommands) -> None:
    context = decode_json(commands.docker(['context', 'inspect', 'default']))
    require(isinstance(context, list) and len(context) == 1)
    item = context[0]
    require(item.get('Name') == 'default' and item.get('Endpoints', {}).get('docker', {}).get('Host') == LOCAL_ENDPOINT)
    require(not item.get('TLSMaterial'))
    require(item.get('Endpoints', {}).get('docker', {}).get('SkipTLSVerify', False) is False)


SOURCE_EXTENSIONS = {'.py', '.ts', '.vue', '.css', '.html', '.json', '.toml', '.ini', '.lock', '.yaml', '.yml', '.sh', '.ps1', '.mako'}
BLOCKED_PARTS = {'data', 'private', 'logs', 'artifacts', 'evidence', 'reports', 'playwright-report',
                 'test-results', 'node_modules', 'dist', 'build', 'credentials', 'secrets'}


def source_allowed(relative: str) -> bool:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or path.parts[0] not in {'backend', 'web', 'scripts', 'contracts'}:
        return False
    if any(part in {'..', '.'} or part.startswith('.') or part in BLOCKED_PARTS for part in path.parts):
        return False
    if any(word in path.name.lower() for word in ('fingerprint', 'credential', 'secret', '.env')):
        return False
    # JSON/YAML may encode private runtime evidence: only named configuration is copied.
    if path.suffix in {'.json', '.yaml', '.yml'}:
        return relative in {'web/package.json', 'web/package-lock.json', 'web/tsconfig.json',
                            'web/tsconfig.e2e.json', 'contracts/openapi.json'}
    return path.suffix in SOURCE_EXTENSIONS


REQUIRED_SOURCE = (
    'scripts/isolated_ml_entry.py', 'scripts/install_ml.py', 'scripts/e2e.py',
    'scripts/fetch_training_asset.py', 'backend/requirements-delivery-linux-cpu.lock',
    'web/package-lock.json', 'backend/tests/export_http_probe.py',
    'backend/tests/test_onnx_runtime_policy.py',
)
RECIPE = 'ci/isolated-ml.Dockerfile'


def copy_source(context: Path, tree: str, read_blob) -> None:
    """Copy verified committed blob bytes, never the mutable worktree/index."""
    copied = set()
    for record in tree.split('\0'):
        if not record:
            continue
        metadata, relative = record.split('\t', 1)
        mode, kind, object_id = metadata.split()
        if not source_allowed(relative) and relative != RECIPE:
            continue
        require(mode in {'100644', '100755'} and kind == 'blob')
        require(bool(re.fullmatch(r'[a-f0-9]{40}', object_id)))
        content = read_blob(object_id)
        require(isinstance(content, bytes))
        header = b'blob ' + str(len(content)).encode('ascii') + b'\0'
        require(sha1(header + content, usedforsecurity=False).hexdigest() == object_id)
        destination = context / ('Dockerfile' if relative == RECIPE else 'source/' + relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as target:
            target.write(content)
        destination.chmod(0o755 if mode == '100755' else 0o644)
        copied.add(relative)
    require(set(REQUIRED_SOURCE).issubset(copied) and RECIPE in copied)


def freeze_source(root: Path, context: Path, commands: PrivateCommands, expected_commit: str) -> None:
    require(bool(re.fullmatch(r'[a-f0-9]{40}', expected_commit)))
    def git(*args):
        return commands.command(['git', '-c', 'core.fsmonitor=false', *args], cwd=root, timeout=15)
    require(git('rev-parse', '--verify', 'HEAD').strip() == expected_commit)
    paths = ('backend', 'web', 'scripts', 'contracts', 'ci')
    require(git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', *paths) == '')
    tree = git('ls-tree', '-r', '-z', expected_commit, '--', *paths)
    copy_source(context, tree, lambda object_id: git('cat-file', 'blob', object_id).encode('utf-8'))
    # A checkout/commit race is not evidence for the requested source revision.
    require(git('rev-parse', '--verify', 'HEAD').strip() == expected_commit)
    require(git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', *paths) == '')


def copy_tool_prefix(source: Path, destination: Path) -> None:
    require(source.is_dir() and not source.is_symlink())
    for path in source.rglob('*'):
        if path.is_symlink():
            require(path.resolve(strict=True).is_relative_to(source.resolve()))
        else:
            require(path.is_file() or path.is_dir())
    shutil.copytree(source, destination, symlinks=True)


def prepare_context(root: Path, private: Path, commands: PrivateCommands, expected_commit: str) -> Path:
    # Python/Node are official setup-action prefixes on the same Ubuntu 24.04 host.
    require(sys.platform == 'linux' and sys.version_info[:3] == (3, 12, 14))
    release = Path('/etc/os-release').read_text()
    require('ID=ubuntu\n' in release and 'VERSION_ID="24.04"\n' in release)
    context = private / 'build-context'
    context.mkdir(mode=0o700)
    freeze_source(root, context, commands, expected_commit)
    copy_tool_prefix(PYTHON_PREFIX, context / 'tool-python')
    copy_tool_prefix(NODE_PREFIX, context / 'tool-node')
    asset = context / 'asset/yolo11n.pt'
    commands.command([str(PYTHON_PREFIX / 'bin/python3'), '-I', '-S', str(context / 'source/scripts/fetch_training_asset.py'),
                      '--output', str(asset)], timeout=75, capture=False)
    require(asset.is_file() and not asset.is_symlink() and asset.stat().st_size == 5613764)
    require(sha256(asset.read_bytes()).hexdigest() == '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1')
    return context


def environment_map(entries: list[str]) -> dict[str, str]:
    require(isinstance(entries, list))
    result = {}
    for entry in entries:
        require(isinstance(entry, str) and '=' in entry)
        name, value = entry.split('=', 1)
        require(name not in result)
        result[name] = value
    return result


def verify_owned(container: dict, name: str, token: str, image: str) -> None:
    require(container.get('Name') == '/' + name and container.get('Image') == image)
    require(container.get('Config', {}).get('Labels', {}).get(OWNER_LABEL) == token)
    require(bool(CONTAINER_ID.fullmatch(container.get('Id', ''))))


def verify_container(container: dict, name: str, token: str, image: str, host_netns: str,
                     *, exited: bool = False) -> None:
    verify_owned(container, name, token, image)
    config, host, state = container['Config'], container['HostConfig'], container['State']
    args = ['-I', '-S', ENTRY, '--host-netns', host_netns]
    require(config.get('Image') == image and config.get('User') == '10001:10001')
    require(config.get('Entrypoint') == [CONTAINER_PYTHON] and config.get('Cmd') == args)
    require(container.get('Path') == CONTAINER_PYTHON and container.get('Args') == args)
    require(config.get('WorkingDir') == '/opt/edgevision')
    require(environment_map(config.get('Env')) == BASE_ENV)
    require(not config.get('Volumes') and not config.get('ExposedPorts'))
    require(config.get('Healthcheck', {}).get('Test') == ['NONE'])
    require(host.get('NetworkMode') == 'none' and host.get('Privileged') is False)
    require(host.get('CapDrop') == ['ALL'] and not host.get('CapAdd'))
    require(host.get('SecurityOpt') in (['no-new-privileges=true'], ['no-new-privileges:true']))
    require(host.get('IpcMode') == 'private' and host.get('CgroupnsMode') == 'private')
    require(host.get('PidMode') == '' and host.get('UTSMode') == '' and host.get('UsernsMode') == '')
    require(host.get('ShmSize') == 256 * 1024**2 and host.get('PidsLimit') == 512)
    require(host.get('Memory') == 6 * 1024**3 and host.get('MemorySwap') == 6 * 1024**3)
    require(host.get('NanoCpus') == 2_000_000_000)
    for field in ('Binds', 'Mounts', 'Tmpfs', 'Devices', 'DeviceRequests', 'DeviceCgroupRules',
                  'PortBindings', 'ExtraHosts', 'Links', 'VolumesFrom', 'GroupAdd', 'Sysctls'):
        require(not host.get(field))
    require(host.get('PublishAllPorts') is False and not container.get('Mounts'))
    require(host.get('RestartPolicy', {}).get('Name') == 'no')
    require(host.get('AutoRemove') is False)
    networks = container.get('NetworkSettings', {}).get('Networks', {})
    require(set(networks) == {'none'})
    for field in ('IPAddress', 'GlobalIPv6Address', 'Gateway', 'IPv6Gateway'):
        require(not networks['none'].get(field))
    require(state.get('Running') is False and state.get('Paused') is False and state.get('Restarting') is False)
    require(state.get('Pid') == 0 and state.get('Status') == ('exited' if exited else 'created'))
    require(state.get('OOMKilled') is False and not state.get('Error'))
    if exited:
        require(state.get('ExitCode') == 0)


class IsolatedRun:
    def __init__(self, commands: PrivateCommands, private: Path, *, token: str | None = None):
        self.commands = commands
        self.private = private
        self.token = token or secrets.token_hex(16)
        self.name = 'edgevision-ml-' + self.token
        self.image: str | None = None
        self.build_attempted = False
        self.build_resolved = False
        self.create_attempted = False
        self.create_resolved = False
        self.cleanup_unknown = False
        self.stage = 'preparation'
        self.result: dict | None = None
        self.host_netns = os.readlink('/proc/self/ns/net')
        require(bool(re.fullmatch(r'net:\[[0-9]+\]', self.host_netns)))

    def find_container(self, deadline: float | None = None) -> dict | None:
        deadline = deadline if deadline is not None else time.monotonic() + 20
        ids = self.commands.docker(['container', 'ls', '--all', '--quiet', '--no-trunc',
                                   '--filter', f'name=^/{self.name}$'], timeout=before_deadline(deadline)).split()
        require(len(ids) <= 1 and all(CONTAINER_ID.fullmatch(item) for item in ids))
        if not ids:
            return None
        values = decode_json(self.commands.docker(['container', 'inspect', ids[0]], timeout=before_deadline(deadline)))
        require(isinstance(values, list) and len(values) == 1 and values[0].get('Name') == '/' + self.name)
        return values[0]

    def build(self, context: Path) -> None:
        self.stage = 'build'
        iidfile = self.private / 'image-id'
        self.build_attempted = True
        try:
            self.commands.docker(['build', '--builder', 'default', '--platform', 'linux/amd64',
                                  '--no-cache', '--pull=false', '--provenance=false', '--iidfile', str(iidfile),
                                  '--label', f'{OWNER_LABEL}={self.token}', '--file', str(context / 'Dockerfile'),
                                  str(context)], timeout=BUILD_TIMEOUT, capture=False)
        finally:
            # A timed-out client can still leave an image; reconcile its exact ID.
            if iidfile.is_file():
                image = iidfile.read_text().strip()
                require(bool(IMAGE_ID.fullmatch(image)))
                self.image = image
        require(self.image is not None)
        self.build_resolved = True

    def execute(self) -> None:
        require(self.image is not None)
        deadline = time.monotonic() + EXECUTION_TIMEOUT
        def remaining() -> float:
            value = deadline - time.monotonic()
            require(value > 0)
            return value
        self.stage = 'create'
        # Never adopt or delete a container that already occupied the random name.
        require(self.find_container(deadline) is None)
        self.create_attempted = True  # Before the client call: timeout is ambiguous.
        self.commands.docker([
            'create', '--name', self.name, '--label', f'{OWNER_LABEL}={self.token}',
            '--pull', 'never', '--network', 'none', '--user', '10001:10001', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges=true', '--ipc', 'private', '--cgroupns', 'private',
            '--shm-size', '256m', '--pids-limit', '512', '--memory', '6g', '--memory-swap', '6g',
            '--cpus', '2', '--no-healthcheck', '--restart', 'no', '--workdir', '/opt/edgevision',
            '--entrypoint', CONTAINER_PYTHON, self.image, '-I', '-S', ENTRY,
            '--host-netns', self.host_netns], timeout=min(15, remaining()))
        self.create_resolved = True
        self.stage = 'inspect'
        container = self.find_container(deadline)
        require(container is not None)
        verify_container(container, self.name, self.token, self.image, self.host_netns)
        self.stage = 'execution'
        # If the client disappears or output is malformed, actual child outcomes
        # are unknown, not falsely reported as never run.
        self.result = {'schema_version': 1, 'stage': 'isolated_ml', 'status': 'failed',
                       'stages': [{'stage': name, 'status': 'unverified'} for name in STAGES]}
        try:
            output = self.commands.docker(['start', '--attach', container['Id']], timeout=remaining())
        except PrivateCommandError as failure:
            if failure.output.stat().st_size <= 8192:
                self.result = validate_summary(failure.output.read_text())
            raise
        self.result = validate_summary(output)
        require(self.result['status'] == 'passed')
        # Exit code alone or a forged/missing stage summary cannot mean success.
        self.stage = 'inspect'
        container = self.find_container(deadline)
        require(container is not None)
        verify_container(container, self.name, self.token, self.image, self.host_netns, exited=True)

    def cleanup(self) -> bool:
        deadline = time.monotonic() + CLEANUP_TIMEOUT
        # A client timeout before an image/container becomes visible is not
        # proof that the daemon did nothing. Never claim cleanup from no handle.
        self.cleanup_unknown = self.build_attempted and not self.build_resolved
        okay = not self.cleanup_unknown
        if self.create_attempted:
            try:
                container = self.find_container(deadline)
                if container is not None:
                    verify_owned(container, self.name, self.token, self.image)
                    self.commands.docker(['container', 'rm', '--force', container['Id']],
                                         timeout=before_deadline(deadline), capture=False)
                    require(self.find_container(deadline) is None)
                    self.create_resolved = True
                elif not self.create_resolved:
                    self.cleanup_unknown = True
                    okay = False
            except BaseException:
                okay = False
        if self.image is not None:
            try:
                values = decode_json(self.commands.docker(['image', 'inspect', self.image], timeout=before_deadline(deadline)))
                require(isinstance(values, list) and len(values) == 1)
                require(values[0].get('Id') == self.image and
                        values[0].get('Config', {}).get('Labels', {}).get(OWNER_LABEL) == self.token)
                self.commands.docker(['image', 'rm', self.image],
                                     timeout=before_deadline(deadline), capture=False)
                images = self.commands.docker(['image', 'ls', '--all', '--quiet', '--no-trunc'], timeout=before_deadline(deadline)).split()
                require(all(IMAGE_ID.fullmatch(image) for image in images) and self.image not in images)
            except BaseException:
                okay = False
        return okay

    def run(self, context: Path) -> dict:
        passed = False
        try:
            self.build(context)
            self.execute()
            passed = True
        except BaseException:
            pass
        finally:
            if not self.cleanup():
                self.stage, passed = ('cleanup_unknown' if self.cleanup_unknown else 'cleanup'), False
        return public_summary('complete' if passed else self.stage, passed, self.result)


def main(argv: list[str] | None = None) -> int:
    result = public_summary('preparation', False)
    report: Path | None = None
    execution_finished = False
    previous_signal = signal.signal(signal.SIGTERM, interrupt_for_cleanup)
    previous_mask = os.umask(0o077)
    try:
        parser = QuietParser(add_help=False)
        parser.add_argument('--execute', action='store_true')
        parser.add_argument('--expected-commit', required=True)
        parser.add_argument('--report-dir', type=Path, required=True)
        options = parser.parse_args(argv)
        report = options.report_dir
        require(options.execute)
        reject_overrides(dict(os.environ))
        verify_hosted_workflow(dict(os.environ), options.expected_commit)
        # Remove our private context/log files before publishing success. Docker
        # preparation layers may remain in the local default-builder cache until
        # this ephemeral hosted runner is destroyed; do not export or prune it.
        with tempfile.TemporaryDirectory(prefix='edgevision-isolated-') as directory:
            private = Path(directory)
            commands = PrivateCommands(private)
            verify_local_endpoint(commands)  # Before build or acquisition.
            context = prepare_context(ROOT, private, commands, options.expected_commit)
            result = IsolatedRun(commands, private).run(context)
            execution_finished = True
    except BaseException:
        # Includes preparation, toolchain, Docker, timeout and local cleanup faults.
        result = failed_outer('cleanup' if execution_finished else 'preparation', result)
    try:
        if report is not None:
            report.mkdir(parents=True, exist_ok=True)
            (report / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    except BaseException:
        result = failed_outer('cleanup', result)
    os.umask(previous_mask)
    signal.signal(signal.SIGTERM, previous_signal)
    print(json.dumps(result, separators=(',', ':')), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
