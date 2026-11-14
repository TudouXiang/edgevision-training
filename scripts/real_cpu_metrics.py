"""Frozen single-head test metric at score > .25 and IoU >= .5; NOT mAP.

The subset has exactly one labelled head per image. Each image contributes at
most one true positive; duplicate detections count as false positives. Empty
predictions use precision=0 by convention, not as an unexecuted placeholder.
"""
import math


def require(value):
    if not value:raise ValueError('real test metrics rejected')


def box(value):
    require(type(value) is list and len(value)==4)
    require(all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=30_000_000 for v in value))
    require(value[0]<value[2] and value[1]<value[3])
    return value


def iou(a,b):
    overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return overlap/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap)


def evaluate(truth,predictions):
    require(type(truth) is list and type(predictions) is list and len(truth)==len(predictions)==20)
    tp=fp=0
    for target,items in zip(truth,predictions):
        require(type(target) is dict and set(target)=={'class_id','xyxy'})
        require(type(target['class_id']) is int and target['class_id'] in (0,1));box(target['xyxy'])
        require(type(items) is list and len(items)<=300)
        match=False
        for item in items:
            require(type(item) is dict and set(item)=={'class_id','score','xyxy'})
            require(type(item['class_id']) is int and item['class_id'] in (0,1))
            require(type(item['score']) in (int,float) and math.isfinite(item['score']) and .25<item['score']<=1)
            box(item['xyxy'])
            if item['class_id']==target['class_id'] and iou(item['xyxy'],target['xyxy'])>=.5:match=True
        tp+=int(match);fp+=len(items)-int(match)
    return {'images':20,'ground_truth':20,'tp':tp,'fp':fp,'fn':20-tp,
            'precision':tp/(tp+fp) if tp+fp else 0.,'recall':tp/20}


def voc_box_from_yolo(label,width,height):
    """Invert our frozen .12g encoding of integer VOC corners, not arbitrary boxes.

One selected edge is -1.875e-10 after binary-float decoding, despite the source
VOC corner being exactly zero. Require each recovered coordinate within 1e-6
pixel of an integer, then verify exact image bounds. Never clamp a bad box.
"""
    require(type(label) is bytes and len(label)<=256 and type(width) is int and type(height) is int and width>0 and height>0)
    fields=label.split();require(len(fields)==5 and fields[0] in (b'0',b'1'))
    cx,cy,w,h=map(float,fields[1:]);require(all(math.isfinite(v) for v in (cx,cy,w,h)))
    raw=[(cx-w/2)*width,(cy-h/2)*height,(cx+w/2)*width,(cy+h/2)*height]
    corners=[round(v) for v in raw]
    require(all(abs(a-b)<=1e-6 for a,b in zip(raw,corners)))
    box(corners);require(corners[2]<=width and corners[3]<=height)
    return {'class_id':int(fields[0]),'xyxy':corners}
