"""P must remain closed until the genuinely standalone proof is implemented."""
import pytest


def test_i_success_or_arbitrary_record_cannot_enable_package(tmp_path, monkeypatch):
    from app import package_assets, inference_assets
    monkeypatch.setattr(inference_assets,'capability',lambda:{'available':True})
    (tmp_path/'package-capability.json').write_text('{"available":true}')
    monkeypatch.setenv('EDGEVISION_DATA_ROOT',str(tmp_path))
    assert package_assets.capability()['available'] is False
    assert package_assets.capability()['reason_code']=='PACKAGE_SETUP_REQUIRED'
    with pytest.raises(ValueError):package_assets.validated_template()
