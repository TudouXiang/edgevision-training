"""Explicit isolated runtime fault injection, never selectable by production code."""
from pathlib import Path
import json
import os
import shutil
import sys
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.run_files import atomic_json,read_json,run_directory
from app.training_assets import runtime_identity,digest_json,verify_asset
from app import training_runtime

case, source_root = sys.argv[1:]
root=Path(source_root)
os.environ['PLATFORM_DATA_ROOT']=str(root)
from app.database import transaction
with transaction() as connection:
    row=connection.execute("SELECT input_snapshot_json FROM jobs WHERE kind='train' AND status='succeeded' ORDER BY created_at DESC LIMIT 1").fetchone()
frozen=json.loads(row[0]); frozen['runtime_binding']=digest_json(runtime_identity())
job,run=str(uuid4()),str(uuid4())
directory=run_directory(job,run,create=True)
atomic_json(directory/'input.json',{'schema_version':1,'job_id':job,'run_id':run,'kind':'train','input':frozen})
original=training_runtime.initialize
if case=='unknown_class':
    training_runtime.prepare_environment(directory)
    shutil.copyfile(root/'models/base/yolo11n.pt',directory/'yolo11n.pt')
    other=directory/'unknown.pt'
    torch,_,_,_,_,fatal,_=original(directory,{directory/'yolo11n.pt',other})
    class UnknownData: pass
    torch.save({'unknown':UnknownData()},other)
    try:torch.load(other,weights_only=True)
    except training_runtime.TrainingPolicyError:pass
    else:raise AssertionError('Unknown checkpoint class was allowed')
    assert fatal==['CHECKPOINT_CLASS_REJECTED']
else:
    def injected_initialize(*args):
        values=list(original(*args)); Base=values[2]
        class FaultYOLO(Base):
            def add_callback(self,event,callback):
                def wrapped(trainer):
                    if event=='on_train_start' and case=='batch_drift':trainer.args.batch+=1
                    if event=='on_train_epoch_end' and case=='nonfinite':
                        next(trainer.ema.ema.parameters()).data.fill_(float('nan'))
                    callback(trainer)
                return super().add_callback(event,wrapped)
        values[2]=FaultYOLO
        return values
    training_runtime.initialize=injected_initialize
    from app.training_runner import run as execute
    assert execute(job,run)==68
    assert not (directory/'evidence.json').exists()
print('PASS '+case,flush=True)
