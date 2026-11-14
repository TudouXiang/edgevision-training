import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('real_cpu_dataset', ROOT/'scripts/real_cpu_dataset.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def archive(path, entries):
    with tarfile.open(path, 'w:gz') as out:
        for name, data in entries:
            member=tarfile.TarInfo(name);member.size=len(data)
            out.addfile(member,io.BytesIO(data))


def fixture(tmp_path, monkeypatch, bad=None):
    rows=[];xmls=[];images=[]
    for i in range(100):
        name=f'pet_{i:03d}';species=1 if i<50 else 2
        rows.append(f'{name} 1 {species} 1')
        image=Image.new('RGB',(20,16),(i*2,i,255-i));stream=io.BytesIO();image.save(stream,format='JPEG',quality=100)
        images.append((f'images/{name}.jpg',stream.getvalue()))
        xmin=0 if bad=='box' and i==0 else 1
        width=21 if bad=='size' and i==0 else 20
        xml=f'<annotation><filename>{name}.jpg</filename><size><width>{width}</width><height>16</height></size><object><name>{"cat" if species==1 else "dog"}</name><bndbox><xmin>{xmin}</xmin><ymin>1</ymin><xmax>20</xmax><ymax>16</ymax></bndbox></object></annotation>'
        if bad=='entity' and i==0:xml='<!DOCTYPE annotation [<!ENTITY x "secret">]>'+xml
        xmls.append((f'annotations/xmls/{name}.xml',xml.encode()))
    if bad=='duplicate-image':images[1]=(images[1][0],images[0][1])
    if bad=='traversal':images.append(('../outside',b'x'))
    if bad=='duplicate-member':images.append(images[0])
    a=tmp_path/'annotations.tar.gz';b=tmp_path/'images.tar.gz'
    archive(a,[('annotations/trainval.txt','\n'.join(rows).encode()),*xmls]);archive(b,images)
    monkeypatch.setattr(module,'SOURCE_PINS',{'images':(b.stat().st_size,hashlib.sha256(b.read_bytes()).hexdigest()),'annotations':(a.stat().st_size,hashlib.sha256(a.read_bytes()).hexdigest())})
    return b,a


def test_freezes_disjoint_deterministic_actual_bytes(tmp_path,monkeypatch):
    b,a=fixture(tmp_path,monkeypatch)
    first=module.prepare_subset(b,a,tmp_path/'one');second=module.prepare_subset(b,a,tmp_path/'two')
    assert first==second
    assert first['counts']=={'train':60,'val':20,'test':20}
    manifest=json.loads((tmp_path/'one/manifest.json').read_text())
    assert len({x['name'] for x in manifest['samples']})==100
    for split, count in [('train',30),('val',10),('test',10)]:
        for class_id in (0,1):
            assert sum(x['split']==split and x['class_id']==class_id for x in manifest['samples'])==count
    assert len({x['image_sha256'] for x in manifest['samples']})==100
    with zipfile.ZipFile(tmp_path/'one/dataset.zip') as z:
        assert len(z.namelist())==201
        labels=[z.read(n).decode() for n in z.namelist() if n.endswith('.txt')]
        assert all(x.split()[1:]==['0.5','0.5','1','1'] for x in labels)
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'one')


@pytest.mark.parametrize('bad',['box','size','entity','duplicate-image','traversal','duplicate-member'])
def test_rejects_unsafe_or_inconsistent_inputs(tmp_path,monkeypatch,bad):
    b,a=fixture(tmp_path,monkeypatch,bad)
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_pin_mismatch_rejected_before_output(tmp_path,monkeypatch):
    b,a=fixture(tmp_path,monkeypatch);b.write_bytes(b.read_bytes()+b'x')
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_source_path_replacement_after_pin_cannot_change_snapshot(tmp_path,monkeypatch):
    b,a=fixture(tmp_path,monkeypatch)
    expected=module.prepare_subset(b,a,tmp_path/'baseline')
    original=module.members;changed=False
    def replace_then_read(source,wanted):
        nonlocal changed
        if not changed:
            b.unlink();b.write_bytes(b'not the pinned image archive');changed=True
        return original(source,wanted)
    monkeypatch.setattr(module,'members',replace_then_read)
    assert module.prepare_subset(b,a,tmp_path/'snapshot')==expected


def repin(monkeypatch,images,annotations):
    monkeypatch.setattr(module,'SOURCE_PINS',{k:(p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()) for k,p in [('images',images),('annotations',annotations)]})


@pytest.mark.parametrize('kind',['symlink','hardlink','truncated','oversize'])
def test_archive_types_and_bounds_fail_closed(tmp_path,monkeypatch,kind):
    b,a=fixture(tmp_path,monkeypatch)
    if kind=='truncated':b.write_bytes(b.read_bytes()[:100])
    else:
        with tarfile.open(b) as src:entries=[(m.name,src.extractfile(m).read()) for m in src if m.isfile()]
        with tarfile.open(b,'w:gz') as out:
            for name,data in entries:
                m=tarfile.TarInfo(name);m.size=len(data);out.addfile(m,io.BytesIO(data))
            m=tarfile.TarInfo('images/unsafe')
            if kind=='oversize':m.size=16*1024**2+1;out.addfile(m,io.BytesIO(b'\0'*m.size))
            else:m.type=tarfile.SYMTYPE if kind=='symlink' else tarfile.LNKTYPE;m.linkname='../outside';out.addfile(m)
    repin(monkeypatch,b,a)
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'out')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('kind',['orientation','same-pixels'])
def test_image_semantics_are_not_silently_transformed(tmp_path,monkeypatch,kind):
    b,a=fixture(tmp_path,monkeypatch)
    with tarfile.open(b) as src:entries=[(m.name,src.extractfile(m).read()) for m in src if m.isfile()]
    if kind=='same-pixels':entries[1]=(entries[1][0],entries[0][1]+b'ignored trailing comment')
    else:
        with Image.open(io.BytesIO(entries[0][1])) as image:
            exif=image.getexif();exif[274]=6;out=io.BytesIO();image.save(out,format='JPEG',exif=exif)
            entries[0]=(entries[0][0],out.getvalue())
    archive(b,entries);repin(monkeypatch,b,a)
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_partial_output_is_not_success_and_never_overwritten(tmp_path,monkeypatch):
    b,a=fixture(tmp_path,monkeypatch)
    def fail(*args,**kwargs):raise OSError('simulated disk full')
    monkeypatch.setattr(zipfile.ZipFile,'writestr',fail)
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'out')
    assert (tmp_path/'out').is_dir()
    assert not (tmp_path/'out/receipt.json').exists()
    with pytest.raises(ValueError):module.prepare_subset(b,a,tmp_path/'out')


@pytest.mark.parametrize(('coordinates','expected'),[((2,3,5,7),(.15,.28125,.2,.3125)),((1,1,1,1),(.025,.03125,.05,.0625))])
def test_voc_inclusive_geometry(coordinates,expected):
    box=''.join(f'<{k}>{v}</{k}>' for k,v in zip(('xmin','ymin','xmax','ymax'),coordinates))
    raw=f'<annotation><filename>pet.jpg</filename><size><width>20</width><height>16</height></size><object><name>cat</name><bndbox>{box}</bndbox></object></annotation>'.encode()
    assert module.annotation(raw,'pet',1)[2]==pytest.approx(expected)
