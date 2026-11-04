"""Explicit operator download of one fixed official asset; no custom URL or model."""
import argparse
from hashlib import sha256
from pathlib import Path
import urllib.request
URL='https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt'
SIZE=5613764
SHA='0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
if args.output.exists():raise SystemExit('Destination already exists; verify it before reusing')
partial=args.output.with_suffix('.part')
digest=sha256();count=0
with urllib.request.urlopen(URL,timeout=60) as response,partial.open('xb') as target:
    while chunk:=response.read(1024*1024):
        count+=len(chunk)
        if count>SIZE:raise RuntimeError('Fixed asset exceeds expected size')
        digest.update(chunk);target.write(chunk)
if count!=SIZE or digest.hexdigest()!=SHA:raise RuntimeError('Fixed asset fingerprint mismatch; partial retained for inspection')
partial.rename(args.output)
print('Fixed official YOLO11n asset size and SHA256 verified. No publisher signature is claimed.')
