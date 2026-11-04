"""Native policy acceptance is explicitly opt-in and NOT_RUN in lightweight lanes."""
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.skipif(not os.environ.get('EDGEVISION_ONNX_POLICY_ROOT'), reason='Explicit private, network-isolated ONNX policy root required')
@pytest.mark.parametrize('case', ['corrupt', 'external', 'custom', 'sparse', 'numeric', 'no_fallback'])
def test_actual_onnx_policy(case):
    root = Path(os.environ['EDGEVISION_ONNX_POLICY_ROOT']).resolve()
    with (root / ('onnx-policy-' + case + '.log')).open('w') as diagnostic:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('onnx_policy_probe.py')), case, str(root)], stdout=diagnostic, stderr=diagnostic, timeout=180)
    assert result.returncode == 0, 'Native ONNX policy failed; diagnostics retained privately'
