# T070 real-data export diagnostic and independent recovery drills

Status: implementation checkpoint; native run of this revision NOT_RUN.

## Verified preceding failure

Exact remote `6a4ecab39f3ba1c667568a886bbc356185aa3401`, workflow #65
(https://github.com/TudouXiang/edgevision-training/actions/runs/43655585978):
isolation, dataset, dependency check and real training passed; export failed with
`ONNX_MODEL_INVALID` / `compare_tolerance`. Evaluation, timings and recovery drills
were NOT_RUN. Cleanup remained unverified in that receipt. Ordinary checks and
Windows checks passed. This is evidence of a trained-artifact numerical mismatch,
not proof of its cause, and not full-project acceptance.

## Pre-result diagnostic protocol

A separate explicit `export_compare_v1` workflow profile trains the frozen real
subset once, then runs three managed, independent diagnostic children:

| Arm | Network exported | Constant folding | Reference |
| --- | --- | --- | --- |
| A | original eval network | on | original eval network |
| B | original eval network | off | original eval network |
| C | independently copied, explicitly fused network | on | original eval network |

The fixed zeros, gradient and pattern inputs, FP32/640 shape and existing
`1e-4 + 1e-4 * abs(reference)` comparison tolerance are unchanged. Record closed
boolean/null observations for PT repeat stability before/after export, source
hash, exported-network parameters/buffers, PT/ONNX BN presence, each ORT
comparison, and (C only) original-vs-fused PT comparison. No raw tensor, model,
private path or unrestricted error text is published. BN presence is an
observation, not a required true value. The original reference is never replaced
with the fused network. No product exporter or capability is changed by this
profile. A successful diagnostic means complete observations, even if comparison
arms fail; it does not mean product export acceptance.

Only the reviewed exact SHA can run in the existing GitHub-hosted network-none,
nonroot, no-capability/no-new-privilege, no-host-mount container with 2 CPU / 6 GiB.
Outer execution remains 1500 seconds; entry 1440; coordinator 1360; three arms
require 630 seconds remaining before starting. Each arm has its own managed GO,
input/runtime/source binding, timeout and completed tree-drain proof. Dynamic
modules, arbitrary input paths and a public API job kind are not added. Native ML
is NOT run in the unisolated cloud workspace or on Windows as part of this plan.
Profiles are mutually exclusive and dispatched sequentially, not simultaneously.

## Independent drills despite export mismatch

The real-data profile may continue cancel/recovery/backup drills only after the
specific drained `failed / ONNX_MODEL_INVALID` export result, bound to the actual
job/run, completed exit 74 receipt and unchanged validated source/runtime. It
retains the original failure, leaves ONNX evaluation/timings NOT_RUN, and rethrows
the export failure after independent drills. Timeout, changed source, policy
failure and incomplete drain never receive this continuation. Thus recovery
checks can produce separate evidence without converting export failure into a
successful experiment.

## Verification at this checkpoint

Focused synthetic contract/privacy/profile tests: 256 passed. These import no
native models. The initial invocation from repository root failed collection
because app was not on Python's import path; the documented backend-directory
invocation then passed. Full aggregate, independent review and exact-SHA native
runs remain required. Official accuracy/latency and GPU/Windows ML remain untested.

Independent review found and blocked two issues before publication: a swallowed
native policy exception could leave a nonempty fatal audit marker unchecked, and
the summary validator accepted complete fields with a forbidden failure code.
Both received failing regression tests before correction. The final observation
write now rejects any fatal marker as POLICY_FAILED/68; complete failed arms count
as diagnostic observations only for PT_REPEAT_MISMATCH, FUSED_MISMATCH or
ONNX_MISMATCH. The focused suite now has 258 passing tests. The first frozen full
aggregate passed, but the corrected revision requires its own full rerun. Arm C
does not separately compare fused PT against ORT, so no such alignment claim may
be inferred from the recorded original-reference comparisons.
