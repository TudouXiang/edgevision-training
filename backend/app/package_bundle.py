"""Deterministic, fixed-member source package; never executes a model."""
from hashlib import sha256
import io
from pathlib import Path
import stat
import struct
import tempfile
import zipfile
from . import package_cli as portable
from .package_contract import FrozenPackage
from .package_inputs import copy_input, verify_input

ROOT = Path(__file__).resolve().parents[2]
LOCK_NAMES = frozenset(('pillow','numpy','onnx','onnxruntime','protobuf','ml_dtypes','flatbuffers','packaging','typing_extensions'))


def entry(name, content):
    return {'path': name, 'size_bytes': len(content), 'sha256': sha256(content).hexdigest()}


def synthetic_example():
    """Fixed PNG encoded with stdlib only: identity checks never import Pillow."""
    import zlib
    width, height = 257, 193
    rows = b''.join(b'\x00' + bytes(value for x in range(width)
        for value in ((3*x+y)%256, (x+5*y)%256, (7*x+11*y)%256)) for y in range(height))
    def chunk(kind, content):
        body = kind + content
        return struct.pack('>I', len(content)) + body + struct.pack('>I', zlib.crc32(body))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B',width,height,8,2,0,0,0)) + chunk(b'IDAT', zlib.compress(rows,9)) + chunk(b'IEND',b'')


def template_files():
    lines = (ROOT/'backend/requirements-delivery-linux-cpu.lock').read_text().splitlines()
    selected = (ROOT/'backend/requirements-package-linux-cpu.lock').read_text().splitlines()
    expected = {line for line in lines if line.split('==')[0].lower() in LOCK_NAMES}
    if len(selected) != len(LOCK_NAMES) or set(selected) != expected: portable.fail()
    return {
        'run.py': Path(__file__).with_name('package_cli.py').read_bytes(),
        'delivery_infer.py': Path(__file__).with_name('delivery_infer.py').read_bytes(),
        'requirements.lock': ('\n'.join(selected)+'\n').encode(),
        'example.png': synthetic_example(),
        'LICENSE': (ROOT/'LICENSE').read_bytes(),
        'README.md': b'# EdgeVision independent ONNX source package\n\nTarget: Linux x86_64, glibc >= 2.28, CPython 3.12, CPU.\nThis archive contains no Python interpreter, wheels, Torch, or platform server.\nInstall the exact hashed dependencies in an isolated virtual environment:\n\n    python -m pip install --require-hashes --only-binary=:all: -r requirements.lock\n\nInitial installation requires internet access or a separately prepared matching wheelhouse.\nFor offline installation add --no-index --find-links=/path/to/wheelhouse.\nArchive integrity is not proof that inference ran for this particular model.\nRun once per fresh process with Python isolated mode:\n\n    python -I run.py --image example.png --format png --output results\n\nThe output directory must not already exist. Outputs: result.json and preview.png.\nPreview is a sanitized source image; result.json contains detections.\nOn an output-write failure, the partial directory is retained. Do not treat it as successful.\nInspect/remove it yourself before reusing that path; the CLI never deletes existing files.\n',
        'LICENSE_SCOPE.md': (ROOT/'LICENSE_SCOPE.md').read_bytes() + b'\n## Independent package supplement\n\nThe original repository scope above is preserved, including AGPL-3.0-only.\nRepository paths mentioned there do not imply those assets are bundled here.\nNo dependency wheels, original training data or legacy prototype are included.\nThird-party dependencies and model inputs retain their separate rights.\n',
        'THIRD_PARTY_NOTICES.md': ('# Dependency notice\n\nNo third-party wheel binaries are bundled. requirements.lock pins the following\nseparately installed packages; obtain their applicable license/notice files from\nthe distributions when redistributing them. This is not a complete binary license audit.\n\n'+'\n'.join(line.split(' --hash')[0] for line in selected)+'\n').encode(),
        'MODEL_NOTICE.md': b'# Model notice\n\nThis model derives from the platform approved Ultralytics YOLO11n base.\nUpstream source: https://github.com/ultralytics/ultralytics\nBase weights: https://github.com/ultralytics/assets/releases/tag/v8.3.0\nUpstream AGPL-3.0 terms apply; no commercial license is granted here.\nThe owner remains responsible for training-data and redistribution rights.\n',
    }


def identity(files):
    entries = [entry(name, files[name]) for name in sorted(files)]
    return {'protocol': portable.PROTOCOL, 'image_protocol': 'detection-image-v1', 'target': portable.TARGET,
            'template_sha256': portable.digest(entries), 'core_sha256': sha256(files['delivery_infer.py']).hexdigest(),
            'lock_sha256': sha256(files['requirements.lock']).hexdigest()}


def template_identity():
    return identity(template_files())


