"""Synthetic handoff tests. No native runtime imports or model execution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
from uuid import uuid4

import pytest
from app import export_backend_handoff as handoff
from app.run_files import run_directory

SOURCE = 'a' * 64
RUNTIME = 'b' * 64
PRECISION = {'mkldnn_enabled': True, 'global': 'ieee', 'backend': 'none', 'conv': 'ieee', 'matmul': 'ieee'}
RAW = b'\0' * handoff.RAW_BYTES


def setup_run(monkeypatch, root):
    monkeypatch.setenv('PLATFORM_DATA_ROOT', str(root))
    job, run = str(uuid4()), str(uuid4())
    directory = run_directory(job, run, create=True)
    (directory / 'model.onnx').write_bytes(b'ONNX-TEST')
    for name in handoff.CURRENT_FILES:
        (directory / name).write_bytes(RAW)
    frozen = {'source_sha256': SOURCE, 'runtime_binding': RUNTIME}
    return job, run, directory, frozen


def test_capture_verify_copy_roundtrip_uses_fixed_files_only(tmp_path, monkeypatch):
    job, run, source, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    manifest = handoff.capture(job, run, frozen, PRECISION)
    assert set(manifest) == {'schema_version','job_id','run_id','source_sha256','runtime_binding','precision','files'}
    assert set(manifest['files']) == set(handoff.FIXED_FILES)
    assert set(handoff.verify(manifest, frozen)) == set(handoff.FIXED_FILES)
    dest = run_directory(str(uuid4()), str(uuid4()), create=True)
    copied = handoff.copy_to(manifest, frozen, dest)
    assert set(copied) == set(handoff.FIXED_FILES)
    assert all(path.is_file() and path.read_bytes() == (source / name).read_bytes() for name, path in copied.items())


def test_manifest_rejects_unknown_file_stale_bindings_and_bad_precision(tmp_path, monkeypatch):
    job, run, _, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    manifest = handoff.capture(job, run, frozen, PRECISION)
    bad = json.loads(json.dumps(manifest)); bad['files']['../../private'] = {'size_bytes':1,'sha256':'0'*64}
    with pytest.raises(ValueError): handoff.verify(bad, frozen)
    with pytest.raises(ValueError): handoff.verify(manifest, {**frozen, 'source_sha256':'c'*64})
    bad = json.loads(json.dumps(manifest)); bad['precision']['mkldnn_enabled'] = False
    with pytest.raises(ValueError): handoff.verify(bad, frozen)


def test_verify_rejects_manifest_tampering_and_symlink_file(tmp_path, monkeypatch):
    job, run, directory, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    manifest = handoff.capture(job, run, frozen, PRECISION)
    (directory / 'current-zeros.f32').write_bytes(b'changed')
    with pytest.raises(ValueError): handoff.verify(manifest, frozen)
    (directory / 'current-zeros.f32').unlink()
    target = tmp_path / 'target'; target.write_bytes(RAW)
    (directory / 'current-zeros.f32').symlink_to(target)
    with pytest.raises(ValueError): handoff.verify(manifest, frozen)


def test_equal_length_mutation_hash_tamper_and_stale_runtime_fail_closed(tmp_path, monkeypatch):
    job, run, directory, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    manifest = handoff.capture(job, run, frozen, PRECISION)
    (directory / 'current-zeros.f32').write_bytes(b'\x01' + RAW[1:])
    with pytest.raises(ValueError): handoff.verify(manifest, frozen)
    (directory / 'current-zeros.f32').write_bytes(RAW)
    bad = json.loads(json.dumps(manifest)); bad['files']['model.onnx']['sha256'] = '0' * 64
    with pytest.raises(ValueError): handoff.verify(bad, frozen)
    with pytest.raises(ValueError): handoff.verify(manifest, {**frozen, 'runtime_binding':'c'*64})
    bad = json.loads(json.dumps(manifest)); bad['job_id'] = bad['job_id'].upper()
    with pytest.raises(ValueError): handoff.verify(bad, frozen)


def test_fifo_is_rejected_without_blocking(tmp_path, monkeypatch):
    if not hasattr(os, 'mkfifo'): pytest.skip('requires POSIX fifo')
    job, run, directory, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    (directory / 'current-pattern.f32').unlink()
    os.mkfifo(directory / 'current-pattern.f32')
    with pytest.raises(ValueError): handoff.capture(job, run, frozen, PRECISION)


def test_capture_rejects_bad_raw_length_nonfinite_and_oversized_model(tmp_path, monkeypatch):
    job, run, directory, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    (directory / 'current-pattern.f32').write_bytes(b'bad')
    with pytest.raises(ValueError): handoff.capture(job, run, frozen, PRECISION)
    (directory / 'current-pattern.f32').write_bytes(struct.pack('<f', float('nan')) * (handoff.RAW_BYTES // 4))
    with pytest.raises(ValueError): handoff.capture(job, run, frozen, PRECISION)
    manifest = {'schema_version':1,'job_id':job,'run_id':run,'source_sha256':SOURCE,'runtime_binding':RUNTIME,'precision':PRECISION,
                'files':{name:{'size_bytes':handoff.MAX_ONNX_BYTES+1 if name=='model.onnx' else handoff.RAW_BYTES,'sha256':'0'*64} for name in handoff.FIXED_FILES}}
    with pytest.raises(ValueError): handoff.verify(manifest, frozen)


def test_copy_rejects_symlinked_destination_parent(tmp_path, monkeypatch):
    job, run, _, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    manifest = handoff.capture(job, run, frozen, PRECISION)
    real = tmp_path / 'real'; real.mkdir(); link = tmp_path / 'link'; link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError): handoff.copy_to(manifest, frozen, link)


def test_copy_never_overwrites_and_detects_source_change_during_copy(tmp_path, monkeypatch):
    job, run, source, frozen = setup_run(monkeypatch, tmp_path / 'platform')
    manifest = handoff.capture(job, run, frozen, PRECISION)
    dest = run_directory(str(uuid4()), str(uuid4()), create=True)
    copied = handoff.copy_to(manifest, frozen, dest)
    before = copied['model.onnx'].read_bytes()
    with pytest.raises(FileExistsError): handoff.copy_to(manifest, frozen, dest)
    assert copied['model.onnx'].read_bytes() == before

    changed_dest = run_directory(str(uuid4()), str(uuid4()), create=True)
    original_write = handoff._write_exclusive
    calls = []
    def changing_write(path, raw):
        original_write(path, raw)
        calls.append(path.name)
        if len(calls) == 1:
            (source / 'current-gradient.f32').write_bytes(b'\x01' + RAW[1:])
    monkeypatch.setattr(handoff, '_write_exclusive', changing_write)
    with pytest.raises(ValueError): handoff.copy_to(manifest, frozen, changed_dest)


def test_precision_snapshot_reads_effective_values_and_only_enabled_can_change():
    class Obj: pass
    backends = Obj(); backends.fp32_precision='ieee'
    backends.mkldnn=Obj(); backends.mkldnn.enabled=True; backends.mkldnn.fp32_precision='none'
    backends.mkldnn.conv=Obj(); backends.mkldnn.conv.fp32_precision='bf16'
    backends.mkldnn.matmul=Obj(); backends.mkldnn.matmul.fp32_precision='tf32'
    torch=Obj(); torch.backends=backends
    assert handoff.precision_snapshot(torch)=={'mkldnn_enabled':True,'global':'ieee','backend':'none','conv':'bf16','matmul':'tf32'}


def test_precision_snapshot_never_substitutes_gpu_controls_for_cpu_mkldnn():
    class Obj: pass
    backends=Obj(); backends.fp32_precision='ieee'; backends.mkldnn=Obj(); backends.mkldnn.enabled=True
    backends.cudnn=Obj(); backends.cudnn.conv=Obj(); backends.cudnn.conv.fp32_precision='tf32'
    backends.cuda=Obj(); backends.cuda.matmul=Obj(); backends.cuda.matmul.fp32_precision='bf16'
    torch=Obj(); torch.backends=backends
    with pytest.raises(ValueError): handoff.precision_snapshot(torch)


def test_diagnostic_schema_is_fixed_a_d_and_records_three_directions():
    from app import real_export_diagnostic as diagnostic
    assert diagnostic.arm_settings('A') == {'export':True, 'disable_mkldnn':False}
    assert diagnostic.arm_settings('D') == {'export':False, 'disable_mkldnn':True}
    for bad in ('B','C','a',True):
        with pytest.raises(ValueError): diagnostic.arm_settings(bad)
    for arm in ('A','D'):
        proof=diagnostic.empty_proof(arm)
        assert proof['schema_version']==3 and proof['arm']==arm and proof['precision'] is None
        assert set(proof['checks']) == {'source_bn','onnx_batchnorm','pt_repeat_pre','pt_repeat_post','source_unchanged','network_unchanged','reference_ort_match','backend_reference_match','shared_input_unchanged'}
        assert set(proof['metrics']) == {'current_ort','current_disabled','disabled_ort'}
        assert proof['checks']['backend_reference_match'] is None


def test_typed_comparator_keeps_only_complete_numeric_mismatch_stats():
    from app import real_export_diagnostic as diagnostic
    class Error(Exception):
        def __init__(self, code): self.diagnostic=code
    stats={'boxes':{'mismatch_count':1}}
    class Metrics:
        @staticmethod
        def measure_arrays(*args): return stats
    def mismatch(*args): raise Error('compare_tolerance')
    assert diagnostic._compare_one(Metrics, mismatch, Error, None, None, None, 'gradient') is stats
    def incomplete(*args): raise Error('compare_shape_dtype')
    with pytest.raises(Error): diagnostic._compare_one(Metrics, incomplete, Error, None, None, None, 'gradient')
