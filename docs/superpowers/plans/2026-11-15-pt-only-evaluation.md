# PT-only frozen test evaluation implementation plan

> Execute inline under executing-plans; final independent review before native run.

**Goal:** Independent truthful PT test metrics despite ONNX failure.
**Architecture:** Closed hosted profile, existing frozen dataset/training/PT helpers,
separate receipt. No product/UI changes or device operations.
**Tech Stack:** Existing stdlib runner, FastAPI/Worker, pinned Linux CPU runtime.
**Spec:** ../specs/2026-11-15-pt-only-evaluation-design.md

## Constraints and review focus

All spec bounds apply. Test split must never train; no export/model conversion.
No public predictions/identifiers/logs. Failed metric/source/cleanup checks cannot
pass; malformed/nonfinite/inconsistent counts rejected. Timeout before each stage
must preserve cleanup. Four ML flags mutually exclusive. Source tree remains
isolated from UI work and remote publication uses a new feature branch.

## Tasks

1. [ ] RED then GREEN closed report tests for exact schema/counts/null/passed gates,
   unknown fields and nonfinite/duplicate JSON. Implement scripts/pt_eval_report.py.
2. [ ] RED then GREEN guard/profile tests; create pt_eval_ci.py,pt_eval_entry.py and
   closed profile allowlist in isolated_ml_ci.py; add dedicated opt-in workflow
   job and mutual exclusions. Reuse fixed real-data recipe, no safety loosening.
3. [ ] RED then GREEN probe guards/bounded result+lineage tests; implement
   backend/tests/pt_eval_probe.py with platform train, then only PT measurement.
   Reuse existing helpers by fixed imports, no broad real lifecycle invocation.
4. [ ] Freeze focused/full tests, independent safety review, safe isolated branch
   push and ordinary CI. One exact-SHA native run; preserve actual metrics/failure.
5. [ ] Record results and limitations, avoid UI/main integration collision, report.

## Baseline

New worktree edge-pt-eval at local5ac921a, equivalent remote main d109572 tree.
43 focused existing dataset/metrics/profile tests passed. No native run locally.

Review refinements: verify the actual measure-pt/model.pt copy before loading and
after inference, not only downloaded source; enforce tp+fp<=6000; retain manifest
test order for images/truth/predictions and independently validate image+label hashes.

## Verification ledger

- Closed receipt15, binding8, lifecycle guards10 and profile/entry20 tests developed
  with RED/GREEN checks. Review identified cleanup reserve too small; work budget
  now1140 within unchanged1200 entry, HTTP timeout bounded by remaining work.
- Initial full run:1105 passed,14 skipped;3 failures. Two exact workflow expectations
  updated to require the new fourth exclusion. A real ESRCH race in existing Linux
  process identity was reproduced deterministically and fixed in a separate commit;
  PermissionError and other OSError remain errors, not evidence of process exit.
- Focused affected suites after fixes:274 passed,60 warnings,102.04s. Final frozen
  full aggregate pending. No model run has occurred in the cloud workspace.
- Final frozen full aggregate exit0:1112 backend passed,14 native skipped,312
  warnings,391.88s;157 frontend passed, typecheck/build and live contract match.
  Independent review accepted profile/measurement boundaries and the narrow ESRCH
  fix. No native PT evaluation has occurred yet; next is isolated feature backup,
  ordinary CI, and one exact-SHA hosted evaluation.
