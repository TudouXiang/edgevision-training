# Bounded export error groups implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Quantify the already reproduced mismatch without changing product validation.
**Architecture:** Extend only the separately selected diagnostic profile. A pure helper owns fixed grouped statistics and validation, shared by child and public report. Preserve three independent managed arms and existing resource limits.
**Tech Stack:** Existing Python/NumPy runtime; stdlib-only public validator; no new dependency.
**Spec:** `docs/evidence/T070-real-cpu-diagnostic-2026-11-15.md` and the read-only review of its proposed next experiment.

## Global constraints
- Fixed A/B/C, zero/gradient/pattern inputs, original reference and `1e-4 + 1e-4 * abs(reference)`.
- Two known classes in this frozen research subset; boxes 33600 elements, scores 16800 per input. No class names, coordinates, raw values or tensor hashes.
- Only finite bounded numeric summaries; nonfinite groups have null numeric statistics and cannot count as complete acceptable observations.
- Original→ORT all arms; original→fused and fused→ORT only C. Left side is reference; original product judgment never replaced by fused judgment.
- No product exporter, capability, API kind, budget, privacy or kernel-boundary changes. Schema version 2 labels new receipts distinctly from #68.

## Review focus
- Exact threshold and zero reference; no rounded comparisons.
- Reference direction cannot accidentally reverse.
- Slice boundaries/count consistency, dtype/shape rejection before arithmetic.
- Nonfinite values are not silently discarded; bool is not accepted as numeric data.
- Partial/runtime/policy failures cannot be promoted by full-looking statistics.

## Task 1: Pure grouped statistics and public contract
Files: new `scripts/export_compare_metrics.py`, new `backend/tests/test_export_compare_metrics.py`; update `scripts/export_compare_report.py` and its tests.
Interface: `measure_arrays(np, reference, actual) -> {boxes:stats,scores:stats}` (shape/dtype gate), `measure_values(reference, actual)` (pure FP64 scalar reduction); `empty_matrix(arm)`; `validate_matrix(matrix, arm, checks)`; `complete(matrix, arm)`.
Stats keys: elements, finite, mismatch_count, max_absolute_error, max_tolerance_ratio. Fixed shape (1,6,8400), FP32; arithmetic FP64. Max absolute bound1e40, ratio1e44. Exactly two groups and fixed directions/inputs. Unexecuted sample=null.
- [x] Add failing threshold/direction/shape/count/nonfinite/closed-schema tests.
- [x] Implement minimal pure helper and proof v2 validation, preserving diagnostic-only status semantics.
- [x] Run synthetic tests; no native model execution.

## Task 2: Native diagnostic wiring and bounded receipt
Files: `backend/app/real_export_diagnostic.py`, coordinator/entry/report guards and tests.
- [x] Collect statistics on the same already-computed output arrays; no extra input/model run. C adds fused→ORT statistics.
- [x] Derive consistency checks while retaining original product compare_arrays for pass/fail; validate before writing.
- [x] Keep fatal audit marker and source/runtime checks; modest bounded JSON increase only if required by maximum schema size.
- [ ] Run focused tests, independent read-only review, frozen full aggregate, exact safe branch publication.
- [ ] Wait ordinary CI then dispatch one reviewed exact-SHA diagnostic profile. Save evidence and do not claim a fix from diagnostics alone.

## Checkpoint

280 focused tests passed. Independent review found a partial-receipt window when statistics were saved before a comparator runtime error; two RED tests reproduced missing atomic observation behavior. `compare_observation` now returns stats+decision together only after a completed comparison, so runtime errors preserve a null suffix. Proof limit8192, summary32768; maximum closed schema fixture fits. Full regression and native validation pending.
