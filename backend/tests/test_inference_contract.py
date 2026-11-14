"""Pure strict image contract checks; no native model imports or real inference."""
from copy import deepcopy
from uuid import uuid4
import pytest
from app.schemas import (InferenceParams, PreprocessRecord, DecodedImageRecord,
                         InferenceInputMetadata, InferenceInputArtifactPublic, ArtifactPublic,
                         PostprocessCounts)
from app.delivery_infer import letterbox_record


@pytest.mark.parametrize('value', [True, False, '0.5', float('nan'), float('inf'), -.1, 1.1])
@pytest.mark.parametrize('field', ['confidence', 'iou'])
def test_strict_thresholds(value, field):
    data = {'model_artifact_id': str(uuid4()), 'image_artifact_id': str(uuid4()), 'backend': 'pt', field: value}
    with pytest.raises(ValueError): InferenceParams.model_validate(data)


@pytest.mark.parametrize('field,value', [('target_width', True), ('resized_height', True), ('scale_x', '1'), ('tensor_sha256', 'bad'), ('left', 1)])
def test_strict_preprocess(field, value):
    record = {**letterbox_record(640, 640), 'tensor_sha256': 'a'*64}
    record[field] = value
    with pytest.raises(ValueError): PreprocessRecord.model_validate(record)


def test_input_metadata_and_artifact_never_fall_back():
    data = {'id': str(uuid4()), 'project_id': str(uuid4()), 'job_id': None, 'kind': 'inference_input', 'format': 'png',
            'sha256': 'a'*64, 'size_bytes': 10, 'metadata_schema_version': 1, 'validation_state': 'unverified',
            'metadata': {'schema_version': 1, 'declared_format': 'png', 'validation_scope': 'bounded_upload_bytes'},
            'created_at': '2026-11-05T00:00:00Z'}
    ArtifactPublic.model_validate(data)
    for field, value in [('metadata', {}), ('metadata_schema_version', True), ('size_bytes', True), ('job_id', str(uuid4())), ('validation_state', 'passed'), ('format', 'jpeg')]:
        with pytest.raises(ValueError): ArtifactPublic.model_validate({**data, field: value})
    with pytest.raises(ValueError): InferenceInputMetadata.model_validate({**data['metadata'], 'width': 1})


def test_image_and_counts_cross_binding():
    with pytest.raises(ValueError):
        DecodedImageRecord.model_validate({'encoded_width': 3, 'encoded_height': 2, 'image_width': 3, 'image_height': 2,
            'orientation': 6, 'format': 'png', 'rgb_sha256': 'a'*64})
    with pytest.raises(ValueError):
        PostprocessCounts.model_validate({'candidates': 3001, 'candidate_truncated': 0, 'nms_kept': 1, 'result_truncated': 0, 'clip_removed': 0})


@pytest.mark.parametrize('value', [True, False, '1', 0, -1, 1024**2+1, 2*1024**3])
def test_inference_evidence_member_is_strict_and_bounded(value):
    from app.inference_contract import InferenceEvidence
    entries = [{'path': name, 'size_bytes': 10, 'sha256': 'a'*64} for name in ('result.json', 'metadata.json', 'preview.png')]
    entries[0]['size_bytes'] = value
    with pytest.raises(ValueError): InferenceEvidence.model_validate({'schema_version': 1, 'job_id': str(uuid4()),
        'run_id': str(uuid4()), 'frozen_input_sha256': 'a'*64, 'outputs': entries})
