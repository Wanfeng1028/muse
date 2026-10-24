import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, expect, it } from "vitest";
import { migrateLegacyWorks } from "../harness/legacy-migration.js";
import { listWorkManifests, loadWorkManifest } from "../harness/work-store.js";
import { createInitialWorkManifestWrite, syncWorkSourceArtifacts } from "../harness/source-sync.js";
import { StateManager } from "../state/manager.js";
import { loadTranslationManifest, loadTranslationChapter } from "../translation/run-store.js";
import {readBookRules} from '../agents/rules-reader.js';
import {loadRuntimeStateSnapshot,loadRuntimeStateSnapshotAtChapter} from '../state/runtime-state-store.js';
import {NewHookCandidateSchema} from '../models/runtime-state.js';

const roots: string[] = [];
afterEach(async () => { await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))); });

it("upgrades early accepted revisions by their current pointer and preserves the original manifest", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-manifest-upgrade-")); roots.push(root);
  const initial = createInitialWorkManifestWrite({workId:"early",title:"Early",profileId:"script",language:"en",writes:[{relativePath:"works/early/source/script.md",content:"current"}]});
  const artifact = initial.manifest.artifacts[0]!;
  const current = artifact.revisions[0]!;
  const raw = {...initial.manifest,artifacts:[{...artifact,revisions:[
    {...current,id:"old-revision",status:"accepted"},
    {...current,status:"accepted"},
  ]}]};
  await mkdir(join(root,"works/early"),{recursive:true});
  const original = JSON.stringify(raw);
  await writeFile(join(root,"works/early/work.json"),original);
  expect((await migrateLegacyWorks(root))[0]?.status).toBe("ready");
  expect((await migrateLegacyWorks(root,{apply:true}))[0]?.status).toBe("migrated");
  const upgraded = await loadWorkManifest(root,"early");
  expect(upgraded.artifacts[0]?.currentRevisionId).toBe(current.id);
  expect(upgraded.artifacts[0]?.revisions.map((revision)=>revision.status)).toEqual(["superseded","current"]);
  expect(await readFile(join(root,".inkos/migrations/early-accepted-manifest.json"),"utf8")).toBe(original);
  expect(await migrateLegacyWorks(root,{apply:true})).toEqual([]);
});

