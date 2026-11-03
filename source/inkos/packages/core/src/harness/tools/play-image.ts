import { relative } from 'node:path';
import { toPosixPath } from '../../utils/posix-path.js';
import { StateManager } from '../../state/manager.js';
import { withWorkMutationScope, runInWorkMutationQueue } from '../../utils/work-mutation-scope.js';
import { syncWorkSourceArtifacts } from '../source-sync.js';
import type { ActionArtifactRef } from '../contracts.js';
import { Type } from '@sinclair/typebox';
import type { AgentTool } from '@mariozechner/pi-agent-core';
import { PlayStore } from '../../play/play-store.js';
import { createPlayDB } from '../../play/play-db-factory.js';
import { buildPlayEntityImagePrompt,buildPlaySceneImagePrompt,playSceneImageKey,generatePlayImage,playImageContext } from '../../play/play-image.js';

const Parameters=Type.Object({target:Type.Union([Type.Literal('entity'),Type.Literal('scene')]),
  entityId:Type.Optional(Type.String()),
  instruction:Type.Optional(Type.String({description:'The requested visual direction for this generation or regeneration, such as lighting, framing, or style. Preserve the current world facts.'}))});
export function createPlayImageTool(root:string,worldId:string,runId='main'):AgentTool<typeof Parameters> & { artifactsCommitted: true; managesWorkLock: true }{
  return {artifactsCommitted:true,managesWorkLock:true,name:'generate_play_image',label:'Generate Play Image',parameters:Parameters,
    description:'Generate or regenerate a scene illustration or entity portrait for the current world. Pass the requested visual changes in instruction. Preserve request and image versions; this does not advance a turn.',
    async execute(_id,params,signal){
      const locked = <T>(task: () => Promise<T>) => runInWorkMutationQueue(`${root}\0${worldId}`, () => withWorkMutationScope(root,worldId,() => new StateManager(root).acquireBookLock(worldId),task));
      const {runDir,key,prompt}=await locked(async()=>{
      signal?.throwIfAborted();
      const store=new PlayStore(root),world=await store.loadWorld(worldId);
      if(!world)throw Object.assign(new Error('Interactive world does not exist'),{code:'PLAY_WORLD_NOT_FOUND'});
      const runDir=store.runDir(worldId,runId),state=await store.loadCurrentState(worldId,runId);
      let key:string,prompt:string;
      if(params.target==='scene'){
        const scene=(await store.readProjection(worldId,runId,'projections/scene.md')).trim();
        if(!scene)throw Object.assign(new Error('There is no current scene to illustrate'),{code:'PLAY_SCENE_REQUIRED'});
        const db=createPlayDB(runDir);
        try{const context=playImageContext(world,db.snapshot(),state);
          key=playSceneImageKey(typeof state?.turn==='number'?state.turn:0,scene,context);
          prompt=buildPlaySceneImagePrompt(scene,context);
        }finally{db.close?.();}
      }else{
        const db=createPlayDB(runDir);
        try{
          const entity=params.entityId?db.getEntity(params.entityId):null;
          if(!entity)throw Object.assign(new Error('Select an existing entity to illustrate'),{code:'PLAY_ENTITY_NOT_FOUND'});
          key=entity.id;prompt=buildPlayEntityImagePrompt(entity,world);
        }finally{db.close?.();}
      }
      if(params.instruction?.trim())prompt+='\n\nRequested visual direction:\n'+params.instruction.trim();
      return {runDir,key,prompt};
      });
      const receipts=new Map<string,ActionArtifactRef>();
      const entry=await generatePlayImage({root,runDir,key,prompt,signal,prepareSceneBrief:params.target==='scene',withCommitLock:locked,commit:async(writes)=>{
        const work=await syncWorkSourceArtifacts({projectRoot:root,workId:worldId,accept:true,episodeId:_id,writes});
        const paths=new Set(writes.map(write=>toPosixPath(relative(`works/${worldId}`,write.relativePath))));
        for(const artifact of work.artifacts){
          const revision=artifact.revisions.find(r=>r.id===artifact.currentRevisionId);
          if(revision&&paths.has(revision.path))receipts.set(artifact.id,{workId:worldId,artifactId:artifact.id,revisionId:revision.id,path:revision.path});
        }
      }});
      if(entry.status!=='ready')throw Object.assign(new Error(entry.error??'Image generation failed'),{code:'PLAY_IMAGE_GENERATION_FAILED',key});
      const url=`/api/v1/play/runs/${encodeURIComponent(worldId)}/${encodeURIComponent(runId)}/images/${encodeURIComponent(entry.file!)}`;
      const data={committedArtifacts:[...receipts.values()],kind:'play_image_generated',workId:worldId,worldId,runId,key,ok:true,...entry,url};
      return {content:[{type:'text',text:`Generated illustration: ${url}`}],details:data};
    }};
}
