import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type {
  TranslationChapterFile,
  TranslationGlossaryTerm,
  TranslationProjectManifest,
} from "./types.js";
import {
  TranslationChapterFileSchema,
  TranslationGlossarySchema,
  TranslationProjectManifestSchema,
  validateTranslationManifestOwnership,
  normalizeTranslationArtifactPath,
} from "./types.js";
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";
import { workDirectory } from "../harness/work-store.js";
import { safeChildPath } from "../utils/path-safety.js";

export function translationProjectDir(projectRoot: string, projectId: string): string {
  return join(workDirectory(projectRoot, projectId), "source");
}

export function translationManifestPath(projectRoot: string, projectId: string): string {
  return join(translationProjectDir(projectRoot, projectId), "manifest.json");
}

export async function loadTranslationManifest(
  projectRoot: string,
  projectId: string,
): Promise<TranslationProjectManifest> {
  const path = translationManifestPath(projectRoot, projectId);
  return validateTranslationManifestOwnership(TranslationProjectManifestSchema.parse(JSON.parse(await readFile(path, "utf-8"))),projectId);
}

export async function saveTranslationManifest(
  projectRoot: string,
  manifest: TranslationProjectManifest,
): Promise<void> {
  const parsed = validateTranslationManifestOwnership(TranslationProjectManifestSchema.parse(manifest),manifest.id);
  await writeFile(translationManifestPath(projectRoot, parsed.id), JSON.stringify(parsed, null, 2), "utf-8");
}

export async function loadTranslationChapter(
  projectRoot: string,
  chapterPath: string,
): Promise<TranslationChapterFile> {
  return TranslationChapterFileSchema.parse(JSON.parse(await readFile(safeChildPath(projectRoot, chapterPath), "utf-8")));
}

export async function saveTranslationChapter(
  projectRoot: string,
  chapterPath: string,
  chapter: TranslationChapterFile,
): Promise<void> {
  const parsed = TranslationChapterFileSchema.parse(chapter);
  await writeFile(safeChildPath(projectRoot, chapterPath), JSON.stringify(parsed, null, 2), "utf-8");
}

export async function loadTranslationGlossary(
  projectRoot: string,
  projectId: string,
): Promise<ReadonlyArray<TranslationGlossaryTerm>> {
  try {
    const raw = JSON.parse(await readFile(join(translationProjectDir(projectRoot, projectId), "glossary.json"), "utf-8"));
    return TranslationGlossarySchema.parse(raw).terms;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

export async function saveTranslationGlossary(
  projectRoot: string,
  projectId: string,
  terms: ReadonlyArray<TranslationGlossaryTerm>,
): Promise<void> {
  await writeFile(
    join(translationProjectDir(projectRoot, projectId), "glossary.json"),
    JSON.stringify({ terms: mergeGlossaryTerms(terms) }, null, 2),
    "utf-8",
  );
}

export async function saveTranslationProgress(
  projectRoot: string,
  projectId: string,
  chapterPath: string,
  chapter: TranslationChapterFile,
  terms: ReadonlyArray<TranslationGlossaryTerm>,
): Promise<void> {
  await commitAtomicFileSet({
    rootDir: projectRoot,
    writes: [
      {
        relativePath: normalizeTranslationArtifactPath(projectId,chapterPath),
        content: `${JSON.stringify(chapter, null, 2)}\n`,
      },
      {
        relativePath: join("works", projectId, "source", "glossary.json"),
        content: `${JSON.stringify({ terms: mergeGlossaryTerms(terms) }, null, 2)}\n`,
      },
    ],
  });
}

export function mergeGlossaryTerms(terms: ReadonlyArray<TranslationGlossaryTerm>): ReadonlyArray<TranslationGlossaryTerm> {
  const map = new Map<string, TranslationGlossaryTerm>();
  for (const term of terms) {
    const key = term.source.trim().toLowerCase();
    if (!key) continue;
    map.set(key, {
      source: term.source.trim(),
      target: term.target.trim(),
      ...(term.note?.trim() ? { note: term.note.trim() } : {}),
    });
  }
  return [...map.values()];
}
