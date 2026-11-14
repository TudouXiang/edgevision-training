# Independent ONNX CPU Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trusted ONNX source ZIP with an independently verified CPU runner.
**Architecture:** Strict contract and portable closed unit first; existing managed lifecycle next; independent native acceptance last.
**Tech Stack:** Python3.12 stdlib/Pydantic, existing locked Pillow/NumPy/ONNX/ORT, Vue/TS. No new dependency.
**Spec:** `docs/adr/0015-t060-independent-package.md`.

## Global Constraints

Fixed Linux x86_64 CPU/detection-image-v1, ADR's exact 11-member ZIP and byte limits; unchanged delivery_infer source. Preserve PackageParams.onnx_artifact_id. No nested unmanaged Popen, extra queue, network/security relaxation, training images or platform package in ZIP. Ordinary tests do not run ML. P remains501 until implemented; source tests never count as native acceptance. Return only to authenticated owner; retain known base-model AGPL provenance, do not infer user-data/public-distribution rights.

## Review Focus

- Verification/use races: private descriptor-bound copy and download tests in stages2/4.
- Read-only source, symlink/existing output: stage3 rejects overwrite, leaves package untouched.
- Runtime/template drift: stage5 invalidates P capability, never reuses I proof.
- Lost response/account switch: stage5 user/project-bound request identity.
- Import contamination/licensing omissions: stages2/6 exact members and genuinely independent venv.

## 1. Strict contracts and source freeze

**Files:** new backend/app/package_contract.py, package_inputs.py; schemas.py; tests/test_package_contract.py, test_package_inputs.py.
**Interfaces:** `freeze_source(connection, project_id: str, onnx_artifact_id: str) -> dict`; `verify_input(frozen: dict, connection=None) -> dict`. Strict PackageManifest/FrozenPackage/PackageEvidence/PackageArtifactMetadata/PackageArtifactPublic. Preserve onnx_artifact_id; add optional source_job_id on PackageJobCreate for explicit retry; separate deployment_zip from arbitrary OtherArtifactPublic.
- [ ] Red tests: extra/bool/nonfinite/duplicate members, wrong project/parent, changed source, historical package compatibility; run both new pytest files.
- [ ] Implement existing E source validation reuse and complete frozen lineage/code/lock binding; check for actual historical success before tightening DTO.
- [ ] Green focused tests plus existing contract tests; regenerate OpenAPI/TS with project generator.
- [ ] Review and commit explicit task files.

## 2. Fixed builder and portable manifest validator

**Files:** new backend/app/package_cli.py (portable stdlib-only module copied unchanged as run.py), package_bundle.py, package_template/{requirements.lock,README.md,MODEL_NOTICE.md}; tests/test_package_bundle.py, test_package_licenses.py.
**Interfaces:** portable `validate_manifest(value: object) -> dict`, `verify_package(root: Path) -> dict`; builder `build_bundle(frozen: dict, directory: Path) -> dict`, `verify_bundle(path: Path, frozen: dict) -> dict`. Both use same stdlib validator, no jsonschema dependency. Returned dict is normalized known schema, no arbitrary passthrough.
- [ ] Red tests: exact11 members/limits, traversal/duplicate/link/extra, each member tampered, replaced model fd, missing notices, unchanged core/run.py bytes.
- [ ] Implement ADR's bounded stable ZIP_STORED and descriptor-copy rules. Extract complete minimal dependency closure from exact wheel METADATA and joint-lock hashes, not guessed transitive pins. Include honest source/license scope, known base notice, no images other than synthetic example.
- [ ] Green focused tests, lock-subset validation and no forbidden bundled files.
- [ ] Review and commit explicit files.

## 3. Independent runner closed unit

