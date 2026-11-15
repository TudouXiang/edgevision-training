import importlib.util
from pathlib import Path
import pytest
P=Path(__file__).resolve().parents[2]/'scripts/export_compare_metrics.py'
s=importlib.util.spec_from_file_location('error_groups',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def test_threshold_zero_and_group_boundary():
    ref=[0.0]*50400;actual=ref.copy();actual[33599]=1e-4;actual[33600]=1.0001e-4
    result=m.measure_values(ref,actual)
    assert result['boxes']['mismatch_count']==0
    assert result['scores']['mismatch_count']==1
    assert result['boxes']['elements']==33600 and result['scores']['elements']==16800
    assert sum(g['mismatch_count'] for g in result.values())==1


def test_reference_direction_is_preserved():
    ref=[1.0]*50400;actual=[1.00020001]*50400
    assert m.measure_values(ref,actual)['boxes']['mismatch_count']==33600
    assert m.measure_values(actual,ref)['boxes']['mismatch_count']==0


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_is_not_filtered(bad):
    ref=[0.0]*50400;actual=ref.copy();actual[0]=bad
    result=m.measure_values(ref,actual)
    assert result['boxes']=={'elements':33600,'finite':False,'mismatch_count':None,'max_absolute_error':None,'max_tolerance_ratio':None}
    assert result['scores']['finite'] is True


def test_length_bound():
    with pytest.raises(ValueError):m.measure_values([0.0],[0.0])


def test_closed_groups_and_numeric_types():
    result=m.measure_values([0.0]*50400,[0.0]*50400)
    m.validate_groups(result)
    result['boxes']['mismatch_count']=True
    with pytest.raises(ValueError):m.validate_groups(result)


def test_unexecuted_matrix_is_incomplete():
    matrix=m.empty_matrix('D')
    assert not m.complete(matrix,'D')
    assert set(matrix)=={'current_ort','current_disabled','disabled_ort'}


@pytest.mark.parametrize('shape,dtype',[((1,5,8400),'float32'),((1,6,8400),'float64'),((50400,),'float32')])
def test_array_shape_and_dtype_rejected_before_read(shape,dtype):
    class NP:float32='float32'
    class A:
        def ravel(self):raise AssertionError('must not read malformed array')
    a=A();a.shape=shape;a.dtype=dtype
    with pytest.raises(ValueError):m.measure_arrays(NP,a,a)


@pytest.mark.parametrize('key,value',[('max_absolute_error',float('nan')),('max_absolute_error',True),('max_tolerance_ratio',1e45),('mismatch_count',33601),('elements',1)])
def test_bounded_numeric_schema(key,value):
    result=m.measure_values([0.0]*50400,[0.0]*50400)
    result['boxes'][key]=value
    with pytest.raises(ValueError):m.validate_groups(result)


def test_statistics_and_boolean_must_agree():
    matrix=m.empty_matrix('A');matrix['current_ort']['zeros']=m.measure_values([0.0]*50400,[0.0]*50400)
    checks={'reference_ort_match':{'zeros':False,'gradient':None,'pattern':None},'backend_reference_match':None}
    with pytest.raises(ValueError):m.validate_matrix(matrix,'A',checks)
    checks['reference_ort_match']['zeros']=True
    m.validate_matrix(matrix,'A',checks)
    assert not m.complete(matrix,'A')


def test_unknown_direction_and_extra_group_rejected():
    matrix=m.empty_matrix('A');matrix['raw_tensor']=[]
    with pytest.raises(ValueError):m.validate_matrix(matrix,'A',{})
    result=m.measure_values([0.0]*50400,[0.0]*50400);result['raw']=[]
    with pytest.raises(ValueError):m.validate_groups(result)
