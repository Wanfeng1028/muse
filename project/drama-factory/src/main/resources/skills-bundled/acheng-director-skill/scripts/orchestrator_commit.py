#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, json, os, shutil, tempfile, re
from pathlib import Path
from workflow_state import atomic_write_json, committed_artifact, completed_node_ids, file_hash, load_state, save_state, transition, validate_state
from h3_contract import english_word_count
from h3_final_format import validate_h3_file

# This is the safety floor for nodes created by older plans. New plans write a
# segment-specific h3_min_words value derived from duration and complexity.
REF2VA_MIN_WORDS = 2000
REF2VA_FIELDS = (
    'subject_definitions', 'summary', 'retention_analysis',
    'detailed_description', 'overall_soundscape', 'non_diegetic_music',
)

def validate_model_artifact(source, node, production_revision=None):
    """Accept H3 only from final file bytes and a revision-bound input manifest."""
    phase = node.get('phase') if isinstance(node, dict) else None
    suffix = source.suffix.lower()
    is_h3 = source.name.lower().endswith((".h3", ".h3.txt"))
    if phase == 'model' and not is_h3:
        raise ValueError('model node requires a .h3/.h3.txt artifact and its validated delivery bundle')
    if phase == 'model' and node.get('id') == 'model' and not node.get('segment_id'):
        raise ValueError('segment discovery is unfinished; replan against the committed production with concrete Segments')
    if not is_h3 and suffix != ".txt":
        return
    text = source.read_text(encoding='utf-8')
    is_ref = "detailed_description:" in text and "subject_definitions:" in text
    is_base_h3 = "integrated_multimodal_description:" in text
    is_h3 = is_h3 or (phase == "model" and (is_ref or is_base_h3))
    if not is_h3 and not is_ref and "integrated_multimodal_description:" not in text:
        return
    if is_ref:
        from h3_final_format import _section
        words = english_word_count(_section(text, "detailed_description"))
        minimum = max(REF2VA_MIN_WORDS, int(node.get("h3_min_words", REF2VA_MIN_WORDS)))
        if words < minimum:
            raise ValueError(f"Ref2VA artifact detailed_description is {words} words; minimum is {minimum}. Submit partial with a cursor.")
    manifest = Path(str(source) + ".check.json")
    if not manifest.is_file():
        raise ValueError("H3 final-file check manifest missing: " + str(manifest))
    contract = json.loads(manifest.read_text(encoding="utf-8"))
    if production_revision is not None and contract.get("input_revision") != production_revision:
        raise ValueError("stale H3 final-file check manifest input_revision")
    if is_ref:
        contract["minimum_words"] = max(minimum, int(contract.get("minimum_words", 0)))
    receipt = validate_h3_file(source, contract, manifest.parent)
    # Every new complete H3 submission needs its card, including old-plan CLI
    # callers. Legacy already-COMMITTED records remain readable, not upgraded.
    if receipt:
        from h3_delivery import validate_segment_bundle
        delivery = Path(str(source) + '.delivery.json')
        if not delivery.is_file():
            raise ValueError('per-Segment upload card/binding manifest missing')
        entry = json.loads(delivery.read_text(encoding='utf-8'))
        if entry.get('input_revision') != production_revision or entry.get('file') != source.name:
            raise ValueError('stale or disconnected Segment delivery manifest')
        if node.get('segment_id') and entry.get('segment_id') != node['segment_id']:
            raise ValueError('H3 artifact belongs to a different Segment than the planned node')
        joint = validate_segment_bundle(source.parent, entry)
        if joint['joint_status'] != 'PASSED':
            raise ValueError('draft or unresolved binding cannot be committed as complete')
        receipt['joint_delivery'] = joint
    return receipt

def safe_id(value): return ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in str(value))
def node_id(node):
    if isinstance(node,str) and node: return node
    if isinstance(node,dict) and node.get('id'): return node['id']
    raise ValueError('node id is required')
def atomic_copy(source,target):
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): raise FileExistsError('artifact target already exists: '+str(target))
    fd,tmp=tempfile.mkstemp(prefix='.'+target.name+'.',dir=str(target.parent)); os.close(fd)
    try:
        shutil.copyfile(source,tmp)
        # Windows rejects fsync on a read-only descriptor; flush the staged
        # artifact through a read/write handle before the atomic replace.
        with open(tmp,'r+b') as f:
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,target)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
def schedule_next(state):
    validate_state(state)
    if state['status'] in {'PAUSED','FAILED','COMPLETED'}:
        return None
    done=completed_node_ids(state)
    for n in state['nodes']:
        if n.get('id') in done: continue
        if set(n.get('depends_on',[])) <= done: return n
    return None