**Files:** package_cli.py; tests/test_package_cli.py.
**Interfaces:** `main(argv: list[str] | None = None) -> int`; `run_image(package_root: Path, image: Path, output: Path, confidence: float, iou: float) -> dict`. Flags --image/--output/--confidence/--iou, defaults.25/.45. Portable result schema1 has hashes/params/runtime/detections/image/preprocess/preview, no fake platform IDs.
- [ ] Red tests: no app/FastAPI/Torch imports; Python -I launch; readonly package; existing/symlink output; bad image/threshold; no auto-install/network; private verified model copy; no traceback.
- [ ] Implement using unchanged core. Explicitly load only the already-verified local delivery_infer.py by file loader (not ambient sys.path); -I does not supply cwd imports. One fresh process owns one load_onnx call. Pre-import verify, use private model copy, never modify package, create fresh output only.
- [ ] Green ordinary CLI/core tests with native boundary mocked and labelled; do not run native here.
- [ ] Review stages1–3 and commit.

## 4. Managed job/API/download integration

**Files:** new package_service.py, package_runner.py, package_publication.py, package_download.py, package_errors.py; main.py/job_service.py/worker.py/task_process.py/artifact dispatch; tests/test_package.py.
**Interfaces:** submit/retry uses existing inference service call conventions; `run(job_id: str, run_id: str) -> int`; `publish(job: dict) -> bool`; consume stages1–3 signatures unchanged.
- [ ] Red tests: auth/archive/cross-project, idempotency/retry, cancel before/afterGO, missingreceipt, rename/CAS, changed source/runtime, download fd replacement.
- [ ] Implement existing guardian lifecycle. Each package child checks source/template/ZIP members and hashes only; no ML import. Emit explicit trusted_model_fixed_package_integrity and not_run_for_this_artifact. Independent model execution is stage6, not inferred from ZIP creation. No nested Popen or historical same-model I task prerequisite.
- [ ] Verify full receipt/tree exit, intent/rename/CAS and cancellation; no orphan auto-success; protected download corruption409. This per-package integrity receipt is not independent-runtime proof.
- [ ] Green focused and full scripts/dev.py check; review and commit explicit files.

## 5. Capability and minimal UI

**Files:** package_assets.py/package_probe.py/tests/test_package_probe.py; PackagePanel.vue/PackagePanel.test.ts, api.ts/App.vue, generated contracts; web/e2e/t060-package.browser.ts.
**Interfaces:** `runtime_identity() -> dict`, `capability() -> dict`; operator `python -m app.package_probe --onnx-artifact-id UUID`; same package job/download API.
- [ ] Red tests: failed attempt clearsoldtrue, shared lock/recovery, template/lock/runtime drift, no API ML import, I success notP success; UI doubleclick/lostresponse/retry/refresh/accountswitch/late response.
- [ ] Implement P-specific proof using existing managed sequential fresh children, each imports ORT only once. Explicit probe may generate verified same-source I reference in one child and standalone result in another, then compare in lightweight parent. I capability establishes protocol readiness, not a same-model historic job prerequisite. Record runtime self-check scope honestly.
- [ ] Implement concise eligible ONNX selection, dependency-preparation notice, existing queue controls and verified download; preserve request identity partitioned by user/project. API only reads lightweight fresh record.
- [ ] Green probe/frontend/build/e2etypecheck; review and commit. No native execution in ordinary lane.

## 6. Clean-runtime exact-SHA acceptance

