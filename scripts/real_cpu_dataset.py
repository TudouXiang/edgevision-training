"""Fixed public Oxford subset; no network, model imports or arbitrary extraction.

Actual images/manifest remain private. Public receipts carry only counts/hashes.
VOC inclusive 1-based corners become continuous [xmin-1, ymin-1, xmax, ymax].
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import io
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
import re
import tarfile
import xml.etree.ElementTree as ET
import zipfile

SOURCE_PINS = {
    'images': (791918971, '67195c5e1c01f1ab5f9b6a5d22b8c27a580d896ece458917e61d459337fa318d'),
    'annotations': (19173078, '52425fb6de5c424942b7626b428656fcbd798db970a937df61750c0f1d358e91'),
}
PLAN = 'edgevision-real-cpu-v1'
NAME = re.compile(r'[A-Za-z][A-Za-z_0-9]{0,95}')
SPLITS = (('train', 30), ('val', 10), ('test', 10))


def require(value):
    if not value:
        raise ValueError('fixed real dataset validation failed')


def digest(path: Path) -> str:
    h=sha256()
    with path.open('rb') as source:
        while block:=source.read(1024*1024):h.update(block)
    return h.hexdigest()


@contextmanager
def pinned_archive(path: Path, kind: str):
    size,expected=SOURCE_PINS[kind]
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as source, tempfile.TemporaryFile('w+b') as snapshot:
        info=os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size==size)
        h=sha256();count=0
        while block:=source.read(1024*1024):
            count+=len(block);require(count<=size);h.update(block);snapshot.write(block)
        require(count==size and h.hexdigest()==expected)
        snapshot.seek(0)
        yield snapshot


def members(source, wanted) -> dict[str, bytes]:
    result={};seen=set();total=0
    with tarfile.open(fileobj=source,mode='r|gz') as archive:
        for count, item in enumerate(archive,1):
            name=item.name;parts=PurePosixPath(name).parts
            require(count<=20000 and name not in seen and not name.startswith('/')
                    and '\\' not in name and parts and '..' not in parts
                    and (item.isfile() or item.isdir()) and not item.issparse())
            seen.add(name);total+=item.size
            require(0<=item.size<=16*1024**2 and total<=2*1024**3)
            if item.isfile() and wanted(name):
                raw=archive.extractfile(item).read(item.size+1)
                require(len(raw)==item.size);result[name]=raw
    return result


def annotation(raw: bytes, name: str, species: int):
    require(len(raw)<=65536 and b'<!' not in raw)
    try:
        root=ET.fromstring(raw)
        require(root.tag=='annotation' and root.findtext('filename')==name+'.jpg')
        width=int(root.findtext('size/width'));height=int(root.findtext('size/height'))
        require(width>0 and height>0 and width*height<=30_000_000)
        objects=root.findall('object');require(len(objects)==1)
        obj=objects[0];require(obj.findtext('name')==('cat' if species==1 else 'dog'))
        values=[int(obj.findtext('bndbox/'+key)) for key in ('xmin','ymin','xmax','ymax')]
        x0,y0,x1,y1=values
        require(1<=x0<=x1<=width and 1<=y0<=y1<=height)
        # Full-image inclusive box maps to exact center .5 and extent 1.
        box=((x0-1+x1)/(2*width),(y0-1+y1)/(2*height),(x1-x0+1)/width,(y1-y0+1)/height)
        return width,height,box
    except (ET.ParseError,TypeError,ValueError) as exc:
        raise ValueError('fixed annotation rejected') from exc


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode()


def prepare_subset(images_archive: Path, annotations_archive: Path, destination: Path) -> dict:
    require(not destination.exists() and not destination.is_symlink())
    try:
        with pinned_archive(images_archive,'images') as images_source, pinned_archive(annotations_archive,'annotations') as annotation_source:
            return prepare_pinned(images_source,annotation_source,destination)
    except (OSError, tarfile.TarError, EOFError) as exc:raise ValueError('fixed archive rejected') from exc


def prepare_pinned(images_source,annotation_source,destination):
    annotations=members(annotation_source,lambda n:n=='annotations/trainval.txt' or n.startswith('annotations/xmls/'))
    raw_list=annotations.get('annotations/trainval.txt',b'');require(0<len(raw_list)<=1024**2)
    pools={1:[],2:[]};seen=set();excluded=0
    for line in raw_list.decode('ascii').splitlines():
        if not line or line.startswith('#'):continue
        fields=line.split();require(len(fields)==4 and NAME.fullmatch(fields[0]))
        name=fields[0];require(name not in seen);seen.add(name)
        require(fields[2] in ('1','2'));species=int(fields[2])
        raw=annotations.get(f'annotations/xmls/{name}.xml')
        if raw is None:excluded+=1;continue
        # Entity declarations never qualify for an exclusion/resampling path.
        require(b'<!' not in raw)
        try:width,height,box=annotation(raw,name,species)
        except ValueError:excluded+=1;continue
        pools[species].append((name,species,width,height,box,raw))
    chosen=[]
    for species,pool in pools.items():
        pool.sort(key=lambda row:sha256((PLAN+':'+row[0]).encode()).hexdigest())
        require(len(pool)>=50);offset=0
        for split,count in SPLITS:
            chosen.extend((split,*row) for row in pool[offset:offset+count]);offset+=count
    names={f'images/{row[1]}.jpg' for row in chosen}
    images=members(images_source,lambda n:n in names);require(set(images)==names)
    from PIL import Image
    samples=[];files={};seen_bytes=set();seen_pixels=set()
    for split,name,species,width,height,box,xml in chosen:
        raw=images[f'images/{name}.jpg'];image_hash=sha256(raw).hexdigest()
        require(image_hash not in seen_bytes);seen_bytes.add(image_hash)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                require(image.format=='JPEG' and image.size==(width,height) and image.mode=='RGB'
                        and image.getexif().get(274,1)==1)
                image.load();pixel_hash=sha256(f'{width}x{height}:'.encode()+image.tobytes()).hexdigest()
        except (OSError,Image.DecompressionBombError) as exc:raise ValueError('fixed image rejected') from exc
        require(pixel_hash not in seen_pixels);seen_pixels.add(pixel_hash)
        label=(str(species-1)+' '+' '.join(format(v,'.12g') for v in box)+'\n').encode()
        files[f'images/{split}/{name}.jpg']=raw;files[f'labels/{split}/{name}.txt']=label
        samples.append({'name':name,'split':split,'class_id':species-1,'width':width,'height':height,
                        'image_sha256':image_hash,'pixel_sha256':pixel_hash,'xml_sha256':sha256(xml).hexdigest(),
                        'label_sha256':sha256(label).hexdigest()})
    files['data.yaml']=b'train: images/train\nval: images/val\ntest: images/test\nnames:\n  0: cat_head\n  1: dog_head\n'
    manifest={'schema_version':1,'plan':PLAN,'source_sha256':{k:v[1] for k,v in SOURCE_PINS.items()},
              'voc_corners':'one_based_inclusive','excluded_missing_or_invalid_xml':excluded,
              'counts':{'train':60,'val':20,'test':20},'samples':samples}
    encoded=canonical(manifest)
    destination.mkdir(mode=0o700)
    (destination/'manifest.json').write_bytes(encoded)
    with zipfile.ZipFile(destination/'dataset.zip','x',compression=zipfile.ZIP_STORED) as archive:
        for name,raw in sorted(files.items()):
            item=zipfile.ZipInfo(name,(1980,1,1,0,0,0));item.external_attr=0o100644<<16
            archive.writestr(item,raw)
    receipt={'schema_version':1,'plan':PLAN,'counts':manifest['counts'],'manifest_sha256':sha256(encoded).hexdigest(),
             'dataset_sha256':digest(destination/'dataset.zip')}
    (destination/'receipt.json').write_bytes(canonical(receipt))
    return receipt
