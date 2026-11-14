import importlib.util
from pathlib import Path
import pytest


def load():
    path=Path(__file__).resolve().parents[2]/'scripts/real_cpu_metrics.py'
    assert path.is_file(),'frozen real test metric implementation missing'
    spec=importlib.util.spec_from_file_location('real_metrics',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_single_head_one_to_one_precision_recall_not_map():
    m=load();truth=[{'class_id':0,'xyxy':[0,0,10,10]}]*20
    detected=[[{'class_id':0,'score':.9,'xyxy':[0,0,10,10]}] for _ in truth]
    assert m.evaluate(truth,detected)=={'images':20,'ground_truth':20,'tp':20,'fp':0,'fn':0,'precision':1.,'recall':1.}
    detected[0].append(dict(detected[0][0]));detected[1]=[]
    result=m.evaluate(truth,detected)
    assert (result['tp'],result['fp'],result['fn'])==(19,1,1)
    assert result['precision']==.95 and result['recall']==.95
    assert m.evaluate(truth,[[] for _ in truth])['precision']==0


def test_wrong_class_and_below_threshold_not_matches():
    m=load();truth=[{'class_id':0,'xyxy':[0,0,10,10]}]*20
    detected=[[{'class_id':1,'score':.9,'xyxy':[0,0,10,10]}] for _ in truth]
    assert m.evaluate(truth,detected)['tp']==0
    with pytest.raises(ValueError):m.evaluate(truth[:-1],detected)


def test_frozen_voc_integer_corners_survive_decimal_yolo_roundtrip():
    m=load();assert hasattr(m,'voc_box_from_yolo'),'integer VOC reconstruction missing'
    label=b'1 0.494 0.165333333333 0.272 0.330666666667\n'
    assert m.voc_box_from_yolo(label,500,375)=={'class_id':1,'xyxy':[179,0,315,124]}
    with pytest.raises(ValueError):m.voc_box_from_yolo(b'1 0.495 0.165333333333 0.272 0.330666666667\n',500,375)