def source_manifest(frozen):
    model = frozen['model']
    return {'onnx_artifact_id': model['source_artifact_id'], 'export_job_id': model['source_job_id'],
            'parent_artifact_id': model['export_input']['source_artifact_id'], 'sha256': model['source_sha256'],
            'size_bytes': model['source_size_bytes'], 'metadata_sha256': model['source_metadata_sha256']}


def build_bundle(value, directory):
    frozen = verify_input(value)
    files = template_files()
    if identity(files) != frozen['template']: portable.fail()
    path = directory/'package.zip'
    # Exclusive destination creation is intentional: preserve any preexisting artifact.
    with path.open('xb') as sink:
        try:
            with tempfile.TemporaryDirectory(prefix='package-', dir=directory) as temporary:
                model = copy_input(frozen, Path(temporary))
                _, _, files['model.onnx'] = portable.verified_file(model, portable.MAX_MODEL,
                    {'size_bytes': frozen['model']['source_size_bytes'], 'sha256': frozen['model']['source_sha256']}, capture=True)
                manifest = {'schema_version': 1, 'protocol': portable.PROTOCOL, 'image_protocol': 'detection-image-v1',
                    'target': portable.TARGET, 'classes': frozen['model']['export_input']['training_input']['classes'],
                    'source': source_manifest(frozen),
                    'template': {k: frozen['template'][k] for k in ('template_sha256','core_sha256','lock_sha256')},
                    'members': [entry(name, files[name]) for name in sorted(files)]}
                files['manifest.json'] = portable.canonical(portable.validate_manifest(manifest))
                with zipfile.ZipFile(sink, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
                    for name in sorted(files):
                        info = zipfile.ZipInfo(name, (1980,1,1,0,0,0)); info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o644) << 16
                        archive.writestr(info, files[name])
            verify_input(frozen)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    return verify_bundle(path, frozen)


def verify_bundle(path, value):
    try:
        return _verify_bundle(path, value)
    except (zipfile.BadZipFile, struct.error, UnicodeError) as exc:
        raise ValueError("PACKAGE_BUNDLE_INVALID") from exc


def _verify_bundle(path, value):
    frozen = FrozenPackage.model_validate(value).model_dump(mode='json')
    # Bound and fingerprint from one descriptor, then parse that immutable byte snapshot.
    size, fingerprint, raw = portable.verified_file(path, portable.MAX_TOTAL, capture=True)
    if len(raw) < 22: portable.fail()
    end = struct.unpack('<4s4H2LH', raw[-22:])
    signature, disk, cd_disk, count_disk, count, cd_size, cd_offset, comment = end
    if signature != b'PK\x05\x06' or disk or cd_disk or count_disk != 11 or count != 11 or comment or cd_size > 8192 or cd_offset+cd_size != size-22:
        portable.fail()
    members = {}; offset = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if [info.filename for info in infos] != sorted([*portable.MEMBERS,'manifest.json']): portable.fail()
        for info in infos:
            limit = portable.MAX_MODEL if info.filename == 'model.onnx' else portable.MAX_SMALL
            if (info.header_offset != offset or info.compress_type != 0 or info.flag_bits or info.extra or info.comment
                or info.file_size != info.compress_size or not 0 < info.file_size <= limit or info.create_system != 3
                or info.external_attr >> 16 != stat.S_IFREG | 0o644 or info.date_time != (1980,1,1,0,0,0)):
                portable.fail()
            header = struct.unpack('<4s5H3L2H', raw[offset:offset+30])
            sig, version, flags, method, tm, date, crc, compressed, expanded, name_size, extra_size = header
            name = info.filename.encode('ascii')
            if (sig != b'PK\x03\x04' or version != 20 or flags or method or tm or date != 33 or extra_size
                or crc != info.CRC or compressed != info.file_size or expanded != info.file_size
                or name_size != len(name) or raw[offset+30:offset+30+name_size] != name): portable.fail()
            offset += 30+name_size+info.file_size
            if offset > cd_offset: portable.fail()
            members[info.filename] = archive.read(info)
    if offset != cd_offset: portable.fail()
    manifest_raw = members.pop('manifest.json')
    manifest = portable.parse_manifest(manifest_raw)
    if manifest['members'] != [entry(name,members[name]) for name in sorted(members)]: portable.fail()
    if manifest['source'] != source_manifest(frozen): portable.fail()
    if manifest['classes'] != frozen['model']['export_input']['training_input']['classes']: portable.fail()
    if manifest['template'] != {k: frozen['template'][k] for k in manifest['template']}: portable.fail()
    return {'manifest': manifest, 'size_bytes': size, 'sha256': fingerprint,
            'manifest_sha256': sha256(manifest_raw).hexdigest(), 'manifest_size_bytes': len(manifest_raw)}
