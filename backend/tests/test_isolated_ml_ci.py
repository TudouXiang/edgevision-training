"""Fresh stdlib/mock tests. These never invoke Docker, install or import ML."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci = load('isolated_ml_ci')
entry = load('isolated_ml_entry')
TOKEN = 'a' * 32
IMAGE = 'sha256:' + 'b' * 64
CID = 'c' * 64


def full_summary():
    return {'schema_version': 2, 'stage': 'isolated_ml', 'status': 'passed',
            'stages': [{'stage': stage, 'status': 'passed'} for stage in ci.STAGES]}


def container(name, netns, *, exited=False):
    args = ['-I', '-S', ci.ENTRY, '--host-netns', netns]
    return {
        'Id': CID, 'Name': '/' + name, 'Image': IMAGE, 'Path': ci.CONTAINER_PYTHON, 'Args': args,
        'Config': {'Image': IMAGE, 'User': '10001:10001', 'Labels': {ci.OWNER_LABEL: TOKEN},
                   'Entrypoint': [ci.CONTAINER_PYTHON], 'Cmd': args,
                   'WorkingDir': '/opt/edgevision', 'Env': [f'{k}={v}' for k, v in ci.BASE_ENV.items()],
                   'Healthcheck': {'Test': ['NONE']}},
        'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'CapDrop': ['ALL'], 'CapAdd': None,
                       'SecurityOpt': ['no-new-privileges=true'], 'IpcMode': 'private',
                       'CgroupnsMode': 'private', 'PidMode': '', 'UTSMode': '', 'UsernsMode': '',
                       'ShmSize': 256 * 1024**2, 'PidsLimit': 512, 'Memory': 6 * 1024**3,
                       'MemorySwap': 6 * 1024**3, 'NanoCpus': 2_000_000_000,
                       'PublishAllPorts': False, 'RestartPolicy': {'Name': 'no'}, 'AutoRemove': False},
        'Mounts': [], 'NetworkSettings': {'Networks': {'none': {}}},
        'State': {'Running': False, 'Paused': False, 'Restarting': False, 'Pid': 0,
                  'Status': 'exited' if exited else 'created', 'OOMKilled': False, 'Error': '', 'ExitCode': 0},
    }


class FakeDocker:
    def __init__(self, private, failure=None, mutate=None):
        self.private = private
        self.failure = failure
        self.mutate = mutate
        self.calls = []
        self.current = None
        self.image_exists = False
        self.name = 'edgevision-ml-' + TOKEN

    def docker(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[:3] == ['context', 'inspect', 'default']:
            return json.dumps([{'Name': 'default', 'Endpoints': {'docker': {'Host': ci.LOCAL_ENDPOINT}}, 'TLSMaterial': {}}])
        if args[0] == 'build':
            (self.private / 'image-id').write_text(IMAGE)
            self.image_exists = True
            if self.failure == 'build_timeout':
                raise subprocess.TimeoutExpired('SECRET build detail', 600)
            return ''
        if args[:2] == ['container', 'ls']:
            return CID if self.current else ''
        if args[:2] == ['container', 'inspect']:
            return json.dumps([self.current])
        if args[0] == 'create':
            self.current = container(self.name, args[-1])
            if self.mutate:
                self.mutate(self.current)
            if self.failure == 'create_timeout':
                raise subprocess.TimeoutExpired('SECRET create detail', 15)
            return CID
        if args[0] == 'start':
            if self.failure == 'start_timeout':
                self.current['State'].update(Status='running', Running=True, Pid=999)
                raise subprocess.TimeoutExpired('SECRET start detail', 480)
            self.current['State']['Status'] = 'exited'
            if self.failure == 'post_inspect':
                self.current['HostConfig']['NetworkMode'] = 'host'
            if self.failure == 'private_output':
                return 'SECRET private traceback /home/user/data\n' + json.dumps(full_summary())
            if self.failure == 'missing_stage':
                result = full_summary()
                result['stages'].pop()
                return json.dumps(result)
            return json.dumps(full_summary())
        if args[:2] == ['container', 'rm']:
            if self.failure == 'remove':
                raise ci.IsolationError('SECRET cleanup detail')
            if self.failure != 'remove_noop':
                self.current = None
            return CID
        if args[:2] == ['image', 'inspect']:
            return json.dumps([{'Id': IMAGE, 'Config': {'Labels': {ci.OWNER_LABEL: TOKEN}}}])
        if args[:2] == ['image', 'rm']:
            if self.failure == 'image_remove':
                raise ci.IsolationError('SECRET image detail')
            self.image_exists = False
            return ''
        if args[:2] == ['image', 'ls']:
            return IMAGE if self.image_exists else ''
        raise AssertionError(f'unexpected fake call: {args}')


def run_fake(tmp_path, failure=None, mutate=None):
    commands = FakeDocker(tmp_path, failure, mutate)
    run = ci.IsolatedRun(commands, tmp_path, token=TOKEN)
    result = run.run(tmp_path)
    assert 'SECRET' not in json.dumps(result)
    return result, commands


def test_full_pass_only_after_post_inspect_and_confirmed_removal(tmp_path):
    result, docker = run_fake(tmp_path)
    assert result == {**full_summary(), 'stage': 'complete'}
    ops = [args[:2] for args, _ in docker.calls]
    start = ops.index(['start', '--attach'])
    remove = ops.index(['container', 'rm'])
    assert ['container', 'inspect'] in ops[:start]
    assert ['container', 'inspect'] in ops[start + 1:remove]
    assert ['container', 'ls'] in ops[remove + 1:]
    assert ops[-1] == ['image', 'ls']
    build = next(kwargs for args, kwargs in docker.calls if args[0] == 'build')
    assert build['timeout'] == 600
    assert next(kwargs['timeout'] for args, kwargs in docker.calls if args[0] == 'start') <= 480


@pytest.mark.parametrize('failure', ['build_timeout', 'create_timeout', 'start_timeout', 'remove',
                                     'remove_noop', 'image_remove', 'post_inspect', 'private_output', 'missing_stage'])
def test_failures_never_report_pass_and_reconcile_owned_container(tmp_path, failure):
    result, docker = run_fake(tmp_path, failure)
    assert result['status'] == 'failed'
    if failure in {'create_timeout', 'start_timeout'}:
        assert any(args[:2] == ['container', 'rm'] for args, _ in docker.calls)
        assert docker.current is None
    if failure in {'remove', 'remove_noop', 'image_remove'}:
        assert result['stage'] == 'cleanup'


@pytest.mark.parametrize(('section', 'key', 'value'), [
    ('HostConfig', 'NetworkMode', 'host'), ('HostConfig', 'Privileged', True),
    ('HostConfig', 'CapAdd', ['NET_ADMIN']), ('HostConfig', 'CapDrop', []),
    ('HostConfig', 'SecurityOpt', ['seccomp=unconfined']), ('HostConfig', 'IpcMode', 'host'),
    ('HostConfig', 'PidMode', 'host'), ('HostConfig', 'UTSMode', 'host'),
    ('HostConfig', 'PidsLimit', -1), ('HostConfig', 'Memory', 0),
    ('HostConfig', 'Binds', ['/var/run/docker.sock:/socket']),
    ('HostConfig', 'PortBindings', {'8000/tcp': [{'HostPort': '8000'}]}),
    ('HostConfig', 'Devices', [{'PathOnHost': '/dev/sda'}]),
    ('Config', 'User', '0'), ('Config', 'Env', ['TOKEN=SECRET']),
    ('Config', 'Entrypoint', ['/bin/sh']), ('Config', 'Volumes', {'/data': {}}),
])
def test_bad_stopped_inspection_never_starts(tmp_path, section, key, value):
    result, docker = run_fake(tmp_path, mutate=lambda obj: obj[section].__setitem__(key, value))
    assert result['status'] == 'failed' and result['stage'] == 'inspect'
    assert not any(args[0] == 'start' for args, _ in docker.calls)
    assert docker.current is None


def test_unknown_ownership_never_removed(tmp_path):
    result, docker = run_fake(tmp_path, mutate=lambda obj: obj['Config']['Labels'].clear())
    assert result['status'] == 'failed' and result['stage'] == 'cleanup'
    assert not any(args[:2] == ['container', 'rm'] for args, _ in docker.calls)


def test_preexisting_name_is_not_adopted(tmp_path):
    docker = FakeDocker(tmp_path)
    docker.current = container(docker.name, 'net:[123]')
    run = ci.IsolatedRun(docker, tmp_path, token=TOKEN)
    result = run.run(tmp_path)
    assert result['status'] == 'failed'
    assert not any(args[0] == 'create' or args[:2] == ['container', 'rm'] for args, _ in docker.calls)


@pytest.mark.parametrize('key', ci.BLOCKED_OVERRIDES)
def test_remote_override_rejected_even_if_empty_or_local(key):
    with pytest.raises(ci.IsolationError):
        ci.reject_overrides({key: ''})
    ci.reject_overrides({'PATH': '/usr/bin', 'GITHUB_TOKEN': 'not-forwarded'})


@pytest.mark.parametrize('endpoint', ['tcp://example:2375', 'unix:///tmp/other.sock', 'ssh://remote'])
def test_nonlocal_endpoint_rejected(endpoint):
    class Fake:
        def docker(self, args):
            return json.dumps([{'Name': 'default', 'Endpoints': {'docker': {'Host': endpoint}}}])
    with pytest.raises(ci.IsolationError):
        ci.verify_local_endpoint(Fake())


@pytest.mark.parametrize('change', [
    lambda obj: obj.update(extra='SECRET'), lambda obj: obj.update(schema_version=True),
    lambda obj: obj['stages'].reverse(), lambda obj: obj['stages'].append(obj['stages'][0]),
    lambda obj: obj['stages'][0].update(status='SECRET'), lambda obj: obj['stages'][0].update(path='SECRET'),
    lambda obj: obj['stages'][0].update(status='NOT_RUN'),
])
def test_public_schema_rejects_extra_private_or_incomplete_fields(change):
    value = full_summary()
    change(value)
    with pytest.raises(ci.IsolationError):
        ci.validate_summary(json.dumps(value))


def test_duplicate_fields_rejected():
    with pytest.raises(ci.IsolationError):
        ci.validate_summary('{"schema_version":1,"schema_version":1}')


@pytest.mark.parametrize('path', ['.env', 'backend/.venv/lib/test.py', 'backend/data/key.json',
                                 'backend/private/secret.py', 'scripts/secret.json',
                                 'backend/tests/fingerprint.json', 'web/test-results/x.json',
                                 'backend/model.pt', 'backend/database.db', '../backend/a.py', '/backend/a.py',
                                 'backend/tests/evidence.json', 'web/.npmrc'])
def test_context_excludes_private_and_unapproved_files(path):
    assert not ci.source_allowed(path)


@pytest.mark.parametrize('path', ['backend/app/main.py', 'backend/requirements-delivery-linux-cpu.lock',
                                 'backend/alembic/script.py.mako', 'web/package-lock.json', 'web/src/App.vue',
                                 'contracts/openapi.json', 'scripts/isolated_ml_entry.py'])
def test_context_accepts_source_and_named_configuration(path):
    assert ci.source_allowed(path)


def test_source_copy_rejects_tracked_symlink(tmp_path):
    source = tmp_path / 'backend/a.py'
    source.parent.mkdir()
    source.symlink_to('/etc/passwd')
    with pytest.raises(ci.IsolationError):
        ci.copy_source(tmp_path / 'context', '120000 blob ' + '0' * 40 + '\tbackend/a.py\0', lambda _oid: b'')


def kernel_fixture(tmp_path, monkeypatch):
    (tmp_path / 'self').mkdir()
    (tmp_path / 'net').mkdir()
    (tmp_path / 'self/status').write_text('Uid:\t10001 10001 10001 10001\nCapEff:\t00000000\nNoNewPrivs:\t1\nSeccomp:\t2\n')
    (tmp_path / 'net/route').write_text('Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n')
    (tmp_path / 'net/ipv6_route').write_text('')
    monkeypatch.setenv('ORT_DISABLE_TELEMETRY', '1')
    return {'proc': tmp_path, 'uid': 10001, 'interfaces': ['lo'], 'netns': 'net:[456]'}


def test_structural_boundary_accepts_only_private_loopback(tmp_path, monkeypatch):
    kwargs = kernel_fixture(tmp_path, monkeypatch)
    entry.verify_boundary('net:[123]', **kwargs)
    for change in ({'uid': 0}, {'interfaces': ['lo', 'eth0']}, {'netns': 'net:[123]'}):
        with pytest.raises(ValueError):
            entry.verify_boundary('net:[123]', **{**kwargs, **change})


@pytest.mark.parametrize(('needle', 'replacement'), [('CapEff:\t00000000', 'CapEff:\t00000001'),
    ('NoNewPrivs:\t1', 'NoNewPrivs:\t0'), ('Seccomp:\t2', 'Seccomp:\t0'),
    ('10001 10001 10001 10001', '10001 0 10001 10001')])
def test_kernel_security_drift_is_rejected(tmp_path, monkeypatch, needle, replacement):
    kwargs = kernel_fixture(tmp_path, monkeypatch)
    path = tmp_path / 'self/status'
    path.write_text(path.read_text().replace(needle, replacement))
    with pytest.raises(ValueError):
        entry.verify_boundary('net:[123]', **kwargs)


@pytest.mark.parametrize(('filename', 'route'), [
    ('route', 'eth0 00000000 0100000A 0003 0 0 0 00000000 0 0 0\n'),
    ('route', 'lo 00000000 00000000 0001 0 0 0 00000000 0 0 0\n'),
    ('ipv6_route', '0'*32+' 00 '+'0'*32+' 00 '+'0'*32+' 00000001 00000000 00000000 00000001 eth0\n'),
])
def test_external_or_default_routes_rejected(tmp_path, monkeypatch, filename, route):
    kwargs = kernel_fixture(tmp_path, monkeypatch)
    with (tmp_path / 'net' / filename).open('a') as handle:
        handle.write(route)
    with pytest.raises(ValueError):
        entry.verify_boundary('net:[123]', **kwargs)


def test_boundary_rejection_prevents_every_child(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entry, 'verify_boundary', lambda *a: (_ for _ in ()).throw(ValueError('SECRET')))
    monkeypatch.setattr(entry, 'run_stage', lambda *a: pytest.fail('a child started'))
    assert entry.main(['--host-netns', 'net:[123]']) == 1
    output = capsys.readouterr()
    assert 'SECRET' not in output.out + output.err
    result = ci.validate_summary(output.out)
    assert result['stages'][0]['status'] == 'failed'
    assert all(row['status'] == 'NOT_RUN' for row in result['stages'][1:])


def test_stage_order_shared_deadline_and_private_logs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entry, 'ROOT', tmp_path)
    monkeypatch.setattr(entry, 'verify_boundary', lambda *a: None)
    monkeypatch.setattr(entry, 'stage_commands', lambda: [(stage, ['never-run'], tmp_path) for stage in ci.STAGES[1:]])
    times = iter([0, 10, 20, 30, 40, 50, 60])
    monkeypatch.setattr(entry.time, 'monotonic', lambda: next(times))
    calls = []
    monkeypatch.setattr(entry, 'run_stage', lambda *args: calls.append(args))
    monkeypatch.setattr(entry, 'verify_policy_report', lambda *args: None)
    assert entry.main(['--host-netns', 'net:[123]']) == 0
    assert [call[-1] for call in calls] == [440, 430, 420, 410, 400, 390]
    assert all(call[3].parent == tmp_path / 'private' for call in calls)
    assert all(call[2]['EDGEVISION_ONNX_POLICY_ROOT'] == str(tmp_path / 'private/http') for call in calls)
    assert ci.validate_summary(capsys.readouterr().out) == full_summary()


def test_no_opt_in_or_top_level_fault_has_only_safe_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ci, 'PrivateCommands', lambda *args: pytest.fail('commands created without opt-in'))
    assert ci.main(['--expected-commit', 'a' * 40, '--report-dir', str(tmp_path / 'report')]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['stage'] == 'preparation' and result['status'] == 'failed'
    assert json.loads((tmp_path / 'report/summary.json').read_text()) == result


def test_private_command_capture_never_prints_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ci.shutil, 'which', lambda *a, **k: '/usr/bin/docker')
    commands = ci.PrivateCommands(tmp_path)
    def fake_run(args, **kwargs):
        kwargs['stdout'].write(b'SECRET private native traceback')
        assert kwargs['stderr'] is subprocess.STDOUT
        assert 'GITHUB_TOKEN' not in kwargs['env']
        assert kwargs['env']['ORT_DISABLE_TELEMETRY'] == '1'
        return subprocess.CompletedProcess(args, 2)
    monkeypatch.setattr(ci.subprocess, 'run', fake_run)
    with pytest.raises(ci.IsolationError):
        commands.command(['never-run'], timeout=1)
    assert capsys.readouterr().out == ''


def test_workflow_dispatch_gate_and_fixed_budget_are_explicit():
    workflow = (ROOT / '.github/workflows/t020-ci.yml').read_text()
    assert 'workflow_dispatch:' in workflow
    assert 'run_isolated_ml:' in workflow and 'default: false' in workflow and 'type: boolean' in workflow
    job = workflow.split('  linux-training:\n')[1]
    assert "if: ${{ github.event_name == 'workflow_dispatch' && inputs.run_isolated_ml == true }}" in job
    assert 'timeout-minutes: 20' in job and 'ubuntu-24.04' in job
    assert 'scripts/install_ml.py' not in job and 'playwright install' not in job
    assert 'summary.json' in job and 'cache-to' not in job and 'docker push' not in job
    assert 'scripts/isolated_ml_ci.py --execute' in job


def test_fixed_image_and_tool_prefixes_no_host_venv_or_early_ml():
    dockerfile = (ROOT / 'ci/isolated-ml.Dockerfile').read_text()
    assert 'FROM --platform=linux/amd64 mcr.microsoft.com/playwright:v1.64.1-noble@sha256:' in dockerfile
    assert 'COPY tool-python/' in dockerfile and 'COPY tool-node/' in dockerfile
    assert 'python3 -I -S scripts/install_ml.py --delivery --defer-check' in dockerfile
    assert 'npm ci --ignore-scripts --no-audit --no-fund' in dockerfile
    assert 'ORT_DISABLE_TELEMETRY=1' in dockerfile
    for name in ('isolated_ml_ci', 'isolated_ml_entry'):
        import ast
        tree = ast.parse((ROOT / 'scripts' / f'{name}.py').read_text())
        modules = [alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        modules += [node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
        assert not set(modules) & {'torch', 'ultralytics', 'onnx', 'onnxruntime', 'numpy', 'app'}


@pytest.mark.parametrize('status', ['failed', 'NOT_RUN', 'unverified'])
def test_incomplete_stage_never_allows_pass(status):
    payload = full_summary()
    payload['status'] = 'failed'
    payload['stages'][2]['status'] = status
    sanitized = ci.validate_summary(json.dumps(payload))
    with pytest.raises(ci.IsolationError):
        ci.public_summary('complete', True, sanitized)


def test_actual_nonzero_container_preserves_only_valid_failure_stages(tmp_path):
    class FailedDocker(FakeDocker):
        def docker(self, args, **kwargs):
            if args[0] == 'start':
                payload = full_summary()
                payload['status'] = 'failed'
                payload['stages'][2]['status'] = 'failed'
                for row in payload['stages'][3:]:
                    row['status'] = 'NOT_RUN'
                output = tmp_path / 'private-failed-command'
                output.write_text(json.dumps(payload))
                raise ci.PrivateCommandError(output)
            return super().docker(args, **kwargs)
    docker = FailedDocker(tmp_path)
    result = ci.IsolatedRun(docker, tmp_path, token=TOKEN).run(tmp_path)
    assert result['status'] == 'failed'
    assert result['stages'][2]['status'] == 'failed'
    assert all(row['status'] == 'NOT_RUN' for row in result['stages'][3:])
    assert docker.current is None


def test_timeout_cannot_claim_unknown_stages_never_ran(tmp_path):
    result, _ = run_fake(tmp_path, 'start_timeout')
    assert all(row['status'] == 'unverified' for row in result['stages'])


def test_actual_mount_rejected_before_start(tmp_path):
    result, docker = run_fake(tmp_path, mutate=lambda obj: obj.update(Mounts=[{'Source': '/private'}]))
    assert result['status'] == 'failed'
    assert not any(args[0] == 'start' for args, _ in docker.calls)


def test_interrupt_during_start_cleans_up_owned_container(tmp_path):
    class InterruptedDocker(FakeDocker):
        def docker(self, args, **kwargs):
            if args[0] == 'start':
                raise KeyboardInterrupt
            return super().docker(args, **kwargs)
    docker = InterruptedDocker(tmp_path)
    result = ci.IsolatedRun(docker, tmp_path, token=TOKEN).run(tmp_path)
    assert result['status'] == 'failed'
    assert docker.current is None


def test_cleanup_deadline_is_shared_and_exhaustion_fails(tmp_path, monkeypatch):
    docker = FakeDocker(tmp_path)
    run = ci.IsolatedRun(docker, tmp_path, token=TOKEN)
    run.image = IMAGE
    run.create_attempted = True
    times = iter([0, 31, 32])
    monkeypatch.setattr(ci.time, 'monotonic', lambda: next(times))
    assert run.cleanup() is False
    assert docker.calls == []


def test_invalid_arguments_do_not_echo_secrets(tmp_path, capsys):
    assert ci.main(['--unknown', 'SECRET']) == 1
    captured = capsys.readouterr()
    assert 'SECRET' not in captured.out + captured.err
    assert captured.err == ''
    assert entry.main(['--unknown', 'SECRET']) == 1
    captured = capsys.readouterr()
    assert 'SECRET' not in captured.out + captured.err
    assert captured.err == ''


def test_late_private_context_cleanup_failure_revokes_public_success(tmp_path, monkeypatch, capsys):
    class Temporary:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return str(tmp_path)
        def __exit__(self, *args):
            raise OSError('SECRET cleanup failure')
    class FakeRun:
        def __init__(self, *args):
            pass
        def run(self, *args):
            return {**full_summary(), 'stage': 'complete'}
    monkeypatch.setattr(ci, 'reject_overrides', lambda *args: None)
    monkeypatch.setattr(ci, 'verify_hosted_workflow', lambda *args: None)
    monkeypatch.setattr(ci.tempfile, 'TemporaryDirectory', Temporary)
    monkeypatch.setattr(ci, 'PrivateCommands', lambda *args: object())
    monkeypatch.setattr(ci, 'verify_local_endpoint', lambda *args: None)
    monkeypatch.setattr(ci, 'prepare_context', lambda *args: tmp_path)
    monkeypatch.setattr(ci, 'IsolatedRun', FakeRun)
    report = tmp_path / 'report'
    assert ci.main(['--execute', '--expected-commit', 'a' * 40, '--report-dir', str(report)]) == 1
    output = capsys.readouterr()
    assert 'SECRET' not in output.out + output.err
    result = json.loads(output.out)
    assert result['status'] == 'failed' and result['stage'] == 'cleanup'
    assert result['stages'] == full_summary()['stages']
    saved = json.loads((report / 'summary.json').read_text())
    assert saved == result


@pytest.mark.parametrize(('tests', 'skipped', 'failures', 'errors'), [
    (0, 0, 0, 0), (3, 3, 0, 0), (3, 1, 0, 0), (3, 0, 1, 0), (3, 0, 0, 1),
])
def test_policy_skip_or_missing_test_is_not_pass(tmp_path, tests, skipped, failures, errors):
    path = tmp_path / 'junit.xml'
    path.write_text(f'<testsuites><testsuite tests="{tests}" skipped="{skipped}" failures="{failures}" errors="{errors}" /></testsuites>')
    with pytest.raises(ValueError):
        entry.verify_policy_report(path)


def test_real_policy_report_requires_nonzero_executed_cases(tmp_path):
    path = tmp_path / 'junit.xml'
    path.write_text('<testsuites><testsuite tests="3" skipped="0" failures="0" errors="0" /></testsuites>')
    entry.verify_policy_report(path)


def test_only_loopback_routes_and_unreachable_ipv6_default_are_allowed(tmp_path, monkeypatch):
    kwargs = kernel_fixture(tmp_path, monkeypatch)
    with (tmp_path / 'net/route').open('a') as handle:
        handle.write('lo 0000007F 00000000 0001 0 0 0 000000FF 0 0 0\n')
    (tmp_path / 'net/ipv6_route').write_text('0'*32+' 00 '+'0'*32+' 00 '+'0'*32+' FFFFFFFF 00000001 00000000 00200200 lo\n')
    entry.verify_boundary('net:[123]', **kwargs)


def test_telemetry_guard_must_exist_before_boundary(tmp_path, monkeypatch):
    kwargs = kernel_fixture(tmp_path, monkeypatch)
    monkeypatch.delenv('ORT_DISABLE_TELEMETRY')
    with pytest.raises(ValueError):
        entry.verify_boundary('net:[123]', **kwargs)


class FakeGit:
    def __init__(self, status=''):
        self.status = status
        self.calls = []
        self.commit = 'd' * 40
        self.blobs = {}
        records = []
        for relative in (*ci.REQUIRED_SOURCE, ci.RECIPE):
            body = ('# Frozen content: ' + relative + '\r\n').encode()
            oid = ci.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body, usedforsecurity=False).hexdigest()
            self.blobs[oid] = body
            records.append('100644 blob ' + oid + '\t' + relative + '\0')
        self.tree = ''.join(records)
    def command(self, args, **kwargs):
        self.calls.append(args)
        command = args[3:]
        if command[0] == 'rev-parse':
            return self.commit + '\n'
        if command[0] == 'status':
            return self.status
        if command[0] == 'ls-tree':
            return self.tree
        if command[0] == 'cat-file':
            return self.blobs[command[2]].decode()
        raise AssertionError(args)


@pytest.mark.parametrize('status', [' M scripts/isolated_ml_entry.py\0',
                                  'M  ci/isolated-ml.Dockerfile\0',
                                  '?? ci/isolated-ml.Dockerfile\0',
                                  ' M scripts/fetch_training_asset.py\0'])
def test_modified_tracked_source_or_untracked_recipe_rejected(tmp_path, status):
    git = FakeGit(status)
    with pytest.raises(ci.IsolationError):
        ci.freeze_source(tmp_path, tmp_path / 'context', git, git.commit)
    assert not any('cat-file' in args for args in git.calls)


def test_source_is_exact_git_blob_not_live_worktree(tmp_path):
    git = FakeGit()
    mutable = tmp_path / 'scripts/fetch_training_asset.py'
    mutable.parent.mkdir()
    mutable.write_text('UNTRUSTED live bytes are never read')
    context = tmp_path / 'context'
    ci.freeze_source(tmp_path, context, git, git.commit)
    assert (context / 'source/scripts/fetch_training_asset.py').read_bytes() == b'# Frozen content: scripts/fetch_training_asset.py\r\n'
    assert (context / 'Dockerfile').read_bytes() == b'# Frozen content: ci/isolated-ml.Dockerfile\r\n'


def test_blob_mismatch_and_wrong_requested_commit_rejected(tmp_path):
    git = FakeGit()
    with pytest.raises(ci.IsolationError):
        ci.freeze_source(tmp_path, tmp_path / 'context', git, 'e' * 40)
    first = next(iter(git.blobs))
    git.blobs[first] = b'changed bytes'
    with pytest.raises(ci.IsolationError):
        ci.freeze_source(tmp_path, tmp_path / 'context', git, git.commit)


def test_missing_integration_inputs_are_not_success_placeholders(tmp_path):
    git = FakeGit()
    git.tree = ''.join(record + '\0' for record in git.tree.split('\0') if record and
                       'backend/tests/export_http_probe.py' not in record)
    with pytest.raises(ci.IsolationError):
        ci.freeze_source(tmp_path, tmp_path / 'context', git, git.commit)


def test_build_timeout_without_iidfile_is_cleanup_unknown(tmp_path):
    class DelayedBuild(FakeDocker):
        def docker(self, args, **kwargs):
            if args[0] == 'build':
                self.calls.append((args, kwargs))
                raise subprocess.TimeoutExpired('SECRET pending daemon build', 600)
            return super().docker(args, **kwargs)
    docker = DelayedBuild(tmp_path)
    result = ci.IsolatedRun(docker, tmp_path, token=TOKEN).run(tmp_path)
    assert result['status'] == 'failed' and result['stage'] == 'cleanup_unknown'
    assert not any(args[0] in {'create', 'start'} for args, _ in docker.calls)
    assert not any('prune' in args for args, _ in docker.calls)


def test_create_timeout_before_object_visible_is_cleanup_unknown(tmp_path):
    class DelayedCreate(FakeDocker):
        pending = None
        def docker(self, args, **kwargs):
            if args[0] == 'create':
                self.calls.append((args, kwargs))
                self.pending = container(self.name, args[-1])
                # Not visible during first reconciliation; daemon outcome is unknown.
                raise subprocess.TimeoutExpired('SECRET delayed daemon create', 15)
            return super().docker(args, **kwargs)
    docker = DelayedCreate(tmp_path)
    result = ci.IsolatedRun(docker, tmp_path, token=TOKEN).run(tmp_path)
    assert result['status'] == 'failed' and result['stage'] == 'cleanup_unknown'
    assert docker.pending is not None
    assert not any(args[0] == 'start' or args[:2] == ['container', 'rm'] for args, _ in docker.calls)
    assert not any('prune' in args for args, _ in docker.calls)


def hosted_context():
    return {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_WORKFLOW': 'EdgeVision feature checks',
            'EDGEVISION_RUN_ISOLATED_ML': 'true', 'GITHUB_SHA': 'd' * 40, 'GITHUB_WORKFLOW_SHA': 'd' * 40,
            'GITHUB_REPOSITORY': 'TudouXiang/edgevision-training',
            'GITHUB_WORKFLOW_REF': 'TudouXiang/edgevision-training/.github/workflows/t020-ci.yml@refs/heads/feature/test'}


def test_reviewed_hosted_workflow_context_required():
    environment = hosted_context()
    ci.verify_hosted_workflow(environment, 'd' * 40)
    for key in environment:
        with pytest.raises(ci.IsolationError):
            ci.verify_hosted_workflow({k: v for k, v in environment.items() if k != key}, 'd' * 40)


@pytest.mark.parametrize(('key', 'value'), [('RUNNER_ENVIRONMENT', 'self-hosted'),
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_EVENT_NAME', 'pull_request'),
    ('EDGEVISION_RUN_ISOLATED_ML', 'false'), ('GITHUB_SHA', 'e' * 40), ('GITHUB_WORKFLOW_SHA', 'e' * 40),
    ('GITHUB_WORKFLOW', 'other workflow'),
    ('GITHUB_WORKFLOW_REF', 'TudouXiang/edgevision-training/.github/workflows/unreviewed.yml@refs/heads/feature/test')])
def test_non_hosted_or_unreviewed_context_rejected(key, value):
    with pytest.raises(ci.IsolationError):
        ci.verify_hosted_workflow({**hosted_context(), key: value}, 'd' * 40)


def test_missing_hosted_context_stops_before_docker_or_acquisition(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ci, 'reject_overrides', lambda *args: None)
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setattr(ci, 'PrivateCommands', lambda *args: pytest.fail('commands started'))
    monkeypatch.setattr(ci, 'prepare_context', lambda *args: pytest.fail('acquisition started'))
    assert ci.main(['--execute', '--expected-commit', 'd' * 40, '--report-dir', str(tmp_path / 'report')]) == 1
    assert json.loads(capsys.readouterr().out)['stage'] == 'preparation'


def test_fixed_python_library_path_is_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv('LD_LIBRARY_PATH', '/untrusted/host/path')
    monkeypatch.setattr(ci.shutil, 'which', lambda *args, **kwargs: '/usr/bin/docker')
    commands = ci.PrivateCommands(tmp_path)
    assert commands.environment['LD_LIBRARY_PATH'] == str(ci.PYTHON_PREFIX / 'lib')
    assert ci.BASE_ENV['LD_LIBRARY_PATH'] == str(ci.PYTHON_PREFIX / 'lib')
    assert 'LD_LIBRARY_PATH=/opt/hostedtoolcache/Python/3.12.14/x64/lib' in (ROOT / 'ci/isolated-ml.Dockerfile').read_text()


def test_signal_handler_converts_termination_to_owned_cleanup(tmp_path, monkeypatch, capsys):
    callbacks = []
    prior = object()
    def fake_signal(signum, callback):
        callbacks.append(callback)
        return prior
    monkeypatch.setattr(ci.signal, 'signal', fake_signal)
    class TerminatedDocker(FakeDocker):
        def docker(self, args, **kwargs):
            if args[0] == 'start':
                callbacks[0](ci.signal.SIGTERM, None)
            return super().docker(args, **kwargs)
    docker = TerminatedDocker(tmp_path)
    monkeypatch.setattr(ci, 'reject_overrides', lambda *args: None)
    monkeypatch.setattr(ci, 'verify_hosted_workflow', lambda *args: None)
    monkeypatch.setattr(ci, 'PrivateCommands', lambda *args: docker)
    monkeypatch.setattr(ci, 'verify_local_endpoint', lambda *args: None)
    monkeypatch.setattr(ci, 'prepare_context', lambda *args: tmp_path)
    # Use the actual orchestrator with a fixed token and shared fake private root.
    original = ci.IsolatedRun
    monkeypatch.setattr(ci, 'IsolatedRun', lambda commands, private: original(commands, tmp_path, token=TOKEN))
    assert ci.main(['--execute', '--expected-commit', 'd' * 40, '--report-dir', str(tmp_path / 'report')]) == 1
    assert docker.current is None and not docker.image_exists
    assert callbacks == [ci.interrupt_for_cleanup, prior]
    assert json.loads(capsys.readouterr().out)['status'] == 'failed'


def test_entry_interrupt_kills_owned_process_group_without_output(tmp_path, monkeypatch, capsys):
    killed = []
    class FakeProcess:
        pid = 12345
        calls = 0
        def wait(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                entry.interrupt_for_cleanup(entry.signal.SIGTERM, None)
            return -9
    monkeypatch.setattr(entry.subprocess, 'Popen', lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(entry.os, 'killpg', lambda *args: killed.append(args))
    with pytest.raises(KeyboardInterrupt):
        entry.run_stage(['never-run'], tmp_path, {}, tmp_path / 'private.log', 10)
    assert killed == [(12345, entry.signal.SIGKILL)]
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('unknown', [False, True])
def test_report_write_failure_preserves_prior_sanitized_outcomes(tmp_path, monkeypatch, capsys, unknown):
    previous = {**full_summary(), 'stage': 'complete'}
    if unknown:
        previous.update(stage='execution', status='failed')
        previous['stages'][2]['status'] = 'unverified'
    class FakeRun:
        def __init__(self, *args):
            pass
        def run(self, *args):
            return previous
    monkeypatch.setattr(ci, 'reject_overrides', lambda *args: None)
    monkeypatch.setattr(ci, 'verify_hosted_workflow', lambda *args: None)
    monkeypatch.setattr(ci, 'PrivateCommands', lambda *args: object())
    monkeypatch.setattr(ci, 'verify_local_endpoint', lambda *args: None)
    monkeypatch.setattr(ci, 'prepare_context', lambda *args: tmp_path)
    monkeypatch.setattr(ci, 'IsolatedRun', FakeRun)
    def fail_write(*args, **kwargs):
        raise OSError('SECRET report write failure')
    monkeypatch.setattr(Path, 'write_text', fail_write)
    assert ci.main(['--execute', '--expected-commit', 'd' * 40, '--report-dir', str(tmp_path / 'report')]) == 1
    output = capsys.readouterr()
    assert 'SECRET' not in output.out + output.err
    result = json.loads(output.out)
    assert result['stage'] == 'cleanup' and result['status'] == 'failed'
    assert result['stages'] == previous['stages']


def test_workflow_uses_independent_approved_sha_input_without_shell_interpolation():
    import yaml
    workflow = yaml.load((ROOT / '.github/workflows/t020-ci.yml').read_text(), Loader=yaml.BaseLoader)
    approved = workflow['on']['workflow_dispatch']['inputs']['approved_commit']
    assert approved == {'description': 'Full reviewed commit SHA required only for explicit isolated ML', 'type': 'string', 'required': 'false', 'default': ''}
    job = workflow['jobs']['linux-training']
    assert job['env']['EDGEVISION_APPROVED_COMMIT'] == '${{ inputs.approved_commit }}'
    command = next(step['run'] for step in job['steps'] if step.get('name') == 'Run reviewed isolated validation')
    assert '--expected-commit "$EDGEVISION_APPROVED_COMMIT"' in command
    assert '$GITHUB_SHA' not in command and '${{' not in command


@pytest.mark.parametrize('approved', ['', 'd' * 7, 'e' * 40, '; never-execute'])
def test_unapproved_or_moved_commit_stops_before_any_preparation(tmp_path, monkeypatch, capsys, approved):
    environment = hosted_context()
    monkeypatch.setattr(ci.os, 'environ', environment)
    monkeypatch.setattr(ci, 'PrivateCommands', lambda *args: pytest.fail('must not prepare commands'))
    monkeypatch.setattr(ci, 'prepare_context', lambda *args: pytest.fail('must not acquire or build'))
    assert ci.main(['--execute', '--expected-commit', approved, '--report-dir', str(tmp_path / 'report')]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['stage'] == 'preparation' and result['status'] == 'failed'
    assert all(row['status'] == 'NOT_RUN' for row in result['stages'])


def test_schema_v1_cannot_omit_deferred_dependency_check():
    payload = full_summary()
    payload['schema_version'] = 1
    payload['stages'] = [row for row in payload['stages'] if row['stage'] != 'dependency_check']
    with pytest.raises(ci.IsolationError): ci.validate_summary(json.dumps(payload))


def test_dependency_check_is_first_child_after_boundary():
    commands = entry.stage_commands()
    assert [name for name, _, _ in commands] == list(ci.STAGES[1:])
    assert commands[0][0] == 'dependency_check'
    assert commands[0][1][1:] == ['-I', '-m', 'pip', 'check']


def test_dependency_failure_prevents_every_ml_stage(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entry, 'ROOT', tmp_path)
    boundary = []
    monkeypatch.setattr(entry, 'verify_boundary', lambda *a: boundary.append(True))
    calls = []
    def reject(args, *rest):
        assert boundary == [True]
        calls.append(args)
        raise RuntimeError('private dependency conflict')
    monkeypatch.setattr(entry, 'run_stage', reject)
    assert entry.main(['--host-netns', 'net:[123]']) == 1
    assert len(calls) == 1 and calls[0][1:] == ['-I', '-m', 'pip', 'check']
    output = capsys.readouterr()
    assert 'private dependency conflict' not in output.out + output.err
    result = ci.validate_summary(output.out)
    assert [row['status'] for row in result['stages']] == ['passed', 'failed'] + ['NOT_RUN'] * 5


def test_tool_python_path_override_rejected_before_copy(tmp_path):
    source = tmp_path / 'source'
    (source / 'lib').mkdir(parents=True)
    (source / 'lib/libpython3.12._pth').write_text('import site\n')
    destination = tmp_path / 'destination'
    with pytest.raises(ci.IsolationError): ci.copy_tool_prefix(source, destination, python=True)
    assert not destination.exists()
