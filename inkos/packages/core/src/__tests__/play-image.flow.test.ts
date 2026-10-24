import{Type}from'@sinclair/typebox';
import{createServer}from'node:http';import{once}from'node:events';import{mkdtemp,readFile,writeFile,rm}from'node:fs/promises';
import{tmpdir}from'node:os';import{join}from'node:path';import{createHash}from'node:crypto';import{it,expect,vi}from'vitest';
import{PlayCurrentStateSchema}from'../models/play.js';
import{saveSecrets}from'../llm/secrets.js';
import{PlayStore}from'../play/play-store.js';import{playSceneImageKey,readPlayImageManifest,generatePlayImage,playImageContext,buildPlaySceneImagePrompt}from'../play/play-image.js';
import{createPlayImageTool}from'../harness/tools/play-image.js';import{executeExplicitCapabilityTool}from'../harness/explicit-action.js';
import{loadWorkManifest}from'../harness/work-store.js';import{CreativeEpisodeStore}from'../harness/episode-store.js';

it('includes current entity descriptions in image identity and preserves graph input',()=>{
  const world={premise:'A workshop'},scene='A worker carries a toolbox.';
  const original={entities:[{id:'box',type:'item' as const,label:'Toolbox',summary:'Red toolbox',status:'held',createdEventId:'e0',updatedEventId:'manual-edit'}],edges:[]};
  const before=JSON.stringify(original),context=playImageContext(world,original);
  const changed=playImageContext(world,{...original,entities:[{...original.entities[0],summary:'Blue toolbox'}]});
  expect(playSceneImageKey(1,scene,context)).not.toBe(playSceneImageKey(1,scene,changed));
  expect(JSON.parse(context!.visualFacts!).entities[0].summary).toBe(original.entities[0].summary);
  expect(buildPlaySceneImagePrompt(scene,context)).not.toBe(buildPlaySceneImagePrompt(scene,world));
  expect(JSON.stringify(original)).toBe(before);
  const current=playImageContext(world,original,PlayCurrentStateSchema.parse({turn:5,lastSummary:'Work has ended.',timeAdvance:{elapsed:'4 minutes',anchor:'19:31',rationale:'Closing',synchronized:[]},lastEventId:null,blocked:false}));
  expect(current?.currentMoment).toEqual({turn:5,anchor:'19:31',summary:'Work has ended.'});
  expect(playSceneImageKey(1,scene,current)).not.toBe(playSceneImageKey(1,scene,context));
  const transferred=playImageContext(world,{...original,edges:[
    {id:'old',fromId:'actor_player',toId:'box',type:'holds',value:{role:'holding'},visibility:{},validFromEventId:'e0',validUntilEventId:'e4',sourceEventId:'e0'},
    {id:'new',fromId:'caretaker',toId:'box',type:'holds',value:{role:'holding'},visibility:{},validFromEventId:'e4',validUntilEventId:null,sourceEventId:'e4'},
  ]});
  expect(JSON.parse(transferred!.visualFacts!).currentHoldings).toEqual([{holderId:'caretaker',holder:'caretaker',itemId:'box',item:'Toolbox',sinceEventId:'e4'}]);
  expect(playSceneImageKey(1,scene,transferred)).not.toBe(playSceneImageKey(1,scene,context));
});

