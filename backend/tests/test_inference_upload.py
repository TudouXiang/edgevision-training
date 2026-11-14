"""Upload remains byte-only and immutable; decoder execution belongs to the Worker."""
import asyncio
from hashlib import sha256
from uuid import uuid4
import pytest
from fastapi import Request
from app.dataset_storage import UploadError, stage_multipart_upload
from app.image_storage import image_format
from test_dataset_api import data_root, headers, create_user, setup_admin


@pytest.fixture
def client(data_root):
    return setup_admin(data_root)[0]


def request_body(body, content_length=None, content_type='multipart/form-data; boundary=bound'):
    chunks=[body[i:i+11] for i in range(0,len(body),11)]
    async def receive():
        if chunks: return {'type':'http.request','body':chunks.pop(0),'more_body':bool(chunks)}
        return {'type':'http.request','body':b'','more_body':False}
    h=[(b'content-type',content_type.encode())]
    if content_length is not None: h.append((b'content-length',str(content_length).encode()))
    return Request({'type':'http','headers':h,'method':'POST','path':'/'},receive)


def stage(request,path,max_bytes=20):
    return asyncio.run(stage_multipart_upload(request,path,max_bytes=max_bytes,filename_check=image_format,
        media_check=lambda name,media:media==b'image/png',too_large_code='IMAGE_TOO_LARGE',type_code='IMAGE_TYPE_UNSUPPORTED',type_message='Wrong image type',empty_message='Empty image'))


def body(content=b'raw bytes',extra=b''):
    return b'--bound\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\nContent-Type: image/png\r\n\r\n'+content+b'\r\n'+extra+b'--bound--\r\n'


@pytest.mark.parametrize('declared',[None,1])
def test_actual_file_limit_not_content_length(tmp_path,declared):
    with pytest.raises(UploadError) as error: stage(request_body(body(b'x'*21),declared),tmp_path/'x.part')
    assert error.value.status_code==413 and error.value.code=='IMAGE_TOO_LARGE'
    assert not (tmp_path/'x.part').exists()


@pytest.mark.parametrize('fault',['empty','truncated','part','duplicate','filename','type','length','headers'])
def test_multipart_closed_failures(tmp_path,fault):
    value=body(); length=None
    if fault=='empty':value=body(b'')
    if fault=='truncated':value=value[:-12]
    if fault=='part':value=body(extra=b'--bound\r\nContent-Disposition: form-data; name="other"\r\n\r\nx\r\n')
    if fault=='duplicate':value=value.replace(b'Content-Type: image/png',b'Content-Type: image/png\r\nContent-Type: image/png')
    if fault=='filename':value=value.replace(b'x.png',b'../x.png')
    if fault=='type':value=value.replace(b'image/png',b'image/jpeg')
    if fault=='length':length='not-an-int'
    if fault=='headers':value=value.replace(b'Content-Type: image/png',b'X-Long: '+b'x'*4097+b'\r\nContent-Type: image/png')
    with pytest.raises(UploadError):stage(request_body(value,length),tmp_path/'x.part')


def test_bytes_only_upload_and_auth(client,monkeypatch):
    project=client.post('/api/v1/projects',headers=headers(client),json={'name':'Image inputs'}).json()['id']
    def reject_decode(*a,**kw):pytest.fail('API must not decode images')
    monkeypatch.setattr('PIL.Image.open',reject_decode)
    response=client.post(f'/api/v1/projects/{project}/images',headers=headers(client),files={'file':('x.PNG',b'not yet decoded','image/png')})
    assert response.status_code==201,response.text
    value=response.json()
    assert value['validation_state']=='unverified' and value['job_id'] is None and value['format']=='png'
    assert value['sha256']==sha256(b'not yet decoded').hexdigest()
    assert value['metadata']=={'schema_version':1,'declared_format':'png','validation_scope':'bounded_upload_bytes'}
    assert 'x.PNG' not in str(value) and 'width' not in str(value)
    second=client.post(f'/api/v1/projects/{project}/images',headers=headers(client),files={'file':('x.PNG',b'not yet decoded','image/png')})
    assert second.json()['id']!=value['id']  # Upload explicitly has no idempotency promise.
    assert client.post(f'/api/v1/projects/{project}/images',files={'file':('x.png',b'x','image/png')}).status_code==403
    other=create_user(client,'image-upload-other')
    assert other.post(f'/api/v1/projects/{project}/images',headers=headers(other),files={'file':('x.png',b'x','image/png')}).status_code==404


@pytest.mark.parametrize('change',['archive','disable','revoke'])
def test_upload_rechecks_authority_after_stream(client,monkeypatch,change):
    from app import image_storage
    from app.database import transaction
    from app.security import timestamp
    project=client.post('/api/v1/projects',headers=headers(client),json={'name':'Image race'}).json()['id']
    original=image_storage.stage_multipart_upload
    async def staged(*args,**kwargs):
        result=await original(*args,**kwargs)
        with transaction() as c:
            if change=='archive':c.execute("UPDATE projects SET status='archived',archived_at=? WHERE id=?",(timestamp(),project))
            if change=='disable':c.execute('UPDATE users SET is_active=0 WHERE id=(SELECT owner_id FROM projects WHERE id=?)',(project,))
            if change=='revoke':c.execute('UPDATE sessions SET revoked_at=?',(timestamp(),))
        return result
    monkeypatch.setattr(image_storage,'stage_multipart_upload',staged)
    response=client.post(f'/api/v1/projects/{project}/images',headers=headers(client),files={'file':('x.png',b'x','image/png')})
    assert response.status_code==(409 if change=='archive' else 401)
    with transaction() as c:assert c.execute("SELECT COUNT(*) FROM artifacts WHERE kind='inference_input'").fetchone()[0]==0