**Files:** scripts/package_e2e.py, backend/tests/package_http_probe.py, test_package_validation_entry.py; isolated_ml_entry.py/isolated_ml_ci.py, existing preparation/workflow; dated evidence.
**Interfaces:** new closed summary schema with required P stages; oldschema3 proves I only. Raw models/results/logs private.
- [ ] Red tests: missing/skippedP, oldsummary rejected asP, secrets rejected, platform-contaminated runtime, missinglicense, cleanup failure.
- [ ] Prepare minimal venv from verified closure with pip check, no app/FastAPI/Torch/Ultralytics or backend path. Existing approved preparation may fetch pinned wheels; execution remains network-isolated/non-root/nohostmount/resource bounded.
- [ ] Execute extracted CLI under Python -I with PYTHONPATH cleared in fresh directory; compare to same-source already verified private I result (or separately managed fresh reference stage), frozen matching bounds unchanged. Assert dependency/provider/model/image negative cases and actual HTTP/browser download. Never call full backend venv standalone.
- [ ] Full ordinary regression, freeze exact SHA/tree, then authorized isolated execution. Document all stages, independent runtime/import checks, dependencyclosure, notices andcleanup. No public model upload.
- [ ] Review before scopedPacceptance. Keep WindowsML/GPU/NPU/accuracy/load/fullnativefaultmatrix unaccepted; no claim onegreen means wholeproject delivery. Commit explicit evidence/status files.

## Handoff

Coordinator reviews before implementation. No user-choice blocker. Engineering checks: exact minimal wheel closure, independent runtime, historical successful package compatibility and source notices. Fixed base AGPL record is known, user data rights remain unproven. Protect untracked backend/.venv and web/node_modules; never stage them.

## Implementation checkpoint: standalone proof and isolated entry

- Implemented the three distinct managed runs: fresh platform ONNX reference, independent nine-package raw execution, independent CLI execution. Strict private record binds runtime, template, dependencies, input, output and drained receipts; complete raw comparison retains the fixed tolerance.
- Reference PNG uses Pillow encoding and portable example PNG uses standard-library encoding. Original encoded bytes are separately bound; equality is required for decoded RGB, preprocessing tensor, preview and subsequent numerical outputs. This is not a claim of identical encoded PNG bytes.
- Added strict current-runtime capability validation, fixed ZIP expansion, explicit isolated HTTP/Worker/download acceptance and a fourth fresh CLI execution of the downloaded package. This implementation has not yet run native models.
- Added the separate hash-locked nine-package installation to the existing isolated Docker build and exactly two root license files to committed-source freezing. No broader root-directory copying or execution security relaxation.
- New schema 4 requires `package_http` in addition to all ten I stages. Historical schemas 2 and 3 retain E/I-only meanings and cannot pass a current run. P browser integration remains pending; schema 4 is not full UI/project acceptance.
- Ordinary evidence so far: 129 package tests and 168 isolated-entry/HTTP opt-in tests pass. Full ordinary backend regression is pending for this checkpoint. No package dependency installation, ABI check, native P inference or P browser execution has been performed.

## First actual P attempt and follow-up

- Exact remote `2f056c944371a2cdb589c5f9c168de02a5bf91c7`, Actions #36 (`43623696620`) executed schema 4. All ten previous I stages passed; `package_http` failed. Thus P remains unaccepted. Isolated build/installation completed far enough to enter execution; this does not establish successful standalone inference.
- Complete local ordinary backend regression for that source: 817 passed, 14 skipped, 42 subtests passed (395.77 s). The skips are not native evidence.
- Added only closed anonymous HTTP/probe phase markers for the next diagnostic attempt, not private exception text, IDs, paths, results or model bytes. No safety or numerical conditions were loosened. 177 targeted boundary tests passed.
- Implemented the minimal package panel using the existing guarded polling lifecycle, user/project-scoped persisted request and acceptance receipts, retry-source identity, cancellation/logs, and same-job verified ZIP links. Full frontend: 130 tests passed, build and E2E type check passed; final targeted panel suite: 12 passed. A native browser acceptance for P remains pending.

## Second P attempt: copied-interpreter identity

