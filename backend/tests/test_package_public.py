"""Closed public package contracts; synthetic metadata, not native evidence."""
from copy import deepcopy
from uuid import uuid4
import pytest


def metadata():
    ids = [str(uuid4()) for _ in range(6)]
    return {'schema_version': 1, 'protocol': 'edgevision-python-onnx-v1',
        'provenance': dict(zip(('job_id','run_id','project_id','onnx_artifact_id','export_job_id','parent_artifact_id'), ids)) |
            {'frozen_input_sha256':'a'*64,'model_sha256':'b'*64,'model_size_bytes':100,'model_metadata_sha256':'c'*64,'runtime_binding':'d'*64,'code_version':'e'*64},
        'template': {'protocol':'edgevision-python-onnx-v1','image_protocol':'detection-image-v1','target':'linux-x86_64-cpython312-cpu','template_sha256':'f'*64,'core_sha256':'a'*64,'lock_sha256':'b'*64},
        'package_sha256':'c'*64,'package_size_bytes':500,'manifest_sha256':'d'*64,'manifest_size_bytes':100,
        'template_validation_sha256':'e'*64,'validation_scope':'trusted_model_fixed_package_integrity','standalone_execution':'not_run_for_this_artifact'}


def test_public_package_preserves_honest_scope_and_binding():
    from app.schemas import PackageArtifactMetadata
    value=metadata()
    assert PackageArtifactMetadata.model_validate(value).model_dump(mode='json')==value


@pytest.mark.parametrize('fault',['extra','executed','scope','bool','overlimit','private'])
def test_public_metadata_rejects_false_claims_and_unknowns(fault):
    from app.schemas import PackageArtifactMetadata
    value=metadata()
    if fault=='extra': value['extra']='anything'
    if fault=='executed': value['standalone_execution']='passed'
    if fault=='scope': value['validation_scope']='real_inference'
    if fault=='bool': value['package_size_bytes']=True
    if fault=='overlimit': value['package_size_bytes']=144*1024**2+1
    if fault=='private': value['provenance']['source_key']='private/server'
    with pytest.raises(ValueError):PackageArtifactMetadata.model_validate(value)


def test_package_retry_is_explicit_optional_uuid():
    from app.schemas import PackageJobCreate
    value={'kind':'package','params':{'onnx_artifact_id':str(uuid4())},'source_job_id':str(uuid4())}
    assert PackageJobCreate.model_validate(value).model_dump(mode='json')==value


def test_template_identity_never_imports_pillow(monkeypatch):
    from app.package_bundle import template_identity
    import builtins
    original=builtins.__import__
    def guarded(name,*args,**kwargs):
        if name=='PIL' or name.startswith('PIL.'): raise AssertionError('native image import in identity')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    assert template_identity()['protocol']=='edgevision-python-onnx-v1'


def test_deployment_artifact_cannot_fall_back_to_untyped_metadata():
    from app.schemas import ArtifactPublic
    m=metadata()
    value={'id':str(uuid4()),'project_id':m['provenance']['project_id'],'job_id':m['provenance']['job_id'],
        'kind':'deployment_zip','format':'zip','sha256':m['package_sha256'],'size_bytes':m['package_size_bytes'],
        'metadata_schema_version':1,'validation_state':'passed','metadata':m,'created_at':'2026-11-14T00:00:00Z'}
    assert ArtifactPublic.model_validate(value).root.metadata.standalone_execution=='not_run_for_this_artifact'
    for fault in ('hash','empty','project'):
        bad=deepcopy(value)
        if fault=='hash':bad['sha256']='f'*64
        if fault=='empty':bad['metadata']={}
        if fault=='project':bad['project_id']=str(uuid4())
        with pytest.raises(ValueError):ArtifactPublic.model_validate(bad)
