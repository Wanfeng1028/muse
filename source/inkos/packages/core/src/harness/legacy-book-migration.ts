import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {isDeepStrictEqual} from 'node:util';
import yaml from 'js-yaml';
import {BookConfigSchema} from '../models/book.js';
import {BookRulesSchema} from '../models/book-rules.js';
import {ChapterMetaSchema} from '../models/chapter.js';
import {LengthTelemetrySchema} from '../models/length-governance.js';
import {StateManifestSchema,CurrentStateStateSchema,CurrentStateFactSchema,HooksStateSchema,HookRecordSchema,ChapterSummariesStateSchema,ChapterSummaryRowSchema} from '../models/runtime-state.js';

/** One-time conversion of v1 book documents; live readers keep the v2 schema. */
export async function migrateLegacyBookDocuments(root:string,names:readonly string[],projectLanguage:unknown) {
  const relevant=names.filter(name=>{
    const path=name.replaceAll('\\','/');
    return ['book.json','chapters/index.json','story/book_rules.md','story/book_rules.json','story/outline/story_frame.md'].includes(path)
      ||(path.startsWith('story/')&&path.includes('/state/')&&path.endsWith('.json'));
  });
  const documents=new Map(await Promise.all(relevant.map(async name=>[name.replaceAll('\\','/'),await readFile(join(root,name),'utf8')] as const)));
  const overrides=new Map<string,string>();
  const put=(name:string,value:unknown)=>{
    const original=documents.get(name);
    if(original!==undefined&&isDeepStrictEqual(JSON.parse(original),value))return;
    overrides.set(name,JSON.stringify(value,null,2)+'\n');
  };
  const raw=JSON.parse(documents.get('book.json')!);
  const metadata=BookConfigSchema.strip().parse({...raw,
    targetChapters:raw.targetChapters===undefined?200:raw.targetChapters,chapterWordCount:raw.chapterWordCount===undefined?3000:raw.chapterWordCount,
    language:raw.language===undefined?projectLanguage??'zh':raw.language,
  });
  put('book.json',metadata);
  if(documents.has('chapters/index.json')){
    const chapters=JSON.parse(documents.get('chapters/index.json')!) as Array<Record<string,any>>;
    put('chapters/index.json',chapters.map(chapter=>ChapterMetaSchema.parse({
      number:chapter.number,title:chapter.title,wordCount:chapter.wordCount===undefined?0:chapter.wordCount,
      createdAt:chapter.createdAt,updatedAt:chapter.updatedAt,provenance:chapter.provenance??'imported',
      observations:chapter.observations??[
        ...(chapter.auditIssues??[]).map((summary:string)=>({code:'legacy-review',summary,evidence:[]})),
        ...(chapter.lengthWarnings??[]).map((summary:string)=>({code:'legacy-length-warning',summary,evidence:[]})),
        ...(chapter.reviewNote?[{code:'legacy-review-note',summary:chapter.reviewNote,evidence:[]}]:[]),
      ],
      ...(chapter.tokenUsage?{tokenUsage:{promptTokens:chapter.tokenUsage.promptTokens??0,completionTokens:chapter.tokenUsage.completionTokens??0,totalTokens:chapter.tokenUsage.totalTokens??0}}:{}),
      ...(chapter.lengthTelemetry?{lengthTelemetry:LengthTelemetrySchema.strip().parse(chapter.lengthTelemetry)}:{}),
    })));
  }

  const rulesMarkdown=documents.get('story/book_rules.md');
  const rulesJson=documents.get('story/book_rules.json');
  if(rulesMarkdown!==undefined||rulesJson!==undefined){
    const frontmatter=(text:string)=>{
      const match=text.trimStart().match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
      return match?{raw:match[1]!,data:yaml.load(match[1]!) as Record<string,unknown>}:undefined;
    };
    let source=rulesJson?JSON.parse(rulesJson):frontmatter(rulesMarkdown??'')?.data??{};
    const shim=rulesMarkdown?.includes('本书规则（兼容指针——已废弃）')||rulesMarkdown?.includes('Book Rules (compat pointer — deprecated)');
    if(shim&&!rulesJson){
      const frame=frontmatter(documents.get('story/outline/story_frame.md')??'');
      if(!frame?.data)throw new Error('Legacy rule pointer has no recoverable story-frame metadata');
      source=frame.data;
      overrides.set('story/book_rules.md','# Book rules\n\n```yaml\n'+frame.raw+'\n```\n');
    }
    const rules=BookRulesSchema.parse({version:'2',
      ...(source.protagonist?{protagonist:{name:source.protagonist.name,personalityLock:source.protagonist.personalityLock??[],behavioralConstraints:source.protagonist.behavioralConstraints??[]}}:{}),
      ...(source.genreLock?{genreLock:{primary:source.genreLock.primary,forbidden:source.genreLock.forbidden??[]}}:{}),
      ...(typeof source.narrativePerson==='string'&&source.narrativePerson.trim()?{narrativePerson:source.narrativePerson}:{}),
      prohibitions:source.prohibitions??[],enableFullCastTracking:source.enableFullCastTracking??false,
      ...(source.fanficMode?{fanficMode:source.fanficMode}:{}),allowedDeviations:source.allowedDeviations??[],
    });
    put('story/book_rules.json',rules);
    if(rulesMarkdown===undefined)overrides.set('story/book_rules.md','# Book rules\n\n```json\n'+JSON.stringify(source,null,2)+'\n```\n');
  }

  for(const [name,text] of documents){
    if(!name.startsWith('story/')||!name.includes('/state/')||!name.endsWith('.json'))continue;
    if(name.endsWith('/state/manifest.json'))put(name,StateManifestSchema.strip().parse(JSON.parse(text)));
    if(name.endsWith('/state/current_state.json')){
      const state=JSON.parse(text);
      put(name,CurrentStateStateSchema.parse({chapter:state.chapter,facts:(state.facts??[]).map((fact:unknown)=>CurrentStateFactSchema.strip().parse(fact))}));
    }
    if(name.endsWith('/state/hooks.json')){
      const state=JSON.parse(text);
      put(name,HooksStateSchema.parse({hooks:(state.hooks??[]).map((hook:Record<string,unknown>)=>HookRecordSchema.strip().parse({...hook,expectedPayoff:hook.expectedPayoff??'',notes:hook.notes??''}))}));
    }
    if(name.endsWith('/state/chapter_summaries.json')){
      const state=JSON.parse(text);
      put(name,ChapterSummariesStateSchema.parse({rows:(state.rows??[]).map((row:Record<string,unknown>)=>ChapterSummaryRowSchema.strip().parse({characters:'',events:'',stateChanges:'',hookActivity:'',mood:'',chapterType:'',...row}))}));
    }
  }
  const required=['story/book_rules.md','story/book_rules.json','story/outline/story_frame.md','story/outline/volume_map.md','chapters/index.json','story/state/manifest.json','story/state/current_state.json','story/state/hooks.json','story/state/chapter_summaries.json'];
  const available=new Set(names.map(name=>name.replaceAll('\\','/')));
  const missing=required.filter(name=>!available.has(name)&&!overrides.has(name));
  return{metadata,overrides,missing};
}
