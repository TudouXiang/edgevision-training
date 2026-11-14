"""Container-only P browser harness using the fresh successful HTTP lineage.

There is no reuse-root CLI. No migration, login bypass, capability copy, training
or export is performed. Session and fixture inputs go only to the private
Playwright child; service logs and raw browser output never leave the container.
"""
from __future__ import annotations

import contextlib
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import traceback

# Shared anonymous receipt validation and owned local-service helpers, not the
# older E main() routine: invoking it would create an unrelated training root.
from e2e import available_port, start_process, stop_owned, wait_for, safe_summary, browser_exit_code
from isolated_ml_entry import verify_boundary

ROOT = Path('/opt/edgevision')
BACKEND = ROOT / 'backend'
WEB = ROOT / 'web'
DATA = ROOT / 'private/http'
PRIVATE = ROOT / 'private/package-browser'
REPORT = ROOT / 'private/package-browser-report'
PYTHON = BACKEND / '.venv-delivery/bin/python'
CURRENT_PHASE = 'boundary'
PHASES = ('boundary', 'settle', 'inputs', 'tools', 'api', 'worker', 'web', 'browser', 'receipt', 'services', 'cleanup', 'unknown', 'ui_setup', 'ui_capabilities', 'ui_inventory', 'ui_submit', 'ui_result', 'ui_download', 'ui_reload', 'ui_offline', 'ui_recovery', 'ui_responsive', 'ui_complete')



def ui_failure_phase(directory: Path) -> str:
    # This is diagnostic only: it cannot alter the browser exit/receipt gates.
    try:
        path = directory / 'ui-phase.json'
        if path.is_symlink() or not path.is_file():
            return 'browser'
        with path.open('rb') as source:
            raw = source.read(257)
        if len(raw) > 256:
            return 'browser'
        value = json.loads(raw)
        if (isinstance(value, dict) and set(value) == {'phase'}
                and isinstance(value['phase'], str) and value['phase'] in PHASES
                and value['phase'].startswith('ui_')):
            return value['phase']
    except Exception:
        pass
    return 'browser'


def boundary():
    if (Path(__file__).resolve().parents[1] != ROOT or sys.platform != 'linux'
            or Path(sys.executable) != PYTHON or os.environ.get('ORT_DISABLE_TELEMETRY') != '1'):
        raise ValueError('fixed isolated image browser runtime required')
    for name in ('PLATFORM_DATA_ROOT', 'EDGEVISION_INFERENCE_HTTP_ROOT', 'EDGEVISION_INFERENCE_POLICY_ROOT', 'EDGEVISION_PACKAGE_HTTP_ROOT'):
        if os.environ.get(name) != str(DATA):
            raise ValueError('fixed private image root required')
    if any(path.is_symlink() for path in (ROOT, ROOT / 'private', DATA)) or DATA.resolve() != DATA:
        raise ValueError('private root identity changed')
    verify_boundary(os.environ.get('EDGEVISION_ISOLATED_HOST_NETNS', ''))
    if PRIVATE.exists() or REPORT.exists():
        raise ValueError('fresh browser attempt required')


def settle() -> bool:
    """Prove shared managed trees drained before and after owning the Worker."""
    from app.worker import worker_lock, recover
    from app.training_probe import recover_probe
    from app.database import transaction
    with worker_lock(DATA):
        if not recover_probe() or recover():
            return False
        with transaction() as connection:
            return connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running','cancelling')").fetchone()[0] == 0


