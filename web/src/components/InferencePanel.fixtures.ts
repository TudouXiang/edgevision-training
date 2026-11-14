// Synthetic generated-contract-shaped fixtures only. No model execution evidence.
import type { Artifact, InferenceInput, InferenceParams, InferenceResult, Job, Project } from '../api'
export const date = '2026-11-04T00:00:00Z', sha = 'a'.repeat(64)
export const project: Project = { id: 'p', owner_id: 'u', name: 'P', description: '', archived_at: null, created_at: date, updated_at: date }
export const capability = { available: true, reason: null, reason_code: null, detected_version: '1.31.1' }
export const sourceJob = (id = 'export-a', state: Job['state'] = 'running', project_id = 'p', kind: Job['kind'] = 'export_onnx'): Job => ({ id, project_id, created_by: 'u', kind, state, params_schema_version: 1, created_at: date, started_at: date, finished_at: null, error_code: null, source_job_id: null })
const params = { dataset_id: 'd', experiment_name: 'Fixture training', base_model: 'yolo11n.pt', device: 'cpu', epochs: 1, batch: 1, imgsz: 320, seed: 0, learning_rate: .01 } as const
const training = { schema_version: 1, dataset_id: 'd', dataset_version: 1, archive_sha256: sha, snapshot_sha256: sha, report_artifact_id: 'report', report_sha256: sha, counts: { images: 8 }, classes: ['object'], base_model_sha256: sha, base_manifest_sha256: sha, params, runtime_binding: sha, code_version: sha } as const
const versions = { torch: '2.15.0+cpu', torchvision: '0.29.2+cpu', ultralytics: '8.4.202' } as const
export function pt(id = 'pt-a', job_id = 'train-a', project_id = 'p'): Extract<Artifact, { kind: 'pt_best' | 'pt_last' }> {
  return { id, project_id, job_id, kind: 'pt_best', format: 'pt', sha256: sha, size_bytes: 100, metadata_schema_version: 1, validation_state: 'passed', created_at: date,
    metadata: { schema_version: 1, task: 'detection', architecture: 'yolo11n', classes: ['object'], provenance: { ...training, classes: ['object'] }, validation_scope: 'weights_only_detection_checkpoint', runtime: { versions, optimizer_steps: 1, completed_epochs: 1, safe_load_count: 2, threads: 2, device: 'cpu', effective: { optimizer: 'SGD', lr0: .01, lrf: .01, warmup_epochs: 0, warmup_bias_lr: 0, warmup_momentum: .8, momentum: .937, weight_decay: .0005, nbs: 64, seed: 0, batch: 1, epochs: 1, imgsz: 320, device: 'cpu', workers: 0, amp: false, plots: false, cache: false, deterministic: true } } } }
}
export function onnx(): Extract<Artifact, { kind: 'onnx' }> {
  return { id: 'onnx-a', project_id: 'p', job_id: 'export-a', kind: 'onnx', format: 'onnx', sha256: sha, size_bytes: 200, metadata_schema_version: 1, validation_state: 'passed', created_at: date,
    metadata: { schema_version: 1, task: 'detection', architecture: 'yolo11n', classes: ['object'], validation_scope: 'checker_ort_raw_tensor_equivalence', validation_sha256: sha,
      provenance: { schema_version: 1, job_id: 'export-a', run_id: 'run-a', input_sha256: sha, parent_artifact_id: 'pt-a', source_job_id: 'train-a', source_sha256: sha, source_size_bytes: 100, source_metadata_sha256: sha, source_training_input_sha256: sha, training: { ...training, classes: ['object'] }, runtime_binding: sha, code_version: sha },
      validation: { schema_version: 1, job_id: 'export-a', run_id: 'run-a', input_sha256: sha, source_sha256: sha, original_graph_sha256: sha, model_sha256: sha, model_size_bytes: 200, classes: ['object'], input_name: 'images', input_shape: [1, 3, 640, 640], output_name: 'output0', output_shape: [1, 5, 8400], dtype: 'float32', tensor_protocol: 'rgb-fixed-v1', atol: .0001, rtol: .0001, checker_passed: true,
        runtime: { versions: { ...versions, onnx: '1.23.2', onnxruntime: '1.31.1' }, provider: 'CPUExecutionProvider', device: 'cpu', threads: 2, opset: 18, ir_version: 8, precision: 'fp32', dynamic: false, simplify: false, nms: false },
        samples: (['zeros', 'gradient', 'pattern'] as const).map(name => ({ name, input_sha256: sha, pt_sha256: sha, ort_sha256: sha, max_absolute_error: 0, max_tolerance_ratio: 0, elements: 42000, passed: true })) } } }
}
export const inferParams: InferenceParams = { backend: 'onnx', confidence: .25, image_artifact_id: 'image-a', iou: .45, model_artifact_id: 'onnx-a' }
export function imageInput(id = 'image-a', project_id = 'p'): InferenceInput {
  return { id, project_id, job_id: null, kind: 'inference_input', format: 'png', sha256: sha, size_bytes: 12, created_at: date, validation_state: 'unverified', metadata_schema_version: 1, metadata: { schema_version: 1, declared_format: 'png', validation_scope: 'bounded_upload_bytes' } }
}
export function inferJob(id = 'infer-a', state: Job['state'] = 'running', project_id = 'p'): Job {
  return { ...sourceJob(id, state, project_id, 'infer'), inference: { model_artifact_id: 'onnx-a', model_job_id: 'export-a', model_sha256: sha, image_artifact_id: 'image-a', image_sha256: sha, protocol: 'detection-image-v1', params: { ...inferParams }, runtime_binding: sha, code_version: sha } }
}
export function inferenceResult(empty = false): InferenceResult {
  return { schema_version: 1, artifact_id: 'result-a', backend: 'onnx', provider: 'CPUExecutionProvider', protocol: 'detection-image-v1', classes: ['object'], image_width: 2400, image_height: 1600,
    image_url: '/api/v1/inferences/result-a/image', params: { ...inferParams },
    image: { encoded_width: 1600, encoded_height: 2400, image_width: 2400, image_height: 1600, format: 'png', orientation: 6, rgb_sha256: sha },
    preview: { width: 1280, height: 853, format: 'png', sha256: sha, size_bytes: 100 },
    preprocess: { image_width: 2400, image_height: 1600, target_width: 640, target_height: 640, resized_width: 640, resized_height: 427, left: 0, right: 0, top: 106, bottom: 107, scale_x: 640 / 2400, scale_y: 427 / 1600, tensor_sha256: sha, color: 'RGB', layout: 'NCHW', dtype: 'float32', normalization: 'divide_255', resampling: 'pillow_bilinear', padding: 114 },
    provenance: { schema_version: 1, project_id: 'p', job_id: 'infer-a', run_id: 'run-a', frozen_input_sha256: sha, model_artifact_id: 'onnx-a', model_job_id: 'export-a', model_sha256: sha, model_size_bytes: 200, model_metadata_sha256: sha, image_artifact_id: 'image-a', image_sha256: sha, image_size_bytes: 12, runtime_binding: sha, code_version: sha },
    runtime: { backend: 'onnx', provider: 'CPUExecutionProvider', device: 'cpu', threads: 2, interop_threads: 1, warmup_runs: 0, raw_elements: 42000, raw_sha256: sha, versions: { numpy: '2.5.4', pillow: '12.3.0', onnx: '1.23.2', onnxruntime: '1.31.1', torch: null, torchvision: null, ultralytics: null } },
    timings: { unit: 'ms', decode: 1, preprocess: 2, load: 3, infer: 4, postprocess: 5, total: 15 },
    counts: { candidates: empty ? 0 : 1, candidate_truncated: 0, nms_kept: empty ? 0 : 1, result_truncated: 0, clip_removed: 0 },
    detections: empty ? [] : [{ class_id: 0, score: .87654, xyxy: [120, 240, 1000, 1200] }],
  }
}
export function output(): Extract<Artifact, { kind: 'inference_result' }> {
  const result = inferenceResult()
  return { id: 'result-a', project_id: 'p', job_id: 'infer-a', kind: 'inference_result', format: 'json', sha256: sha, size_bytes: 500, created_at: date, metadata_schema_version: 1, validation_state: 'passed', metadata: { schema_version: 1, protocol: 'detection-image-v1', validation_scope: 'real_single_image_inference', result_sha256: sha, result_size_bytes: 500, preview: result.preview, provenance: result.provenance } }
}
