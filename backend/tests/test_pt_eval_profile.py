"""PT-only hosted/container boundaries; no Docker or model execution."""
import importlib.util
import json
from pathlib import Path
import pytest
from test_isolated_ml_ci import ci,container,TOKEN,IMAGE


def load(name):
    p=ci.ROOT/'scripts'/f'{name}.py';assert p.is_file(),'PT-only profile missing'
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_fixed_entry_and_opt_in():
    v=container('edgevision-ml-'+TOKEN,'net:[1]')
    for args in (v['Args'],v['Config']['Cmd']):args[2]='/opt/edgevision/scripts/pt_eval_entry.py'
    ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]',profile='pt_eval_v1')
    with pytest.raises(ci.IsolationError):ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]')
    m=load('pt_eval_ci');assert m.EXECUTION_TIMEOUT==1260
    sha='d'*40
    env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_WORKFLOW':'EdgeVision feature checks','GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,'GITHUB_REPOSITORY':'x/y','GITHUB_WORKFLOW_REF':'x/y/.github/workflows/t020-ci.yml@refs/heads/feat/test'}
    with pytest.raises(m.base.IsolationError):m.verify_workflow(env,sha)
    env['EDGEVISION_RUN_PT_EVAL']='true';m.verify_workflow(env,sha)
    env['GITHUB_EVENT_NAME']='push'
    with pytest.raises(m.base.IsolationError):m.verify_workflow(env,sha)


@pytest.mark.parametrize('fault',['network','root','caps','memory','entry','env'])
def test_pt_boundary_does_not_relax_existing_controls(fault):
    v=container('edgevision-ml-'+TOKEN,'net:[1]')
    for args in (v['Args'],v['Config']['Cmd']):args[2]='/opt/edgevision/scripts/pt_eval_entry.py'
    if fault=='network':v['HostConfig']['NetworkMode']='bridge'
    if fault=='root':v['Config']['User']='0:0'
    if fault=='caps':v['HostConfig']['CapDrop']=[]
    if fault=='memory':v['HostConfig']['Memory']=0
    if fault=='entry':v['Args'][2]='/tmp/arbitrary.py'
    if fault=='env':v['Config']['Env'].append('SECRET=bad')
    with pytest.raises(ci.IsolationError):ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]',profile='pt_eval_v1')


def test_four_profiles_are_mutually_exclusive():
    raw=(ci.ROOT/'.github/workflows/t020-ci.yml').read_text()
    profiles={'run_isolated_ml','run_real_cpu','run_export_compare','run_pt_eval'}
    for profile in profiles:
        clause=next(line for line in raw.splitlines() if 'if: ${{' in line and 'inputs.'+profile+' == true' in line)
        assert "github.event_name == 'workflow_dispatch'" in clause
        for other in profiles-{profile}:assert 'inputs.'+other+' != true' in clause


def test_boundary_failure_starts_nothing(tmp_path,monkeypatch,capsys):
    m=load('pt_eval_entry');monkeypatch.setattr(m,'ROOT',tmp_path)
    def deny(_):raise ValueError('private boundary detail')
    monkeypatch.setattr(m.boundary,'verify_boundary',deny)
    monkeypatch.setattr(m.boundary,'run_stage',lambda *a:pytest.fail('started before boundary'))
    assert m.main(['--host-netns','net:[1]'])==1
    assert json.loads(capsys.readouterr().out)['stages'][0]['status']=='failed'
    assert not (tmp_path/'private').exists()


@pytest.mark.parametrize('mode',['private','missing','child_failed'])
def test_child_failure_and_untrusted_receipt_cannot_pass(tmp_path,monkeypatch,capsys,mode):
    m=load('pt_eval_entry');monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m.boundary,'verify_boundary',lambda _:None)
    def run(args,cwd,env,output,budget):
        assert budget==1200 and args[2].endswith('pt_eval_probe.py')
        assert env['EDGEVISION_PT_EVAL_PROFILE']=='v1'
        if mode=='missing':return
        from test_pt_eval_report import passing
        value={'secret':'private'} if mode=='private' else passing(m.report)
        (tmp_path/'private/pt-eval-receipt.json').write_text(json.dumps(value))
        if mode=='child_failed':raise RuntimeError('private child detail')
    monkeypatch.setattr(m.boundary,'run_stage',run)
    assert m.main(['--host-netns','net:[1]'])==1
    raw=capsys.readouterr().out;assert 'secret' not in raw and 'private' not in raw
    assert json.loads(raw)['status']=='failed'


@pytest.mark.parametrize('fault',[None,'network','start_timeout','post_inspect','private_output','remove','remove_noop','image_remove'])
def test_owned_cleanup_and_closed_output(tmp_path,fault):
    from test_isolated_ml_ci import FakeDocker
    from test_pt_eval_report import passing
    m=load('pt_eval_ci')
    class Commands(FakeDocker):
        def docker(self,args,**kwargs):
            output=super().docker(args,**kwargs)
            if args[0]=='create':
                for argv in (self.current['Args'],self.current['Config']['Cmd']):argv[2]=m.ENTRY
                if fault=='network':self.current['HostConfig']['NetworkMode']='host'
            if args[0]=='start' and fault!='private_output':return json.dumps(passing(m.report))
            return output
    commands=Commands(tmp_path,failure=fault)
    result=m.RealRun(commands,tmp_path,token=TOKEN).run(tmp_path)
    assert result['status']==('passed' if fault is None else 'failed')
    assert 'SECRET' not in json.dumps(result)
    assert commands.current is None or fault in ('remove','remove_noop')
