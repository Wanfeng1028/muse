import {createServer} from 'node:http';
import {once} from 'node:events';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {it,expect} from 'vitest';
import {createWorkManifest,saveWorkManifest,syncWorkSourceArtifacts,loadWorkManifest,StateManager} from '@actalk/inkos-core';
import {createStudioServer} from '../api/server.js';

it('preserves a confirmed source revision and chapter bounds through the actual API before a producer failure',async()=>{
 const root=await mkdtemp(join(tmpdir(),'inkos-confirmed-source-'));let calls=0;
 const upstream=createServer(async(req,res)=>{for await(const _chunk of req){}calls++;res.writeHead(401,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Fixture unavailable'}}));});
 upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
 try{
  await mkdir(join(root,'.inkos'));
  const baseUrl=`http://127.0.0.1:${(upstream.address() as {port:number}).port}/v1`;
  await writeFile(join(root,'inkos.json'),JSON.stringify({name:'fixture',version:'0.1.0',language:'en',llm:{defaultModel:'fixture-model',services:[{service:'custom',name:'fixture',baseUrl,apiFormat:'chat',stream:false,models:['fixture-model']}]}}));
  await writeFile(join(root,'.inkos/secrets.json'),JSON.stringify({services:{'custom:fixture':{apiKey:'fixture'}}}));
  await saveWorkManifest(root,createWorkManifest({id:'parent',title:'Gallery',profileId:'longform-novel',language:'en'}));
  await mkdir(join(root,'works/parent/source'),{recursive:true});
  const manuscript='Nora returns the borrowed green map.\n';
  const parent=await syncWorkSourceArtifacts({projectRoot:root,workId:'parent',accept:true,writes:[{relativePath:'works/parent/source/manuscript.md',content:manuscript}]});
  const artifact=parent.artifacts[0]!;
  const source={workId:'parent',artifactId:artifact.id,revisionId:artifact.currentRevisionId!};
  const app=createStudioServer({} as never,root);
  const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const {session}=await(await app.request('/api/v1/sessions',post({sessionKind:'chat'}))).json();
  const response=await app.request('/api/v1/agent',post({sessionId:session.sessionId,sessionKind:'chat',instruction:'Create a parallel story from the registered Gallery source. Keep each chapter between20and30words.',actionSource:'button',requestedIntent:'fanfic_init',actionPayload:{fanficCreate:{title:'parallel',source,language:'en',chapterWordCount:25,minChapterLength:20,maxChapterLength:30}},model:'fixture-model',service:'custom:fixture'}));
  expect(response.status).toBeGreaterThanOrEqual(400);
  expect(calls).toBeGreaterThan(0);
  expect(await new StateManager(root).loadBookConfig('parallel')).toMatchObject({chapterWordCount:25,minChapterLength:20,maxChapterLength:30});
  expect((await loadWorkManifest(root,'parallel')).lineage).toEqual([{relation:'derived-from',sourceWorkId:source.workId,sourceArtifactId:source.artifactId,sourceRevisionId:source.revisionId}]);
  expect(await readFile(join(root,'works/parallel/source/source-material.md'),'utf8')).toBe(manuscript);
 }finally{upstream.closeAllConnections();await new Promise<void>(resolve=>upstream.close(()=>resolve()));await rm(root,{recursive:true,force:true});}
},20000);
