"""Acquire only the two pinned public Oxford archives; never decode or execute."""
import argparse
from hashlib import sha256
from pathlib import Path
import urllib.request

PINS={
    'images':(791918971,'67195c5e1c01f1ab5f9b6a5d22b8c27a580d896ece458917e61d459337fa318d'),
    'annotations':(19173078,'52425fb6de5c424942b7626b428656fcbd798db970a937df61750c0f1d358e91'),
}

def fetch(kind,destination):
    if kind not in PINS or destination.exists() or destination.is_symlink():raise ValueError('fixed download rejected')
    size,expected=PINS[kind]
    url=f'https://thor.robots.ox.ac.uk/~vgg/data/pets/{kind}.tar.gz'
    destination.parent.mkdir(parents=True,exist_ok=True)
    partial=destination.with_suffix('.part')
    h=sha256();count=0
    with urllib.request.urlopen(url,timeout=60) as response,partial.open('xb') as target:
        while chunk:=response.read(1024*1024):
            count+=len(chunk)
            if count>size:raise ValueError('fixed download rejected')
            h.update(chunk);target.write(chunk)
    if count!=size or h.hexdigest()!=expected:raise ValueError('fixed download rejected')
    # Exclusive final creation; do not overwrite a concurrently created path.
    import os
    os.link(partial,destination)
    partial.unlink()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True)
    options=parser.parse_args()
    for kind in PINS:fetch(kind,options.output_dir/f'{kind}.tar.gz')

if __name__=='__main__':main()
