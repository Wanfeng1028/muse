import {readArtifactRevision} from './artifact-reader.js';
import {loadWorkManifest} from './work-store.js';
import type {WorkLineage} from './contracts.js';

/** Read one captured inventory of accepted versions, never mutable working files. */
export async function readPinnedParentCanon(projectRoot:string,targetWorkId:string,parentWorkId:string){
  const target=await loadWorkManifest(projectRoot,targetWorkId);
  const targetAt=(path:string)=>target.artifacts.find(a=>a.revisions.some(r=>r.id===a.currentRevisionId&&r.path===path));
  const prior=targetAt('source/story/parent_canon.md');
  if(target.status==='draft'&&prior&&target.lineage.some(s=>s.sourceWorkId===parentWorkId&&s.sourceRevisionId)){
    const source=await readArtifactRevision({projectRoot,workId:targetWorkId,artifactId:prior.id,revisionId:prior.currentRevisionId!});
    return {canon:source.bytes.toString('utf8'),lineage:target.lineage,styleGuide:undefined};
  }
  const bound=targetAt('source/source-material.md');
  if(bound&&target.lineage.some(s=>s.sourceWorkId===parentWorkId&&s.sourceRevisionId)){
    const source=await readArtifactRevision({projectRoot,workId:targetWorkId,artifactId:bound.id,revisionId:bound.currentRevisionId!});
    return {canon:source.bytes.toString('utf8'),lineage:target.lineage,styleGuide:undefined};
  }
  const parent=await loadWorkManifest(projectRoot,parentWorkId);
  const current=parent.artifacts.flatMap(artifact=>{
    const revision=artifact.revisions.find(r=>r.id===artifact.currentRevisionId);
    return revision?[{artifact,revision}]:[];
  });
  const mandatory=['source/story/outline/story_frame.md','source/story/outline/volume_map.md','source/story/book_rules.md'];
  for(const path of mandatory)if(!current.some(item=>item.revision.path===path))throw Object.assign(new Error('The parent requires registered foundation artifacts before canon import.'),{code:'PARENT_SOURCE_NOT_REGISTERED',path});
  const selected=current.filter(({revision:r})=>mandatory.includes(r.path)||(r.path.startsWith('source/story/roles/')&&r.path.endsWith('.md'))
    ||['source/story/current_state.md','source/story/pending_hooks.md','source/story/chapter_summaries.md','source/story/style_guide.md'].includes(r.path));
  if(!selected.some(({revision:r})=>r.path.startsWith('source/story/roles/')))throw Object.assign(new Error('The parent requires registered character cards.'),{code:'PARENT_SOURCE_NOT_REGISTERED'});
  const sources=await Promise.all(selected.map(async({artifact,revision})=>{
    const source=await readArtifactRevision({projectRoot,workId:parentWorkId,artifactId:artifact.id,revisionId:revision.id});
    return {path:revision.path,text:source.bytes.toString('utf8'),lineage:{relation:'derived-from',sourceWorkId:parentWorkId,sourceArtifactId:artifact.id,sourceRevisionId:revision.id} satisfies WorkLineage};
  }));
  return {canon:[`# ${parent.language==='en'?'Parent canon':'正传正典'} — ${parent.title}`,...sources.filter(s=>!s.path.endsWith('/style_guide.md')).map(s=>`## ${s.path}\n\n${s.text}`)].join('\n\n'),
    styleGuide:sources.find(s=>s.path.endsWith('/style_guide.md'))?.text,
    lineage:[...target.lineage.filter(s=>s.sourceWorkId!==parentWorkId),...sources.map(s=>s.lineage)]};
}
