import { access } from 'node:fs/promises';
import { join } from 'node:path';
import { Type } from '@sinclair/typebox';
import type { AgentTool } from '@mariozechner/pi-agent-core';
import { PlayStore } from '../../play/play-store.js';
import { createPlayDB } from '../../play/play-db-factory.js';

const Parameters=Type.Object({});
export function createInspectPlayStateTool(root:string,worldId:string):AgentTool<typeof Parameters>{
  return {name:'inspect_play_state',label:'Inspect Play State',parameters:Parameters,
    description:'Read the current interactive world, exact entity IDs, current status, active relationships and state slots before editing. This does not advance a turn.',
    async execute(){
      const store=new PlayStore(root),world=await store.loadWorld(worldId);
      if(!world)throw Object.assign(new Error('Interactive world does not exist'),{code:'PLAY_WORLD_NOT_FOUND'});
      const runDir=store.runDir(worldId,'main');
      await access(join(runDir,'play.db'));
      const db=createPlayDB(runDir);
      try{
        const graph=db.snapshot(),currentState=await store.loadCurrentState(worldId,'main');
        const data={kind:'play_state_inspected',workId:worldId,runId:'main',currentState,
          currentPresentation:await store.readPresentation(worldId,'main'),
          entities:graph.entities.map(({id,type,label,status,summary})=>({id,type,label,status,summary})),
          activeEdges:graph.edges.filter(edge=>edge.validUntilEventId==null),stateSlots:graph.stateSlots,
          latestEvent:graph.events.at(-1)??null};
        return {content:[{type:'text',text:JSON.stringify(data)}],details:data};
      }finally{db.close?.();}
    }};
}
