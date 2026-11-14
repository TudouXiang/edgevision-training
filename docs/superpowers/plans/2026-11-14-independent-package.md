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
