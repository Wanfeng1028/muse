import type {WorkManifest,WorkProfile} from './contracts.js';

/** Storage namespaces maintained by the corresponding domain operations.
 * Other artifacts remain editable when capabilities are combined in a Work. */
export function artifactDomainOwner(work:WorkManifest,path:string,profile:WorkProfile):string|undefined{
  if(profile.capabilityIds.includes('longform')
    &&(path==='source/book.json'||path.startsWith('source/story/')||path.startsWith('source/chapters/')))return 'longform';
  if(profile.capabilityIds.includes('interactive-world')
    &&(path==='source/world.json'||path.startsWith('source/runs/')))return 'interactive-world';
  if(profile.artifactSchemas[path]==='story-graph')return 'interactive-film';
  if(profile.capabilityIds.includes('interactive-film')){
    if(['source/brief.md','source/story-graph.json','source/authoring-state.json','source/delivery-requirements.json','source/interactive-spec.md','source/story-tree.md','source/flags.json','source/flags.md'].includes(path)
      ||path.startsWith('source/snapshots/'))return 'interactive-film';
    // The film bundle's script and images are projections of its interactive
    // spec. A separate script in a composed profile has no such source spec.
    const filmBundle=work.artifacts.some(artifact=>artifact.revisions.some(revision=>revision.id===artifact.currentRevisionId&&revision.path==='source/interactive-spec.md'));
    if(filmBundle&&['source/script.md','source/storyboard.md','source/image-prompts.md','source/assets.json'].includes(path))return 'interactive-film';
  }
  return undefined;
}

export function assertGenericArtifactEditable(work:WorkManifest,path:string,profile:WorkProfile):void{
  const owner=artifactDomainOwner(work,path,profile);
  if(owner)throw Object.assign(new Error(`This artifact is maintained by ${owner} operations; use its domain edit action to preserve associated state.`),{
    code:'ARTIFACT_DOMAIN_ACTION_REQUIRED',path,capabilityId:owner,
    recovery:{action:'workspace__inspect_work',parameters:{workId:work.id},reason:`Select the ${owner} operation for this artifact. Other independent text artifacts remain editable.`},
  });
}
