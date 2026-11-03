#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, hashlib, json, os, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path
SCHEMA_VERSION='4.0'
TERMINAL={'COMPLETED','FAILED'}
EXECUTION_MODES={'interactive_segment','autonomous_file_batch'}
def content_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def atomic_write_json(path,payload):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=str(path.parent),text=True)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            json.dump(payload,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
def new_state(request_id,production_revision,plan=None,run_id=None):
    if not isinstance(request_id,str) or not request_id.strip(): raise ValueError('request_id is required')
    if not isinstance(production_revision,str) or len(production_revision)!=64: raise ValueError('production_revision must be a SHA-256 hex digest')
    mode=(plan or {}).get('execution_mode','autonomous_file_batch')
    if mode not in EXECUTION_MODES: raise ValueError('execution_mode must be interactive_segment or autonomous_file_batch')
    return {'schema_version':SCHEMA_VERSION,'run_id':run_id or 'run_'+uuid.uuid4().hex,'request_id':request_id,'execution_mode':mode,'status':'PLANNED','current_phase':'plan','current_cursor':{},'production_revision':production_revision,'plan_id':(plan or {}).get('plan_id'),'nodes':copy.deepcopy((plan or {}).get('nodes',[])),'artifacts':[],'retries':{},'blocked':[],'unresolved':[],'evidence':[],'continuation_required':False,'created_at':now(),'updated_at':now()}
def validate_state(state):
    if not isinstance(state,dict) or state.get('schema_version')!=SCHEMA_VERSION: raise ValueError('workflow state schema_version must be 4.0')
    for k in ('run_id','request_id','production_revision','current_phase','status'):
        if not isinstance(state.get(k),str) or not state[k].strip(): raise ValueError('workflow state missing '+k)
    if len(state['production_revision'])!=64: raise ValueError('workflow state production_revision must be SHA-256')
    if state['status'] not in {'PLANNED','RUNNING','PAUSED','COMPLETED','FAILED'}: raise ValueError('invalid workflow state status')
    if state.get('execution_mode','autonomous_file_batch') not in EXECUTION_MODES: raise ValueError('invalid execution_mode')
    for k in ('nodes','artifacts','blocked','unresolved','evidence'):
        if not isinstance(state.get(k),list): raise ValueError('workflow state '+k+' must be a list')
    if not isinstance(state.get('retries'),dict) or not isinstance(state.get('current_cursor'),dict): raise ValueError('workflow state retries/current_cursor must be objects')
    return state
def load_state(path): return validate_state(json.loads(Path(path).read_text(encoding='utf-8')))
def save_state(path,state): validate_state(state); state['updated_at']=now(); atomic_write_json(Path(path),state)
def transition(state,status,phase=None,cursor=None,reason=None):
    validate_state(state)
    if status not in {'PLANNED','RUNNING','PAUSED','COMPLETED','FAILED'}: raise ValueError('invalid transition status: '+status)
    if state['status'] in TERMINAL and status not in TERMINAL: raise ValueError('terminal workflow cannot resume without explicit resume')
    state['status']=status
    if phase is not None: state['current_phase']=phase
    if cursor is not None:
        if not isinstance(cursor,dict): raise ValueError('current_cursor must be an object')
        state['current_cursor']=copy.deepcopy(cursor)
    if reason:
        bucket=state['blocked'] if status=='PAUSED' else state['unresolved']
        if reason not in bucket: bucket.append(reason)
    state['updated_at']=now(); return state
def committed_artifact(state,artifact_id):
    return next((x for x in reversed(state.get('artifacts',[])) if x.get('artifact_id')==artifact_id and x.get('status')=='COMMITTED' and x.get('accepted') is True),None)
def completed_node_ids(state):
    return {x['node_id'] for x in state.get('artifacts',[]) if x.get('status')=='COMMITTED' and x.get('accepted') is True}
def latest_committed(state):
    xs=[x for x in state.get('artifacts',[]) if x.get('status')=='COMMITTED' and x.get('accepted') is True]; return xs[-1] if xs else None
def resume_from_last_commit(state):
    validate_state(state)
    if state['status'] not in {'PAUSED','FAILED'}: raise ValueError('resume requires PAUSED or FAILED workflow')
    for artifact in state['artifacts']:
        if artifact.get('status')=='COMMITTED' and artifact.get('accepted') is True:
            path=Path(artifact['path'])
            if not path.is_file() or file_hash(path)!=artifact['sha256']:
                raise ValueError('committed artifact missing or changed: '+str(path))
    for node in state['nodes']:
        if node.get('status')=='RUNNING': node['status']='PENDING'
    # A later partial owns the resume cursor; an older full artifact cannot erase it.
    if not state.get('continuation_required'):
        state['current_cursor']={}
    else:
        partial=next((a for a in reversed(state['artifacts']) if a.get('status')=='PARTIAL' and a.get('node_id') not in completed_node_ids(state)),None)
        if partial:
            path=Path(partial['path'])
            if not path.is_file() or file_hash(path)!=partial['sha256']:
                raise ValueError('partial artifact missing or changed: '+str(path))
            state['current_phase']=partial.get('phase',state['current_phase'])
            state['current_cursor']=copy.deepcopy(partial.get('next_cursor',{}))
    state['status']='RUNNING'; state['blocked']=[]; state['updated_at']=now(); return state
def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    a=s.add_parser('init'); a.add_argument('--request-id',required=True); a.add_argument('--production-revision',required=True); a.add_argument('--out',type=Path,required=True)
    b=s.add_parser('show'); b.add_argument('state',type=Path)
    c=s.add_parser('resume'); c.add_argument('state',type=Path); c.add_argument('--out',type=Path,required=True)
    x=p.parse_args()
    if x.cmd=='init': save_state(x.out,new_state(x.request_id,x.production_revision)); print(x.out)
    elif x.cmd=='show': print(json.dumps(load_state(x.state),ensure_ascii=False,indent=2))
    else: save_state(x.out,resume_from_last_commit(load_state(x.state))); print(x.out)
if __name__=='__main__': main()
