"""Three-file package verification and witnessed intent/rename/CAS publication."""
import json
import os
import stat
from uuid import uuid4
from .config import data_root
from .database import transaction
from .dataset_storage import safe_directory
from .job_service import canonical, transition
from .run_files import read_json, run_directory, relative_file
from .security import timestamp
from .package_contract import PackageEvidence,PackageValidation,MAX_PACKAGE_BYTES,MAX_PACKAGE_JSON_BYTES
from .package_inputs import verify_input,source_binding
from .inference_files import verified_file
from .package_assets import runtime_identity,validated_template
from .package_runner import check_runtime
from .package_bundle import verify_bundle
from .package_service import provenance
from .training_assets import digest_json
from .schemas import PackageArtifactMetadata


def bundle_documents(bundle,entries,frozen):
    limits={'package.zip':MAX_PACKAGE_BYTES,'metadata.json':MAX_PACKAGE_JSON_BYTES,'validation.json':MAX_PACKAGE_JSON_BYTES}
    if not stat.S_ISDIR(bundle.lstat().st_mode) or set(entries)!=set(limits):raise ValueError('package bundle invalid')
    if {item.name for item in bundle.iterdir()}!=set(limits):raise ValueError('package members changed')
    documents={}
    for name,limit in limits.items():
        entry=entries[name]
        if set(entry)!={'path','size_bytes','sha256'} or entry['path']!=name:raise ValueError('package member invalid')
        with verified_file(relative_file(bundle,name),entry['size_bytes'],entry['sha256'],limit) as source:
            if name.endswith('.json'):
                content=source.read(entry['size_bytes']+1)
                from hashlib import sha256
                if len(content)!=entry['size_bytes'] or sha256(content).hexdigest()!=entry['sha256']:raise ValueError('document changed')
                documents[name]=json.loads(content)
    metadata=PackageArtifactMetadata.model_validate(documents['metadata.json']).model_dump(mode='json')
    validation=PackageValidation.model_validate(documents['validation.json']).model_dump(mode='json')
    archive=verify_bundle(relative_file(bundle,'package.zip'),frozen)
    if validation['metadata']!=metadata or validation['manifest']!=archive['manifest']:raise ValueError('package documents mismatch')
    if (archive['size_bytes'],archive['sha256'])!=(entries['package.zip']['size_bytes'],entries['package.zip']['sha256']):raise ValueError('archive changed during verification')
    if (metadata['package_size_bytes'],metadata['package_sha256'],metadata['manifest_size_bytes'],metadata['manifest_sha256'])!=(archive['size_bytes'],archive['sha256'],archive['manifest_size_bytes'],archive['manifest_sha256']):raise ValueError('package fingerprint mismatch')
    if metadata['template']!=frozen['template'] or metadata['template_validation_sha256']!=frozen['template_validation_sha256']:raise ValueError('package template validation mismatch')
    return metadata,validation


def verify(job,bundle=None,connection=None):
    directory=run_directory(job['id'],job['run_id'])
    frozen=verify_input(json.loads(job['input_snapshot_json']),connection)
    if job['kind']!='package' or frozen['project_id']!=job['project_id'] or frozen['params']!=json.loads(job['payload_json']) or frozen['code_version']!=job['code_version']:raise ValueError('package job changed')
    check_runtime(frozen,runtime_identity(),validated_template())
    if read_json(directory/'input.json')!={'schema_version':1,'job_id':job['id'],'run_id':job['run_id'],'kind':'package','input':frozen}:raise ValueError('package managed input changed')
    evidence=PackageEvidence.model_validate(read_json(directory/'evidence.json',MAX_PACKAGE_JSON_BYTES))
    if (str(evidence.job_id),str(evidence.run_id),evidence.input_sha256)!=(job['id'],job['run_id'],digest_json(frozen)):raise ValueError('package evidence changed')
    entries={entry.path:entry.model_dump(mode='json') for entry in evidence.outputs}
    metadata,validation=bundle_documents(bundle or directory/'bundle',entries,frozen)
    if metadata['provenance']!=provenance(frozen,job['id'],job['run_id']):raise ValueError('package provenance changed')
    return frozen,metadata,entries,validation


def publish(job):
    from .worker import drain_receipt
    receipt=drain_receipt(job)
    if not receipt or receipt['reason']!='completed' or receipt['exit_code']!=0 or not receipt['logs_complete'] or not receipt['started']:raise ValueError('successful tree exit unconfirmed')
    frozen,metadata,entries,validation=verify(job)
    key=f"packages/{job['id']}/{job['run_id']}"
    intent={'schema_version':1,'run_id':job['run_id'],'bundle_key':key,'outputs':entries}
    with transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("UPDATE jobs SET publication_json=? WHERE id=? AND run_id=? AND status='running'",(canonical(intent),job['id'],job['run_id'])).rowcount!=1:return False
    parent=safe_directory(data_root(),'packages',job['id']);destination=parent/job['run_id']
    if destination.exists():raise ValueError('immutable package destination exists')
    os.rename(run_directory(job['id'],job['run_id'])/'bundle',destination)
    if os.name!='nt':
        descriptor=os.open(parent,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    with transaction() as connection:
        connection.execute('BEGIN')
        frozen,metadata,entries,validation=verify(job,destination,connection)
        binding=source_binding(connection,frozen)
    with transaction() as connection:
        connection.execute('BEGIN IMMEDIATE')
        current=connection.execute('SELECT * FROM jobs WHERE id=? AND run_id=?',(job['id'],job['run_id'])).fetchone()
        if not current or current['status']!='running':return False
        if any(current[k]!=job[k] for k in ('project_id','kind','run_id','input_snapshot_json','payload_json','code_version')) or current['publication_json']!=canonical(intent):raise ValueError('package job changed before publication')
        if source_binding(connection,frozen)!=binding:raise ValueError('source changed before publication')
        entry,now=entries['package.zip'],timestamp()
        connection.execute('INSERT INTO artifacts(id,project_id,job_id,parent_id,kind,format,storage_key,sha256,size_bytes,validation_status,metadata_json,created_at,validated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (str(uuid4()),job['project_id'],job['id'],frozen['model']['source_artifact_id'],'deployment_zip','zip',key+'/package.zip',entry['sha256'],entry['size_bytes'],'passed',canonical(metadata),now,now))
        connection.execute('UPDATE jobs SET environment_json=? WHERE id=?',(canonical({'template':frozen['template'],'standalone_execution':'not_run_for_this_artifact'}),job['id']))
        if not transition(connection,job['id'],'running','succeeded',run_id=job['run_id'],process_exited=True,evidence_verified=True):raise RuntimeError('package publication CAS lost')
    return True
