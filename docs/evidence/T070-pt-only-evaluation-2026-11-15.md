# T070 independent PT-only real test-set evaluation

## Exact evidence and scope

- Source: `ebb7b0eff36411c9fd5534636fc8c89cf29316fc` on
  `feat/t070-pt-evaluation` (not a claim about current main).
- [Ordinary source CI #79](https://github.com/TudouXiang/edgevision-training/actions/runs/43672056388)
  passed before the explicit experiment.
- [Explicit experiment #80](https://github.com/TudouXiang/edgevision-training/actions/runs/43673168097),
  native job `132687470950`, emitted the closed result at 2026-11-15 03:40:22 UTC.
- `pt_eval_v1`, protocol `single-head-p025-iou050-v1`: isolation, dataset,
  dependency check, training, evaluation and cleanup all passed;
  `lineage_verified=true`.
- All selected jobs in #80 completed successfully: ordinary checks, Windows
  process checks and the native PT evaluation.
- Only PT-only native profile was selected. The legacy ML, real-CPU lifecycle
  and export-comparison profiles were skipped. No ONNX export was attempted.

## Frozen measurement

Reuse the previously frozen Oxford 100-image subset, 60 training / 20 validation /
20 test, with original manifest, archive hashes and license restrictions unchanged.
This run trained a **fresh** checkpoint through the actual platform: 1 epoch,
320 training resolution, batch 1, seed 0, learning rate 0.01, CPU. It is not the
checkpoint from experiment #74, whose ephemeral container was removed.

Evaluate the actual `pt_best` using the production PT loader and preprocessing at
640 FP32, score greater than 0.25, class-aware NMS IoU 0.45. Count correct-class
matches at IoU at least 0.5 against one labelled head per image, in frozen manifest
order. Source lineage, download bytes and the actual loaded model copy were
verified before/after inference. No test-set-driven tuning or repeated scan.

| Metric | Measured value |
| --- | ---: |
| Test images | 20 |
| Ground-truth objects | 20 |
| True positives | 5 |
| False positives | 63 |
| False negatives | 15 |
| Precision | 5 / 68 = 0.07352941176470588 (7.35%) |
| Recall | 5 / 20 = 0.25 (25%) |

## Interpretation and limits

The evaluation pipeline succeeded, **not a model-quality acceptance**. The small,
1-epoch research model has low precision and recall under this fixed protocol.
These are point precision/recall counts, not mAP, whole-dataset accuracy, a formal
benchmark or evidence of production usefulness. No timing/performance conclusion
is published. A meaningful quality study would require a separately planned,
resource-bounded training/validation protocol, retaining untouched test data and
reporting all results honestly rather than optimizing against this test receipt.

No result here resolves the retained strict real-data ONNX export failure, proves
PT/ONNX parity, or validates Windows ML, CUDA/GPU, RKNN/NPU or an edge device.
The successful engineering package baseline is separate from this real-data model.
Whole-project acceptance remains open.

## Privacy and execution boundary

The hosted container retained network-none, non-root, no capabilities,
no-new-privileges, no host mounts and 2 CPU / 6 GiB limits. Work and cleanup were
bounded; owned cleanup passed. Only the closed anonymous aggregate receipt was
published. No images, model files, raw predictions, private paths, private task/user identifiers,
credentials or raw training logs were uploaded. No user device or UI worktree was
modified.
