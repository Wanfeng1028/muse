import { createHash } from "node:crypto";
import { loadTranslationManifest, loadTranslationChapter, loadTranslationGlossary } from "./run-store.js";
import { syncWorkSourceArtifacts } from "../harness/source-sync.js";
import type { TranslationModelPort } from "./types.js";

export async function reviseTranslationSegment(projectRoot:string,projectId:string,options:{
  readonly chapterNumber:number;readonly paragraph:number|"last";
  readonly instruction:string;readonly model:TranslationModelPort;
}){
  if(options.paragraph!=="last"&&(!Number.isInteger(options.paragraph)||options.paragraph<1))throw Object.assign(new Error("Select last or a paragraph number starting at 1"),{code:"TRANSLATION_PARAGRAPH_REQUIRED"});
  const manifest=await loadTranslationManifest(projectRoot,projectId);
  const info=manifest.chapters.find(chapter=>chapter.number===options.chapterNumber);
  if(!info)throw Object.assign(new Error("Translation chapter not found"),{code:"TRANSLATION_CHAPTER_NOT_FOUND"});
  const source=await loadTranslationChapter(projectRoot,info.sourcePath);
  const chapter=await loadTranslationChapter(projectRoot,info.translatedPath);
  const paragraphNumber=options.paragraph==="last"?source.segments.length:options.paragraph;
  const sourceSegment=source.segments[paragraphNumber-1];
  if(!sourceSegment)throw Object.assign(new Error("Translation source paragraph not found"),{code:"TRANSLATION_SEGMENT_NOT_FOUND"});
  const current=chapter.segments.find(segment=>segment.index===sourceSegment.index);
  if(!current?.target?.trim())throw Object.assign(new Error("Translate the target paragraph before revising it"),{code:"TRANSLATION_TARGET_MISSING"});
  if(!options.model.reviseSegment)throw Object.assign(new Error("Translation model has no revision method"),{code:"TRANSLATION_REVISION_UNAVAILABLE"});
  const position=source.segments.findIndex(segment=>segment.index===sourceSegment.index);
  const neighbors=source.segments.slice(Math.max(0,position-1),position+2).filter(segment=>segment.index!==sourceSegment.index).map(segment=>({
    ...segment,target:chapter.segments.find(current=>current.index===segment.index)?.target,
  }));
  const {target}=await options.model.reviseSegment({
    sourceLanguage:manifest.sourceLanguage,targetLanguage:manifest.targetLanguage,chapterTitle:chapter.title,
    segment:{...sourceSegment,target:current.target},neighbors,glossary:await loadTranslationGlossary(projectRoot,projectId),instruction:options.instruction,
  });
  if(!target.trim())throw Object.assign(new Error("A revised paragraph cannot be empty"),{code:"TRANSLATION_TARGET_EMPTY"});
  const nextTarget=target.trim(),changed=nextTarget!==current.target;
  if(changed){
    const nextChapter={...chapter,segments:chapter.segments.map(segment=>segment.index===current.index?{...segment,target:nextTarget}:segment)};
    const nextManifest={...manifest,updatedAt:new Date().toISOString(),chapters:manifest.chapters.map(chapter=>chapter.number===info.number?{...chapter,reviewSummary:undefined,observations:undefined}:chapter)};
    await syncWorkSourceArtifacts({projectRoot,workId:projectId,accept:true,writes:[
      {relativePath:info.translatedPath,content:JSON.stringify(nextChapter,null,2)+"\n"},
      {relativePath:`works/${projectId}/source/manifest.json`,content:JSON.stringify(nextManifest,null,2)+"\n"},
    ]});
  }
  const hash=(text:string)=>"sha256:"+createHash("sha256").update(text).digest("hex");
  const excerpt=(text:string)=>text.slice(0,400);
  return {projectId,chapterNumber:info.number,paragraphNumber,paragraphCount:source.segments.length,sourceSegmentIndex:current.index,isLastParagraph:paragraphNumber===source.segments.length,changed,
    previousTargetHash:hash(current.target),targetHash:hash(nextTarget),sourcePreserved:true,otherSegmentsPreserved:true,
    sourceExcerpt:excerpt(sourceSegment.source),previousTargetExcerpt:excerpt(current.target),targetExcerpt:excerpt(nextTarget),
    reviewRequired:changed,exportRequired:changed};
}