- Exact remote `ba7aac8965c0ec1e6560c1a3e4d407a248d1e1b4`, Actions #38 (`43625172940`): ordinary checks and Windows process validation passed. Native schema 4 again passed all ten I stages, then reported the closed diagnostic `package_http_failure=probe_identity`. P remains unaccepted.
- Both installers use `venv.EnvBuilder` with its default `symlinks=False`. The prior launch check compared resolved executable paths across two virtual environments, incorrectly rejecting legitimate copies before any standalone inference. A real standard-library venv regression reproduced this failure.
- The minimal fix compares executable size/SHA-256 against the fixed base interpreter. Existing configuration-base, startup-hook, exact nine-package and full installed RECORD-byte checks remain required. A changed interpreter is rejected. Focused launch/installer tests: 19 passed. Complete ordinary backend regression: 825 passed, 14 skipped, 42 subtests passed (400.74 s); warnings are existing deprecations/test fixtures, not hidden native skips. Independent static review accepted the fix. New exact-SHA native validation remains pending. This fixes a reproduced identity-check defect, not a claim of completed P runtime acceptance.

## Delivery-stage regression investigation

- Exact remote `0c40b7fba1faf7974e1d7f203bb45f51938ac37e`, Actions #40 (`43627012194`), attempts 1 and 2: ordinary checks and Windows process passed; isolated schema 4 passed the first six stages but failed `browser_delivery`. All later I/P stages were `NOT_RUN`. The second attempt only retried the failed Linux job. These attempts cannot establish whether P standalone execution now works.
- Added a closed `browser_delivery_failure` enum, bounded to 256-byte private checkpoint JSON and only permitted on the failed current-schema E browser stage. Harness and UI checkpoints contain no exception text, identities, paths, outputs or credentials. Existing browser assertions, cleanup and resource/time limits remain unchanged. Markers report the last observed step, not a root-cause claim.
- Independently proved and removed unnecessary work: absent/false/malformed P proof now fails closed before runtime hashing. A valid proof still requires all current identity, environment, source, entry and receipt checks. Three new regression cases failed before the order change and passed afterward. This is not yet proven to explain the E browser failure.
- Focused diagnostics/gate suite: 194 passed. E2E TypeScript check passed. Complete backend regression: 840 passed, 14 skipped, 42 subtests passed (396.53 s). Independent static review found no blocker. Fresh native validation pending at this checkpoint. P browser acceptance remains unimplemented and unaccepted.

## Verified P HTTP checkpoint and final browser lane

- Actions #42 (`43630286972`), exact remote `9e232e061ec9371793b76cf111ac78e931d3009b` (local `420c4a41f4dfd36952f6dd0ca966c4b2224d75fd`, tree `f19aef686b2a1b0cc763ac67612463bb291ab729`) completed successfully: ordinary checks, Windows process and Linux isolated jobs all passed.
- Its public schema 4 `stage=complete` receipt contains all eleven stages passed, including `package_http`. Thus the fixed Linux CPU nine-package runtime, three-stage reference/raw/CLI comparison, managed HTTP/Worker package creation and downloaded-ZIP CLI execution have actual scoped evidence. This does not prove P UI acceptance, arbitrary artifacts/hardware or full project delivery.
- Added a dedicated package browser harness using the same verified fresh HTTP lineage/session. It requires current strict P proof and verifies the prior downloaded task/proof and historical package before starting services. Existing controlled service ownership, process-tree settlement, private diagnostics and cleanup gates are retained.
- Dedicated UI scenario asserts eligible source provenance, capability, one new job under double click, actual ZIP download size/hash, per-artifact `not_run_for_this_artifact` scope, accepted identity after reload, offline/recovery and narrow viewport. It does not run an extra model inside the browser or seed a fake backend result.
- Schema 5 adds mandatory twelfth stage `package_browser`. Schema 4 remains historical P HTTP-only evidence; no old receipt can satisfy the new current run. Execution bounds and isolation remain unchanged. Dedicated discovery found exactly one case and executed zero; full frontend 130 passed, build and E2E typecheck passed. Static independent review found no blocker. Full backend regression: 858 passed, 14 skipped, 42 subtests passed (392.57 s). Exact-SHA native browser validation remains pending.
