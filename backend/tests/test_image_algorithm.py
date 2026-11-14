"""ADR0014 protocol fixtures; mathematical/Pillow tests, not ML execution evidence."""
from array import array
from hashlib import sha256
from io import BytesIO
import math
import struct
import sys

import pytest
from PIL import Image


def encode(image, fmt='PNG', **kwargs):
    sink = BytesIO()
    image.save(sink, format=fmt, **kwargs)
    return sink.getvalue()


def raw_rows(*anchors, nc=2):
    """Explicit synthetic raw values, never model output."""
    value = array('f', [0.]) * ((4 + nc) * 8400)
    for index, row in enumerate(anchors):
        assert len(row) == 4 + nc
        for channel, number in enumerate(row):
            value[channel * 8400 + index] = number
    if sys.byteorder != 'little':
        value.byteswap()
    return value.tobytes()


@pytest.mark.parametrize('width,height,expected', [
    (640, 640, (640, 640, 0, 0, 0, 0)),
    (3, 2, (640, 427, 0, 0, 106, 107)),
    (2, 3, (427, 640, 106, 107, 0, 0)),
    (1, 1, (640, 640, 0, 0, 0, 0)),
    (30000, 1, (640, 1, 0, 0, 319, 320)),
])
def test_integer_letterbox(width, height, expected):
    from app.delivery_infer import letterbox_record
    value = letterbox_record(width, height)
    assert tuple(value[key] for key in ('resized_width', 'resized_height', 'left', 'right', 'top', 'bottom')) == expected
    assert value['scale_x'] == expected[0] / width
    assert value['scale_y'] == expected[1] / height


def test_stable_single_label_class_aware_nms_and_clip():
    from app.delivery_infer import letterbox_record, postprocess
    geometry = letterbox_record(640, 640)
    raw = raw_rows((100, 100, 20, 20, .9, .9), (100, 100, 20, 20, .9, 0),
                   (100, 100, 20, 20, 0, .9), (0, 0, 20, 20, .8, 0))
    result = postprocess(raw, ['a', 'b'], geometry, .25, .45)
    assert [(d['class_id'], d['xyxy']) for d in result['detections']] == [
        (0, [90., 90., 110., 110.]), (1, [90., 90., 110., 110.]), (0, [0., 0., 10., 10.])]


def test_threshold_equality_and_empty_detection():
    from app.delivery_infer import letterbox_record, postprocess
    geometry = letterbox_record(640, 640)
    assert postprocess(raw_rows((20, 20, 10, 10, .25, 0)), ['a', 'b'], geometry, .25, .45)['detections'] == []
    result = postprocess(raw_rows((20, 20, 10, 10, .75, 0), (20, 20, 10, 10, .5, 0)), ['a', 'b'], geometry, .25, 1.)
    assert len(result['detections']) == 2  # IoU == threshold is not suppressed.


