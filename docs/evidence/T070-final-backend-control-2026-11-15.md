# T070 final fixed CPU backend control: no compliant repair

Exact remote source `8c83441256a1d5fccc56acdd24b0bfd75d57b89c`, tree
`fd3a2a83421188ccb9a9184eccde7fff1258b32f`, feature branch
`feat/t070-real-cpu`. Local equivalent product tree is `64b2c56`.

- Frozen local aggregate:1056 backend passed,14 native skipped,312 warnings;
  157 frontend passed; typecheck/build and generated contract parity passed.
- [Ordinary CI #73](https://github.com/TudouXiang/edgevision-training/actions/runs/43666493136):success.
- [Explicit final comparison #74](https://github.com/TudouXiang/edgevision-training/actions/runs/43667357743),
  native job132669601060:success means complete diagnostic collection, **not**
  successful product export. Ordinary checks and Windows process jobs also completed
  success; legacy ML and real-data CPU profiles were intentionally skipped.
- Schema3 isolation,dataset,dependency_check,training,diagnostic,cleanup all passed.
  No accepted model artifact was published.

## Fixed experiment and integrity

Same frozen checkpoint, same exact A-exported ONNX, and same A PyTorch reference
bytes; D did not re-export. A used MKLDNN enabled=True, D changed only enabled=False.
The recorded precision control values global/backend/conv/matmul were all `none`
in both arms. These are configuration values, not claims about every operator's
internal arithmetic. There is no fallback to GPU precision settings.

Three fixed640 FP32 inputs, production shape/finite comparator and original
`1e-4 + 1e-4 * abs(reference)` elementwise tolerance were retained. Both arms
confirmed source/checkpoint, network and shared files unchanged, and PyTorch
pre/post repetitions stable. D's retained current→ORT baseline was exactly equal
to A's summary across every input/group/field. Kernel network isolation and bounded
managed process cleanup passed. Input preparation and license limits remain in the
[real-data plan](../experiments/real-data-cpu-plan.md).

## Numerical evidence

Each input has33600 box-coordinate elements and16800 score elements. All values
were finite; every score group had zero mismatches. Left side is the tolerance
reference, so directions must not be interchanged.

| Direction | Input | Box mismatches | Max absolute error | Max tolerance ratio |
| --- | --- | ---: | ---: | ---: |
| current PT→ORT (A and D identical) | zeros | 0 | 0.002227783203125 | 0.16500247324359352 |
| current PT→ORT | gradient | 1 | 0.022308349609375 | 1.0867383725684043 |
| current PT→ORT | pattern | 0 | 0.004150390625 | 0.160550503703595 |
| current PT→disabled PT | zeros | 0 | 0.010284423828125 | 0.6786855711447574 |
| current PT→disabled PT | gradient | 2 | 0.01055908203125 | 1.8968691847060015 |
| current PT→disabled PT | pattern | 0 | 0.0040283203125 | 0.1333615731204756 |
| disabled PT→ORT | zeros | 0 | 0.010772705078125 | 0.6015213863988302 |
| disabled PT→ORT | gradient | 8 | 0.0247802734375 | 1.3079375459821792 |
| disabled PT→ORT | pattern | 0 | 0.0047607421875 | 0.2244786809545531 |

A retained `ONNX_MISMATCH`; D retained `BACKEND_MISMATCH`. Its disabled→ORT path
also failed. Disabling MKLDNN is therefore **not** a compliant repair. A larger
absolute maximum does not necessarily imply a larger tolerance ratio because
reference magnitudes differ.

## Stop decision and remaining work

This was the final bounded backend control. Backend-switch/folding/fusion scans
stop here. No tolerance, product reference, capability or exporter was changed to
make this example pass. The result supports neither a specific faulty operator
nor a claim that post-NMS detections are unaffected.

Continue safe source integration, operator documentation and runnable lightweight
UI/API/Worker delivery. Real-data ONNX acceptance, matched formal accuracy/timing,
Windows/CUDA and RKNN/NPU remain unaccepted. Whole-project acceptance remains open.
Historical #67/#68/#71 evidence is preserved rather than replaced.

## Integration review

A read-only independent review compared the seven production/host files against
main57bc, confirming remote blobs matched the local review base. It found no
integration blocker: only the bounded bytes decode entry and closed error
classification/sidecar were added; tolerance/reference/runtime assertions remained
unchanged. Fingerprint coverage expanded, so old capability receipts must be
re-probed after upgrading. No arbitrary HTTP diagnostic job or host execution
entry was introduced. This review does not replace native E/I/P regression.

## Existing engineering baseline revalidation (not another backend scan)

[Run #75](https://github.com/TudouXiang/edgevision-training/actions/runs/43668254841)
revalidated the same exact8c83441 source using only the existing fixed engineering
ML profile. Native job132672361976 returned schema5 complete/passed with all12
stages passed: isolation,dependency_check,training_http,export_http,onnx_policy,
training_policy,browser_delivery,inference_http,inference_policy,inference_browser,
package_http,package_browser. Ordinary checks and Windows process jobs also passed;
real-data and export-comparison profiles were intentionally skipped.

This demonstrates the fixed engineering E/I/P chain still works after diagnostic
changes. It does not convert the failed Oxford-trained model into an accepted
ONNX artifact, provide formal accuracy/latency, or verify Windows/GPU/NPU ML.

## Integration source boundary

The delivery revision following8c83441 changes documentation only. The product
code is the exact tree exercised by #73–#75. Main may advance only by an expected-
head, non-forced fast-forward from verified57bc2b5 ancestry; unexpected remote
changes require fresh comparison rather than replacement. Main publication and
its ordinary CI must be verified separately. User machine deployments remain on
their recorded57bc code until explicitly upgraded with fresh capability probes.
