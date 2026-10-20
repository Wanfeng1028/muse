#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from contract_core import content_hash
from workflow_state import atomic_write_json,new_state,save_state
from h3_contract import detail_policy
from animation_term_catalog import select_terms
ROOT=Path(__file__).resolve().parents[1]
EXECUTION_MODE_ALIASES={
    '1':'autonomous_file_batch','method1':'autonomous_file_batch','autonomous':'autonomous_file_batch',
    'file_batch':'autonomous_file_batch','autonomous_file_batch':'autonomous_file_batch',
    '2':'interactive_segment','method2':'interactive_segment','interactive':'interactive_segment',
    'interactive_segment':'interactive_segment','segment_by_segment':'interactive_segment',
}
def execution_mode(request):
    raw=request.get('execution_mode',request.get('delivery_mode','autonomous_file_batch'))
    key=norm(raw)
    mode=EXECUTION_MODE_ALIASES.get(key)
    if mode is None: raise ValueError('execution_mode must be interactive_segment or autonomous_file_batch')
    return mode
def norm(v): return re.sub(r'[^a-z0-9_-]+','-',str(v or '').strip().lower()).strip('-')
def feature_set(req,prod):
    vals=req.get('features',[]); vals=[vals] if isinstance(vals,str) else vals
    out={norm(v) for v in vals}
    for shot in prod.get('shots',[]):
        f=shot.get('features',{})
        if f.get('combat'): out.add('combat')
        if f.get('supernatural_vfx'): out.add('vfx')
        if f.get('colossal'): out.add('colossal')
    return out

def terminology_selection(request, features, intent):
    """Return advisory term choices without turning catalog order into production truth.

    Explicit term IDs/categories are resolved deterministically. In automatic mode,
    the planner reports candidate categories only; the host model must choose terms
    from the Segment facts and expand each selected term into observable evidence.
    """
    requested = request.get('animation_terms', request.get('art_terms', []))
    requested = [requested] if isinstance(requested, str) else list(requested or [])
    categories = request.get('animation_term_categories', request.get('term_categories', []))
    categories = [categories] if isinstance(categories, str) else list(categories or [])
    auto = str(request.get('animation_terms_mode', 'auto')).strip().lower()
    if auto not in {'auto', 'off', 'explicit'}:
        raise ValueError('animation_terms_mode must be auto, explicit or off')
    if auto == 'off':
        return {'mode': 'off', 'term_ids': [], 'categories': [], 'candidate_categories': [],
                'catalog': 'data/animation-art-terminology.json'}
    explicit_categories = list(categories)
    candidate_categories = list(categories)
    if auto == 'auto' and not requested and not explicit_categories and intent in {'full','full-production','production','make','h3','h3-compile','video','compile'}:
        candidate_categories = ['timing_exposure', 'camera_editing']
        if 'combat' in features:
            candidate_categories.append('combat_impact')
        if 'vfx' in features or 'colossal' in features:
            candidate_categories.append('effects_debris')
        if 'performance' in features or intent in {'full','full-production','production','make'}:
            candidate_categories.append('acting_motion')
        return {'mode': 'auto', 'term_ids': [], 'categories': [],
                'candidate_categories': candidate_categories,
                'selection_instruction': 'Host must read data/animation-art-terminology.json and choose only facts-supported terms, normally 3-12 per Segment; then expand each into time, observable fact, camera/layout, sound or QA evidence.',
                'catalog': 'data/animation-art-terminology.json'}
    terms = select_terms(requested=requested, categories=explicit_categories,
                         limit=int(request.get('animation_term_limit', 12)))
    return {'mode': 'explicit', 'term_ids': [item['id'] for item in terms],
            'categories': explicit_categories, 'candidate_categories': explicit_categories,
            'catalog': 'data/animation-art-terminology.json'}
def node(i,owner,phase,deps=None,reason='',segment_id=None,frozen=None,h3_policy=None,term_ids=None):
    value = {'id':i,'owner':owner,'phase':phase,'depends_on':list(deps or []),'reason':reason,'segment_id':segment_id,'frozen_paths':list(frozen or []),'status':'PENDING','attempt':0}
    if h3_policy is not None:
        value.update({
            'h3_min_words': h3_policy['minimum_words'],
            'h3_target_words': h3_policy['target_words'],
            'h3_density_policy': {
                'duration_seconds': h3_policy.get('duration_seconds'),
                'complexity_addition': h3_policy.get('complexity_addition', 0),
                'minimum_words_per_second': h3_policy.get('minimum_words_per_second'),
                'target_words_per_second': h3_policy.get('target_words_per_second'),
            },
        })
    if term_ids:
        value['animation_term_ids'] = list(term_ids)
    return value
