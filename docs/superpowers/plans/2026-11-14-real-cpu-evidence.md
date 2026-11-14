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
