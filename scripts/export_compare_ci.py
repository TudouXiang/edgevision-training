"""Explicit fixed real-data profile. Reuses owned image cleanup and kernel checks.

No native imports, dataset decoding or model execution occur on the host.
"""
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]

def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

base=load('isolated_ml_ci')
report=load('export_compare_report')
ENTRY='/opt/edgevision/scripts/export_compare_entry.py'
EXECUTION_TIMEOUT=1500

def verify_workflow(environment,sha):
    base.require(environment.get('EDGEVISION_RUN_EXPORT_COMPARE')=='true')
    base.verify_hosted_workflow(environment,sha,profile='export_compare_v1')

class RealRun(base.IsolatedRun):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.result=report.initial()

    def execute(self) -> None:
        base.require(self.image is not None)
        deadline = time.monotonic() + EXECUTION_TIMEOUT
        def remaining() -> float:
            value = deadline - time.monotonic()
            base.require(value > 0)
            return value
        self.stage = 'create'
        # Never adopt or delete a container that already occupied the random name.
        base.require(self.find_container(deadline) is None)
        self.create_attempted = True  # Before the client call: timeout is ambiguous.
        self.commands.docker([
            'create', '--name', self.name, '--label', f'{base.OWNER_LABEL}={self.token}',
            '--pull', 'never', '--network', 'none', '--user', '10001:10001', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges=true', '--ipc', 'private', '--cgroupns', 'private',
            '--shm-size', '256m', '--pids-limit', '512', '--memory', '6g', '--memory-swap', '6g',
            '--cpus', '2', '--no-healthcheck', '--restart', 'no', '--workdir', '/opt/edgevision',
            '--entrypoint', base.CONTAINER_PYTHON, self.image, '-I', '-S', ENTRY,
            '--host-netns', self.host_netns], timeout=min(15, remaining()))
        self.create_resolved = True
        self.stage = 'inspect'
        container = self.find_container(deadline)
        base.require(container is not None)
        base.verify_container(container, self.name, self.token, self.image, self.host_netns, profile='export_compare_v1')
        self.stage = 'execution'
        # If the client disappears or output is malformed, actual child outcomes
        # are unknown, not falsely reported as never run.
        self.result = report.initial()
        for item in self.result['stages']:item['status']='unverified'
        try:
            output = self.commands.docker(['start', '--attach', container['Id']], timeout=remaining())
        except base.PrivateCommandError as failure:
            if failure.output.stat().st_size <= 32768:
                self.result = report.validate(failure.output.read_text())
            raise
        self.result = report.validate(output)
        base.require(self.result['status'] == 'passed')
        # Exit code alone or a forged/missing stage summary cannot mean success.
        self.stage = 'inspect'
        container = self.find_container(deadline)
        base.require(container is not None)
        base.verify_container(container, self.name, self.token, self.image, self.host_netns, exited=True, profile='export_compare_v1')

    def run(self,context):
        try:
            self.build(context)
            self.execute()
        except BaseException:
            self.result['status']='failed'
        finally:
            if not self.cleanup():
                self.result['status']='failed'
                self.result['stages'][-1]['status']='failed'
        return report.validate(json.dumps(self.result))


def prepare(private,commands,expected_commit):
    context=base.prepare_context(ROOT,private,commands,expected_commit,recipe='ci/isolated-real-cpu.Dockerfile')
    commands.command([str(base.PYTHON_PREFIX/'bin/python3'),'-I','-S',
                      str(context/'source/scripts/fetch_real_cpu_data.py'),
                      '--output-dir',str(context/'public-data')],timeout=300,capture=False)
    # Recheck acquired bytes before network-connected image build; no decoding.
    pins=load('fetch_real_cpu_data').PINS
    from hashlib import sha256
    for kind,(size,expected) in pins.items():
        path=context/'public-data'/f'{kind}.tar.gz'
        base.require(path.is_file() and not path.is_symlink() and path.stat().st_size==size)
        digest=sha256()
        with path.open('rb') as source:
            while block:=source.read(1024*1024):digest.update(block)
        base.require(digest.hexdigest()==expected)
    return context


def main(argv=None):
    result=report.initial();destination=None;finished=False
    old_mask=os.umask(0o077)
    old_signal=signal.signal(signal.SIGTERM,base.interrupt_for_cleanup)
    try:
        parser=base.QuietParser(add_help=False)
        parser.add_argument('--execute',action='store_true')
        parser.add_argument('--expected-commit',required=True)
        parser.add_argument('--report-dir',type=Path,required=True)
        options=parser.parse_args(argv);destination=options.report_dir
        base.require(options.execute);base.reject_overrides(dict(os.environ))
        verify_workflow(dict(os.environ),options.expected_commit)
        with tempfile.TemporaryDirectory(prefix='edgevision-real-cpu-') as directory:
            private=Path(directory);commands=base.PrivateCommands(private)
            base.verify_local_endpoint(commands)
            context=prepare(private,commands,options.expected_commit)
            result=RealRun(commands,private).run(context);finished=True
    except BaseException:
        result['status']='failed'
        if finished:result['stages'][-1]['status']='failed'
    try:
        result=report.validate(json.dumps(result))
        if destination is not None:
            destination.mkdir(parents=True,exist_ok=True)
            (destination/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    except BaseException:
        result=report.initial()
        result['stages'][-1]['status']='failed'
    finally:
        os.umask(old_mask);signal.signal(signal.SIGTERM,old_signal)
    print(json.dumps(result,separators=(',',':')),flush=True)
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
