import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtemp, rm, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createFillNodeTool, createReviseNodeTool, type FilmLLMDeps } from "../agent/film-authoring-tools.js";
import { loadStoryGraph } from "../interactive-film/graph-store.js";
import { saveStoryGraph } from "../interactive-film/graph-store.js";
import { StoryGraphSchema, StoryNodeSchema } from "../interactive-film/graph-schema.js";
import {createServer} from 'node:http';
import {once} from 'node:events';
import {createLLMClient} from '../llm/provider.js';
import {filmLLMDepsFromClient} from '../agent/film-authoring-tools.js';
import {createWorkManifest,saveWorkManifest} from '../harness/work-store.js';

const node = StoryNodeSchema.parse({
  id: "n1",
  type: "branch",
  title: "抉择",
  sceneDesc: "宫门前",
  dialogue: [{ speaker: "阿梅", text: "账不能错", emotion: "坚定" }],
  choices: [{ id: "a", text: "公开", targetNodeId: "e" }],
});

function filmDeps(overrides: Partial<FilmLLMDeps> = {}): FilmLLMDeps {
  return {
    submitNode: async (_system, _user, nodeId) => ({ ...node, id: nodeId }),
    submitStructure: async () => [],
    ...overrides,
  };
}

describe("fill_node tool (stubbed LLM)", () => {
  let root: string;
  beforeEach(async () => {
    root = await mkdtemp(join(tmpdir(), "if-llm-"));
    await mkdir(join(root, "works", "p", "source"), { recursive: true });
    await saveStoryGraph(root, "p", StoryGraphSchema.parse({ schemaVersion: 1, projectId: "p", title: "T", variables: [], nodes: [{ id: "n1", type: "branch", choices: [] }, { id: "e", type: "ending", choices: [] }], endings: [] }));
  });
  afterEach(async () => { await rm(root, { recursive: true, force: true }); });

  it("fills a node from stubbed LLM text and persists it", async () => {
    const tool = createFillNodeTool(root, "p", filmDeps({
      skillIds: () => ["inkos-interactive-film"],
    }));
    const result = await tool.execute("call-1", { nodeId: "n1", instruction: "写抉择场景" } as never);
    const g = await loadStoryGraph(root, "p");
    expect(g?.nodes.find(n => n.id === "n1")?.dialogue?.[0].speaker).toBe("阿梅");
    expect(result.details).toMatchObject({ skillIds: ["inkos-interactive-film"] });
  });

});