it("previews and migrates legacy works with readable chapters and translations while preserving originals", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-migration-")); roots.push(root);
  const now = new Date().toISOString();
  const legacy = new Map<string, string>([
    ["books/novel/book.json", JSON.stringify({id:"novel",title:"Novel",platform:"other",genre:"general",status:"active",createdAt:now,updatedAt:now,writing:{reviewMode:"manual",revisionGate:"lenient"}})],
    ["books/novel/chapters/0001_One.md", "# One\n\nOriginal text.\n"],
    ["books/novel/chapters/index.json", JSON.stringify([{number:1,title:"One",wordCount:2,createdAt:now,updatedAt:now,status:"audit-failed",auditIssues:["Legacy observation"],tokenUsage:{totalTokens:12},lengthTelemetry:{target:1000,countingMode:'en_words',writerCount:2,postReviseCount:2,finalCount:2,repairApplied:false,softMin:900,softMax:1100,hardMin:800,hardMax:1200,lengthWarning:true}}])],
    ["translations/translated/manifest.json", JSON.stringify({id:"translated",title:"Translation",sourceLanguage:"en",targetLanguage:"zh",createdAt:now,updatedAt:now,source:{kind:"markdown",path:"input.md",charCount:3},chapters:[{number:1,title:"One",sourcePath:"translations/translated/source/chapter-0001.json",translatedPath:"translations/translated/translated/chapter-0001.json",segmentCount:1,charCount:3,status:"reviewed"}]})],
    ["translations/translated/source/chapter-0001.json", JSON.stringify({number:1,title:"One",sourceLanguage:"en",targetLanguage:"zh",segments:[{index:0,source:"One"}]})],
    ["translations/translated/translated/chapter-0001.json", JSON.stringify({number:1,title:"One",sourceLanguage:"en",targetLanguage:"zh",segments:[{index:0,source:"One",target:"一"}]})],
    ["shorts/short/outline/v001.md", "# Outline"],
    ["dramas/script/script-spec.md", "# Script"],
    ["storyboards/storyboard/storyboard-spec.md", "# Storyboard"],
    ["interactive-films/film/story-graph.json", JSON.stringify({title:"Film"})],
    ["worlds/world/world.json", JSON.stringify({title:"World",mode:"open"})],
    ["worlds/runtime-only/runs/main/state.json", "{}"],
  ]);
  for(const [name,content] of Object.entries({
    'story/outline/story_frame.md':'# Story\nA witness keeps a promise.',
    'story/outline/volume_map.md':'# Volume\nThe next scene follows the first.',
    'story/book_rules.md':"---\nversion: '1.0'\nprotagonist:\n  name: Ada\nprohibitions:\n  - Keep the established promise.\n---\nThe witness decides through action.\n",
    'story/current_state.md':'# Current state\n',
    'story/pending_hooks.md':'# Pending hooks\n',
    'story/state/manifest.json':JSON.stringify({schemaVersion:2,language:'en',lastAppliedChapter:1,projectionVersion:1,migrationWarnings:['old import note']}),
    'story/state/current_state.json':JSON.stringify({chapter:1}),
    'story/state/hooks.json':JSON.stringify({hooks:[{hookId:'promise',startChapter:0,type:'promise',status:'open',lastAdvancedChapter:0,payoffTiming:'slow-burn',promoted:true}]}),
    'story/state/chapter_summaries.json':JSON.stringify({rows:[{chapter:1,title:'One',events:'The witness arrives.'}]}),
    'story/snapshots/0/state/manifest.json':JSON.stringify({schemaVersion:2,language:'en',lastAppliedChapter:0,projectionVersion:1,migrationWarnings:[]}),
    'story/snapshots/0/state/current_state.json':JSON.stringify({chapter:0}),
    'story/snapshots/0/state/hooks.json':JSON.stringify({}),
    'story/snapshots/0/state/chapter_summaries.json':JSON.stringify({}),
  }))legacy.set('books/novel/'+name,content);
  for (const [path, content] of legacy) {
    await mkdir(join(root, path, ".."), {recursive:true}); await writeFile(join(root,path),content);
  }
  await writeFile(join(root,'inkos.json'),JSON.stringify({language:'en'}));
  const preview = await migrateLegacyWorks(root);
  expect(preview.map((x) => x.status)).toEqual(Array(7).fill("ready"));
  expect(await listWorkManifests(root)).toEqual([]);
  const applied = await migrateLegacyWorks(root,{apply:true});
  expect(applied.map((x) => x.status)).toEqual(Array(7).fill("migrated"));
  const config=await new StateManager(root).loadBookConfig('novel');
  expect(config).toMatchObject({targetChapters:200,chapterWordCount:3000,language:'en'});
  expect('writing' in config).toBe(false);
  const rules=await readBookRules(join(root,'works/novel/source'));
  expect(rules.rules).toMatchObject({version:'2',protagonist:{name:'Ada',personalityLock:[],behavioralConstraints:[]},prohibitions:['Keep the established promise.']});
  const runtime=await loadRuntimeStateSnapshot(join(root,'works/novel/source'));
  expect(runtime.manifest.lastAppliedChapter).toBe(1);
  expect(runtime.hooks.hooks[0]).toMatchObject({hookId:'promise',expectedPayoff:'',notes:''});
  expect('promoted' in runtime.hooks.hooks[0]!).toBe(false);
  expect(NewHookCandidateSchema.safeParse({type:'promise',expectedPayoff:'',notes:''}).success).toBe(false);
  expect((await loadRuntimeStateSnapshotAtChapter({bookDir:join(root,'works/novel/source'),chapterNumber:0,language:'en'})).manifest.lastAppliedChapter).toBe(0);
  expect(await listWorkManifests(root)).toHaveLength(7);
  const [chapter] = await new StateManager(root).loadChapterIndex("novel");
  expect({number:chapter?.number,provenance:chapter?.provenance,observation:chapter?.observations[0]?.code})
    .toEqual({number:1,provenance:"imported",observation:"legacy-review"});
  expect(chapter?.tokenUsage).toEqual({promptTokens:0,completionTokens:0,totalTokens:12});
  expect(chapter?.lengthTelemetry).toEqual({target:1000,countingMode:'en_words',writerCount:2,postReviseCount:2,finalCount:2,repairApplied:false});
  const translation = await loadTranslationManifest(root,"translated");
  expect(translation.chapters[0]?.translatedSegments).toBe(1);
  expect((await loadTranslationChapter(root,translation.chapters[0]!.translatedPath)).segments[0]?.target).toBe("一");
  expect((await migrateLegacyWorks(root,{apply:true})).map((x) => x.status)).toEqual(Array(7).fill("already-migrated"));
  for (const [path,content] of legacy) expect(await readFile(join(root,path),"utf8")).toBe(content);
  await mkdir(join(root,"dramas/novel"),{recursive:true});
  await writeFile(join(root,"dramas/novel/script-spec.md"),"# Collision");
  expect((await migrateLegacyWorks(root,{apply:true,source:"dramas/novel"}))[0]?.status).toBe("conflict");
  expect(await readFile(join(root,"works/novel/source/chapters/0001_One.md"),"utf8")).toBe(legacy.get("books/novel/chapters/0001_One.md"));
  // Recover a Work copied by an earlier 2.0 migration without rewriting the
  // retained v1 source or losing the unconverted artifact revision.
  const oldConfig=legacy.get('books/novel/book.json')!;
  const oldWork=await syncWorkSourceArtifacts({projectRoot:root,workId:'novel',accept:true,writes:[{relativePath:'works/novel/source/book.json',content:oldConfig}]});
  const oldArtifact=oldWork.artifacts.find(a=>a.revisions.some(r=>r.path==='source/book.json'))!;
  expect((await migrateLegacyWorks(root,{apply:true,source:'books/novel'}))[0]?.status).toBe('migrated');
  expect(await new StateManager(root).loadBookConfig('novel')).toEqual(config);
  const repaired=await loadWorkManifest(root,'novel');
  const retained=repaired.artifacts.find(a=>a.id===oldArtifact.id)!.revisions.find(r=>r.id===oldArtifact.currentRevisionId)!;
  expect(await readFile(join(root,'works/novel',retained.snapshotPath!),'utf8')).toBe(oldConfig);
  expect(await readFile(join(root,'books/novel/book.json'),'utf8')).toBe(oldConfig);
  await mkdir(join(root,'books/broken'),{recursive:true});
  await writeFile(join(root,'books/broken/book.json'),JSON.stringify({id:'broken',title:'Incomplete fixture'}));
  expect((await migrateLegacyWorks(root,{apply:true,source:'books/broken'}))[0]?.status).toBe('invalid');
  expect((await listWorkManifests(root)).some(w=>w.id==='broken')).toBe(false);
});
