# T060 I opt-in validation source checkpoints

2026-11-05 UTC. Parent source: `af2b7dfbc49e98aa9d3f8cf64a589a6e81cd25b9`.
Manual project Skills: feature-delivery and experiment-evidence. Scope is source
and lightweight verification only. Real Docker, dependency installation, model
acquisition, Torch/ORT execution, managed model probes and ML browser execution
are **NOT_RUN**. No E/I acceptance claim follows from these tests.

## Checkpoint 1: HTTP and native-policy entry source

- Add `backend/tests/inference_http_probe.py`: require a fresh explicitly opted-in
  shared training → E private data root; check successful same-project lineage;
  invoke `python -m app.inference_probe --onnx-artifact-id <E ONNX UUID>` rather
  than copying capability records. Recheck strict proof/schema/runtime/source
  binding and bounded stdlib raw comparison; exercise real HTTP image upload,
  both selected backends, idempotent submit, result/preview/download hashes,
  unauthenticated rejection, immutable unverified input, and managed bad-image
  failure with no result artifact. Synthetic input is engineering smoke only.
- Add five opt-in native negative cases: corrupt copied ONNX; simulated missing
  ORT import; actual CPU session with injected provider mismatch/execution error;
  actual CPU result changed to NaN. A test-only PT fallback sentinel must remain
  unused. Faults affect private copies or one fresh helper interpreter, not
  production selectors, original files or capabilities. Dependency absence is
  injected, not an actual uninstall. No fault case has been executed here.
- Extend isolated stage summaries to schema v3. Historical v2's exact seven E
  stages remain decodable but cannot satisfy a current execution or completion
  gate. New I stages never count as historical E evidence. Existing 450-second
  shared child budget, 480-second container budget and all isolation gates remain.
- Focused lightweight command, from backend: clear all `EDGEVISION_*` native
  opt-ins and run the existing lightweight interpreter with `-m pytest
  tests/test_isolated_ml_ci.py tests/test_inference_validation_entry.py
  tests/test_inference_runtime_policy.py -q`: exit 0, **154 passed, 5 skipped**.
  The skipped cases are the five new native cases, not passes. The first attempt
  to write the new test used an incorrect relative directory; pytest exited 4
  with file-not-found and ran no tests. Corrected before the successful run.

The exact locked/native candidate and private data root must be freshly reviewed
and authorized before the actual workflow is dispatched. Do not run these
entries in the lightweight development environment.

## Checkpoint 2: dedicated I browser and fail-closed default lanes

- Add `scripts/inference_e2e.py`, accepted only in the reviewed Linux container
  at `/opt/edgevision`, using `/opt/edgevision/private/http`. It takes no reuse
  path or credentials on the command line. The isolation entry supplies the
  observed host network namespace only through its private child environment;
  the harness reruns the existing non-root/network/capabilities/seccomp boundary
  check. Missing namespace or ordinary development invocation is rejected.
- Before starting services, acquire the shared lock and settle managed recovery;
  revalidate current production probe, raw comparison, successful HTTP result
  publication/source bindings and the still-active synthetic smoke session.
  No migration, model download, training, export, new login, capability copy or
  database copy occurs. API/Worker/Vite are owned local services; only Playwright
  gets the private session JSON, selected source IDs and synthetic PNG path.
- Require the existing strict anonymous browser receipt with every discovered
  case actually passed (no skip/flaky/unknown count acceptance). Stop all owned
  service roots and then confirm `worker.lock`, `recover_probe`, `recover` and
  absence of active jobs. Keep raw diagnostics/root private for the outer
  container owner to remove. Browser failures cannot become successful stages.
- Final v3 stage order is the exact old seven-stage sequence, followed by
  `inference_http`, `inference_policy`, `inference_browser`. Historical v2 cannot
  satisfy current execution or completion. Missing, duplicated, reordered I
  rows and incorrectly declared versions fail. Fixed no-network/non-root/no-host-
  mount isolation, fixed public asset, 450-second shared child budget, 480-second
  outer execution and 20-minute job remain unchanged. Budget exhaustion fails;
  it does not skip or extend a stage.
