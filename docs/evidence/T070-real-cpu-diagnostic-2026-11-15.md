# T070 real-data recovery and export comparison evidence

Exact reviewed remote source: `deafc8d78089ae25c3daa7ba0d83280ea7972fd3`.
Local source commit `b7ee01c84c8c46d23857b1a8d346301a576c76f9` shares tree
`9f923d8681c579fdb4da7e39805f0ed30bd1f3ff`. Main was not changed.

## Ordinary regression

`python scripts/dev.py check` exited 0 on the frozen final source: 1015 backend
passed, 14 opt-in native tests skipped, 157 frontend passed; production build,
typecheck and generated contract check passed. Independent review found two
issues (fatal audit marker and forbidden-error summary promotion); both were
fixed with red-to-green tests before that final full run and publication.
[CI #66](https://github.com/TudouXiang/edgevision-training/actions/runs/43658453183)
checks and Windows process checks succeeded; native profiles were not selected.

## Real CPU and independent drills

[Run #67](https://github.com/TudouXiang/edgevision-training/actions/runs/43659565126)
selected only real_cpu_v1. Its closed native receipt records:

- Isolation, frozen real dataset, dependencies and actual training: passed.
- Export: failed / ONNX_MODEL_INVALID / compare_tolerance.
- Evaluation and timings: NOT_RUN; no numeric accuracy/latency claim.
- Actual cancellation, Worker interruption/recovery, backup/restore and cleanup:
  passed. These continued only after the validated, drained export failure.
- Overall native run deliberately remains failed. Ordinary checks and Windows
  checks succeeded. No export acceptance is inferred from independent drills.

The unchanged dataset manifest is
`fea46ddb1fbe822acbc7cfaa79fdeea6b986f50f71c2cae85992fde0ad93d124`,
ZIP `16b58d944a2c414063409e7bb95a8007e1b117a672c249d28c2d4a9c51df3ee6`.
This is the bounded two-class Oxford subset, not a formal accuracy benchmark.

## Separate three-arm diagnostic

[Run #68](https://github.com/TudouXiang/edgevision-training/actions/runs/43660414680)
selected only export_compare_v1. Native isolation, dataset, dependencies, training,
diagnostic and cleanup passed. This means observations are complete, **not that
product export passed**. The fixed original-reference tolerance was not changed.

| Arm | ONNX BN present | zeros match | gradient match | pattern match | Failure |
| --- | --- | --- | --- | --- | --- |
| A original, folding on | false | true | false | true | ONNX_MISMATCH |
| B original, folding off | true | false | false | true | ONNX_MISMATCH |
| C copied fused, folding on | false | false | true | true | FUSED_MISMATCH |

For all three arms: original PT contains BN; source hash and exported network
parameters/buffers are unchanged; repeated original PT output is stable before
and after export. Arm C's original-PT versus fused-PT comparison is false.
No fused-PT versus ORT comparison was recorded, so their alignment is unknown.

These results reject the simple explanation that disabling constant folding
alone fixes the mismatch. Explicit fusion is not a verified product fix either.
Only closed booleans were collected; mismatch magnitude and output grouping were
not measured. Root cause and a compliant production correction remain open.
#68 Windows, ordinary checks and the native diagnostic job all subsequently
completed successfully. That workflow success retains the diagnostic-only
meaning above and is not product export acceptance.

## Remaining delivery limits

The real-data ONNX export gate is still closed. Formal evaluation/timing,
Windows ML/CUDA, NPU/hardware validation and whole-project completion remain
unverified. Existing fixed Linux CPU engineering acceptance does not imply those
broader outcomes. No model, source images, user logs or private run paths were
published by these experiments.
