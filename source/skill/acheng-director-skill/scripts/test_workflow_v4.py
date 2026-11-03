import copy, json, tempfile, unittest
from pathlib import Path
from contract_core import content_hash
from orchestrator_commit import commit_artifact, schedule_next
from orchestrator_plan import OrchestratorAdapter, plan, plan_and_state
from h3_contract import detail_policy, english_word_count
from animation_term_catalog import select_terms
from workflow_state import load_state, new_state, save_state

class WorkflowV4Acceptance(unittest.TestCase):
    def setUp(self):
        self.production={'version':'2.0','project_id':'demo','delivery_scope':'prompt_only','shots':[{'id':'SHOT_001','features':{'combat':False,'supernatural_vfx':False,'colossal':False}}],'segments':[{'id':'SEG_001','shot_ids':['SHOT_001'],'mode':'T2VA'}],'asset_plan':[{'id':'STYLE_MOTHER','kind':'style'}]}
    def test_capability_graph_not_fixed_pipeline(self):
        story=plan({'request_id':'REQ_SCRIPT','intent':'script'},self.production)
        self.assertEqual([n['id'] for n in story['nodes']],['story','continuity','audit'])
        h3=plan({'request_id':'REQ_H3','intent':'h3-compile'},self.production)
        self.assertIn('model:SEG_001',[n['id'] for n in h3['nodes']]); self.assertNotIn('style-anchor',[n['id'] for n in h3['nodes']])
        vfx=plan({'request_id':'REQ_VFX','intent':'vfx-optimize','frozen_paths':['/shots/0/camera']},self.production)
        self.assertEqual([n['id'] for n in vfx['nodes']],['effects','continuity','audit'])
        scene=plan({'request_id':'REQ_SCENE','intent':'scene-design'},self.production)
        self.assertEqual([n['id'] for n in scene['nodes']],['style-anchor','scene-design','assets','audit'])
        combat = copy.deepcopy(self.production); combat['shots'][0]['features']['combat'] = True
        self.assertEqual([n['id'] for n in plan({'request_id':'VFX_ONLY','intent':'vfx'},combat)['nodes']], ['effects','continuity','audit'])
        empty_scene = copy.deepcopy(self.production); empty_scene['shots'] = []
        self.assertEqual([n['id'] for n in plan({'request_id':'SCENE_ONLY','intent':'scene'},empty_scene)['nodes']], ['style-anchor','scene-design','assets','audit'])
        self.assertEqual([n['id'] for n in plan({'request_id':'SHOTS','intent':'storyboard'},self.production)['nodes']], ['shots','continuity','audit'])
        with self.assertRaisesRegex(ValueError, 'unsupported intent'):
            plan({'request_id':'UNKNOWN','intent':'typo-task'},self.production)
        with self.assertRaisesRegex(ValueError, 'unknown segments'):
            plan({'request_id':'UNKNOWN_SEG','intent':'h3','segment_ids':['missing']},self.production)
    def test_execution_mode_is_explicit_and_persisted(self):
        interactive=plan({'request_id':'REQ_INTERACTIVE','intent':'h3-compile','execution_mode':'1'},self.production)
        self.assertEqual(interactive['execution_mode'],'autonomous_file_batch')
        self.assertTrue(interactive['delivery_mode_contract']['autonomous_file_batch']['default'])
        batch=plan({'request_id':'REQ_BATCH','intent':'h3-compile','execution_mode':'2'},self.production)
        self.assertEqual(batch['execution_mode'],'interactive_segment')
        self.assertEqual(batch['delivery_mode_contract']['interactive_segment']['max_complete_segments_per_turn'],1)
        _,state=plan_and_state({'request_id':'REQ_BATCH_STATE','intent':'h3-compile','execution_mode':'autonomous_file_batch'},self.production)
        self.assertEqual(state['execution_mode'],'autonomous_file_batch')
        default_plan=plan({'request_id':'REQ_DEFAULT','intent':'h3-compile'},self.production)
        self.assertEqual(default_plan['execution_mode'],'autonomous_file_batch')
        with self.assertRaisesRegex(ValueError,'execution_mode'):
            plan({'request_id':'REQ_BAD_MODE','intent':'h3-compile','execution_mode':'all-at-once'},self.production)
    def test_state_is_control_metadata_only(self):
        state=new_state('REQ',content_hash(self.production),{'plan_id':'p','nodes':[]})
        serialized=json.dumps(state)
        for forbidden in ('ShotSpec','asset_cards','integrated_multimodal_description','STYLE_MOTHER'): self.assertNotIn(forbidden,serialized)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'workflow_state.json'; save_state(p,state); self.assertEqual(load_state(p)['schema_version'],'4.0')
    def test_commit_hash_idempotency_and_stale_rejection(self):
        rev=content_hash(self.production); _,state=plan_and_state({'request_id':'REQ','intent':'script'},self.production)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); sp=d/'state.json'; src=d/'result.md'; save_state(sp,state); src.write_text('story result',encoding='utf8'); node=state['nodes'][0]
            first=commit_artifact(state,sp,node,src,rev,artifact_root=d/'artifacts'); self.assertEqual(first['status'],'COMMITTED')
            self.assertEqual(commit_artifact(state,sp,node,src,rev,artifact_root=d/'artifacts')['status'],'IDEMPOTENT')
            with self.assertRaisesRegex(ValueError,'stale input'): commit_artifact(state,sp,{'id':'audit'},src,'0'*64,artifact_root=d/'artifacts')
    def test_partial_cursor_then_completion(self):
        rev=content_hash(self.production); _,state=plan_and_state({'request_id':'REQ','intent':'script'},self.production)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); sp=d/'state.json'; save_state(sp,state); node=state['nodes'][0]; part=d/'part.txt'; part.write_text('prefix',encoding='utf8')
            result=commit_artifact(state,sp,node,part,rev,artifact_root=d/'artifacts',artifact_id='part',status='partial',cursor={'segment_id':'SEG_001','offset':128}); self.assertTrue(result['state']['continuation_required']); self.assertEqual(result['state']['current_cursor']['offset'],128)
            full=d/'full.txt'; full.write_text('complete',encoding='utf8'); done=commit_artifact(state,sp,node,full,rev,artifact_root=d/'artifacts',artifact_id='full'); self.assertFalse(done['state']['continuation_required']); self.assertIsNotNone(schedule_next(done['state']))

    def test_dynamic_h3_density_and_english_word_count(self):
        simple = {'version':'2.0','fps_num':24,'fps_den':1,
                  'shots':[{'id':'S1','features':{}}],
                  'segments':[{'id':'A','shot_ids':['S1'],'generation_clip_duration':10}]}
        base = detail_policy(simple, simple['segments'][0])
        self.assertEqual((base['minimum_words'], base['target_words']), (2000, 2400))
        simple['segments'][0]['generation_clip_duration'] = 12
        longer = detail_policy(simple, simple['segments'][0])
        self.assertEqual((longer['minimum_words'], longer['target_words']), (2400, 2880))
        simple['shots'][0]['features']['combat'] = True
        complex_policy = detail_policy(simple, simple['segments'][0])
        self.assertEqual(complex_policy['minimum_words'], 2600)
        self.assertEqual(english_word_count('English words 24 中文 123'), 2)
        simple['prompt_detail_policy'] = {'ref2va_min_words': 2000}
        with self.assertRaisesRegex(ValueError, 'derived 2600'):
            detail_policy(simple, simple['segments'][0])

    def test_automatic_terms_are_candidates_and_explicit_conflicts_fail(self):
        auto = plan({'request_id':'REQ_TERMS','intent':'h3-compile'}, self.production)
        self.assertEqual(auto['terminology']['mode'], 'auto')
        self.assertEqual(auto['terminology']['term_ids'], [])
        self.assertTrue(auto['terminology']['candidate_categories'])
        chosen = select_terms(requested=['acting.eye_trace','acting.breath_beat'])
        self.assertEqual([term['id'] for term in chosen],
                         ['acting.eye_trace','acting.breath_beat'])
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            select_terms(requested=['timing.on_ones','timing.on_twos'])
        with self.assertRaisesRegex(ValueError, 'animation_terms_mode'):
            plan({'request_id':'REQ_BAD_TERMS_MODE','intent':'h3-compile',
                  'animation_terms_mode':'everything'}, self.production)

    def test_short_ref2va_cannot_be_committed_as_complete(self):
        rev=content_hash(self.production); _,state=plan_and_state({'request_id':'REQ_REF_GATE','intent':'h3-compile'},self.production)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); sp=d/'state.json'; node=next(n for n in state['nodes'] if n['phase']=='model'); node['depends_on']=[]; state['nodes']=[node]; save_state(sp,state)
            short=d/'short.h3.txt'
            short.write_text('subject_definitions:\n<Picture 1> is a reference.\n\nsummary:\n[reference generation] test.\n\nretention_analysis:\n<Picture 1>: weak_reference - test.\n\ndetailed_description:\n' + ('short body ' * 100) + '\n\noverall_soundscape:\nN/A\n\nnon_diegetic_music:\nN/A\n', encoding='utf8')
            with self.assertRaisesRegex(ValueError,'minimum is 2000'):
                commit_artifact(state,sp,node,short,rev,artifact_root=d/'artifacts',artifact_id='short-ref')
    def test_adapter_pause_and_execution_boundary(self):
        adapter=OrchestratorAdapter()
        with self.assertRaises(NotImplementedError): adapter.execute({'id':'story'}, {})
        _,state=plan_and_state({'request_id':'REQ','intent':'script'},self.production)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json'; save_state(p,state); adapter.pause('user decision required',state,p); self.assertEqual(load_state(p)['status'],'PAUSED')
if __name__=='__main__': unittest.main()
