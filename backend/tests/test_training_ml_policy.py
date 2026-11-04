import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.skipif(not os.environ.get('EDGEVISION_ML_POLICY_ROOT'),reason='Explicit private ML smoke root required')
@pytest.mark.parametrize('case',['unknown_class','batch_drift','nonfinite'])
def test_actual_fixed_runtime_fails_closed(case):
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('runtime_policy_probe.py')),case,os.environ['EDGEVISION_ML_POLICY_ROOT']],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PASS '+case in result.stdout