def plan(request,production):
    if not isinstance(request,dict) or not isinstance(production,dict): raise ValueError('request and production must be objects')
    rid=request.get('request_id');
    if not isinstance(rid,str) or not rid.strip(): raise ValueError('request_id is required')
    mode=execution_mode(request)
    intent=norm(request.get('intent') or request.get('stage') or request.get('task') or 'full'); feats=feature_set(request,production); nodes=[]; ids=set()
    def add(*args,**kwargs):
        n=node(*args,**kwargs)
        if n['id'] not in ids: nodes.append(n); ids.add(n['id'])
        return n['id']
    full=intent in {'full','full-production','production','make'}; script=intent in {'script','story','story-only'}; assets_only=intent in {'asset','assets','asset-only'}; h3=intent in {'h3','h3-compile','video','compile'}; vfx_only=intent in {'vfx','vfx-optimize','optimize-vfx'}
    terminology = terminology_selection(request, feats, intent)
    scene_intent=intent in {'scene','scene-design','environment','concept-art','moodboard-to-scene'}
    shots_only=intent in {'shots','storyboard'}
    performance_only=intent in {'performance','perform','action'}
    continuity_only=intent in {'continue','continuity'}
    if not any((full,script,assets_only,h3,vfx_only,scene_intent,shots_only,performance_only,continuity_only,intent=='audit')):
        raise ValueError('unsupported intent: '+intent)
    scene_requested=scene_intent or bool(request.get('scene_design')) or bool({'scene','scene-design','environment','concept-art','moodboard'} & feats)
    story=None; shots=None; perf=None; style_anchor=None; assets=None; effects=None; scene_design=None
    if script or full: story=add('story','story','story',reason='author or validate story facts; preserve already confirmed content')
    if full or h3 or shots_only or (performance_only and not production.get('shots')): shots=add('shots','shots','shots',[x for x in (story,) if x],reason='author or validate ShotSpec for selected output; preserve confirmed facts')
    if full or h3 or performance_only: perf=add('performance','performance','performance',[x for x in (shots,) if x],reason='author or validate only applicable performance/action facts')
    # H3 compilation and asset generation are separate capabilities.  A missing
    # asset registry must not silently spend the H3 request on STYLE_MOTHER;
    # only an explicit asset request, full production, scene work, or an
    # assets feature may open that branch.
    asset_generation_requested = assets_only or full or scene_intent or bool(request.get('generate_assets')) or (not production.get('asset_cards') and 'assets' in feats)
    if asset_generation_requested:
        style_anchor=add('style-anchor','assets','style-anchor',[x for x in (story,shots,perf) if x],reason='STYLE_MOTHER must be planned and approved before dependent asset images; explicit waiver is recorded, never inferred')
    if scene_requested:
        scene_design=add('scene-design','assets','scene-design',[x for x in (story,shots,style_anchor) if x],reason='scene-art contract requested; specialist remains advisory and assets owns final merge')
    if asset_generation_requested: assets=add('assets','assets','assets',[x for x in (story,shots,perf,style_anchor,scene_design) if x],reason='asset registry or scene-art handoff is requested or required')
    if (full and ('vfx' in feats or 'colossal' in feats or request.get('include_effects'))) or vfx_only: effects=add('effects','effects','effects',[x for x in (shots,perf) if x],reason='effects explicitly triggered; frozen paths remain outside production writes',frozen=request.get('frozen_paths',[]))
    if full or h3 or request.get('compile_h3'):
        deps=[x for x in (shots,perf,assets,effects) if x]; wanted=request.get('segment_ids'); wanted=[wanted] if isinstance(wanted,str) else wanted
        segs=[s for s in production.get('segments',[]) if not wanted or s.get('id') in set(wanted)]
        if wanted and (not isinstance(wanted,list) or set(wanted) - {s.get('id') for s in production.get('segments', [])}):
            raise ValueError('segment_ids contain unknown segments; discover segments before selecting them')
        if segs:
            for s in segs:
                policy = detail_policy(production, s)
                binding = add('reference-binding:'+str(s.get('id')), 'model', 'reference-binding', deps,
                    reason='resolve Shot reference requirements and approved local asset versions; no asset generation or mode fallback', segment_id=s.get('id'))
                add('model:'+str(s.get('id')), 'model', 'model', [binding],
                    reason='each Segment is an independent H3 compilation unit',
                    segment_id=s.get('id'), h3_policy=policy,
                    term_ids=terminology['term_ids'])
        else: add('model','model','model',deps,reason='H3 compilation requested; segment discovery remains a production concern')
    if full or script or assets_only or h3 or vfx_only or shots_only or performance_only or continuity_only or request.get('continue'): add('continuity','continuity','continuity',[n['id'] for n in nodes],reason='replay and persist continuity after selected slice')
    if request.get('audit',True) or full or script or assets_only or h3 or vfx_only: add('audit','continuity','audit',[n['id'] for n in nodes],reason='single delivery-integrity and claim-honesty receipt')
    if not nodes: raise ValueError('no executable capability for intent: '+intent)
    completed=set(request.get('completed_nodes',[]))
    if completed:
        raise ValueError('completed_nodes alone is not completion evidence; resume the saved workflow with committed artifacts')
    from director_dispatch import registry
    modules = registry()
    for n in nodes:
        module = modules[n['owner']]
        n['required_reads'] = [module['entry'], *module['reads']]
        n['allowed_write_paths'] = module['owns']
        n['neighbor_checks'] = [{'module': mid, 'focus': module['check_focus'], 'write_paths': []} for mid in module['checks_with']]
        if n['phase'] == 'scene-design':
            n['required_reads'] += ['modules/assets/scene-design/SKILL.md']
            n['allowed_write_paths'] = []
        if n['phase'] in {'model', 'reference-binding'}:
            n['external_required_reads'] = ['h3-prompt-writing/SKILL.md', 'h3-prompt-writing/references/ref-en.txt', 'h3-prompt-writing/references/base-en.txt']
        if n['phase'] == 'model':
            n['delivery_contract'] = '4.3.6'
            n['required_artifacts'] = ['complete H3', 'binding snapshot', 'per-Segment upload card', 'final-file receipt', 'joint delivery receipt']
            if n.get('animation_term_ids'):
                n['required_artifacts'].append('animation_term_evidence expanded in the Segment and consumed by H3')
    return {'contract_version':'4.3.6','plan_id':'plan_'+content_hash({'request':request,'production':content_hash(production)})[:16],'request_id':rid,'intent':intent,'execution_mode':mode,'default_execution_mode':'autonomous_file_batch','delivery_mode_contract':{'autonomous_file_batch':{'default':True,'artifact_per_segment':True,'chat_output':'per_segment_upload_cards_and_manifest','requires_workspace_write':True,'must_pause_on_runtime_or_permission_block':True},'interactive_segment':{'max_complete_segments_per_turn':1,'advance_signal':'user must send continue/下一段 after the committed Segment'}},'production_revision':content_hash(production),'delivery_scope':production.get('delivery_scope','prompt_only'),'features':sorted(feats),'terminology':terminology,'style_policy':request.get('style_policy','required') if asset_generation_requested else None,'nodes':nodes,'frozen_paths':list(request.get('frozen_paths',[])),'pause_conditions':['missing user decision','missing irreplaceable material','missing permission','missing external capability','workspace file writing unavailable for autonomous_file_batch','STYLE_MOTHER approval required before dependent asset submission'],'execution':'plan-only; modules and models are not invoked'}