def inputs():
    # Reuse only verified I lineage/session reading, not its execution routine.
    from inference_e2e import inputs as reference_inputs
    from app.database import transaction
    from app.run_files import read_json
    from app.package_assets import validated_template
    from app.package_probe_contract import PackageProbeRecord,StandaloneInput,StandaloneProof
    from app.package_download import verified_result
    from app.training_assets import digest_json
    pair,cookies=reference_inputs()
    evidence=read_json(DATA/'package-http-result.json',1024**2)
    if (set(evidence)!={'schema_version','status','job_id','artifact_id','proof_sha256','download_task','download_proof'}
            or type(evidence['schema_version']) is not int or evidence['schema_version']!=1 or evidence['status']!='passed'):
        raise ValueError('successful P HTTP proof required')
    record=PackageProbeRecord.model_validate(read_json(DATA/'package-capability.json',1024**2)).model_dump(mode='json')
    if evidence['proof_sha256']!=digest_json(record) or validated_template()['record_sha256']!=digest_json(record):
        raise ValueError('P proof changed')
    task=StandaloneInput.model_validate(evidence['download_task']).model_dump(mode='json')
    proof=StandaloneProof.model_validate(evidence['download_proof']).model_dump(mode='json')
    if (task['mode']!='cli' or proof['mode']!='cli' or proof['task_sha256']!=digest_json(task)
            or proof['job_id']!=task['job_id'] or proof['run_id']!=task['run_id'] or not proof['receipt_sha256']
            or task['package_sha256']!=record['package_sha256'] or task['package_size_bytes']!=record['package_size_bytes']
            or proof['environment_sha256']!=record['environment_sha256'] or proof['output']!=record['cli']['output']):
        raise ValueError('downloaded standalone proof changed')
    if any(task[key]!=value for key,value in record['cli_task'].items() if key not in {'job_id','run_id'}):
        raise ValueError('downloaded task binding changed')
    with transaction() as connection:
        row=connection.execute("SELECT * FROM artifacts WHERE id=? AND job_id=? AND project_id=? AND kind='deployment_zip'",
            (evidence['artifact_id'],evidence['job_id'],pair['onnx']['project_id'])).fetchone()
    if not row or row['parent_id']!=pair['onnx']['source_artifact_id'] or row['sha256']!=record['package_sha256']:
        raise ValueError('HTTP package lineage changed')
    verified_result(row)
    return pair,cookies


def environments(origin, api_port, web_port, pair, cookies, image):
    service={key:value for key,value in os.environ.items() if not key.startswith('EDGEVISION_E2E_')}
    service.update(ORT_DISABLE_TELEMETRY='1',PLATFORM_DATA_ROOT=str(DATA),EDGEVISION_ALLOWED_ORIGINS=origin,
        EDGEVISION_COOKIE_SECURE='false',EDGEVISION_DEV_API_PORT=str(api_port),EDGEVISION_DEV_WEB_PORT=str(web_port),PYTHONPATH=str(BACKEND))
    browser={**service,'EDGEVISION_E2E_PACKAGE':'1','EDGEVISION_E2E_BASE_URL':origin,
        'EDGEVISION_E2E_REPORT_DIR':str(REPORT),'EDGEVISION_E2E_OUTPUT_DIR':str(PRIVATE/'output'),
        'EDGEVISION_E2E_PACKAGE_SESSION':json.dumps(cookies,separators=(',',':')),
        'EDGEVISION_E2E_PACKAGE_PROJECT_ID':pair['pt']['project_id'],
        'EDGEVISION_E2E_PACKAGE_ONNX_ID':pair['onnx']['source_artifact_id'],
        'EDGEVISION_E2E_PACKAGE_PHASE_FILE':str(PRIVATE/'ui-phase.json')}
    return service,browser


