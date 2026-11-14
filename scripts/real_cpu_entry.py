"""Stdlib-only network namespace check before the fixed real experiment child."""
import importlib.util
import json
import os
from pathlib import Path
import signal

ROOT=Path('/opt/edgevision')
SOURCE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location(name,SOURCE/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

boundary=load('isolated_ml_entry')
report=load('real_cpu_report')


def main(argv=None):
    result=report.initial();launched=False
    old_mask=os.umask(0o077)
    old_signal=signal.signal(signal.SIGTERM,boundary.interrupt_for_cleanup)
    try:
        parser=boundary.QuietParser(add_help=False);parser.add_argument('--host-netns',required=True)
        args=parser.parse_args(argv)
        boundary.verify_boundary(args.host_netns)
        result['stages'][0]['status']='passed'
        private=ROOT/'private';private.mkdir(mode=0o700)
        environment={**os.environ,'ORT_DISABLE_TELEMETRY':'1',
                     'PLATFORM_DATA_ROOT':str(private/'real-platform'),
                     'EDGEVISION_SMOKE_ASSET':str(ROOT/'asset/yolo11n.pt'),
                     'EDGEVISION_ISOLATED_HOST_NETNS':args.host_netns}
        launched=True
        try:
            boundary.run_stage([str(ROOT/'backend/.venv-delivery/bin/python'),'-I',
                                str(ROOT/'backend/tests/real_cpu_probe.py')],
                               ROOT/'backend',environment,private/'real-private.log',1440)
        finally:
            path=private/'real-receipt.json'
            if path.is_symlink() or not path.is_file():raise ValueError('receipt missing')
            with path.open('rb') as source:raw=source.read(16385)
            if len(raw)>16384:raise ValueError('receipt size')
            result=report.validate(raw.decode('utf-8'))
    except BaseException:
        result['status']='failed'
        if not launched:result['stages'][0]['status']='failed'
        elif result['stages'][0]['status']=='passed' and all(x['status']=='NOT_RUN' for x in result['stages'][1:]):
            for x in result['stages'][1:]:x['status']='unverified'
    finally:
        os.umask(old_mask);signal.signal(signal.SIGTERM,old_signal)
    print(json.dumps(result,separators=(',',':')),flush=True)
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
