"""Container-only, standard-library boundary check before any ML child starts.

Do not execute while actual ML remains unapproved. No outbound connectivity
probe is used: namespace/interface/route/process state is checked structurally.
Child stdout, stderr, databases and artifacts stay inside the disposable container.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
from xml.etree import ElementTree

ROOT = Path('/opt/edgevision')
PYTHON = ROOT / 'backend/.venv-delivery/bin/python'
STAGES = ('isolation', 'dependency_check', 'training_http', 'export_http', 'onnx_policy', 'training_policy', 'browser_delivery')
STAGE_BUDGET = 450


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('arguments')


def interrupt_for_cleanup(_signal, _frame):
    raise KeyboardInterrupt


def summary(statuses: dict[str, str]) -> dict:
    return {'schema_version': 2, 'stage': 'isolated_ml',
            'status': 'passed' if all(statuses.get(s) == 'passed' for s in STAGES) else 'failed',
            'stages': [{'stage': s, 'status': statuses.get(s, 'NOT_RUN')} for s in STAGES]}


def verify_boundary(host_netns: str, *, proc: Path = Path('/proc'), uid: int | None = None,
                    interfaces: list[str] | None = None, netns: str | None = None) -> None:
    """Fail closed on missing, malformed or non-isolated kernel observations."""
    if (os.getuid() if uid is None else uid) == 0:
        raise ValueError('boundary')
    if not re.fullmatch(r'net:\[[0-9]+\]', host_netns):
        raise ValueError('boundary')
    own_netns = os.readlink(proc / 'self/ns/net') if netns is None else netns
    if not re.fullmatch(r'net:\[[0-9]+\]', own_netns) or own_netns == host_netns:
        raise ValueError('boundary')
    names = [name for _, name in socket.if_nameindex()] if interfaces is None else interfaces
    if names != ['lo']:
        raise ValueError('boundary')
    status = {}
    for line in (proc / 'self/status').read_text().splitlines():
        key, _, value = line.partition(':')
        status[key] = value.strip()
    if (int(status['CapEff'], 16) != 0 or status['NoNewPrivs'] != '1' or status['Seccomp'] != '2'
            or any(int(value) == 0 for value in status['Uid'].split())):
        raise ValueError('boundary')
    # /proc/net/route: kernel values are little-endian hex IPv4 addresses.
    lines = (proc / 'net/route').read_text().splitlines()
    if not lines or not lines[0].split()[:3] == ['Iface', 'Destination', 'Gateway']:
        raise ValueError('boundary')
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 11 or fields[0] != 'lo':
            raise ValueError('boundary')
        destination, gateway, mask = (int(fields[i], 16) for i in (1, 2, 7))
        address = ipaddress.IPv4Address(destination.to_bytes(4, 'little'))
        netmask = ipaddress.IPv4Address(mask.to_bytes(4, 'little'))
        network = ipaddress.IPv4Network(f'{address}/{netmask}', strict=False)
        if gateway or not network.subnet_of(ipaddress.IPv4Network('127.0.0.0/8')):
            raise ValueError('boundary')
    for line in (proc / 'net/ipv6_route').read_text().splitlines():
        fields = line.split()
        if len(fields) != 10 or fields[9] != 'lo':
            raise ValueError('boundary')
        # Kernel emits unreachable default routes on lo. They carry RTF_REJECT,
        # no gateway and cannot route packets. Only that or ::1/128 is accepted.
        destination = ipaddress.IPv6Address(int(fields[0], 16))
        prefix, gateway, flags = int(fields[1], 16), int(fields[4], 16), int(fields[8], 16)
        unreachable_default = destination == ipaddress.IPv6Address('::') and prefix == 0 and flags & 0x200
        if gateway or not (unreachable_default or (destination.is_loopback and prefix == 128)):
            raise ValueError('boundary')
    if os.environ.get('ORT_DISABLE_TELEMETRY') != '1':
        raise ValueError('boundary')


def stage_commands(root: Path = ROOT) -> list[tuple[str, list[str], Path]]:
    python = str(root / 'backend/.venv-delivery/bin/python')
    backend = root / 'backend'
    return [
        ('dependency_check', [python, '-I', '-m', 'pip', 'check'], backend),
        ('training_http', [python, 'tests/training_http_probe.py'], backend),
        ('export_http', [python, 'tests/export_http_probe.py'], backend),
        ('onnx_policy', [python, '-m', 'pytest', 'tests/test_onnx_runtime_policy.py', '-q',
                         '--junitxml=' + str(root / 'private/onnx_policy.xml')], backend),
        ('training_policy', [python, '-m', 'pytest', 'tests/test_training_ml_policy.py', '-q',
                             '--junitxml=' + str(root / 'private/training_policy.xml')], backend),
        ('browser_delivery', [python, str(root / 'scripts/e2e.py'), '--delivery', '--ml-asset',
                              str(root / 'asset/yolo11n.pt'), '--report-dir',
                              str(root / 'private/browser-report')], root),
    ]


def verify_policy_report(path: Path) -> None:
    # Pytest exit 0 may mean every case was skipped. That is not ML evidence.
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('policy report')
    root = ElementTree.fromstring(path.read_bytes())
    suites = [root] if root.tag == 'testsuite' else list(root)
    if root.tag not in {'testsuite', 'testsuites'} or not suites:
        raise ValueError('policy report')
    count = 0
    for suite in suites:
        if suite.tag != 'testsuite' or any(int(suite.attrib[name]) != 0 for name in ('failures', 'errors', 'skipped')):
            raise ValueError('policy report')
        count += int(suite.attrib['tests'])
    if count <= 0:
        raise ValueError('policy report')


def run_stage(args: list[str], cwd: Path, environment: dict[str, str], output: Path, remaining: float) -> None:
    if remaining <= 0:
        raise TimeoutError('budget')
    with output.open('xb') as log:
        process = subprocess.Popen(args, cwd=cwd, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            if process.wait(timeout=remaining) != 0:
                raise RuntimeError('stage')
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            raise


def main(argv: list[str] | None = None) -> int:
    statuses = dict.fromkeys(STAGES, 'NOT_RUN')
    current = 'isolation'
    previous_signal = signal.signal(signal.SIGTERM, interrupt_for_cleanup)
    previous_mask = os.umask(0o077)
    try:
        parser = QuietParser(add_help=False)
        parser.add_argument('--host-netns', required=True)
        args = parser.parse_args(argv)
        verify_boundary(args.host_netns)
        statuses[current] = 'passed'
        private = ROOT / 'private'
        private.mkdir(mode=0o700)
        data = private / 'http'
        # Fresh shared HTTP evidence is used by both policy suites and export.
        environment = {**os.environ, 'ORT_DISABLE_TELEMETRY': '1',
                       'PLATFORM_DATA_ROOT': str(data),
                       'EDGEVISION_SMOKE_ASSET': str(ROOT / 'asset/yolo11n.pt'),
                       'EDGEVISION_ML_POLICY_ROOT': str(data),
                       'EDGEVISION_ONNX_POLICY_ROOT': str(data),
                       'PYTHONPATH': str(ROOT / 'backend')}
        deadline = time.monotonic() + STAGE_BUDGET
        for current, command, cwd in stage_commands():
            run_stage(command, cwd, environment, private / f'{current}.log', deadline - time.monotonic())
            if current in {'onnx_policy', 'training_policy'}:
                verify_policy_report(private / f'{current}.xml')
            statuses[current] = 'passed'
    except BaseException:
        # No exception text or child output reaches Docker's public output stream.
        statuses[current] = 'failed'
    result = summary(statuses)
    os.umask(previous_mask)
    signal.signal(signal.SIGTERM, previous_signal)
    print(json.dumps(result, separators=(',', ':')), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
