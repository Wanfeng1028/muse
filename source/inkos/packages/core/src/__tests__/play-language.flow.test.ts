import {mkdtemp,rm,mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {expect,it} from 'vitest';
import {createPlayStartTool} from '../agent/agent-tools.js';
import {PlayStore} from '../play/play-store.js';
import {PlayRunner} from '../play/play-runner.js';
import {seedPlayGraph} from '../play/play-reducer.js';
import {PlayMutationSchema} from '../models/play.js';
import {loadWorkManifest,createWorkManifest,saveWorkManifest} from '../harness/work-store.js';
import {syncWorkSourceArtifacts} from '../harness/source-sync.js';
import {createBuiltInWorkProfileRegistry} from '../harness/builtin-profiles.js';

it('persists the requested world language over the project default and uses it on later turns',async()=>{
  const root=await mkdtemp(join(tmpdir(),'inkos-play-language-'));
  try{
    const pipeline={runWithAgentContext:async(_options:unknown,fn:()=>unknown)=>fn(),createAgentContext:()=>({})};
    const empty={entities:{upsert:[]},edges:{upsert:[],expire:[]},stateSlots:{upsert:[]},evidence:{transitions:[]},blocked:false,blockedReason:'',notes:[]};
    const seed=PlayMutationSchema.parse({...empty,turn:0,eventId:'evt-0',actionKind:'look',summary:'Opening',entities:{upsert:[
      {id:'actor_player',type:'actor',label:'Player',summary:'An adult visitor',createdEventId:'evt-0',updatedEventId:'evt-0'},
      {id:'room',type:'location',label:'Room',summary:'A quiet room',createdEventId:'evt-0',updatedEventId:'evt-0'},
    ]}});
    await createPlayStartTool(pipeline as never,root,'english','open',{language:'zh',runnerFactory:({db})=>({seedOpening:async()=>{seedPlayGraph({db,mutation:seed});return{mutation:seed};}})}).execute('start',{title:'A quiet room',language:'en',initialScene:'A window is open.'});
    const store=new PlayStore(root);
    expect((await store.loadWorld('english'))?.language).toBe('en');
    expect((await loadWorkManifest(root,'english')).language).toBe('en');
    let receivedLanguage:string|undefined;
    const contextHistory=(await store.readTranscript('english','main')).map(({role,content})=>({role,content}));
    const runner=new PlayRunner({projectRoot:root,worldId:'english',runId:'main',store,agents:{openingState:{extract:async()=>seed},turn:{run:async input=>{
      receivedLanguage=input.language;
      expect(contextHistory).not.toHaveLength(0);
      expect(input.context).toContain(JSON.stringify(contextHistory));
      return{action:{actionKind:'wait',intent:'Wait',manner:'',risk:'',ambiguity:'',secondaryActions:[]},mutation:PlayMutationSchema.parse({...empty,turn:1,eventId:'evt-1',actionKind:'wait',summary:'The breeze passes.'}),sceneText:'A breeze passes through the window.',suggestedActions:[]};
    }}}});
    try{await runner.step('Wait.');}finally{runner.close();}
    expect(receivedLanguage).toBe('en');
    expect((await store.loadCurrentState('english','main'))?.turn).toBe(1);
    await mkdir(join(root,'.inkos/profiles'),{recursive:true});
    const profile={...createBuiltInWorkProfileRegistry().require('interactive-world'),id:'composed-world',capabilityIds:['workspace','interactive-world','longform']};
    await writeFile(join(root,'.inkos/profiles/composed-world.json'),JSON.stringify(profile));
    await saveWorkManifest(root,createWorkManifest({id:'composed',title:'Established title',profileId:profile.id,language:'en',metadata:{intent:'Preserve the saved brief'},lineage:[{relation:'derived-from',sourceWorkId:'reference'}]}));
    await mkdir(join(root,'works/composed/source'),{recursive:true});
    const before=await syncWorkSourceArtifacts({projectRoot:root,workId:'composed',accept:true,writes:[{relativePath:'works/composed/source/brief.md',content:'The established creation request.'}]});
    await store.createWorld({id:'composed',title:before.title,language:'en',mode:'open',premise:'A gallery',worldContract:'',visualContract:''});
    const after=await loadWorkManifest(root,'composed');
    expect(after).toMatchObject({title:before.title,profileId:before.profileId,language:before.language,createdAt:before.createdAt,metadata:before.metadata,lineage:before.lineage});
    expect(after.artifacts.find(artifact=>artifact.id===before.artifacts[0].id)).toEqual(before.artifacts[0]);
  }finally{await rm(root,{recursive:true,force:true});}
});