describe("revise_node tool (stubbed LLM)", () => {
  let root: string;
  beforeEach(async () => {
    root = await mkdtemp(join(tmpdir(), "if-llm-rv-"));
    await mkdir(join(root, "works", "p", "source"), { recursive: true });
    await saveStoryGraph(root, "p", StoryGraphSchema.parse({
      schemaVersion: 1, projectId: "p", title: "T", variables: [],
      nodes: [
        { id: "n1", type: "branch", sceneDesc: "旧场景", dialogue: [{ speaker: "旧人", text: "旧台词", emotion: "平静" }], choices: [] },
        { id: "e", type: "ending", choices: [] },
      ],
      endings: [],
    }));
  });
  afterEach(async () => { await rm(root, { recursive: true, force: true }); });

  it("revises a node via stubbed LLM text and persists updated dialogue", async () => {
    const revised = StoryNodeSchema.parse({
      id: "n1",
      type: "branch",
      title: "修改后",
      sceneDesc: "新场景",
      dialogue: [{ speaker: "新人", text: "新台词", emotion: "激动" }],
      choices: [{ id: "c1", text: "继续", targetNodeId: "e" }],
    });
    const tool = createReviseNodeTool(root, "p", filmDeps({
      submitNode: async (_system, _user, nodeId) => ({ ...revised, id: nodeId }),
    }));
    await tool.execute("call-2", { nodeId: "n1", instruction: "改写", fields: ["sceneDesc", "dialogue"] });
    const g = await loadStoryGraph(root, "p");
    const updated = g?.nodes.find(n => n.id === "n1");
    expect(updated?.dialogue?.[0].speaker).toBe("新人");
    expect(updated?.sceneDesc).toBe("新场景");
  });

  it('sends complete state contracts and accepts only the editable prose fields through the real worker boundary',async()=>{
    await saveWorkManifest(root,createWorkManifest({id:'p',title:'Control room',profileId:'interactive-film',language:'en'}));
    const graph=StoryGraphSchema.parse({schemaVersion:1,projectId:'p',title:'Control room',variables:[{name:'power',type:'boolean',default:false,desc:'Whether the relay is powered.'}],nodes:[
      {id:'arrival',type:'start',sceneDesc:'The owner left an instruction beside the entrance.',dialogue:[{speaker:'Owner',text:'The west relay belongs to the night crew.',emotion:'calm'}],choices:[{id:'enter',text:'Enter the hallway',targetNodeId:'s'}]},
      {id:'s',type:'branch',sceneDesc:'The operator reaches the relay.',choices:[{id:'switch',text:'Power the relay',targetNodeId:'n1',effects:[{var:'power',op:'set',value:true}]}]},
      {id:'n1',type:'branch',title:'Relay',act:'One',sceneDesc:'The relay is quiet.',dialogue:[],choices:[{id:'leave',text:'Leave',targetNodeId:'e',condition:{var:'power',op:'==',value:true}}],imageSlot:{prompt:'A relay'},position:{x:1,y:2}},
      {id:'e',type:'ending',sceneDesc:'The operator leaves.',choices:[]},
    ]});await saveStoryGraph(root,'p',graph);
    const requests:any[]=[];
    const replacement={sceneDesc:'The relay cabinet is closed.',dialogue:[{speaker:'Operator',text:'The relay is powered.',emotion:'calm',condition:{var:'power',op:'==',value:true}}]};
    const server=createServer(async(req,res)=>{const chunks:Buffer[]=[];for await(const chunk of req)chunks.push(Buffer.from(chunk));const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));requests.push(body);const name=body.tools[0].function.name;const selected=JSON.parse(body.messages.find((m:any)=>m.role==='user').content).fields as Array<keyof typeof replacement>;const result=Object.fromEntries(selected.map(field=>[field,replacement[field]]));res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({choices:[{finish_reason:'tool_calls',message:{tool_calls:[{id:'edit',type:'function',function:{name,arguments:JSON.stringify(result)}}]}}]}));});
    server.listen(0,'127.0.0.1');await once(server,'listening');
    try{
      const client=createLLMClient({service:'custom',provider:'openai',configSource:'studio',model:'fixture',apiKey:'fixture',baseUrl:`http://127.0.0.1:${(server.address() as {port:number}).port}/v1`,apiFormat:'chat',stream:false,temperature:0,thinkingBudget:0});
      const tool=createReviseNodeTool(root,'p',filmLLMDepsFromClient(client,'fixture'),'en');
      await tool.execute('edit',{nodeId:'n1',fields:['dialogue'],instruction:'Clarify only the dialogue.'});
      expect(requests).toHaveLength(1);
      expect(requests[0].tools[0].function.parameters.required).toEqual(['dialogue']);
      expect(requests[0].tools[0].function.parameters.properties).not.toHaveProperty('sceneDesc');
      const submitted=JSON.parse(requests[0].messages.find((m:any)=>m.role==='user').content);
      expect(submitted.context.variables).toEqual(graph.variables);
      expect(submitted.context.nodes).toEqual(graph.nodes);
      expect(submitted.targetNodeId).toBe('n1');
      const dialogueOnly={...graph,nodes:graph.nodes.map(n=>n.id==='n1'?{...n,dialogue:replacement.dialogue}:n)};
      expect(await loadStoryGraph(root,'p')).toEqual(dialogueOnly);
      await tool.execute('describe',{nodeId:'n1',fields:['sceneDesc'],instruction:'Clarify only the setting.'});
      expect(requests).toHaveLength(2);
      expect(requests[1].tools[0].function.parameters.required).toEqual(['sceneDesc']);
      expect(requests[1].tools[0].function.parameters.properties).not.toHaveProperty('dialogue');
      expect(await loadStoryGraph(root,'p')).toEqual({...graph,nodes:graph.nodes.map(n=>n.id==='n1'?{...n,...replacement}:n)});
    }finally{server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));}
  },20000);
});
