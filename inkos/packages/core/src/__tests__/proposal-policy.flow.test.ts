import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { expect, it } from 'vitest';
import { Value } from '@sinclair/typebox/value';
import { createProductionCapabilityRegistry } from '../harness/production-capabilities.js';
import { createBuiltInWorkProfileRegistry } from '../harness/builtin-profiles.js';
import { createCapabilityPiTools } from '../harness/pi-tools.js';
import { CreativeHarnessRuntime, ActionConfirmationRequiredError } from '../harness/runtime.js';
import { CreativeEpisodeStore } from '../harness/episode-store.js';
import { PipelineRunner } from '../pipeline/runner.js';

it('offers confirmations only when the same execution policy requires them', async () => {
  const root = await mkdtemp(join(tmpdir(), 'inkos-proposal-policy-'));
  let ledger: CreativeEpisodeStore | undefined;
  try {
    const profiles = createBuiltInWorkProfileRegistry(root);
    const script = profiles.require('script');
    const guarded = {...script,id:'guarded-script',confirmation:{...script.confirmation,inferredMutation:'confirm' as const}};
    await mkdir(join(root,'.inkos/profiles'),{recursive:true});
    await writeFile(join(root,'.inkos/profiles/guarded-script.json'),JSON.stringify(guarded));
    const pipeline = new PipelineRunner({client:{} as never,model:'unused',projectRoot:root});
    const environment = {pipeline,projectRoot:root,sessionId:'policy',profileId:'script',work:null,language:'en',playWorldExists:false,sameSessionProposal:false,allowSystemFileRead:false};
    const direct = createProductionCapabilityRegistry(environment);
    ledger = new CreativeEpisodeStore(join(root,'.inkos/harness.sqlite'));
    const runtime = new CreativeHarnessRuntime(root,direct,profiles,ledger);
    const handle = runtime.startEpisode({profileId:'script',work:null});
    const tools = createCapabilityPiTools({registry:direct,profile:script,executeAction:(capabilityId,actionId,parameters)=>runtime.executeAction({handle,capabilityId,actionId,parameters,source:'agent'})});
    expect(tools.some(tool=>tool.name==='workspace__propose_action')).toBe(false);
    await tools.find(tool=>tool.name==='workspace__create_work')!.execute('create',{workId:'direct',profileId:'storyboard',title:'Direct work',intent:'One shot.'});
    runtime.finishEpisode(handle,'completed');

    const guardedRegistry = createProductionCapabilityRegistry({...environment,profileId:guarded.id});
    const guardedRuntime = new CreativeHarnessRuntime(root,guardedRegistry,createBuiltInWorkProfileRegistry(root),ledger);
    const guardedHandle = guardedRuntime.startEpisode({profileId:guarded.id,work:null});
    const create = {handle:guardedHandle,capabilityId:'workspace',actionId:'create_work',source:'agent' as const,parameters:{workId:'guarded',profileId:'script',title:'Guarded work',intent:'One scene.'}};
    await expect(guardedRuntime.executeAction(create)).rejects.toBeInstanceOf(ActionConfirmationRequiredError);
    const proposal = guardedRegistry.resolve('workspace','propose_action').action;
    const args = {action:'script_create',title:'Create script',summary:'Create the requested scene.',instruction:'Create one scene.',scriptCreate:{title:'Guarded work'}};
    expect(Value.Check(proposal.parameters,args)).toBe(true);
    expect((await guardedRuntime.executeAction({handle:guardedHandle,capabilityId:'workspace',actionId:'propose_action',source:'agent',parameters:args})).data).toMatchObject({kind:'proposed_action',action:'script_create'});
    await expect(guardedRuntime.executeAction({...create,confirmed:true})).resolves.toMatchObject({status:'success'});
    guardedRuntime.finishEpisode(guardedHandle,'completed');

  } finally {ledger?.close();await rm(root,{recursive:true,force:true});}
});
