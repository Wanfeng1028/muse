import {mkdtemp,readFile,readdir,rm,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {expect,it,vi} from 'vitest';
import {PipelineRunner} from '../pipeline/runner.js';
import {StateManager} from '../state/manager.js';
import {loadWorkManifest} from '../harness/work-store.js';
import {mkdir} from 'node:fs/promises';
import {ArchitectAgent,type ArchitectOutput} from '../agents/architect.js';
import {BookRulesSchema} from '../models/book-rules.js';
import {syncWorkSourceArtifacts} from '../harness/source-sync.js';

it('preserves explicit continuation direction across a failed import and its retry',async()=>{
  const root=await mkdtemp(join(tmpdir(),'inkos-import-direction-'));
  const runner=new PipelineRunner({projectRoot:root,model:'fixture',client:{} as never});
  const now=new Date().toISOString();const instruction='Verify the owner and hand over the still locked cabinet.';
  const generate=vi.spyOn(ArchitectAgent.prototype,'generateFoundationFromImport').mockRejectedValue(Object.assign(new Error('Fixture failure'),{code:'FIXTURE_FAILURE'}));
  try{
    await runner.prepareDraftBook({id:'imported',title:'Import',genre:'other',platform:'other',language:'en',status:'outlining',targetChapters:2,chapterWordCount:250,createdAt:now,updatedAt:now});
    const input={bookId:'imported',chapters:[{title:'Source',content:'A clerk finds a key beside a locked cabinet.'}],importMode:'continuation' as const};
    await expect(runner.importChapters({...input,continuationInstruction:instruction})).rejects.toMatchObject({code:'FIXTURE_FAILURE'});
    await expect(runner.importChapters(input)).rejects.toMatchObject({code:'FIXTURE_FAILURE'});
    expect(generate.mock.calls.map(call=>call[2])).toEqual([instruction,instruction]);
    expect((await readFile(join(root,'works/imported/source/story/import-direction.md'),'utf8')).trim()).toBe(instruction);
  }finally{generate.mockRestore();await rm(root,{recursive:true,force:true});}
});

it('replaces foundation role files while preserving runtime history and non-role assets',async()=>{
  const root=await mkdtemp(join(tmpdir(),'inkos-foundation-revision-'));
  const architect=new ArchitectAgent({projectRoot:root,model:'unused',client:{} as never});
  const first:ArchitectOutput={storyFrame:'Original frame',volumeMap:'Original plan',bookRules:'Original rules',bookRulesData:BookRulesSchema.parse({version:'2',prohibitions:[],enableFullCastTracking:false,allowedDeviations:[]}),roles:[{tier:'major',name:'Lead',content:'Original role'},{tier:'minor',name:'Retired',content:'Old supporting role'}],initialHooks:[],pendingHooks:''};
  try {
    await architect.writeFoundationFiles(root,first,'en','init');
    await writeFile(join(root,'story/roles/主要角色/reference.txt'),'Retained asset');
    const oldState=await readFile(join(root,'story/current_state.md'));
    await architect.writeFoundationFiles(root,{...first,storyFrame:'Revised frame',roles:[{tier:'major',name:'Lead',content:'Revised role'},{tier:'minor',name:'Client',content:'New supporting role'}]},'en','revise');
    expect(await readFile(join(root,'story/outline/story_frame.md'),'utf8')).toBe('Revised frame\n');
    expect(await readFile(join(root,'story/roles/主要角色/Lead.md'),'utf8')).toBe('Revised role\n');
    expect(await readdir(join(root,'story/roles/次要角色'))).toEqual(['Client.md']);
    expect(await readFile(join(root,'story/current_state.md'))).toEqual(oldState);
    expect(await readFile(join(root,'story/roles/主要角色/reference.txt'),'utf8')).toBe('Retained asset');
  } finally {await rm(root,{recursive:true,force:true});}
});

it('recovers a partial draft with its canon and candidate revision preserved',async()=>{
  const root=await mkdtemp(join(tmpdir(),'inkos-draft-recovery-'));
  const runner=new PipelineRunner({projectRoot:root,model:'fixture',client:{} as never});
  const state=new StateManager(root);
  const now=new Date().toISOString();
  const book={id:'draft',title:'Draft',genre:'other',platform:'other',language:'en' as const,status:'outlining' as const,targetChapters:1,chapterWordCount:300,createdAt:now,updatedAt:now};
  const foundation:ArchitectOutput={storyFrame:'Recovered frame',volumeMap:'One chapter',bookRules:'Preserve canon',bookRulesData:BookRulesSchema.parse({version:'2',prohibitions:[],enableFullCastTracking:false,allowedDeviations:[]}),roles:[{tier:'major',name:'Lead',content:'Adult clerk'}],initialHooks:[],pendingHooks:''};
  const generate=vi.spyOn(ArchitectAgent.prototype,'generateFoundation').mockResolvedValue(foundation);
  try {
    await runner.prepareDraftBook(book);
    const before=await loadWorkManifest(root,'draft');
    await expect(runner.writeChapters('draft',1)).rejects.toMatchObject({code:'WORK_NOT_READY',workId:'draft',recoveryAction:'revise_foundation'});
    expect(generate).not.toHaveBeenCalled();
    await mkdir(join(state.bookDir('draft'),'story'),{recursive:true});
    await writeFile(join(state.bookDir('draft'),'story/parent_canon.md'),'Sealed letters remain sealed.');
    await syncWorkSourceArtifacts({projectRoot:root,workId:'draft',accept:true});
    expect((await loadWorkManifest(root,'draft')).status).toBe('active');
    expect(await state.isCompleteBookDirectory(state.bookDir('draft'))).toBe(false);
    await runner.reviseFoundation('draft','Complete the preserved draft.');
    expect(generate.mock.calls[0]?.[1]).toContain('Sealed letters remain sealed.');
    expect(await state.isCompleteBookDirectory(state.bookDir('draft'))).toBe(true);
    expect(await state.loadChapterIndex('draft')).toEqual([]);
    const runtime=JSON.parse(await readFile(join(state.bookDir('draft'),'story/state/manifest.json'),'utf8'));
    expect(runtime).toBeTruthy();
    const after=await loadWorkManifest(root,'draft');
    expect(after.status).toBe('active');
    for(const artifact of before.artifacts) {
      expect(after.artifacts.find(item=>item.id===artifact.id)?.revisions).toEqual(expect.arrayContaining(
        artifact.revisions.map(({id,checksum,snapshotPath})=>expect.objectContaining({id,checksum,snapshotPath})),
      ));
    }
    expect(await readFile(join(state.bookDir('draft'),'story/parent_canon.md'),'utf8')).toBe('Sealed letters remain sealed.');
  } finally {generate.mockRestore();await rm(root,{recursive:true,force:true});}
});