def plan_and_state(request,production,state_path=None):
    p=plan(request,production); s=new_state(request['request_id'],p['production_revision'],p)
    if state_path: save_state(state_path,s)
    return p,s
class OrchestratorAdapter:
    def plan(self,request,production): return plan(request,production)
    def execute(self,node,context): raise NotImplementedError('host must provide execute(node, context)')
    def validate(self,node,artifact): return {'status':'UNVERIFIED','node_id':node.get('id'),'artifact':str(artifact)}
    def commit(self,node,artifact,context):
        from orchestrator_commit import commit_artifact
        return commit_artifact(context['state'],context['state_path'],node,artifact,context['production_revision'],**context.get('commit_options',{}))
    def schedule_next(self,state):
        from orchestrator_commit import schedule_next
        return schedule_next(state)
    def pause(self,reason,state,state_path):
        from workflow_state import save_state,transition
        save_state(state_path,transition(state,'PAUSED',reason=reason)); return state
    def resume(self,state,state_path):
        from workflow_state import resume_from_last_commit,save_state
        state=resume_from_last_commit(state); save_state(state_path,state); return state
def main():
    p=argparse.ArgumentParser(); p.add_argument('request',type=Path); p.add_argument('production',type=Path); p.add_argument('--out',type=Path,required=True); p.add_argument('--state-out',type=Path)
    a=p.parse_args(); req=json.loads(a.request.read_text(encoding='utf-8')); prod=json.loads(a.production.read_text(encoding='utf-8')); result,state=plan_and_state(req,prod,a.state_out); atomic_write_json(a.out,result); print(json.dumps({'plan':str(a.out),'state':str(a.state_out) if a.state_out else None,'nodes':len(result['nodes']),'status':state['status']},ensure_ascii=False))
if __name__=='__main__': main()