def run(diagnostic) -> int:
    global CURRENT_PHASE
    CURRENT_PHASE = 'settle'
    if not settle():
        raise RuntimeError('shared managed tree exit unconfirmed')
    CURRENT_PHASE = 'inputs'
    pair, cookies = inputs()
    CURRENT_PHASE = 'tools'
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm:
        raise RuntimeError('locked browser tools unavailable')
    image = None
    api_port, web_port = available_port(), available_port()
    while web_port == api_port:
        web_port = available_port()
    origin = f'http://127.0.0.1:{web_port}'
    service, browser = environments(origin, api_port, web_port, pair, cookies, image)
    owned = []
    status = 2
    try:
        CURRENT_PHASE = 'api'
        api = start_process([str(PYTHON), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(api_port), '--no-access-log'], BACKEND, service)
        owned.append(api)
        wait_for(f'http://127.0.0.1:{api_port}/api/v1/health/ready', api)
        CURRENT_PHASE = 'worker'
        worker = start_process([str(PYTHON), '-m', 'app.worker'], BACKEND, service)
        owned.append(worker)
        CURRENT_PHASE = 'web'
        web = start_process([node, str(WEB / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(web_port), '--strictPort'], WEB, service)
        owned.append(web)
        wait_for(origin + '/api/v1/health/ready', web)
        safe_summary(REPORT, 'browser', 'running')
        CURRENT_PHASE = 'browser'
        child = subprocess.Popen([npm, 'run', 'test:e2e'], cwd=WEB, env=browser,
            stdin=subprocess.DEVNULL, stdout=diagnostic, stderr=diagnostic, start_new_session=True)
        owned.append(child)
        try:
            code = child.wait(timeout=150)
        except subprocess.TimeoutExpired:
            CURRENT_PHASE = ui_failure_phase(PRIVATE)
            raise
        CURRENT_PHASE = ui_failure_phase(PRIVATE) if code else 'receipt'
        status = browser_exit_code(REPORT, code, require_all_passed=True)
        if any(process.poll() is not None for process in (api, worker, web)):
            CURRENT_PHASE = 'services'
            status = 2
    finally:
        # Stop every owned root even if another fails; then use the production
        # shared lock/recovery protocol, not PID guesses, for managed descendants.
        failed_phase = CURRENT_PHASE
        CURRENT_PHASE = 'cleanup'
        cleanup = stop_owned(tuple(reversed(owned)))
        try:
            cleanup = settle() and cleanup
        except Exception:
            cleanup = False
        # Do not delete shared evidence or overwrite a valid browser receipt.
        # A separate private cleanup receipt is not a browser pass.
        (PRIVATE / 'cleanup.json').write_text(json.dumps({'schema_version': 1, 'status': 'passed' if cleanup else 'failed'}))
        if not cleanup:
            CURRENT_PHASE = 'cleanup'
            status = 4
        else:
            CURRENT_PHASE = failed_phase
    return status


def interrupted(_signum, _frame):
    raise KeyboardInterrupt


def main(argv=None):
    global CURRENT_PHASE
    CURRENT_PHASE = 'boundary'
    owned_private = False
    previous_mask = os.umask(0o077)
    previous_signal = signal.signal(signal.SIGTERM, interrupted)
    status = 2
    try:
        if argv:
            raise ValueError('no external inputs accepted')
        boundary()
        sys.path.insert(0, str(BACKEND))
        sys.path.insert(0, str(BACKEND / 'tests'))
        PRIVATE.mkdir(mode=0o700)
        owned_private = True
        with (PRIVATE / 'diagnostic.log').open('x') as diagnostic, contextlib.redirect_stdout(diagnostic), contextlib.redirect_stderr(diagnostic):
            try:
                status = run(diagnostic)
            except BaseException:
                traceback.print_exc()
                status = 2
    except BaseException:
        status = 2
    finally:
        if owned_private and status != 0:
            try:
                phase = CURRENT_PHASE if CURRENT_PHASE in PHASES else 'unknown'
                with (PRIVATE / 'failure.json').open('x') as receipt:
                    json.dump({'phase': phase}, receipt)
            except Exception:
                pass  # Diagnostic failure never changes acceptance or reveals details.
        os.umask(previous_mask)
        signal.signal(signal.SIGTERM, previous_signal)
    print('PASS real isolated package browser' if status == 0 else 'FAIL real isolated package browser; private diagnostics retained')
    return status


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
