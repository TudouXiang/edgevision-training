"""Real profile retains exact kernel/container restrictions; no Docker is used."""
from copy import deepcopy
import pytest
from test_isolated_ml_ci import ci, container, TOKEN, IMAGE


def real_container():
    value=container('edgevision-ml-'+TOKEN,'net:[1]')
    for args in (value['Args'],value['Config']['Cmd']):
        args[2]='/opt/edgevision/scripts/real_cpu_entry.py'
    return value


def test_explicit_fixed_real_entry_and_legacy_unchanged():
    v=real_container()
    ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]',profile='real_cpu_v1')
    with pytest.raises(ci.IsolationError):ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]')
    ci.verify_container(container('edgevision-ml-'+TOKEN,'net:[1]'),'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]')
    assert ci.EXECUTION_TIMEOUT==480 and len(ci.STAGES)==12


@pytest.mark.parametrize('fault',['network','root','caps','memory','entry','env','unknown'])
def test_real_profile_never_relaxes_boundary(fault):
    value=real_container();profile='real_cpu_v1'
    if fault=='network':value['HostConfig']['NetworkMode']='bridge'
    if fault=='root':value['Config']['User']='0:0'
    if fault=='caps':value['HostConfig']['CapDrop']=[]
    if fault=='memory':value['HostConfig']['Memory']=0
    if fault=='entry':value['Args'][2]='/tmp/arbitrary.py'
    if fault=='env':value['Config']['Env'].append('SECRET=bad')
    if fault=='unknown':profile='custom'
    with pytest.raises(ci.IsolationError):ci.verify_container(value,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]',profile=profile)


def test_source_recipe_selection_is_closed(tmp_path):
    with pytest.raises(ci.IsolationError):
        ci.copy_source(tmp_path,'',lambda _:b'',recipe='../../outside')
    with pytest.raises(ci.IsolationError):
        ci.copy_source(tmp_path,'',lambda _:b'',recipe='ci/isolated-real-cpu.Dockerfile')


def load_real_ci():
    import importlib.util
    path=ci.ROOT/'scripts/real_cpu_ci.py'
    assert path.is_file(), 'separate real CPU runner missing'
    spec=importlib.util.spec_from_file_location('real_cpu_ci',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_real_workflow_needs_its_own_opt_in():
    m=load_real_ci();sha='d'*40
    env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
         'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_WORKFLOW':'EdgeVision feature checks',
         'GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,'GITHUB_REPOSITORY':'x/y',
         'GITHUB_WORKFLOW_REF':'x/y/.github/workflows/t020-ci.yml@refs/heads/feat/test',
         'EDGEVISION_RUN_ISOLATED_ML':'true'}
    with pytest.raises(m.base.IsolationError):m.verify_workflow(env,sha)
    env['EDGEVISION_RUN_REAL_CPU']='true'
    m.verify_workflow(env,sha)
    env['GITHUB_EVENT_NAME']='push'
    with pytest.raises(m.base.IsolationError):m.verify_workflow(env,sha)


def test_real_runner_failure_cleanup_is_never_success(tmp_path,monkeypatch):
    m=load_real_ci();runner=m.RealRun(None,tmp_path,token=TOKEN)
    monkeypatch.setattr(runner,'build',lambda _:None)
    monkeypatch.setattr(runner,'execute',lambda:None)
    monkeypatch.setattr(runner,'cleanup',lambda:True)
    result=runner.run(tmp_path)
    assert result['status']=='failed'
    assert result['stages'][0]['status']=='NOT_RUN'
    monkeypatch.setattr(runner,'cleanup',lambda:False)
    result=runner.run(tmp_path)
    assert result['stages'][-1]['status']=='failed'

@pytest.mark.parametrize('fault',[None,'network','start_timeout','post_inspect','private_output','remove','remove_noop','image_remove'])
def test_real_profile_owned_cleanup_and_exact_commands(tmp_path,fault):
    import json
    from test_isolated_ml_ci import FakeDocker
    m=load_real_ci()
    class RealDocker(FakeDocker):
        def docker(self,args,**kwargs):
            output=super().docker(args,**kwargs)
            if args[0]=='create':
                for argv in (self.current['Args'],self.current['Config']['Cmd']):argv[2]=m.ENTRY
                if fault=='network':self.current['HostConfig']['NetworkMode']='host'
            if args[0]=='start' and fault!='private_output':
                v=m.report.initial()
                for item in v['stages']:item['status']='passed'
                v['status']='passed'
                v['measurements']=m.report.measurements({key:[1]*20 for key in m.report.SERIES},{'pt':1.,'onnx':1.})
                v['evaluation']={'protocol':'single-head-p025-iou050-v1',**{b:{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.} for b in ('pt','onnx')}}
                v['evaluation']['comparison']={'images':20,'elements':1008000,'max_absolute_error':0.,'max_tolerance_ratio':0.,'atol':1e-4,'rtol':1e-4,'detections_matched':True}
                return json.dumps(v)
            return output
    commands=RealDocker(tmp_path,failure=fault)
    result=m.RealRun(commands,tmp_path,token=TOKEN).run(tmp_path)
    assert result['status']==('passed' if fault is None else 'failed')
    assert 'SECRET' not in json.dumps(result)
    creates=[args for args,_ in commands.calls if args[0]=='create']
    assert creates and creates[0][-3]==m.ENTRY
    assert commands.current is None or fault in ('remove','remove_noop')


def test_real_workflow_does_not_require_or_forge_legacy_flag():
    m=load_real_ci();sha='d'*40
    env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_EVENT_NAME':'workflow_dispatch',
         'GITHUB_WORKFLOW':'EdgeVision feature checks','GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,
         'GITHUB_REPOSITORY':'x/y','GITHUB_WORKFLOW_REF':'x/y/.github/workflows/t020-ci.yml@refs/heads/feat/test',
         'EDGEVISION_RUN_REAL_CPU':'true'}
    before=dict(env);m.verify_workflow(env,sha);assert env==before


def test_real_main_rejects_unapproved_before_commands(tmp_path,monkeypatch,capsys):
    m=load_real_ci();monkeypatch.delenv('EDGEVISION_RUN_REAL_CPU',raising=False)
    monkeypatch.setattr(m.base,'PrivateCommands',lambda _:pytest.fail('commands before gate'))
    assert m.main(['--execute','--expected-commit','d'*40,'--report-dir',str(tmp_path/'report')])==1
    import json
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='failed'
    assert json.loads((tmp_path/'report/summary.json').read_text())==result


def test_real_workflow_is_separate_explicit_and_uploads_only_receipt():
    text=(ci.ROOT/'.github/workflows/t020-ci.yml').read_text()
    assert 'run_real_cpu:' in text
    real=text.split('  linux-real-cpu:',1)[1]
    assert "github.event_name == 'workflow_dispatch' && inputs.run_real_cpu == true && inputs.run_isolated_ml != true" in real
    assert 'timeout-minutes: 45' in real
    assert 'scripts/real_cpu_ci.py --execute' in real and '--expected-commit "$EDGEVISION_APPROVED_COMMIT"' in real
    assert 'persist-credentials: false' in real and 'include-hidden-files: false' in real
    assert 'real-cpu-report/summary.json' in real
    assert 'upload-artifact' in real and 'docker push' not in real