@pytest.mark.parametrize('number', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_whole_raw_fails(number):
    from app.delivery_infer import ImageInferenceError, letterbox_record, postprocess
    with pytest.raises(ImageInferenceError, match='INFERENCE_OUTPUT_INVALID'):
        postprocess(raw_rows((number, 20, 10, 10, .5, 0)), ['a', 'b'], letterbox_record(640, 640), .25, .45)


@pytest.mark.parametrize('orientation', range(1, 9))
def test_exif_dimensions_and_stripped_preview(tmp_path, orientation):
    from app.delivery_infer import decode_image, preview_png
    original = Image.new('RGB', (3, 2), (10, 20, 30))
    exif = Image.Exif(); exif[274] = orientation
    path = tmp_path / 'image.png'
    path.write_bytes(encode(original, exif=exif))
    rgb, record = decode_image(path, 'png')
    expected = (2, 3) if orientation in (5, 6, 7, 8) else (3, 2)
    assert rgb.size == expected
    assert (record['encoded_width'], record['encoded_height']) == (3, 2)
    assert record['orientation'] == orientation
    preview, size = preview_png(rgb)
    with Image.open(BytesIO(preview)) as image:
        assert image.size == expected == size
        assert not image.info
    assert record['rgb_sha256'] == sha256(rgb.tobytes()).hexdigest()


@pytest.mark.parametrize('mode', ['RGBA', 'LA', 'P', 'RGB', 'L'])
def test_alpha_and_trns_use_fixed_background(tmp_path, mode):
    from app.delivery_infer import decode_image
    if mode == 'RGBA': image = Image.new(mode, (1, 1), (200, 40, 10, 128)); expected = (157, 77, 62)
    elif mode == 'LA': image = Image.new(mode, (1, 1), (200, 128)); expected = (157, 157, 157)
    elif mode == 'P':
        image = Image.new(mode, (1, 1), 0); image.putpalette([200, 40, 10] + [0] * 765); image.info['transparency'] = 0; expected = (114,) * 3
    elif mode == 'RGB': image = Image.new(mode, (1, 1), (200, 40, 10)); image.info['transparency'] = (200, 40, 10); expected = (114,) * 3
    else: image = Image.new(mode, (1, 1), 200); image.info['transparency'] = 200; expected = (114,) * 3
    path = tmp_path / 'image.png'; path.write_bytes(encode(image))
    rgb, _ = decode_image(path, 'png')
    assert rgb.getpixel((0, 0)) == expected


def test_tensor_layout_padding_and_little_endian_hash():
    from app.delivery_infer import preprocess
    raw, record = preprocess(Image.new('RGB', (3, 2), (255, 0, 127)))
    assert len(raw) == 3 * 640 * 640 * 4
    assert struct.unpack_from('<f', raw, 0)[0] == pytest.approx(114 / 255)
    assert struct.unpack_from('<f', raw, (106 * 640) * 4)[0] == 1.
    assert struct.unpack_from('<f', raw, (640*640 + 106*640) * 4)[0] == 0.
    assert record['tensor_sha256'] == sha256(raw).hexdigest()


@pytest.mark.parametrize('kind', ['bad', 'format', 'multiframe', 'mode', 'orientation', 'pixels'])
def test_decode_closed_failures(tmp_path, kind, monkeypatch):
    from app import delivery_infer as core
    image = Image.new('RGB', (3, 2))
    options = {}; declared = 'png'; expected = 'IMAGE_DECODE_FAILED'
    if kind == 'format': declared = 'jpeg'; expected = 'IMAGE_FORMAT_MISMATCH'
    if kind == 'multiframe': options = {'save_all': True, 'append_images': [Image.new('RGB', (3, 2), 'red')]}; expected = 'IMAGE_MULTIFRAME'
    if kind == 'mode': image = Image.new('I;16', (3, 2)); expected = 'IMAGE_MODE_UNSUPPORTED'
    if kind == 'orientation':
        exif = Image.Exif(); exif[274] = 9; options['exif'] = exif
    if kind == 'pixels': monkeypatch.setattr(core, 'MAX_PIXELS', 5); expected = 'IMAGE_PIXEL_LIMIT'
    path = tmp_path / 'image.png'; path.write_bytes(b'broken' if kind == 'bad' else encode(image, **options))
    with pytest.raises(core.ImageInferenceError) as raised: core.decode_image(path, declared)
    assert raised.value.code == expected


def test_bounded_candidates_and_results():
    from app.delivery_infer import postprocess, letterbox_record
    result = postprocess(raw_rows(*([(320, 320, 2, 2, .75, 0)] * 3100)), ['a', 'b'], letterbox_record(640, 640), .25, 1.)
    assert len(result['detections']) == 300
    assert result['counts'] == {'candidates': 3100, 'candidate_truncated': 100, 'nms_kept': 3000, 'result_truncated': 2700, 'clip_removed': 0}


def test_extreme_finite_geometry_stays_finite_and_clips():
    from app.delivery_infer import postprocess, letterbox_record
    result = postprocess(raw_rows((0, 0, 3e38, 3e38, .75, 0)), ['a', 'b'], letterbox_record(3, 2), .25, .45)
    assert result['detections'][0]['xyxy'] == [0., 0., 3., 2.]


def test_maximum_matching_and_empty_sets():
    from app.delivery_infer import match_detections
    detection = {'class_id': 0, 'score': .75, 'xyxy': [0., 0., 100., 100.]}
    assert match_detections([], [])
    assert not match_detections([], [detection])
    assert match_detections([detection], [dict(detection, score=.7509)])
    assert not match_detections([detection], [dict(detection, class_id=1)])


@pytest.mark.parametrize('color_type,channels', [(2, 3), (6, 4)])
def test_reject_encoded_16bit_rgb_rgba_before_pillow_downcast(tmp_path, color_type, channels):
    import zlib
    from app.delivery_infer import decode_image, ImageInferenceError
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name+data) & 0xffffffff)
    raw = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 16, color_type, 0, 0, 0))
    raw += chunk(b'IDAT', zlib.compress(b'\x00' + b'\xff\xff' * channels)) + chunk(b'IEND', b'')
    path = tmp_path / 'high-depth.png'; path.write_bytes(raw)
    with Image.open(path) as image: assert image.mode == ('RGB' if channels == 3 else 'RGBA')
    with pytest.raises(ImageInferenceError, match='IMAGE_MODE_UNSUPPORTED'): decode_image(path, 'png')


def test_error_codes_are_closed():
    from app.delivery_infer import ImageInferenceError
    with pytest.raises(ValueError, match='unknown image failure code'): ImageInferenceError('private untrusted text')
