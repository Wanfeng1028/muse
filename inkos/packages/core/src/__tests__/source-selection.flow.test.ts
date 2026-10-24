import {createServer} from 'node:http';
import {once} from 'node:events';
import {mkdir,mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {it,expect,vi} from 'vitest';
import {ComposerAgent} from '../agents/composer.js';
import {createLLMClient} from '../llm/provider.js';
import {createInitialRuntimeState} from '../state/runtime-state-store.js';
import {withExecutionEvidence} from '../harness/execution-evidence.js';
import {StateManager} from '../state/manager.js';
import {createWorkManifest,saveWorkManifest} from '../harness/work-store.js';
import {PipelineRunner} from '../pipeline/runner.js';
import {WriterAgent} from '../agents/writer.js';
import {savePersistedPlan} from '../pipeline/persisted-governed-plan.js';

it('keeps the complete source corpus without a model dependency when it fits, and selects semantically when it does not',async()=>{
  const root=await mkdtemp(join(tmpdir(),'inkos-complete-context-'));
  const bookDir=join(root,'works/story/source');
  let calls=0;
  const server=createServer(async(request,response)=>{
    const chunks:Buffer[]=[];for await(const chunk of request)chunks.push(Buffer.from(chunk));
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    calls++;
    response.writeHead(200,{'Content-Type':'application/json'});
    response.end(JSON.stringify({choices:[{finish_reason:'tool_calls',message:{tool_calls:[{id:'selection-'+calls,type:'function',function:{name:body.tools[0].function.name,arguments:JSON.stringify({selectedIndices:[1]})}}]}}]}));
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  try{
    await createInitialRuntimeState({bookDir,language:'en'});
    await mkdir(join(bookDir,'story/outline'),{recursive:true});
    await mkdir(join(bookDir,'story/roles/major'),{recursive:true});
    const files={
      'outline/story_frame.md':'# Departure\nThe witness leaves.\n# Return\nThe witness returns.',
      'outline/volume_map.md':'# Before\nA missing letter.\n# After\nAn opened letter.',
      'roles/major/é.md':'The witness keeps the letter.',
      'roles/major/李.md':'The neighbour knows the sender.',
      'volume_summaries.md':'## Earlier\nA letter was hidden.\n## Later\nIts recipient was found.',
    };
    for(const [path,content] of Object.entries(files))await writeFile(join(bookDir,'story',path),content);
    await writeFile(join(bookDir,'story/state/current_state.json'),JSON.stringify({chapter:0,facts:['witness','neighbour'].map(subject=>({subject,predicate:'location',object:'station',validFromChapter:0,validUntilChapter:null,sourceChapter:0}))}));
    const client=createLLMClient({service:'custom',provider:'openai',configSource:'studio',model:'fixture',apiKey:'fixture',baseUrl:`http://127.0.0.1:${(server.address() as {port:number}).port}/v1`,apiFormat:'chat',stream:false,thinkingBudget:0,temperature:0});
    const composer=new ComposerAgent({client,model:'fixture',projectRoot:root});
    const goal='Continue the story.';
    const plan={intent:{chapter:2,goal},memo:{chapter:2,goal,body:goal,threadRefs:[]},intentMarkdown:goal,runtimePath:'runtime/chapter-2.intent.md',plannerInputs:[]};
    const book={id:'story',title:'Story',genre:'general',platform:'other' as const,status:'active' as const,targetChapters:3,chapterWordCount:1000,language:'en' as const,createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()};
    const events:Array<{type:string,payload:Record<string,unknown>}>=[];
    const complete=await withExecutionEvidence((type,payload)=>events.push({type,payload}),()=>composer.composeChapter({book,bookDir,chapterNumber:2,plan,contextBudget:{contextWindowTokens:100000,reservedOutputTokens:1000}}));
    expect(calls).toBe(0);
    expect(complete.contextPackage.selectedContext).toHaveLength(11);
    expect(complete.contextPackage.selectedContext.filter(entry=>entry.source.startsWith('story/roles/')).map(entry=>entry.source)).toEqual(['story/roles/major/é.md','story/roles/major/李.md']);
    expect(complete.trace.retrieval).toMatchObject({selectionMode:'complete',semanticSelectedIds:[]});
    expect(complete.trace.retrieval?.candidates).toHaveLength(2);
    expect(JSON.parse(await readFile(complete.contextPath,'utf8'))).toEqual(complete.contextPackage);
    expect(JSON.parse(await readFile(complete.tracePath,'utf8'))).toEqual(complete.trace);
    expect(events).toEqual([expect.objectContaining({type:'context-selection',payload:expect.objectContaining({mode:'complete',sourceCount:11,modelCalls:0})})]);
    const selected=await composer.selectTaskContext({bookDir,chapterNumber:2,goal,language:'en',contextBudget:{contextWindowTokens:1001,reservedOutputTokens:1000}});
    expect(calls).toBe(5);
    expect(selected.selectedContext).toHaveLength(6);
    const completeSources=new Set(complete.contextPackage.selectedContext.map(entry=>entry.source));
    expect(selected.selectedContext.every(entry=>completeSources.has(entry.source))).toBe(true);
    await saveWorkManifest(root,createWorkManifest({id:book.id,title:book.title,profileId:'longform-novel',language:'en'}));
    const state=new StateManager(root);
    await state.saveBookConfig(book.id,book);
    await state.saveChapterIndex(book.id,[]);
    await writeFile(join(bookDir,'story/book_rules.md'),'# Rules\nPreserve established facts.\n');
    await writeFile(join(bookDir,'story/book_rules.json'),JSON.stringify({version:'2',prohibitions:[],enableFullCastTracking:false,allowedDeviations:[]}));
    await savePersistedPlan(bookDir,{...plan,intent:{chapter:1,goal},memo:{chapter:1,goal,body:goal,threadRefs:[]}});
    // Stop at the external writing boundary; the real pipeline must persist and
    // deliver the complete governed context without another selection call.
    const writer=vi.spyOn(WriterAgent.prototype,'writeChapter').mockRejectedValue(Object.assign(new Error('Writing boundary reached'),{code:'WRITER_BOUNDARY'}));
    await expect(new PipelineRunner({projectRoot:root,client,model:'fixture'}).writeChapters(book.id,1,{startChapterNumber:1})).rejects.toMatchObject({code:'WRITER_BOUNDARY'});
    expect(calls).toBe(5);
    expect(new Set(writer.mock.calls[0]![0].contextPackage?.selectedContext.map(entry=>entry.source))).toEqual(new Set([...completeSources,'story/current_focus.md','story/author_intent.md']));
    const pipelineTrace=JSON.parse(await readFile(join(bookDir,'story/runtime/chapter-0001.trace.json'),'utf8'));
    expect(pipelineTrace.retrieval).toMatchObject({selectionMode:'complete',semanticSelectedIds:[]});
    expect(await state.loadChapterIndex(book.id)).toEqual([]);
  }finally{vi.restoreAllMocks();server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));await rm(root,{recursive:true,force:true});}
},20000);

it('selects a source by its bounded candidate number while preserving its exact external identifier',async()=>{
  const root=await mkdtemp(join(tmpdir(),'inkos-source-selection-'));
  let calls=0;
  const server=createServer(async(request,response)=>{
    const chunks:Buffer[]=[];for await(const chunk of request)chunks.push(Buffer.from(chunk));
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const name=body.tools[0].function.name;
    const result={selectedIndices:++calls===1?[3]:[2]};
    response.writeHead(200,{'Content-Type':'application/json'});
    response.end(JSON.stringify({choices:[{finish_reason:'tool_calls',message:{tool_calls:[{id:'selection-'+calls,type:'function',function:{name,arguments:JSON.stringify(result)}}]}}]}));
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  try{
    const client=createLLMClient({service:'custom',provider:'openai',configSource:'studio',model:'fixture',apiKey:'fixture',baseUrl:`http://127.0.0.1:${(server.address() as {port:number}).port}/v1`,apiFormat:'chat',stream:false,thinkingBudget:0,temperature:0});
    const sources=['notes/é/晴#1','notes/é/睛#2'];
    const result=await new ComposerAgent({client,model:'fixture',projectRoot:root}).selectOutlineSections({fileName:'notes.md',kind:'current-state',chapterNumber:3,goal:'Select the second observation.',outlineNode:'',language:'en',candidates:sources.map((source,index)=>({source,heading:'Observation '+index,excerpt:'Source evidence '+index}))});
    expect(result).toEqual([sources[1]]);
    expect(calls).toBe(2);
  }finally{server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));await rm(root,{recursive:true,force:true});}
},15000);