def advance(state,nid,cursor=None):
    for n in state['nodes']:
        if n.get('id')==nid:
            n['status']='PENDING' if cursor is not None else 'COMPLETED'; break
    if cursor is not None:
        state['current_cursor']=copy.deepcopy(cursor); state['continuation_required']=True; state['status']='RUNNING'; return
    state['current_cursor']={}; state['continuation_required']=False
    nxt=schedule_next(state)
    if nxt:
        nxt['status']='RUNNING'; state['current_phase']=nxt.get('phase',nxt['id']); state['status']='RUNNING'
    else:
        if any(n['id'] not in completed_node_ids(state) for n in state['nodes']):
            raise ValueError('workflow has unfinished nodes but no satisfied dependency path')
        if state['unresolved']:
            state['status']='PAUSED'
            state['blocked'].append('unresolved workflow issues remain')
        else:
            state['current_phase']='complete'; state['status']='COMPLETED'
def commit_artifact(state,state_path,node,source,production_revision,*,artifact_root=None,artifact_id=None,status='complete',accepted=None,cursor=None,evidence=None,unresolved=None,target_path=None):
    validate_state(state); nid=node_id(node); source=Path(source)
    if production_revision!=state['production_revision']: raise ValueError('stale input revision: workflow was planned from a different production revision')
    node=next((n for n in state['nodes'] if n.get('id')==nid),None)
    if node is None: raise ValueError('unknown workflow node: '+nid)
    if not source.is_file(): raise FileNotFoundError('artifact source missing: '+str(source))
    if status not in {'complete','partial','blocked','failed'}: raise ValueError('artifact status must be complete, partial, blocked or failed')
    if accepted is None: accepted=status=='complete' and not unresolved
    if accepted and status!='complete': raise ValueError('partial/blocked/failed artifact cannot be accepted')
    if status=='complete' and (not accepted or unresolved):
        raise ValueError('complete artifact must be accepted with no unresolved items; submit partial or blocked')
    format_receipt = validate_model_artifact(source, node, production_revision) if status == "complete" else None
    digest=file_hash(source); aid=artifact_id or safe_id(nid)+':'+production_revision[:16]; existing=committed_artifact(state,aid)
    if format_receipt and format_receipt["sha256"] != digest:
        raise ValueError("H3 changed after final-file validation")
    if existing:
        if existing.get('sha256')==digest and existing.get('input_revision')==production_revision:
            if not Path(existing['path']).is_file() or file_hash(existing['path'])!=digest:
                raise ValueError('committed artifact missing or changed')
            if format_receipt and format_receipt.get('joint_delivery'):
                if existing.get('joint_delivery') != format_receipt['joint_delivery']:
                    raise ValueError('idempotent H3 content has a different binding/upload card')
                from h3_delivery import validate_segment_bundle
                saved_entry = json.loads(Path(str(existing['path']) + '.delivery.json').read_text(encoding='utf-8'))
                validate_segment_bundle(Path(existing['path']).parent, saved_entry)
            return {'status':'IDEMPOTENT','artifact':copy.deepcopy(existing),'state':state}
        raise ValueError('duplicate artifact_id with different content or input revision')
    if state['status'] in {'PAUSED','FAILED','COMPLETED'}:
        raise ValueError('workflow is not accepting new work; resume explicitly or create a new plan')
    if status=='complete' and not set(node.get('depends_on',[])) <= completed_node_ids(state):
        raise ValueError('node dependencies are not committed and accepted: '+nid)
    prior=next((a for a in reversed(state['artifacts']) if a.get('artifact_id')==aid and a.get('status')==status.upper()
                and a.get('sha256')==digest and a.get('input_revision')==production_revision),None)
    if prior and Path(prior['path']).is_file() and file_hash(prior['path'])==digest:
        return {'status':'IDEMPOTENT','artifact':copy.deepcopy(prior),'state':state}
    bundle = None
    if format_receipt and format_receipt.get('joint_delivery'):
        bundle = json.loads(Path(str(source) + '.delivery.json').read_text(encoding='utf-8'))
    if target_path is None:
        base = Path(artifact_root or Path(state_path).parent/'artifacts')
        target_path = base/(safe_id(nid)+'.'+digest[:16])/source.name if bundle else base/(safe_id(nid)+'.'+status+'.'+digest[:16]+source.suffix)
    target_path=Path(target_path)
    if bundle and target_path.name != source.name:
        raise ValueError('H3 bundle target must retain the source basename')
    if target_path.exists(): raise ValueError('artifact target exists; refusing silent adoption')
    if bundle:
        final_dir = target_path.parent
        if final_dir.exists():
            raise ValueError('H3 bundle target directory exists; choose a new artifact revision')
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        pending = Path(tempfile.mkdtemp(prefix='.pending-h3-', dir=final_dir.parent))
        atomic_copy(source, pending / source.name)
        names = [bundle[k] for k in ('upload_card', 'format_contract', 'format_receipt', 'delivery_manifest')]
        names += [ref['file'] for ref in bundle['references']]
        for name in dict.fromkeys(names):
            atomic_copy(source.parent / name, pending / name)
        from h3_delivery import validate_segment_bundle
        validate_segment_bundle(pending, bundle)
        os.rename(pending, final_dir)
    else:
        atomic_copy(source,target_path)
    if file_hash(target_path) != digest:
        raise ValueError("artifact changed during copy; not committed")
    evidence=list(evidence or []); unresolved=list(unresolved or [])
    if format_receipt:
        receipt_path = Path(str(target_path) + (".commit-acceptance.json" if bundle else ".acceptance.json"))
        atomic_write_json(receipt_path, format_receipt)
        evidence.append(str(receipt_path))
    resume_cursor={**(cursor or {}),'node_id':nid} if status=='partial' else copy.deepcopy(cursor or {})
    record={'artifact_id':aid,'node_id':nid,'phase':node.get('phase',nid),'path':str(target_path),'sha256':digest,'status':'COMMITTED' if status=='complete' else status.upper(),'accepted':bool(accepted),'input_revision':production_revision,'output_revision':digest,'next_cursor':resume_cursor,'evidence':evidence,'unresolved':unresolved,
            'validation_scope':'h3_joint_delivery' if format_receipt else 'artifact_integrity_only',
            'content_validation':'PASSED' if format_receipt else 'NOT_CHECKED_BY_COMMITTER'}
    if bundle:
        record['joint_delivery'] = format_receipt['joint_delivery']
    state['artifacts'].append(record)
    for x in evidence:
        if x not in state['evidence']: state['evidence'].append(x)
    artifact_issues={issue for a in state['artifacts'] for issue in a.get('unresolved',[])}
    manual_issues=[issue for issue in state['unresolved'] if issue not in artifact_issues]
    latest_by_node={a['node_id']:a for a in state['artifacts']}
    state['unresolved']=list(dict.fromkeys(manual_issues + [issue for a in latest_by_node.values() for issue in a.get('unresolved',[])]))
    if status in {'blocked','failed'}:
        state['status']='PAUSED' if status=='blocked' else 'FAILED'
        for x in (unresolved or ['node '+nid+' returned '+status]):
            if x not in state['blocked']: state['blocked'].append(x)
    elif status=='partial':
        state['current_phase']=node.get('phase',nid)
        advance(state,nid,resume_cursor)
    else:
        advance(state,nid)
        if state.get('execution_mode')=='interactive_segment' and node.get('phase')=='model' and state['status']!='COMPLETED':
            state['status']='PAUSED'
            state['blocked'].append('awaiting user continue after the completed Segment')
    save_state(state_path,state)
    return {'status':record['status'],'artifact':record,'state':state}
