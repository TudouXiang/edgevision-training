# Independent PT-only frozen test evaluation

## Intent and scope

Evaluate the actual trained PT model on the already frozen20-image Oxford test
split without depending on a successful ONNX export. This is bounded research
measurement, not a product capability, formal benchmark or quality acceptance.
The owner delegated routine design decisions; no UI or user-machine changes.

## Approaches and decision

1. Move PT evaluation ahead of export in the old real-data lifecycle: fewer new
   files but would still run unwanted export/recovery work and conflate results.
2. Independent opt-in PT-only profile reusing frozen-data, training and inference
   helpers: selected. Separate closed receipt prevents ONNX failure from hiding
   useful PT results or PT success from implying ONNX success.
3. Unmanaged direct notebook/local model loading: rejected; no safe cloud kernel
   isolation here and no need to touch user devices.

## Fixed protocol

- Existing hash-pinned Oxford100 manifest/ZIP and60train/20val/20test split; same
  original license/research limits. No test-driven changes to split or settings.
- Fresh actual1epoch320/batch1/seed0/lr.01 fixed CPU training through the platform.
  Previous ephemeral checkpoints were deleted; this is a new run, not #74's model.
- Use its real pt_best download with verified platform lineage/hash/size and
  completed managed training receipt. Check source and copy before/after evaluation.
- Production PT loader,640 FP32 preprocessing/postprocessing, score>.25,
  class-aware NMS IoU.45; match correct class at IoU>=.5 to exactly one labelled
  head/image. Existing real_cpu_metrics returns TP/FP/FN,precision,recall.
  Empty detections legitimately produce zero precision/recall, never fake data.
- These metrics are NOT mAP, whole-dataset accuracy, PT/ONNX parity, or NPU results.
  No quality threshold; successful measurement may have poor scores.
- Reuse real_cpu_measure.py pt mode only; its timings/raw tensors remain private,
  not reported as a formal performance study. No ONNX model, export/probe or sweep.

## Isolation and output

New `pt_eval_v1` closed profile, hosted exact-SHA opt-in only, mutually exclusive
with all3 existing ML profiles. Reuse real-data image recipe and existing owned
cleanup: network none,nonroot,no capabilities,no-new-privileges,2CPU/6GiB,
no host mounts, bounded image acquisition and run. No local native ML execution.
Total container budget1200s; work1140s with60s cleanup reserve; outer1260s; training600s,measurement180s. Verify
remaining budget before launching; no retries. Cancel/cleanup still fail closed.

Report schema1 exact keys: schema_version,profile='pt_eval_v1',status,
protocol='single-head-p025-iou050-v1',stages,metrics,lineage_verified.
Stages exactly isolation,dataset,dependency_check,training,evaluation,cleanup;
statuses passed/failed/NOT_RUN/unverified. metrics null until complete, else exact
images20,ground_truth20,tp0..20,fp0..6000,fn20-tp,precision and recall recomputed
from counts. No model IDs/paths/hashes, images, names, per-image predictions,
passwords or raw logs in public output. lineage_verified null/true/false;
passed requires all stages passed, complete valid metrics and true lineage.
Bound report4096 bytes and reject duplicate/unknown JSON keys.

Review refinements: verify the actual measure-pt/model.pt copy before loading and
after inference, not only downloaded source; enforce tp+fp<=6000; retain manifest
test order for images/truth/predictions and independently validate image+label hashes.
