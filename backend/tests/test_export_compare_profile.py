"""No native code: a separately opted-in bounded diagnostic container."""
import importlib.util
from pathlib import Path
import pytest
from test_isolated_ml_ci import ci,container,TOKEN,IMAGE


def test_compare_entry_is_fixed_and_distinct():
    v=container('edgevision-ml-'+TOKEN,'net:[1]')
    for args in (v['Args'],v['Config']['Cmd']):args[2]='/opt/edgevision/scripts/export_compare_entry.py'
    ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]',profile='export_compare_v1')
    for profile in ('legacy','real_cpu_v1'):
        with pytest.raises(ci.IsolationError):ci.verify_container(v,'edgevision-ml-'+TOKEN,TOKEN,IMAGE,'net:[1]',profile=profile)


def test_compare_requires_own_opt_in_and_full_sha():
    sha='d'*40
    env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_WORKFLOW':'EdgeVision feature checks','GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,'GITHUB_REPOSITORY':'x/y','GITHUB_WORKFLOW_REF':'x/y/.github/workflows/t020-ci.yml@refs/heads/feat/test','EDGEVISION_RUN_REAL_CPU':'true'}
    with pytest.raises(ci.IsolationError):ci.verify_hosted_workflow(env,sha,profile='export_compare_v1')
    env['EDGEVISION_RUN_EXPORT_COMPARE']='true'
    ci.verify_hosted_workflow(env,sha,profile='export_compare_v1')
    env['GITHUB_EVENT_NAME']='push'
    with pytest.raises(ci.IsolationError):ci.verify_hosted_workflow(env,sha,profile='export_compare_v1')


def test_workflow_has_three_exclusive_native_profiles():
    raw=(ci.ROOT/'.github/workflows/t020-ci.yml').read_text()
    for profile in ('run_isolated_ml','run_real_cpu','run_export_compare'):
        clause=next(line for line in raw.splitlines() if 'if: ${{' in line and 'inputs.'+profile+' == true' in line)
        assert "github.event_name == 'workflow_dispatch'" in clause
        for other in {'run_isolated_ml','run_real_cpu','run_export_compare'}-{profile}:assert 'inputs.'+other+' != true' in clause
    assert 'scripts/export_compare_ci.py --execute --expected-commit' in raw


def test_diagnostic_host_has_same_execution_budget_and_no_untrusted_command():
    p=ci.ROOT/'scripts/export_compare_ci.py'
    spec=importlib.util.spec_from_file_location('compare_ci',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.EXECUTION_TIMEOUT==1500
    assert m.ENTRY=='/opt/edgevision/scripts/export_compare_entry.py'
    assert m.report.initial()['purpose']=='diagnostic_only'


@pytest.mark.parametrize('fault',[None,'network','start_timeout','post_inspect','private_output','remove','remove_noop','image_remove'])
def test_compare_owned_cleanup_and_closed_output(tmp_path,fault):
    import json
    from test_isolated_ml_ci import FakeDocker
    from test_export_compare_report import proof
    p=ci.ROOT/'scripts/export_compare_ci.py'
    spec=importlib.util.spec_from_file_location('compare_ci',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    class Commands(FakeDocker):
        def docker(self,args,**kwargs):
            output=super().docker(args,**kwargs)
            if args[0]=='create':
                for argv in (self.current['Args'],self.current['Config']['Cmd']):argv[2]=m.ENTRY
                if fault=='network':self.current['HostConfig']['NetworkMode']='host'
            if args[0]=='start' and fault!='private_output':
                v=m.report.initial()
                for item in v['stages']:item['status']='passed'
                v['status']='passed';v['arms']={a:proof(a) for a in m.report.ARMS}
                return json.dumps(v)
            return output
    commands=Commands(tmp_path,failure=fault)
    result=m.RealRun(commands,tmp_path,token=TOKEN).run(tmp_path)
    assert result['status']==('passed' if fault is None else 'failed')
    assert 'SECRET' not in json.dumps(result)
    assert commands.current is None or fault in ('remove','remove_noop')
