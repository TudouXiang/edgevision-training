# Real CPU Dataset and Recovery Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce bounded real-data CPU experiment and isolated cancellation/recovery/backup evidence without changing existing acceptance claims.

**Architecture:** First freeze a deterministic licensed public-image subset with strict archive/XML/image validation. Then add a separately selected, exact-SHA reviewed CI profile sharing the existing kernel-isolated runner, preserving the old twelve-stage profile and its budgets. Execute new numeric evidence and recovery checks only inside that new isolated profile.

**Tech Stack:** Python standard library, existing Pillow/pytest, fixed YOLO11n/PyTorch/ONNX Runtime locks, GitHub-hosted Docker network-none.

**Spec:** `docs/experiments/real-data-cpu-plan.md`, `docs/acceptance.md`, existing ADR0012/0013 privacy boundaries.

## Global Constraints

- No native ML on cloud without kernel boundary or on memory-pressured PEC; no user data/model publication.
- Public Oxford archives only, fixed hashes, research-only use with both current webpage and archived license retained.
- 60 train /20 validation /20 test, from annotated official trainval only, cat_head/dog_head, pre-result SHA256-name order.
- 1 epoch/320/batch1/seed0/learning_rate0.01; PT/ONNX inference follows existing640 protocol; current twelve-stage acceptance remains unchanged.
- No fake metrics, no empty-label substitution for absent official test XML, no automatic CI run of ML on push.

## Review Focus

- Archive traversal, links, duplicate members and expansion bombs: reject before extracting selected bytes.
- XML entities, malformed boxes and mismatching dimensions: reject, do not clamp.
- Duplicate image bytes across selected partitions: reject and never silently resample after results.
- Preparation imports executing ML before network isolation: standard-library-only acquisition; image/model work after boundary.
- Untrusted output or failed cleanup: publish only schema-validated bounded values; retain failure/unknown, not success.

## Task 1: Frozen real dataset preparation

Files: create `scripts/real_cpu_dataset.py`, `backend/tests/test_real_cpu_dataset.py`.
Interfaces: `prepare_subset(images_archive: Path, annotations_archive: Path, destination: Path) -> dict`; returns summary counts/hashes, writes fresh private dataset ZIP and manifest, never downloads or runs models.
- [x] Write failing tests for split determinism/disjointness, malformed archive/XML/box/dimension/duplicate-image rejection, fresh-output-only behavior.
- [x] Run focused pytest and verify expected failure before implementation.
- [x] Implement archive inventory bounds and fixed source hashes, parse public trainval/species, frozen ordering, image and VOC conversion validation, selected-byte manifest and YOLO ZIP.
- [x] Run focused tests, then execute preflight on actual downloaded archives without ML; freeze resulting manifest before any training.
- [ ] Review, commit and push checkpoint; publish counts/hashes only, not images or private ZIP.

## Task 2: Separately reviewed isolated experiment profile

Files: new fixed experiment entry/report module; minimal profile extension to `scripts/isolated_ml_ci.py`; explicit workflow choice and corresponding recipe/tests.
- [ ] Independently review reuse design before implementation; no global monkeypatching or weaker default runner checks.
- [ ] Tests must prove unchanged legacy profile, exact commit/entry/env/container verification, fixed archive acquisition, rejected dynamic fields, bounded metrics, failure and cleanup handling.
- [ ] Implement new explicit profile with its own finite budget, stages and summary meaning; acquisition only in preparation, network-none execution with existing UID/capability/6GiB/2CPU limits.
- [ ] Run complete ordinary regression, source/privacy review, publish isolated branch, dispatch exact reviewed SHA.

## Task 3: Real experiment and recovery evidence

