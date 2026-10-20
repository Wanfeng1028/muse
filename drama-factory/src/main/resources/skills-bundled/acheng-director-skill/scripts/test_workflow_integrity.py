"""Reproduced acceptance failures in workflow handoff, not artistic grading."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from contract_core import content_hash
from orchestrator_commit import commit_artifact, schedule_next
from orchestrator_plan import plan
from workflow_state import new_state, save_state, resume_from_last_commit

ROOT = Path(__file__).resolve().parents[1]


class WorkflowIntegrityAcceptance(unittest.TestCase):
    def setup_run(self, folder, *, model=False, mode='autonomous_file_batch'):
        revision=content_hash({'fixture':'workflow integrity'})
        nodes=[{'id':'story','phase':'story','depends_on':[],'status':'PENDING'},
               {'id':'model:S1' if model else 'assets','phase':'model' if model else 'assets',
                'segment_id':'S1' if model else None,'depends_on':['story'],'status':'PENDING'}]
        state=new_state('TEST',revision,{'nodes':nodes,'execution_mode':mode})
        state_path=folder/'workflow.json';save_state(state_path,state)
        source=folder/'artifact.txt';source.write_text('authored artifact',encoding='utf-8')
        return state,state_path,source,revision

    def test_unaccepted_unknown_and_unready_work_never_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,path,source,revision=self.setup_run(Path(tmp))
            with self.assertRaisesRegex(ValueError,'unresolved'):
                commit_artifact(state,path,state['nodes'][0],source,revision,unresolved=['missing required fact'])
            with self.assertRaisesRegex(ValueError,'accepted'):
                commit_artifact(state,path,state['nodes'][0],source,revision,accepted=False)
            with self.assertRaisesRegex(ValueError,'dependencies'):
                commit_artifact(state,path,state['nodes'][1],source,revision)
            with self.assertRaisesRegex(ValueError,'unknown workflow node'):
                commit_artifact(state,path,{'id':'unknown'},source,revision)
            self.assertEqual(state['artifacts'],[])
            self.assertEqual(schedule_next(state)['id'],'story')
            with self.assertRaisesRegex(ValueError,'completion evidence'):
                plan({'request_id':'FAKE','intent':'script','completed_nodes':['story']},{})

    def test_model_cannot_hide_behind_wrong_extension_or_claimed_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);state,path,source,revision=self.setup_run(folder,model=True)
            commit_artifact(state,path,state['nodes'][0],source,revision)
            disguised={'id':'model:S1','phase':'story'}
            with self.assertRaisesRegex(ValueError,'requires a .h3'):
                commit_artifact(state,path,disguised,source,revision)
            renamed=folder/'artifact.json';renamed.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'requires a .h3'):
                commit_artifact(state,path,disguised,renamed,revision)
            self.assertEqual(schedule_next(state)['id'],'model:S1')

    def test_default_partial_identity_can_complete_without_losing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,path,source,revision=self.setup_run(Path(tmp))
            partial=commit_artifact(state,path,state['nodes'][0],source,revision,status='partial',cursor={'offset':8})
            self.assertEqual(partial['status'],'PARTIAL')
            source.write_text('a complete authored artifact',encoding='utf-8')
            full=commit_artifact(state,path,state['nodes'][0],source,revision)
            self.assertEqual(full['artifact']['artifact_id'],partial['artifact']['artifact_id'])
            self.assertTrue(Path(partial['artifact']['path']).is_file())
            self.assertEqual(full['status'],'COMMITTED')
            self.assertFalse(state['continuation_required'])
            self.assertEqual(commit_artifact(state,path,state['nodes'][0],source,revision)['status'],'IDEMPOTENT')
            Path(full['artifact']['path']).write_text('tampered',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'missing or changed'):
                commit_artifact(state,path,state['nodes'][0],source,revision)

    def test_resume_keeps_later_partial_cursor_and_checks_saved_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,path,source,revision=self.setup_run(Path(tmp))
            commit_artifact(state,path,state['nodes'][0],source,revision)
            partial=commit_artifact(state,path,state['nodes'][1],source,revision,status='partial',cursor={'offset':42})
            state['status']='PAUSED';resumed=resume_from_last_commit(state)
            self.assertEqual(resumed['current_cursor'],{'offset':42,'node_id':'assets'})
            self.assertTrue(resumed['continuation_required'])
            resumed['status']='PAUSED'
            Path(partial['artifact']['path']).write_text('changed',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'partial artifact missing or changed'):
                resume_from_last_commit(resumed)

    def test_real_h3_bundle_is_segment_bound_and_interactive_commit_pauses(self):
        from compile_h3 import compile_package
        source=ROOT/'examples/02-drama.production.json'
        payload=json.loads(source.read_text(encoding='utf-8'));revision=content_hash(payload)
        segment=payload['segments'][0]['id']
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);entry=compile_package(source,folder/'bundle')[0]
            nodes=[{'id':'model:'+segment,'phase':'model','segment_id':segment,'depends_on':[],'status':'PENDING'},
                   {'id':'audit','phase':'audit','depends_on':['model:'+segment],'status':'PENDING'}]
            state=new_state('REAL',revision,{'nodes':nodes,'execution_mode':'interactive_segment'})
            state_path=folder/'state.json';save_state(state_path,state)
            prompt=folder/'bundle'/entry['file']
            wrong=copy.deepcopy(state);wrong['nodes'][0]['segment_id']='DIFFERENT'
            with self.assertRaisesRegex(ValueError,'different Segment'):
                commit_artifact(wrong,state_path,wrong['nodes'][0],prompt,revision)
            result=commit_artifact(state,state_path,state['nodes'][0],prompt,revision)
            self.assertTrue(result['artifact']['accepted'])
            self.assertEqual(state['status'],'PAUSED')
            self.assertIsNone(schedule_next(state))
            resume_from_last_commit(state)
            self.assertEqual(schedule_next(state)['id'],'audit')


if __name__=='__main__':
    unittest.main()