def pause(state,state_path,reason): save_state(state_path,transition(state,'PAUSED',reason=reason)); return state
def resume(state,state_path):
    from workflow_state import resume_from_last_commit
    state=resume_from_last_commit(state); save_state(state_path,state); return state
class OrchestratorAdapter:
    def plan(self,request,production):
        from orchestrator_plan import plan
        return plan(request,production)
    def execute(self,node,context): raise NotImplementedError('host must provide execute(node, context)')
    def validate(self,node,artifact): return {'status':'UNVERIFIED','node_id':node_id(node),'artifact':str(artifact)}
    def commit(self,node,artifact,context): return commit_artifact(context['state'],context['state_path'],node,artifact,context['production_revision'],**context.get('commit_options',{}))
    def schedule_next(self,state): return schedule_next(state)
    def pause(self,reason,state,state_path): return pause(state,state_path,reason)
    def resume(self,state,state_path): return resume(state,state_path)
def main():
    p=argparse.ArgumentParser(); p.add_argument('state',type=Path); p.add_argument('node_id'); p.add_argument('artifact',type=Path); p.add_argument('--production-revision',required=True); p.add_argument('--artifact-root',type=Path); p.add_argument('--status',choices=('complete','partial','blocked','failed'),default='complete'); p.add_argument('--cursor',type=json.loads); p.add_argument('--evidence',action='append',default=[]); p.add_argument('--unresolved',action='append',default=[])
    a=p.parse_args(); state=load_state(a.state); node=next((n for n in state['nodes'] if n.get('id')==a.node_id),{'id':a.node_id,'phase':a.node_id}); out=commit_artifact(state,a.state,node,a.artifact,a.production_revision,artifact_root=a.artifact_root,status=a.status,cursor=a.cursor,evidence=a.evidence,unresolved=a.unresolved); print(json.dumps({'status':out['status'],'workflow_status':out['state']['status'],'artifact':out['artifact']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
