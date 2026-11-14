import importlib.util
import json
from pathlib import Path
import pytest


def load():
    path=Path(__file__).resolve().parents[2]/'scripts/real_cpu_entry.py'
    assert path.is_file(),'real isolated entry absent'
    spec=importlib.util.spec_from_file_location('real_entry',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_boundary_failure_starts_nothing(tmp_path,monkeypatch,capsys):
    m=load();monkeypatch.setattr(m,'ROOT',tmp_path)
    def deny(_):raise ValueError('private boundary detail')
    monkeypatch.setattr(m.boundary,'verify_boundary',deny)
    monkeypatch.setattr(m.boundary,'run_stage',lambda *a:pytest.fail('started before boundary'))
    assert m.main(['--host-netns','net:[1]'])==1
    result=json.loads(capsys.readouterr().out)
    assert result['stages'][0]['status']=='failed'
    assert not (tmp_path/'private').exists()


def test_missing_or_private_receipt_not_success(tmp_path,monkeypatch,capsys):
    m=load();monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m.boundary,'verify_boundary',lambda _:None)
    def run(args,cwd,env,output,remaining):
        assert args[1]=='-I' and args[2].endswith('real_cpu_probe.py')
        assert env['EDGEVISION_ISOLATED_HOST_NETNS']=='net:[1]'
        assert remaining==1440
        (tmp_path/'private/real-receipt.json').write_text('{"secret":"private"}')
    monkeypatch.setattr(m.boundary,'run_stage',run)
    assert m.main(['--host-netns','net:[1]'])==1
    text=capsys.readouterr().out;assert 'secret' not in text and 'private' not in text
    assert json.loads(text)['status']=='failed'

@pytest.mark.parametrize('error',[RuntimeError,TimeoutError])
def test_failed_child_cannot_promote_passed_receipt(tmp_path,monkeypatch,capsys,error):
    m=load();monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m.boundary,'verify_boundary',lambda _:None)
    def run(*args):
        v=m.report.initial()
        for item in v['stages']:item['status']='passed'
        v['status']='passed';v['measurements']=m.report.measurements({key:[1]*20 for key in m.report.SERIES},{'pt':1.,'onnx':1.})
        v['evaluation']={'protocol':'single-head-p025-iou050-v1',**{b:{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.} for b in ('pt','onnx')}}
        v['evaluation']['comparison']={'images':20,'elements':1008000,'max_absolute_error':0.,'max_tolerance_ratio':0.,'atol':1e-4,'rtol':1e-4,'detections_matched':True}
        (tmp_path/'private/real-receipt.json').write_text(json.dumps(v))
        raise error('private')
    monkeypatch.setattr(m.boundary,'run_stage',run)
    assert m.main(['--host-netns','net:[1]'])==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'