it('records illustration methods and versioned output, invalidates stale scene images and preserves generation failures',async()=>{
 const root=await mkdtemp(join(tmpdir(),'inkos-play-image-')),requests:Array<{prompt:string;route?:string;reference?:Buffer}>=[];
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64');
 const secondPng=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
 let releaseImage!:()=>void, markPending!:()=>void;
 const imageGate=new Promise<void>(r=>{releaseImage=r;}), imagePending=new Promise<void>(r=>{markPending=r;});
 const briefInputs:any[]=[];
 const server=createServer(async(req,res)=>{const chunks=[];for await(const chunk of req)chunks.push(chunk);const bytes=Buffer.concat(chunks);
  let body:any;
  if(req.headers['content-type']?.startsWith('multipart/form-data')){
   const form=await new Request('http://localhost'+req.url,{method:'POST',headers:{'Content-Type':req.headers['content-type']},body:new Uint8Array(bytes)}).formData();
   const reference=form.get('image') as File;
   body={prompt:String(form.get('prompt')),model:String(form.get('model')),reference:Buffer.from(await reference.arrayBuffer())};
  }else body=JSON.parse(bytes.toString('utf8'));
  if(req.url?.endsWith('/chat/completions')){briefInputs.push(body);res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({choices:[{finish_reason:'tool_calls',message:{tool_calls:[{id:'brief-'+briefInputs.length,type:'function',function:{name:body.tools[0].function.name,arguments:JSON.stringify({prompt:'A worker beside a toolbox. Illustration '+briefInputs.length})}}]}}]}));return;}
  requests.push({...body,route:req.url});
  if(requests.length===3){markPending();await imageGate;}
  res.writeHead(requests.length<=3?200:503,{'Content-Type':'application/json'});res.end(JSON.stringify(requests.length<=3?{data:[{b64_json:(requests.length===1?png:secondPng).toString('base64')}]}:{error:{message:'fixture unavailable'}}));});
 server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  vi.stubEnv('INKOS_COVER_ENDPOINT',`http://127.0.0.1:${(server.address() as {port:number}).port}/v1/images/generations`);
  vi.stubEnv('INKOS_COVER_BASE_URL','');vi.stubEnv('INKOS_COVER_API_KEY','fixture');vi.stubEnv('INKOS_COVER_MODEL','image-fixture');
  await writeFile(join(root,'inkos.json'),JSON.stringify({version:'0.1.0',name:'Illustration flow',llm:{service:'custom',provider:'openai',configSource:'studio',model:'fixture',services:[{service:'custom',name:'Custom',models:['fixture'],baseUrl:`http://127.0.0.1:${(server.address() as {port:number}).port}/v1`,apiFormat:'chat',stream:false}],apiKey:'fixture',baseUrl:`http://127.0.0.1:${(server.address() as {port:number}).port}/v1`,apiFormat:'chat',stream:false}}));
  await saveSecrets(root,{services:{'custom:Custom':{apiKey:'fixture'}}});
  const store=new PlayStore(root),world=await store.createWorld({id:'world',title:'Fixture',premise:'A closed workshop',worldContract:'Wait for player actions',visualContract:'Ink illustration',mode:'guided',language:'en'});
  await store.ensureRun('world','main');await store.saveCurrentState('world','main',{turn:2});await store.writeProjection('world','main','projections/scene.md','A toolbox outside a locked door.');
  const run=(episodeId:string,instruction?:string)=>executeExplicitCapabilityTool({projectRoot:root,workId:'world',episodeId,conversationId:'fixture',binding:{capabilityId:'interactive-world',actionId:'generate_play_image',profileId:'interactive-world',risk:'recoverable-write'},tool:createPlayImageTool(root,'world'),parameters:{target:'scene',instruction}});
  const result=await run('image-ready');expect(result.status).toBe('success');
  const key=playSceneImageKey(2,'A toolbox outside a locked door.',playImageContext(world,{entities:[],edges:[]},await store.loadCurrentState('world','main'))),dir=store.runDir('world','main');
  const manifest=await readPlayImageManifest(dir);expect(manifest[key].status).toBe('ready');
  expect(await readFile(join(dir,'images',manifest[key].file!))).toEqual(png);
  const recordedPrompt=await readFile(join(dir,'images',key+'.request.md'),'utf8');
  expect(createHash('sha256').update(recordedPrompt).digest('hex')).toBe(createHash('sha256').update(requests[0].prompt).digest('hex'));
  const work=await loadWorkManifest(root,'world');expect(work.artifacts.some(a=>a.revisions.some(r=>r.id===a.currentRevisionId&&r.contentType==='image/png'))).toBe(true);
  const beforeState=await store.loadCurrentState('world','main'),beforeScene=await store.readProjection('world','main','projections/scene.md');
  const direction='Closer framing with warm side lighting.';
  await run('image-regenerated',direction);
  const regenerated=await readPlayImageManifest(dir);
  expect(requests[0].route).toBe('/v1/images/generations');
  expect(requests[1].route).toBe('/v1/images/edits');
  expect(requests[1].reference).toEqual(png);
  expect(regenerated[key].file).not.toBe(manifest[key].file);
  expect(await readFile(join(dir,'images',manifest[key].file!))).toEqual(png);
  expect(await readFile(join(dir,'images',regenerated[key].file!))).toEqual(secondPng);
  expect(briefInputs).toHaveLength(2);
  const sourceRequest=await readFile(join(dir,'images',regenerated[key].file!.replace(/\.(png|jpg)$/u,'.source.md')),'utf8');
  expect(sourceRequest).toContain(direction);
  expect(briefInputs[1].messages.findLast((m:any)=>m.role==='user').content).toBe(sourceRequest);
  const imageRequest=await readFile(join(dir,'images',regenerated[key].file!.replace(/\.(png|jpg)$/u,'.request.md')),'utf8');
  expect(imageRequest).toBe(requests[1].prompt);
  expect(await store.loadCurrentState('world','main')).toEqual(beforeState);
  expect(await store.readProjection('world','main','projections/scene.md')).toBe(beforeScene);
  await store.writeProjection('world','main','projections/scene.md','The same toolbox is now inside the open door.');
  const changedKey=playSceneImageKey(2,'The same toolbox is now inside the open door.',playImageContext(world,{entities:[],edges:[]},await store.loadCurrentState('world','main')));expect(changedKey).not.toBe(key);
  const pending=run('image-pending');await imagePending;
  try{
   const advance=await executeExplicitCapabilityTool({projectRoot:root,workId:'world',episodeId:'advance-during-image',binding:{capabilityId:'interactive-world',actionId:'play_step',profileId:'interactive-world',risk:'recoverable-write'},tool:{name:'play_step',label:'Advance world',description:'Fixture transition through the real action lock and artifact adapter',parameters:Type.Object({}),async execute(){await store.saveCurrentState('world','main',{turn:3});await store.writeProjection('world','main','projections/scene.md','The worker leaves the workshop.');return{content:[],details:{workId:'world'}};}},parameters:{}});
   expect(advance.status).toBe('success');
  }finally{releaseImage();}
  const late=await pending;expect(late.artifacts.length).toBeGreaterThan(0);
  expect(late.artifacts.every(a=>a.path?.startsWith('source/runs/main/images/'))).toBe(true);
  expect((await store.loadCurrentState('world','main'))?.turn).toBe(3);
  const pendingManifest=await readPlayImageManifest(dir);expect(pendingManifest[changedKey].status).toBe('ready');
  const newestKey=playSceneImageKey(3,await store.readProjection('world','main','projections/scene.md'),playImageContext(world,{entities:[],edges:[]},await store.loadCurrentState('world','main')));
  expect(pendingManifest[newestKey]).toBeUndefined();
  await expect(run('image-failed')).rejects.toMatchObject({code:'PLAY_IMAGE_GENERATION_FAILED'});
  const after=await readPlayImageManifest(dir);expect(after[key].status).toBe('ready');expect(after[newestKey].status).toBe('failed');
  const failedEdit=await generatePlayImage({root,runDir:dir,key,prompt:'Revise the existing illustration.'});
  expect(failedEdit.status).toBe('failed');
  const retained=(await readPlayImageManifest(dir))[key];
  expect(retained).toMatchObject({status:'ready',file:regenerated[key].file,error:expect.any(String)});
  expect(requests.at(-1)?.reference).toEqual(secondPng);
  expect(await readFile(join(dir,'images',retained.file!))).toEqual(secondPng);
  const episodes=new CreativeEpisodeStore(join(root,'.inkos/harness.sqlite'));
  try{expect(episodes.listEvents('image-ready').find(event=>event.type==='skills-applied')?.payload).toMatchObject({worker:'play-image',skills:[{id:'inkos-play-illustration'}]});expect(episodes.listEvents('image-failed').some(event=>event.type==='episode-failed')).toBe(true);}finally{episodes.close();}
 }finally{releaseImage();vi.unstubAllEnvs();server.closeAllConnections();await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));await rm(root,{recursive:true,force:true});}
},15000);