Files: dedicated private-runtime HTTP exercise using existing product API/Worker, tests for its closed receipt, `docs/evidence/` report.
- [ ] Freeze actual 100-image manifest and measurement parameters before run; verify genuine training and independent test evaluation.
- [ ] Verify PT/ONNX same input and preprocessing, collect bounded raw timings and finite metrics with no post-hoc threshold adjustment.
- [ ] On isolated task data only: cancel a real running task; stop/restart only owned Worker and verify interrupted terminal state/no orphan process; backup quiescent DB plus referenced assets to fresh destination and verify restored readability/hashes.
- [ ] Preserve failures and NOT_RUN. Report exact revision/environment/commands/exit codes; no whole-project acceptance until final gates close.

## Execution ledger

- Task 1 checkpoint: local c3b7266 / remote 914d628c4589188f54e5d55685c9e21fc3715a72, feature branch `feat/t070-real-cpu`; exact tree 4c35a31ae0356c9401d23695c4c271e4afceeffe, main untouched. Focused 18 passed; independent security review passed after private snapshot TOCTOU repair. Two real-data preparations yielded identical frozen receipts. CI #56 started, not yet claimed successful.
- Task 2 in progress: separate `real_cpu_report.py` bounded numeric protocol with 16 focused passing tests; missing module red demonstrated before implementation. No execution profile/entry/runtime wired yet. Synthetic protocol test values are not experimental measurements.
- Ruling: keep native experiment entirely separate from legacy 12-stage receipt and default budgets, with an explicit profile and exact-SHA gate; avoid monkeypatching runner globals. If insufficient budget, report failure rather than silently increasing or rerunning training.
- Task 3 NOT_RUN: real training, evaluation, timing, cancellation, Worker recovery, backup/restore.
- Task 2/3 implementation prepared: closed real CPU entry/runner/recipe/workflow, fixed acquisition, real HTTP train/export/inference, preloaded-byte per-backend measurement, native metric-bound cancellation/Worker interruption, quiescent SQLite/file restore. Not dispatched yet.
- Review fixes: restore respects inference_input 409; interruption waits a complete bound epoch metric, using 2-epoch drill-only tasks; incomplete/error paths cannot claim cleanup passed, successful path checks no active jobs and all drain receipts.
- Ruling: preserve exact VOC integer test corners by bounded inverse rounding of frozen .12g labels; observed -1.875e-10 pixel binary roundoff is not an invalid original box. Reject anything >1e-6 pixel from an integer rather than clamp.
- Ruling: new workflow gets 45-minute outer bound to cover 300-second fixed download, existing600-second build and1500-second execution plus setup/cleanup; old workflow limits unchanged. Both profile toggles together run neither native job to avoid accidental duplicate heavy work.
- Final focused gate:315 tests passed. Native helper refuses non-container checkout. Source-only actual dataset validator:100 images/100 annotations accepted. The aggregate run overlapped late review fixes and cannot establish a final green revision; retain its failure evidence and require exact-commit full CI before native dispatch.
- Exact native-profile checkpoint a31f365: local immutable aggregate 943 backend passed /14 skipped,157 frontend passed, build/contract passed; CI #58 green including browser and Windows. #59 same SHA genuine frozen-data training passed, export failed, later experiment/drill stages NOT_RUN and cleanup unverified. Its ordinary checks/Windows both passed. No model accuracy claim.
- Export boundary diagnostic checkpoint: optional closed phase/error only when export and overall failed; no raw exceptions/output. Seven phases retain original assertions/timeouts. Red tests observed,57 focused tests green, independent read-only review no blockers. Immutable aggregate:950 backend passed /14 skipped (396.86s),157 frontend passed, production build and contract passed. Next exact-SHA native run required; do not treat instrumentation as a fix.
- #60 exact f204cf0 ordinary CI succeeded; native #61 training passed, export_result/assertion failed, later stages NOT_RUN, cleanup unverified. #61 ordinary checks and Windows succeeded. No production fix inferred.
- Closed task-state/code diagnostic: red failures observed before implementation;60 focused passed and independent read-only review no blockers. Keeps every non-succeeded task failing, maps unknown code/state to unknown, never includes error_message/IDs. Full immutable aggregate completed successfully (details in next checkpoint); next native exact-SHA evidence required.
