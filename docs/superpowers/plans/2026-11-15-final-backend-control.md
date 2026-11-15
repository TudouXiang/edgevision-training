# Final fixed CPU backend control implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task.

**Goal:** One last bounded backend control, then stop switch exploration regardless of result.
**Architecture:** Replace the diagnostic-only schema2 A/B/C execution with schema3 A/D. A exports once and retains a four-file private handoff; D is an independent managed process with only MKLDNN enabled=False. Both use the same frozen checkpoint and exact A ONNX bytes.
**Tech Stack:** Existing fixed PyTorch/ORT CPU runtime and stdlib manifest handling; no new dependency.
**Spec:** `docs/evidence/T070-export-error-groups-2026-11-15.md`; parent authorization and independent A/D design review.

## Global constraints
- No product exporter, capability, tolerance or training parameters change; no additional retries or scan.
- A must start with MKLDNN enabled=True. Record effective precision enums global/backend/conv/matmul; D must preserve these, changing enabled only.
- A handoff only after exit0/74, complete observations, no fatal, unchanged source/network and bound drain.
- Four fixed files only: model.onnx (existing128MiB bound), current-zeros.f32/current-gradient.f32/current-pattern.f32, each201600 bytes little-endian FP32 (1,6,8400), finite. No pickle/object format.
- Private manifest contains validated job/run UUIDs, source/runtime bindings, precision and exact size/hash per fixed basename. No arbitrary path; D copies bounded verified bytes into own run, checks before/after execution.
- Schema3 publishes only precision enums, same-file boolean and fixed aggregate numeric statistics; no raw tensors, identifiers, paths or hashes. CurrentPT→ORT, currentPT→disabledPT, disabledPT→ORT use left reference.
- Kernel isolation, GO/STOP/drain, fatal check,2CPU/6GiB unchanged. Reduce arm reserve to2*210 seconds, not more data/work.

## Review focus
- Symlink/traversal/unknown filenames, stale source/runtime and mutated input manifest fail closed.
- Wrong little-endian length, dtype/shape, nonfinite arrays cannot create complete proof.
- Precision settings cannot silently change or already-disabled A pass.
- Complete numerical mismatches may be observed, policy/runtime/source errors may not.
- Atomic sample statistics and outcome keep runtime-error suffix null.

## Tasks
- [x] Implement strict handoff helper and A/D native child in isolated worktree with synthetic failure tests.
- [x] Implement schema3 report/metrics and coordinator handoff freeze/verify, adapt synthetic tests.
- [x] Integrate changes without overwriting work, independent review and frozen full aggregate.
- [x] Safe feature push, wait ordinary CI, dispatch one exact-SHA diagnostic.
- [x] Preserve evidence. Do not replace product reference based on proximity alone. If no deterministic repair is demonstrated, stop backend experiments and continue other delivery gates.

## Implementation ledger

- Parent schema3 metrics/report/coordinator: 51 focused synthetic tests passed,
  1 child-dependent test deliberately excluded pending integration.
- Handoff helper: initial 6 synthetic tests passed in isolated child worktree.
  Independent review found GPU precision fallback could mislabel CPU controls;
  fix and negative tests required before integration/dispatch.
- Delivery preparation continues in parallel: evidence-indexed demo/thesis
  outline added without claiming live demo or formal experiment completion;
  13 local targets resolved and 7 documentation scope tests passed.
- No schema3 native run has occurred at this checkpoint; no product tolerance,
  exporter or runtime capability changes are authorized by this diagnostic.
- Integrated child checkpoint 101c7e9 as local5219402. Three legacy guard/atomic
  helper tests initially failed due deleted helpers; restored helpers and final
  guarded write, then 77 focused tests passed. GPU fallback and path/atomic
  review findings are fixed; final independent read-only review found no blocker.
- Frozen full `python scripts/dev.py check` exit0: 1056 backend passed,14 native
  skipped,312 warnings (391.38s);157 frontend passed; typecheck/build and generated
  contract parity passed. This is not native A/D validation.

- #73 ordinary CI success; #74 A/D safely collected all observations but found no
  compliant repair. Backend scanning stopped. #75 existing fixed engineering
  profile passed all12 native stages plus ordinary/Windows checks. This is not
  an Oxford-model acceptance. Evidence and remaining delivery limits retained.
