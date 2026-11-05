"""Explicit isolated native training smoke. Console is anonymous; details stay private."""
import contextlib
import os
from pathlib import Path
import traceback


def run(diagnostic):
    """Explicit 1-epoch real HTTP/Worker smoke. Set fresh PLATFORM_DATA_ROOT and EDGEVISION_SMOKE_ASSET. Synthetic fixtures are not accuracy evidence."""
    import sys,os,json,subprocess
    from pathlib import Path
    from io import BytesIO
    from zipfile import ZipFile,ZIP_DEFLATED
    from PIL import Image,ImageDraw
    sys.path.insert(0,str(Path.cwd()/'tests'))
    from app.admin_cli import create_admin
    import httpx, secrets, time
    def headers(client): return {'Origin':'http://127.0.0.1:5173','X-CSRF-Token':client.cookies.get('edgevision_csrf')}
    from app.training_assets import capability
    root=Path(os.environ['PLATFORM_DATA_ROOT'])
    if (root/'first-result.json').exists(): raise SystemExit('Fresh smoke root required')
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,stdout=diagnostic,stderr=diagnostic,timeout=30)
    subprocess.run([sys.executable,'-m','app.training_probe','--asset',os.environ['EDGEVISION_SMOKE_ASSET']],check=True,stdout=diagnostic,stderr=diagnostic,timeout=100)
    password=secrets.token_urlsafe(24); create_admin('smoke',password)
    log=(root/'api.log').open('wb')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8891'],stdout=log,stderr=subprocess.STDOUT)
    import atexit
    def close_server():
     server.terminate()
     try: server.wait(timeout=10)
     except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
     log.close()
    atexit.register(close_server)
    client=httpx.Client(base_url='http://127.0.0.1:8891',timeout=30,trust_env=False)
    for _ in range(100):
     try:
      if client.get('/api/v1/health/live').status_code==200:break
     except httpx.TransportError:pass
     time.sleep(.1)
    r=client.post('/api/v1/auth/login',headers={'Origin':'http://127.0.0.1:5173'},json={'username':'smoke','password':password});assert r.status_code==200,r.text
    (root/'smoke-session.json').write_text(json.dumps(dict(client.cookies)))
    os.chmod(root/'smoke-session.json',0o600)
    project=client.post('/api/v1/projects',headers=headers(client),json={'name':'Bounded synthetic smoke'}).json()['id']
    buf=BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
     z.writestr('data.yaml','train: images/train\nval: images/val\nnames: [object]\nnc: 1\n')
     for split in ['train','val']:
      for i in range(4):
       img=Image.new('RGB',(64,64),(20+i*10,40,80)); ImageDraw.Draw(img).rectangle((16,16,48,48),fill=(220,100,40)); out=BytesIO(); img.save(out,format='PNG')
       z.writestr(f'images/{split}/nested/{i}.png',out.getvalue());z.writestr(f'labels/{split}/nested/{i}.txt','0 0.5 0.5 0.5 0.5\n')
    r=client.post(f'/api/v1/projects/{project}/datasets',headers=headers(client),files={'file':('synthetic.zip',buf.getvalue(),'application/zip')});assert r.status_code==201,r.text
    dataset=r.json()['id']
    r=client.post(f'/api/v1/datasets/{dataset}/check',headers={**headers(client),'Idempotency-Key':'check'});assert r.status_code==202,r.text
    subprocess.run([sys.executable,'-m','app.worker','--once'],check=True,stdout=diagnostic,stderr=diagnostic,timeout=60)
    assert client.get(f'/api/v1/datasets/{dataset}').json()['state']=='ready'
    assert capability()['available']
    r=client.post(f'/api/v1/projects/{project}/jobs',headers={**headers(client),'Idempotency-Key':'train'},json={'kind':'train','params':{'dataset_id':dataset,'experiment_name':'bounded synthetic smoke','epochs':1,'batch':1,'imgsz':320,'device':'cpu','seed':0,'learning_rate':.01}});assert r.status_code==202,r.text
    job=r.json()['job_id']
    subprocess.run([sys.executable,'-m','app.worker','--once'],check=True,stdout=diagnostic,stderr=diagnostic,timeout=300)
    result=client.get(f'/api/v1/jobs/{job}').json()
    (root/'training-logs.json').write_text(client.get(f'/api/v1/jobs/{job}/logs').text)

    (root/'first-result.json').write_text(json.dumps(result,indent=2))
    assert result['state']=='succeeded'
    arts=client.get(f'/api/v1/projects/{project}/artifacts').json()['items']
    for art in arts:
     if art['kind'].startswith('pt_'):
      d=client.get(f"/api/v1/artifacts/{art['id']}/download"); assert d.status_code==200
    (root/'artifacts.json').write_text(json.dumps(arts,indent=2))
    (root/'metrics.json').write_text(client.get(f'/api/v1/jobs/{job}/metrics').text)
    close_server(); atexit.unregister(close_server)


def main():
    root = Path(os.environ['PLATFORM_DATA_ROOT']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'training-private.log').open('w') as diagnostic, contextlib.redirect_stdout(diagnostic), contextlib.redirect_stderr(diagnostic):
        try: run(diagnostic)
        except Exception:
            traceback.print_exc()
            success = False
        else: success = True
    print('PASS real managed HTTP training' if success else 'FAIL real managed HTTP training; private diagnostics retained')
    return 0 if success else 1


if __name__ == '__main__': raise SystemExit(main())
