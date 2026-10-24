import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { WorkManifestSchema, WorkResourceIdSchema } from "./contracts.js";
import { createInitialWorkManifestWrite, syncWorkSourceArtifacts } from "./source-sync.js";
import { loadWorkManifest, saveWorkManifest } from "./work-store.js";
import { commitAtomicFileSet, type AtomicFileWrite } from "../utils/atomic-file-set.js";
import { TranslationProjectManifestSchema } from "../translation/types.js";
import {migrateLegacyBookDocuments} from './legacy-book-migration.js';

const SOURCES = [
  ["books", "longform-novel", "book.json"],
  ["shorts", "short-fiction", "outline"],
  ["dramas", "script", "script-spec.md"],
  ["storyboards", "storyboard", "storyboard-spec.md"],
  ["interactive-films", "interactive-film", "story-graph.json"],
  ["worlds", "interactive-world", "world.json"],
  ["translations", "translation", "manifest.json"],
] as const;

export interface LegacyMigrationItem {
  readonly source: string;
  readonly workId: string;
  readonly profileId: string;
  readonly status: "ready" | "migrated" | "already-migrated" | "conflict" | "invalid";
  readonly fileCount?: number;
  readonly error?: string;
}

async function entries(path: string) {
  try { return await readdir(path, { withFileTypes: true }); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

async function files(root: string, relative = ""): Promise<string[]> {
  const result: string[] = [];
  for (const entry of await entries(join(root, relative))) {
    if (entry.name.startsWith(".") || entry.name === "node_modules") continue;
    const path = join(relative, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Legacy asset is a symlink: ${path}`);
    if (entry.isDirectory()) result.push(...await files(root, path));
    else if (entry.isFile()) result.push(path);
  }
  return result;
}

/** Copies legacy assets into canonical Works; original directories are retained. */
export async function migrateLegacyWorks(
  projectRoot: string,
  options: { readonly apply?: boolean; readonly source?: string } = {},
): Promise<LegacyMigrationItem[]> {
  const result: LegacyMigrationItem[] = [];
  const plannedIds = new Set<string>();
  let projectLanguage:unknown='zh';
  try {projectLanguage=JSON.parse(await readFile(join(projectRoot,'inkos.json'),'utf8')).language??'zh';}
  catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
  // Early 2.0 development manifests called every accepted revision "accepted".
  // The existing currentRevisionId, not file order, determines the current one.
  for (const entry of await entries(join(projectRoot, "works"))) {
    if (!entry.isDirectory()) continue;
    const source = `works/${entry.name}`;
    if (options.source && options.source !== source) continue;
    let original: string;
    try { original = await readFile(join(projectRoot, source, "work.json"), "utf8"); }
    catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") continue; throw error; }
    let raw;
    try { raw = JSON.parse(original); }
    catch (error) { result.push({source,workId:entry.name,profileId:"unknown",status:"invalid",error:String(error)}); continue; }
    if (!raw.artifacts?.some((artifact: any) => artifact.revisions?.some((revision: any) => revision.status === "accepted"))) continue;
    const base = {source,workId:entry.name,profileId:String(raw.profileId)};
    try {
      const manifest = WorkManifestSchema.parse({...raw, artifacts: raw.artifacts.map((artifact: any) => ({
        ...artifact, revisions: artifact.revisions.map((revision: any) => ({
          ...revision, status: revision.status === "accepted"
            ? revision.id === artifact.currentRevisionId ? "current" : "superseded"
            : revision.status,
        })),
      }))});
      if (options.apply) await commitAtomicFileSet({rootDir:projectRoot,writes:[
        {relativePath:join(".inkos","migrations",`${WorkResourceIdSchema.parse(entry.name)}-accepted-manifest.json`),content:original},
        {relativePath:join(source,"work.json"),content:JSON.stringify(manifest,null,2)+"\n"},
      ]});
      result.push({...base,status:options.apply?"migrated":"ready",fileCount:1});
    } catch (error) { result.push({...base,status:"invalid",error:error instanceof Error?error.message:String(error)}); }
  }
  for (const [directory, profileId, marker] of SOURCES) {
    for (const entry of await entries(join(projectRoot, directory))) {
      if (!entry.isDirectory()) continue;
      const source = `${directory}/${entry.name}`;
      if (options.source && source !== options.source) continue;
      const base = { source, workId: entry.name, profileId };
      try {
        WorkResourceIdSchema.parse(entry.name);
        const sourceRoot = join(projectRoot, source);
        if (!(await entries(sourceRoot)).some((item) => item.name === marker)) continue;
        const existing = await loadWorkManifest(projectRoot, entry.name).catch((error) => {
          if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
          throw error;
        });
        if (existing || plannedIds.has(entry.name)) {
          if(existing?.metadata.legacySource===source&&profileId==='longform-novel'){
            const currentRoot=join(projectRoot,'works',entry.name,'source');
            const converted=await migrateLegacyBookDocuments(currentRoot,await files(currentRoot),projectLanguage);
            if(converted.overrides.size){
              const paths=[...converted.overrides.keys()].map(name=>'source/'+name);
              if(options.apply){
                const synced=await syncWorkSourceArtifacts({projectRoot,workId:entry.name,accept:true,acceptPaths:paths,writes:[...converted.overrides].map(([name,content])=>({relativePath:join('works',entry.name,'source',name),content}))});
                const {migrationNeedsReconstruction:_previous,...metadata}=synced.metadata;
                await saveWorkManifest(projectRoot,{...synced,language:converted.metadata.language,status:converted.missing.length?'draft':synced.status,metadata:{...metadata,...(converted.missing.length?{migrationNeedsReconstruction:converted.missing}:{})}});
              }
              result.push({...base,status:options.apply?'migrated':'ready',fileCount:converted.overrides.size});
              continue;
            }
          }
          result.push({ ...base, status: existing?.metadata.legacySource === source ? "already-migrated" : "conflict" });
          continue;
        }
        plannedIds.add(entry.name);
        const names = await files(sourceRoot);
        const writes: AtomicFileWrite[] = [];
        let metadata: Record<string, any> = {};
        if (marker.endsWith(".json")) metadata = JSON.parse(await readFile(join(sourceRoot, marker), "utf8"));
        const converted=profileId==='longform-novel'?await migrateLegacyBookDocuments(sourceRoot,names,projectLanguage):undefined;
        if(converted)metadata=converted.metadata;
        for (const name of names) {
          let content: string | Uint8Array = await readFile(join(sourceRoot, name));
          if(converted?.overrides.has(name.replaceAll('\\','/')))content=converted.overrides.get(name.replaceAll('\\','/'))!;
          if (profileId === "translation" && name === "manifest.json") {
            const chapters = await Promise.all(metadata.chapters.map(async (chapter: Record<string, any>) => {
              const sourceName = chapter.sourcePath.replaceAll("\\", "/").split("/").at(-1);
              const targetName = chapter.translatedPath.replaceAll("\\", "/").split("/").at(-1);
              const translated = JSON.parse(await readFile(join(sourceRoot, "translated", targetName), "utf8"));
              return {
                number: chapter.number, title: chapter.title, segmentCount: chapter.segmentCount, charCount: chapter.charCount,
                sourcePath: `works/${entry.name}/source/source/${sourceName}`,
                translatedPath: `works/${entry.name}/source/translated/${targetName}`,
                translatedSegments: translated.segments.filter((segment: { target?: string }) => segment.target?.trim()).length,
                ...(chapter.reviewSummary ? { reviewSummary: chapter.reviewSummary } : {}),
                ...(chapter.observations ? { observations: chapter.observations } : {}),
              };
            }));
            content = JSON.stringify(TranslationProjectManifestSchema.parse({ ...metadata, chapters }), null, 2) + "\n";
          }
          writes.push({ relativePath: join("works", entry.name, "source", name), content });
        }
        for(const [name,content] of converted?.overrides??[])if(!names.some(path=>path.replaceAll('\\','/')===name))writes.push({relativePath:join('works',entry.name,'source',name),content});
        // An orphan source directory must not be overwritten by migration.
        if ((await entries(join(projectRoot, "works", entry.name))).length > 0) {
          result.push({ ...base, status: "conflict" });
          continue;
        }
        const initial = createInitialWorkManifestWrite({
          workId: entry.name, title: metadata.title || entry.name, profileId,
          language: metadata.language || metadata.targetLanguage || "zh",
          writes, createdAt: metadata.createdAt,
          metadata: {
            legacySource: source,
            ...(converted?.missing.length?{migrationNeedsReconstruction:converted.missing}:{}),
            ...(metadata.genre ? { genre: metadata.genre } : {}),
            ...(metadata.platform ? { platform: metadata.platform } : {}),
            ...(metadata.mode ? { mode: metadata.mode } : {}),
            ...(metadata.fanficMode ? { fanficMode: metadata.fanficMode } : {}),
            ...(metadata.fanficMode ? { creationKind: "fanfic" } : {}),
          },
        });
        if(converted?.missing.length)initial.manifest.status='draft';
        if (metadata.parentBookId) {
          initial.manifest.lineage.push({ relation: "derived-from", sourceWorkId: WorkResourceIdSchema.parse(metadata.parentBookId) });
        }
        if (options.apply) await commitAtomicFileSet({ rootDir: projectRoot, writes: [
          ...writes, { ...initial.write, content: JSON.stringify(initial.manifest, null, 2) + "\n" },
        ] });
        result.push({ ...base, status: options.apply ? "migrated" : "ready", fileCount: writes.length });
      } catch (error) {
        result.push({ ...base, status: "invalid", error: error instanceof Error ? error.message : String(error) });
      }
    }
  }
  return result;
}
