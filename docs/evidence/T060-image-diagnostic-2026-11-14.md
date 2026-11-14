# T060 image validation: anonymous failure classification

The restored source tree `c90d8fd8c82d8eee39e0e75da68c5a366157d138`
was published as `c1ad5d3a1fd4bc50fe84e422de07db08fc5d025f`.
Local lightweight checks passed: 647 backend tests, 14 native tests skipped,
117 frontend tests, build and generated contract consistency.

[Hosted run 43607336609](https://github.com/TudouXiang/edgevision-training/actions/runs/43607336609)
passed the ordinary Linux checks and Windows process matrix. Its explicit
isolated CPU execution passed isolation, dependency checks, training HTTP,
export HTTP, ONNX policy, training policy, delivery browser, inference HTTP
and inference policy. The final inference browser stage failed. This is a
partial real execution result, not I business acceptance. P remains 501.

The diagnostic increment adds an optional `inference_browser_failure` to
schema-v3 failure receipts only. It is one closed phase identifier:
`boundary`, `settle`, `inputs`, `tools`, `api`, `worker`, `web`, `browser`,
`receipt`, `services`, `cleanup` or `unknown`. Historical receipts without
this optional failure field remain valid. Success receipts and legacy v2
receipts cannot carry it. Unknown fields or values fail validation.

The private helper writes only the phase; the container reads at most 257
bytes and rejects values exceeding 256 bytes. The public host reconstructs
only allowlisted fields. Exception text, cookies, identifiers, private paths,
images, raw browser output and logs remain private. Missing diagnostic data
is `unknown`, never success. This does not alter isolation, budgets, ML
opt-ins, stage ordering or existing business acceptance conditions.

New tests first failed for the missing receipt and closed-field support.
Independent review found an overlong valid-prefix receipt and cleanup-write
misclassification; regression cases reproduced both before correction.
Focused verification: 183 passed. Full regression and the exact subsequent
hosted execution must be recorded separately; this instrumentation does not
claim the underlying browser failure is fixed.

Local aggregate `python3 scripts/dev.py check` exited 0: 659 passed and 14
native skipped, 117 frontend passed, build and contracts passed. Two final
review regression cases were added after that run collected its cases; the
final diagnostic plus documentation suite was rerun: 190 passed. Independent
read-only review accepted the final diagnostic changes. Raw logs remain
private; the next hosted run binds complete checks to the published SHA.

## UI checkpoints

[Run 43609069043](https://github.com/TudouXiang/edgevision-training/actions/runs/43609069043)
passed ordinary Linux and Windows checks and the first nine isolated stages,
but returned `inference_browser_failure=browser`. This locates the failure in
the Playwright child, not input lineage checks or service startup.

The next diagnostic increment adds fixed `ui_*` checkpoints for setup,
capabilities, inventory, upload, each PT/ONNX submit/result/preview/download/
reload, offline/recovery and responsive checks. The private checkpoint contains
only a phase literal, never an assertion, URL, credential, input or error.
The same bounded allowlist validation applies at every boundary; it does not
change assertions or turn failures into success. A completed checkpoint is not
an acceptance receipt. Independent read-only review found a misleading reload
marker, corrected before publication; all UI codes are tested through all three
boundaries. Focused final suite: 194 passed; e2e typecheck passed. Aggregate:
671 passed, 14 native skipped, 117 frontend passed, build/contracts passed.
The final all-codes boundary test was added after aggregate collection and
passed in the focused final suite. Exact remote validation remains separate.

## Submit boundary refinement

Run 43610853801 at de00ca066213c97229c005b08e1b9b35fcf5a71a passed checks,
Windows and the first nine native stages, but returned `ui_pt_submit`.
This does not identify a product root cause: that block includes inventory,
model selection, thresholds, clicking and the acceptance response.
The next increment adds six fixed subphases per backend and an enabled-button
assertion before the same synchronous double click. The one-job, exact-202,
result identity and all other assertions remain intact. No raw errors, status
bodies or identifiers are published. Twelve new vocabulary tests failed
before implementation; the focused boundary suite then passed 206 cases and
e2e typechecking passed. Local sandboxed Chromium reproduction was unavailable
(socket EPERM); no browser sandbox or system setting was weakened.

Final local aggregate: 684 passed, 14 native skipped, 117 frontend passed;
build and contract checks passed, exit 0. Independent read-only review approved
the six-file diff; native acceptance remains pending.
