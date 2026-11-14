"""Container-only I browser harness using the fresh successful HTTP lineage.

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
PRIVATE = ROOT / 'private/inference-browser'
REPORT = ROOT / 'private/inference-browser-report'
PYTHON = BACKEND / '.venv-delivery/bin/python'
CURRENT_PHASE = 'boundary'
PHASES = ('boundary', 'settle', 'inputs', 'tools', 'api', 'worker', 'web', 'browser', 'receipt', 'services', 'cleanup', 'unknown', 'ui_setup', 'ui_capabilities', 'ui_inventory', 'ui_upload', 'ui_pt_submit', 'ui_pt_submit_inventory', 'ui_pt_submit_model', 'ui_pt_submit_thresholds', 'ui_pt_submit_ready', 'ui_pt_submit_request', 'ui_pt_submit_response', 'ui_pt_result', 'ui_pt_preview', 'ui_pt_download', 'ui_pt_reload', 'ui_onnx_submit', 'ui_onnx_submit_inventory', 'ui_onnx_submit_model', 'ui_onnx_submit_thresholds', 'ui_onnx_submit_ready', 'ui_onnx_submit_request', 'ui_onnx_submit_response', 'ui_onnx_result', 'ui_onnx_preview', 'ui_onnx_download', 'ui_onnx_reload', 'ui_offline', 'ui_recovery', 'ui_responsive', 'ui_complete')



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
    for name in ('PLATFORM_DATA_ROOT', 'EDGEVISION_INFERENCE_HTTP_ROOT', 'EDGEVISION_INFERENCE_POLICY_ROOT'):
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
    from app.database import transaction
    from app.run_files import read_json
    from app.inference_probe import sources
    from app.inference_download import result
    from app.job_service import artifact_public, job_public
    from app.security import parse_timestamp, utc_now
    from inference_http_probe import verify_probe, check_result
    evidence = read_json(DATA / 'inference-http-result.json', 1024**2)
    if (set(evidence) != {'schema_version', 'status', 'pt', 'onnx', 'comparison', 'invalid_image_error'}
            or evidence['schema_version'] != 1 or evidence['status'] != 'passed'
            or evidence['invalid_image_error'] != 'IMAGE_DECODE_FAILED'):
        raise ValueError('successful fresh I HTTP evidence required')
    exported = read_json(DATA / 'export-artifact.json', 1024**2)
    cookies = read_json(DATA / 'smoke-session.json', 16*1024)
    if set(cookies) != {'edgevision_session', 'edgevision_csrf'} or not all(
            isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{40,128}', value) for value in cookies.values()):
        raise ValueError('bounded synthetic session required')
    with transaction() as connection:
        connection.execute('BEGIN')
        pair = sources(connection, exported['id'])
        session = connection.execute("SELECT s.expires_at, s.revoked_at, u.id, u.username, u.role, u.is_active "
            "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.csrf_hash=?",
            (sha256(cookies['edgevision_session'].encode()).hexdigest(), sha256(cookies['edgevision_csrf'].encode()).hexdigest())).fetchone()
        training = read_json(DATA / 'first-result.json', 1024**2)
        if (not session or session['id'] != training['created_by'] or session['username'] != 'smoke'
                or session['role'] != 'admin' or not session['is_active'] or session['revoked_at']
                or parse_timestamp(session['expires_at']) <= utc_now()):
            raise ValueError('synthetic session expired or changed')
        rows = {}
        for backend in ('pt', 'onnx'):
            row = connection.execute("SELECT * FROM artifacts WHERE id=? AND kind='inference_result'", (evidence[backend],)).fetchone()
            if not row:
                raise ValueError('HTTP result artifact missing')
            job = connection.execute('SELECT * FROM jobs WHERE id=?', (row['job_id'],)).fetchone()
            image_id = json.loads(job['input_snapshot_json'])['image']['artifact_id']
            image = connection.execute('SELECT * FROM artifacts WHERE id=?', (image_id,)).fetchone()
            rows[backend] = (dict(row), job_public(job), artifact_public(image))
    record = verify_probe(DATA, pair)
    if record['comparison'] != evidence['comparison']:
        raise ValueError('HTTP comparison receipt changed')
    for backend, (row, job, image) in rows.items():
        check_result(result(row), artifact_public(row), job, pair[backend], image, record)
    return pair, cookies


def environments(origin, api_port, web_port, pair, cookies, image):
    # Credentials/IDs are absent from service environments and command lines.
    service = {key: value for key, value in os.environ.items() if not key.startswith('EDGEVISION_E2E_')}
    service.update(ORT_DISABLE_TELEMETRY='1', PLATFORM_DATA_ROOT=str(DATA),
        EDGEVISION_ALLOWED_ORIGINS=origin, EDGEVISION_COOKIE_SECURE='false',
        EDGEVISION_DEV_API_PORT=str(api_port), EDGEVISION_DEV_WEB_PORT=str(web_port), PYTHONPATH=str(BACKEND))
    browser = {**service, 'EDGEVISION_E2E_INFERENCE': '1', 'EDGEVISION_E2E_BASE_URL': origin,
        'EDGEVISION_E2E_REPORT_DIR': str(REPORT), 'EDGEVISION_E2E_OUTPUT_DIR': str(PRIVATE / 'output'),
        'EDGEVISION_E2E_INFERENCE_SESSION': json.dumps(cookies, separators=(',', ':')),
        'EDGEVISION_E2E_INFERENCE_PROJECT_ID': pair['pt']['project_id'],
        'EDGEVISION_E2E_INFERENCE_PT_ID': pair['pt']['source_artifact_id'],
        'EDGEVISION_E2E_INFERENCE_ONNX_ID': pair['onnx']['source_artifact_id'],
        'EDGEVISION_E2E_INFERENCE_IMAGE': str(image),
        'EDGEVISION_E2E_INFERENCE_PHASE_FILE': str(PRIVATE / 'ui-phase.json')}
    return service, browser


def run(diagnostic) -> int:
    global CURRENT_PHASE
    CURRENT_PHASE = 'settle'
    from app.delivery_infer import synthetic_png
    if not settle():
        raise RuntimeError('shared managed tree exit unconfirmed')
    CURRENT_PHASE = 'inputs'
    pair, cookies = inputs()
    CURRENT_PHASE = 'tools'
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm:
        raise RuntimeError('locked browser tools unavailable')
    image = PRIVATE / 'synthetic.png'
    image.write_bytes(synthetic_png())
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
    print('PASS real isolated image browser' if status == 0 else 'FAIL real isolated image browser; private diagnostics retained')
    return status


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
