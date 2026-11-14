"""Native I policy acceptance is explicit opt-in; skipped in lightweight lanes."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

CASES = ('corrupt_onnx', 'missing_ort', 'provider_mismatch', 'execution_failure', 'nonfinite_output')


@pytest.mark.skipif(not os.environ.get('EDGEVISION_INFERENCE_POLICY_ROOT'),
                    reason='Explicit private, network-isolated I HTTP evidence root required')
@pytest.mark.parametrize('case', CASES)
def test_actual_image_policy(case):
    root = Path(os.environ['EDGEVISION_INFERENCE_POLICY_ROOT']).resolve()
    assert os.environ.get('PLATFORM_DATA_ROOT') and Path(os.environ['PLATFORM_DATA_ROOT']).resolve() == root
    assert (root / 'inference-http-result.json').is_file()
    with (root / ('inference-policy-' + case + '.log')).open('x') as diagnostic:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('inference_policy_probe.py')), case, str(root)],
                                stdout=diagnostic, stderr=diagnostic, timeout=90)
    assert result.returncode == 0, 'Native image policy failed; diagnostics retained privately'
