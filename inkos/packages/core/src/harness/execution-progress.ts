import type {AgentMessage} from '@mariozechner/pi-agent-core';
import {createHash} from 'node:crypto';
import {actionResultFacts} from './action-observation.js';

/** Exact receipts from tool exchanges. These record actions, never infer task completion. */
export function executionProgress(messages: readonly AgentMessage[], maxChars: number): string {
  const calls=new Map<string,{name:string;arguments:Record<string,unknown>}>();
  const entries:Array<{tool:string;status:'success'|'error';arguments:Record<string,unknown>;resultHash:string;facts?:Record<string,unknown>;execution?:{risk:string;status:string;artifacts:unknown[]}}>=[];
  for(const message of messages){
    if(message.role==='assistant')for(const part of message.content)if(part.type==='toolCall')calls.set(part.id,{name:part.name,arguments:part.arguments});
    if(message.role!=='toolResult')continue;
    const call=calls.get(message.toolCallId);if(!call)continue;
    const args=Object.fromEntries(Object.entries(call.arguments).filter(([key,value])=>['path','bookId','workId','worldId','nodeId','chapterNumber','subdir','format','outputDir','artifactId','revisionId','startLine','lineCount'].includes(key)&&['string','number'].includes(typeof value)));
    const details=message.details as {data?:Record<string,unknown>;hostExecution?:{risk:string;status:string;artifacts:unknown[]}}|undefined;
    const data=(details?.data??details) as Record<string,unknown>|undefined;
    const facts=actionResultFacts(data);
    entries.push({tool:call.name,status:message.isError?'error':'success',arguments:args,resultHash:createHash('sha256').update(JSON.stringify(message.content)).digest('hex').slice(0,16),...(Object.keys(facts).length?{facts}:{}),...(details?.hostExecution?{execution:details.hostExecution}:{})});
  }
  if(!entries.length)return '';
  const readPaths=[...new Set(entries.filter(e=>e.status==='success'&&e.tool.split('__').at(-1)==='read').map(e=>e.arguments.path).filter((p):p is string=>typeof p==='string'))];
  const executions=entries.filter(e=>e.execution);
  const totals={successful:entries.filter(e=>e.status==='success').length,failed:entries.filter(e=>e.status==='error').length,uniqueReadPaths:readPaths.length,
    ...(executions.length?{verifiedActions:executions.length,successfulMutations:executions.filter(e=>e.status==='success'&&e.execution!.status==='success'&&e.execution!.risk!=='read').length}: {})};
  const recent=entries.slice(-8);let paths=readPaths;
  let output=JSON.stringify({scope:'current_user_request',totals,readPaths:paths,recent,truncated:entries.length>recent.length});
  while(output.length>maxChars&&(recent.length||paths.length)){
    if(recent.length)recent.shift();else paths=paths.slice(1);
    output=JSON.stringify({scope:'current_user_request',totals,readPaths:paths,recent,truncated:true});
  }
  return output;
}
