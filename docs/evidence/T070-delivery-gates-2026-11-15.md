# T070 delivery gate update (project still open)

Verified remote main remains `57bc2b5a2b9b843ff85a294975b0f4d55bdd5ba1`.
Real-data diagnostic work is on `feat/t070-real-cpu`, not integrated to main.
This supplements, rather than rewrites, the [November 14 ledger](T070-final-gates-2026-11-14.md).

| Gate | New evidence | Remaining limit |
| --- | --- | --- |
| A01–A05 lightweight deployment | PEC loopback deployment documented previously; isolated XiaoHu Windows deployment prepared from main57bc, API ready200 and Web200, no autostart or public bind | Service checks are point-in-time, not uptime guarantees; owner must initialize first administrator locally |
| A09 actual model cancellation | #67 cancelled a genuine training task after actual progress and verified terminal/drain evidence | No arbitrary-load or physical power-loss claim |
| A10 actual Worker interruption | #67 isolated real-model Worker recovery passed with cleanup | Full host restart/power loss still NOT_RUN |
| A11 real data training | Frozen Oxford100-image subset, actual1epoch CPU training passed repeatedly | Bounded research experiment, not formal test-set accuracy |
| A12 backup/restore | #67 quiescent isolated backup/restore and artifact readability passed | No migration/recovery experiment on owner data |
| A13 real-data export | #67 strict gate failed compare_tolerance; #68/#71 independent diagnostic evidence retained | No accepted real-data ONNX artifact; numerical contract remains enforced |
| A14 package | Earlier fixed Linux CPU package engineering evidence remains documented | New real-data trained artifact cannot reach downstream package acceptance until export passes |
| A15 XiaoHu UI | 157 frontend tests, build/typecheck, real ordinary browser5passed/1expectedMLskip, cleanup passed | Model browser flow/GPU not executed on Windows |
| A16 experiment credibility | Dataset license, frozen split/hashes, failures, complete numeric diagnostic and source bindings recorded | PT/ONNX real-data accuracy/timing NOT_RUN, no fabricated thesis results |

## XiaoHu scope

The fresh main57bc checkout and new data, dependencies, downloads, explicit caches,
temporary files and logs live under a separate D-drive deployment directory.
Existing dirty owner checkouts were not modified. Existing Python3.12.10 on C was
reused as the virtual-environment base; no new Python download/installation there.
Because PYTHONPYCACHEPREFIX was not set at initial launch, zero standard-library
bytecode writes to that existing base cannot be guaranteed. Future planned
maintenance can direct bytecode cache to D without altering system security.

Windows UTF-8 document tests passed7/7 with process-local PYTHONUTF8=1. Two
symlink-fixture tests were blocked by WinError1314; no privilege/developer-mode
change was made. GPU hardware visibility is not GPU model verification. Current
product ML adapter supports the fixed Linux CPU environment only.

## Delivery priorities after final fixed backend control

1. Preserve the strict export failure if no deterministic compliant repair is
   demonstrated; stop backend-switch exploration, not relax tolerance to fit it.
2. Integrate only reviewed, tested diagnostics/evidence as appropriate; do not
   enable unsupported runtime capabilities or overwrite owner work.
3. Keep a runnable lightweight UI/API/Worker delivery with clear model-capability
   boundaries and operator-run administrator initialization, start/stop/backup
   instructions. Do not manufacture an administrator password.
4. Produce an evidence-indexed demo/thesis outline that distinguishes engineering
   smoke tests, real-data training and unexecuted accuracy/performance. School
   requirements, formal project title and NPU hardware requirements are unknown;
   do not invent them.

Whole-project acceptance is still open. No line above upgrades Windows ML, CUDA,
RKNN/NPU, formal accuracy/latency or real-data export to passed.

## Final control and administrator update

[#74 final A/D control](T070-final-backend-control-2026-11-15.md) completed safely but
did not resolve numerical acceptance. Backend scans are stopped; strict export
gate remains unchanged. XiaoHu deployment read-only recheck found one active
administrator in its own database and both loopback HTTP endpoints returned200.
No password field was read or used; this is not a password verification.

[#75 engineering baseline](T070-final-backend-control-2026-11-15.md) revalidated all12
existing Linux CPU E/I/P stages at8c83441; ordinary and Windows jobs passed. This
updates the engineering baseline only, not real-data export/formal accuracy/GPU.

## Independent PT evaluation update

[PT-only experiment #80](T070-pt-only-evaluation-2026-11-15.md) now supplies a real,
limited test-set measurement independent of the blocked ONNX export: 20 images,
TP 5 / FP 63 / FN 15, precision 7.35%, recall 25%; six native stages and model
lineage verification passed. This supersedes the earlier PT accuracy NOT_RUN
statement only for this exact fixed single-head protocol and fresh 1-epoch model.
It is not mAP, formal quality acceptance or a latency study. ONNX accuracy/parity,
GPU/NPU and overall project acceptance remain unverified or blocked as stated.

## Integration-status correction (2026-11-15 UTC)

The earlier statement that the `feat/t070-real-cpu` diagnostics were not integrated
described the then-current `57bc2b5` baseline. It is superseded by the later main
history: branch head `d1095723e5a1d6580a4c52f87c0a4f3911a7f0be` is an ancestor of
code commit `694ffd510e7ec2f1c993d5d5ab74533f494c266f` ([compare](https://github.com/TudouXiang/edgevision-training/compare/d1095723e5a1d6580a4c52f87c0a4f3911a7f0be...694ffd510e7ec2f1c993d5d5ab74533f494c266f)); the fixed backend-control commit
`8c83441256a1d5fccc56acdd24b0bfd75d57b89c` is also an ancestor of that main source
([compare](https://github.com/TudouXiang/edgevision-training/compare/8c83441256a1d5fccc56acdd24b0bfd75d57b89c...694ffd510e7ec2f1c993d5d5ab74533f494c266f)). Main subsequently advanced to documentation-only merge `aa0a832e5d6f669c160f662fcba4d791232b0dc0`, whose parent is `694ffd5`.

This corrects only the source-integration status. It does **not** mean the
real-data ONNX issue was repaired or accepted: the Oxford-subset strict
`compare_tolerance` failure remains, no accepted real-data ONNX artifact exists,
and formal PT/ONNX accuracy/performance plus GPU/NPU validation remain unverified.
Run #85 passed the fixed Linux CPU/synthetic engineering profile on `694ffd5`; it
was not a real-data export test and did not run against the later documentation
merge commit.