- Ordinary Linux/Windows workflow jobs clear the three new I opt-ins. `dev.py
  check` passes a child-only sanitized environment through every lightweight
  command, removing old and new ML flags without changing the caller environment.
- Browser scenario/config changes belong to the separate UI author. This branch
  deliberately requires `web/e2e/t060-inference.browser.ts` in frozen source,
  so actual preparation fails until that reviewed source is integrated. The
  agreed fields are `EDGEVISION_E2E_INFERENCE=1`, BASE_URL/REPORT_DIR/OUTPUT_DIR,
  INFERENCE_SESSION/PROJECT_ID/PT_ID/ONNX_ID/IMAGE under `EDGEVISION_E2E_`.

Lightweight focused command from backend, with all native opt-ins removed and
`PYTHONDONTWRITEBYTECODE=1`, using the existing lightweight virtual environment:

`python -m pytest tests/test_isolated_ml_ci.py tests/test_inference_validation_entry.py tests/test_inference_runtime_policy.py tests/test_dev_scripts_unit.py tests/test_ml_privacy.py -q`

Exit 0: **198 passed, 5 skipped, 34 subtests passed**. All five skips are native
negative cases. Seven changed Python entry files pass syntax-only `ast.parse`;
`git diff --check` exits 0. Mock cleanup tests cover web-start failure, browser
wait failure, rejected receipts and unconfirmed managed-tree cleanup.

A full lightweight backend suite was started against this uncommitted source
snapshot after the focused run. It is still in progress at this checkpoint, so
no full-suite pass is claimed. Final integrated verification must run against the final frozen candidate. Core follow-up `d774cb2` was inspected for
interface compatibility but is not cherry-picked into this branch.

## Full lightweight run outcome and isolated prerequisite correction

The full backend run launched against the code snapshot subsequently committed
as `013873fa9188b190bf28d7bed36322ebccf4edb8` completed with exit **1**:
**623 passed, 14 skipped, 1 failed, 42 subtests passed** in 333.65 seconds.
Command, from `backend`, used the existing lightweight interpreter. The interpreter path below is normalized to the project-local `.venv` alias; the original absolute path is retained only in private logs:

`env -u EDGEVISION_RUN_ISOLATED_ML -u EDGEVISION_SMOKE_ASSET -u EDGEVISION_ML_POLICY_ROOT -u EDGEVISION_ONNX_POLICY_ROOT -u EDGEVISION_INFERENCE_HTTP_ROOT -u EDGEVISION_INFERENCE_POLICY_ROOT -u EDGEVISION_E2E_INFERENCE -u EDGEVISION_E2E_ML -u EDGEVISION_E2E_DELIVERY PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q`

The sole failure was `tests/test_bootstrap.py::test_generated_contract_is_current`:
this new worktree lacked its project-local `openapi-typescript` link when that
case ran. The check failed before comparing generated artifacts. No package was
installed. A temporary symlink to the already-installed sibling Node dependency
directory supplied the generator, then both the direct `../scripts/export_contract.py
--check` and the exact failed test were rerun with the same lightweight interpreter
and opt-in-cleared environment:

- Contract check: exit **0**, generated artifacts match live FastAPI/Pydantic.
- `python -m pytest tests/test_bootstrap.py::test_generated_contract_is_current -q`:
  exit **0**, **1 passed** in 1.93 seconds.

The temporary dependency link was removed afterward; no dependency/source file
was changed. The first whole-suite failure remains recorded and is not rewritten
as a whole-suite pass. All 14 native policy cases were skipped. No native ML,
Docker, download, production capability probe or real ML browser was executed.
The separate final integrated, frozen-SHA results are recorded in [the integration report](T060-image-integration-2026-11-05.md).
