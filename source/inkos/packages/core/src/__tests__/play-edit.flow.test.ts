import{mkdtemp,rm,writeFile}from'node:fs/promises';import{tmpdir}from'node:os';import{join}from'node:path';
import{it,expect}from'vitest';
import{PlayStore}from'../play/play-store.js';import{createPlayDB}from'../play/play-db-factory.js';
import{createPlayEditTool,createPlayReviseTool}from'../agent/agent-tools.js';
import{PipelineRunner}from'../pipeline/runner.js';import{createLLMClient}from'../llm/provider.js';
import{createInspectPlayStateTool}from'../harness/tools/play-state.js';
import{PlayRunner}from'../play/play-runner.js';
import{PlayActionIntentSchema,PlayMutationSchema}from'../models/play.js';
import{CreativeEpisodeStore}from'../harness/episode-store.js';
import{syncWorkSourceArtifacts}from'../harness/source-sync.js';
import{loadWorkManifest}from'../harness/work-store.js';
import{readArtifactRevision}from'../harness/artifact-reader.js';

it('inspects exact world identities, rejects a guessed ID before any mutation and edits the original entities without advancing time',async()=>{
 const root=await mkdtemp(join(tmpdir(),'inkos-play-edit-'));
 try{
  const store=new PlayStore(root);
  await store.createWorld({id:'world',title:'Fixture',premise:'Original premise',worldContract:'One action per turn',visualContract:'',mode:'guided',language:'en'});
  await store.ensureRun('world','main');await store.saveCurrentState('world','main',{turn:1});
  const db=createPlayDB(store.runDir('world','main'));
  db.upsertEntity({id:'actor_player',type:'actor',label:'Player',summary:'',status:'inside',createdEventId:'evt-0',updatedEventId:'evt-0'});
  db.upsertEntity({id:'guard',type:'actor',label:'Guard',summary:'',status:'at door',createdEventId:'evt-0',updatedEventId:'evt-0'});
  db.upsertEdge({id:'old_contact',fromId:'actor_player',toId:'guard',type:'near',value:{},validFromEventId:'evt-0',validUntilEventId:null,sourceEventId:'evt-0'});
  db.upsertStateSlot({id:'player_location',ownerEntityId:'actor_player',kind:'flag',label:'Position',value:'inside',updatedEventId:'evt-0'});
  const initialEvent={id:'evt-1',turn:1,actionKind:'wait' as const,rawInput:'Wait',outcomeSummary:'Waited inside',createdAt:new Date().toISOString()};
  db.recordEvent(initialEvent);await store.appendEvent('world','main',initialEvent);
  db.close?.();
  const inspector=createInspectPlayStateTool(root,'world'),edit=createPlayEditTool(root,'world','en');
  const before=await inspector.execute('inspect',{});
  expect(before.details).toMatchObject({currentState:{turn:1},entities:expect.arrayContaining([{id:'guard',type:'actor',label:'Guard',summary:'',status:'at door'}])});
  await expect(edit.execute('bad',{premise:'Should not commit',entityUpdates:[{id:'actor_player',status:'outside'},{id:'actor_guard',type:'actor',status:'inside'}]})).rejects.toMatchObject({code:'PLAY_ENTITY_NOT_FOUND',entityId:'actor_guard'});
  expect((await inspector.execute('again',{})).details).toEqual(before.details);
  expect((await store.loadWorld('world'))?.premise).toBe('Original premise');
  await expect(edit.execute('bad-edge',{entityUpdates:[{id:'actor_player',status:'outside'}],expiredEdgeIds:['unknown']})).rejects.toMatchObject({code:'PLAY_EDGE_NOT_FOUND',edgeId:'unknown'});
  await expect(edit.execute('bad-slot',{premise:'Should not commit',stateSlotUpdates:[{id:'unknown',value:'outside'}]})).rejects.toMatchObject({code:'PLAY_STATE_SLOT_NOT_FOUND',slotId:'unknown'});
  expect((await inspector.execute('still-before',{})).details).toEqual(before.details);
  expect((await store.loadWorld('world'))?.premise).toBe('Original premise');
  await edit.execute('good',{entityUpdates:[{id:'actor_player',status:'outside'},{id:'guard',status:'inside'}],expiredEdgeIds:['old_contact'],stateSlotUpdates:[{id:'player_location',value:'outside'}]});
  const after=(await inspector.execute('after',{})).details as {currentState:{turn:number};entities:Array<{id:string;status:string}>;activeEdges:unknown[];stateSlots:Array<{id:string;value:unknown}>};
  expect(after.currentState.turn).toBe(1);
  expect(after.entities.map(({id,status})=>({id,status}))).toEqual([{id:'actor_player',status:'outside'},{id:'guard',status:'inside'}]);
  expect(after.activeEdges).toEqual([]);
  expect(after.stateSlots).toEqual([expect.objectContaining({id:'player_location',value:'outside'})]);
  const history=createPlayDB(store.runDir('world','main'));
  expect(history.snapshot().edges).toEqual([expect.objectContaining({id:'old_contact',validUntilEventId:'evt-1'})]);
  history.close?.();
  let currentGraph:{activeRelationships:unknown[];stateSlots:unknown[]}|undefined;
  const choices=['Wait outside','Leave the courtyard'];
  const runner=new PlayRunner({projectRoot:root,worldId:'world',runId:'main',agents:{
    openingState:{async extract(){throw new Error('Unexpected opening');}},
    turn:{async run(input){
      currentGraph=input.context.split('\n\n').filter(part=>part.startsWith('{')).map(part=>JSON.parse(part)).find(part=>Array.isArray(part.activeRelationships));
      return {action:PlayActionIntentSchema.parse({actionKind:'wait',intent:'Wait'}),sceneText:'The player waits outside.',suggestedActions:choices,
        mutation:PlayMutationSchema.parse({eventId:'evt-2',turn:2,actionKind:'wait',summary:'Waited',entities:{upsert:[]},edges:{upsert:[],expire:[]},stateSlots:{upsert:[]},evidence:{transitions:[]},blocked:false,blockedReason:'',notes:[]})};
    }},
  }});
  try{await runner.step('Wait');}finally{runner.close();}
  expect(currentGraph).toMatchObject({activeRelationships:[],stateSlots:[expect.objectContaining({id:'player_location',value:'outside'})]});
  expect((await store.loadCurrentState('world','main'))?.turn).toBe(2);
  const beforeReplayDB=createPlayDB(store.runDir('world','main'));
  const beforeReplay=await store.captureRunSnapshot('world','main',{id:'before-rewrite',turn:2,graph:beforeReplayDB.snapshot()});
  beforeReplayDB.close?.();
  expect(await store.readCurrentSuggestedActions('world','main',2,beforeReplay.sceneProjection)).toEqual(choices);
  const legacyTranscript=beforeReplay.transcriptRaw.trim().split('\n').map(line=>{const turn=JSON.parse(line);delete turn.suggestedActions;return JSON.stringify(turn);}).join('\n')+'\n';
  await writeFile(join(store.runDir('world','main'),'transcript.jsonl'),legacyTranscript);
  expect(await store.readCurrentSuggestedActions('world','main',2,beforeReplay.sceneProjection)).toEqual(choices);
  await rm(join(store.runDir('world','main'),'presentation.json'));
  expect(await store.readCurrentSuggestedActions('world','main',2,beforeReplay.sceneProjection)).toBeUndefined();
  const episodes=new CreativeEpisodeStore(join(root,'.inkos/harness.sqlite'));
  for(const [workId,timestamp,suggestedActions] of [['world','2026-09-09T00:00:00Z',choices],['other','2026-09-09T00:00:01Z',['Wrong world choice']]] as const){
    episodes.create({version:2,id:workId,workId,profileId:'interactive-world',status:'completed',startedAt:timestamp,completedAt:timestamp});
    episodes.append({episodeId:workId,workId,type:'action-completed',actionId:'play_revise',payload:{result:{data:{currentState:{turn:2},runId:'main',sceneText:beforeReplay.sceneProjection.trim(),suggestedActions}}}},timestamp);
  }
  episodes.close();
  expect(await store.readCurrentSuggestedActions('world','main',2,beforeReplay.sceneProjection)).toEqual(choices);
  expect(await store.readCurrentSuggestedActions('world','other-run',2,beforeReplay.sceneProjection)).toBeUndefined();
  const rerender=new PlayRunner({projectRoot:root,worldId:'world',runId:'main',agents:{
    openingState:{async extract(){throw new Error('Unexpected opening');}},
    turn:{
      async run(){throw new Error('A prose rewrite must not recompute the turn.');},
      async renderExisting(input){if(input.currentSuggestedActions)expect(input.currentSuggestedActions).toEqual(choices);return {sceneText:'Outside, the player waits by the door.',suggestedActions:['Run','Hide']};},
    },
  }});
  const client=createLLMClient({service:'custom',provider:'openai',configSource:'studio',model:'fixture',apiKey:'fixture',baseUrl:'http://127.0.0.1:1/v1',apiFormat:'chat',stream:true,temperature:0,thinkingBudget:0});
  const proseTool=createPlayReviseTool(new PipelineRunner({client,model:'fixture',projectRoot:root}),root,'world',{runnerFactory:()=>rerender});
  const proseResult=await proseTool.execute('rewrite',{action:'rewrite_scene',instruction:'Rephrase only'});
  expect(proseResult.details).toMatchObject({suggestedActions:choices});
  const afterReplayDB=createPlayDB(store.runDir('world','main'));
  const afterReplay=await store.captureRunSnapshot('world','main',{id:'after-rewrite',turn:2,graph:afterReplayDB.snapshot()});
  afterReplayDB.close?.();
  expect(afterReplay.graph).toEqual(beforeReplay.graph);
  expect(afterReplay.currentStateRaw).toBe(beforeReplay.currentStateRaw);
  expect(afterReplay.eventsRaw).toBe(beforeReplay.eventsRaw);
  expect(afterReplay.stateProjection).toBe(beforeReplay.stateProjection);
  expect(afterReplay.sceneProjection).not.toBe(beforeReplay.sceneProjection);
  const transcript=afterReplay.transcriptRaw.trim().split('\n').map(line=>JSON.parse(line));
  expect(transcript).toHaveLength(beforeReplay.transcriptRaw.trim().split('\n').length);
  expect(transcript.at(-1).content).toBe(afterReplay.sceneProjection.trim());
  expect(transcript.at(-1).suggestedActions).toEqual(choices);
  const originalVariant = await store.saveVariant('world','main',2,beforeReplay);
  const staged=await syncWorkSourceArtifacts({projectRoot:root,workId:'world',accept:false,writes:[{relativePath:'works/world/source/notes.md',content:'An unrelated candidate.'}]});
  const notes=staged.artifacts.find(a=>a.revisions.some(r=>r.path==='source/notes.md'))!;
  const stagingDB=createPlayDB(store.runDir('world','main'));
  try{await store.restoreRunSnapshot('world','main',beforeReplay,stagingDB);}finally{stagingDB.close?.();}
  await syncWorkSourceArtifacts({projectRoot:root,workId:'world',accept:false});
  await rm(join(root,'.inkos/harness.sqlite'));
  const restorer = new PlayRunner({projectRoot:root,worldId:'world',runId:'main',agents:{
    openingState:{async extract(){throw new Error('Unexpected model call');}},
    turn:{async run(){throw new Error('Unexpected model call');}},
  }});
  try {
    const restored = await restorer.restoreVariant({turn:2,variantId:originalVariant});
    expect(restored.suggestedActions).toEqual(choices);
    expect(await new PlayStore(root).readPresentation('world','main')).toEqual(beforeReplay.presentation);
    const accepted=await loadWorkManifest(root,'world');
    const scene=accepted.artifacts.find(a=>a.revisions.some(r=>r.path==='source/runs/main/projections/scene.md'))!;
    expect((await readArtifactRevision({projectRoot:root,workId:'world',artifactId:scene.id})).bytes.toString('utf8')).toBe(beforeReplay.sceneProjection);
    expect(accepted.artifacts.find(a=>a.id===notes.id)?.currentRevisionId).toBeNull();
    expect(restored.sceneText).toBe(beforeReplay.presentation?.sceneText);
  } finally { restorer.close(); }
  await edit.execute('choice-policy',{choiceCount:2});
  expect((await store.loadWorld('world'))?.choiceCount).toBe(2);
  const invalid=new PlayRunner({projectRoot:root,worldId:'world',runId:'main',agents:{openingState:{async extract(){throw new Error('Unexpected opening');}},turn:{async run(){return{
    action:PlayActionIntentSchema.parse({actionKind:'wait',intent:'Wait'}),sceneText:'Waited',suggestedActions:['One','Two','Three'],
    mutation:PlayMutationSchema.parse({eventId:'evt-3',turn:3,actionKind:'wait',summary:'Waited',entities:{upsert:[]},edges:{upsert:[],expire:[]},stateSlots:{upsert:[]},evidence:{transitions:[]},blocked:false,blockedReason:'',notes:[]}),
  };}}}});
  try{await expect(invalid.step('Wait')).rejects.toMatchObject({code:'PLAY_CHOICE_COUNT_MISMATCH',expected:2,actual:3});}finally{invalid.close();}
  expect((await store.readEvents('world','main')).length).toBe(2);
 }finally{await rm(root,{recursive:true,force:true});}
});
