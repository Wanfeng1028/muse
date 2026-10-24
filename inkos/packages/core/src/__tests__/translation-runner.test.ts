import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  createTranslationProjectFromFile,
  runTranslationProject,
  writeTranslationExport,
  type TranslationModelPort,
} from "../translation/index.js";
import { loadWorkManifest } from "../harness/index.js";
import { createReplaceWorkArtifactTool } from "../harness/tools/work-artifacts.js";
import { createReadTool } from "../agent/agent-tools.js";
import { loadTranslationChapter, loadTranslationManifest } from "../translation/run-store.js";
import { createTranslationRevisionTool } from "../harness/tools/translation.js";

describe("translation runner", () => {
  let root: string;

  beforeEach(async () => {
    root = await mkdtemp(join(tmpdir(), "inkos-translation-runner-"));
    await mkdir(join(root, "inputs"), { recursive: true });
    await writeFile(join(root, "inputs", "book.md"), [
      "# 第一章 雨夜",
      "",
      "第一段。",
      "",
      "第二段。",
    ].join("\n"));
  });

  afterEach(async () => {
    await rm(root, { recursive: true, force: true });
  });

  it("translates pending segments, persists review report, and resumes without duplicate model calls", async () => {
    const created = await createTranslationProjectFromFile(root, {
      filePath: "inputs/book.md",
      sourceLanguage: "zh",
      targetLanguage: "en",
    });
    const translateSegments = vi.fn<TranslationModelPort["translateSegments"]>(async ({ segments }) => ({
      chapterTitle: "Rainy Night",
      segments: segments.map((segment) => ({
        index: segment.index,
        target: `EN:${segment.source}`,
      })),
      glossary: [{ source: "雨夜", target: "rainy night", note: "chapter tone" }],
    }));
    const reviewChapter = vi.fn<NonNullable<TranslationModelPort["reviewChapter"]>>(async () => ({
      passed: true,
      summary: "ok",
      observations: [],
    }));

    const first = await runTranslationProject(root, created.manifest.id, {
      model: { translateSegments, reviewChapter },
      batchSize: 1,
    });
    expect(first.translatedSegments).toBe(2);
    expect(first).toMatchObject({ totalSegments: 2, completedSegments: 2, pendingSegments: 0 });
    expect(first.reviewedChapters).toBe(1);
    expect(translateSegments).toHaveBeenCalledTimes(2);
    const workAfterRun = await loadWorkManifest(root, created.manifest.id);
    const translatedArtifact = workAfterRun.artifacts.find((artifact) => (
      artifact.revisions.some((revision) => revision.path.includes("source/translated/chapter-0001.json"))
    ));
    expect(translatedArtifact?.revisions.length).toBeGreaterThan(1);

    const report = await readFile(join(root, first.reportPath), "utf-8");
    expect(report).toContain("ok");
    expect(report).toContain("Rainy Night");

    const second = await runTranslationProject(root, created.manifest.id, {
      model: { translateSegments, reviewChapter },
      batchSize: 1,
    });
    expect(second.translatedSegments).toBe(0);
    expect(translateSegments).toHaveBeenCalledTimes(2);

    const exported = await writeTranslationExport(root, created.manifest.id, { format: "md" });
    const markdown = await readFile(exported.outputPath, "utf-8");
    expect(markdown).toContain("EN:第一段。");
    expect(markdown).toContain("EN:第二段。");
    expect(markdown).toContain("## Rainy Night");
    expect(markdown).not.toContain("\n第一段。\n");
    const workAfterExport = await loadWorkManifest(root, created.manifest.id);
    expect(workAfterExport.artifacts.some((artifact) => (
      artifact.revisions.some((revision) => revision.path.includes("source/exports/"))
    ))).toBe(true);
  });

  it("rejects a truncated chapter replacement and revises the actual last paragraph through export", async () => {
    const sourceText = "# Rain\n\n" + Array.from({ length: 41 }, (_, index) => `Source paragraph ${index + 1}.`).join("\n\n");
    const created = await createTranslationProjectFromFile(root, {
      sourceText, sourceLanguage: "en", targetLanguage: "zh", glossary: [{ source: "Rain", target: "雨" }],
    });
    const model: TranslationModelPort = {
      translateSegments: async ({ segments }) => ({ segments: segments.map(segment => ({ index: segment.index, target: `译文${segment.index}` })) }),
      reviewChapter: async () => ({ passed: true, summary: "Reviewed", observations: [] }),
      reviseSegment: vi.fn<NonNullable<TranslationModelPort["reviseSegment"]>>(async ({ segment, neighbors }) => {
        expect(segment.index).toBe(41);
        expect(neighbors.map(neighbor => neighbor.index)).toEqual([40]);
        return { target: "最后一段的新译文" };
      }),
    };
    const run = await runTranslationProject(root, created.manifest.id, { model });
    expect(run).toMatchObject({ translatedSegments: 41, totalSegments: 41, completedSegments: 41, pendingSegments: 0 });
    const info = created.manifest.chapters[0]!;
    const before = await loadTranslationChapter(root, info.translatedPath);
    const originalBytes = await readFile(join(root, info.sourcePath));
    const glossaryPath = join(root, created.projectDir, "glossary.json");
    const glossaryBytes = await readFile(glossaryPath);
    const work = await loadWorkManifest(root, created.manifest.id);
    const artifact = work.artifacts.find(item => item.revisions.some(revision => revision.path === "source/translated/chapter-0001.json"))!;
    const preview = await createReadTool(root, { scope: "project", workId: work.id }).execute("preview", { artifactId: artifact.id });
    expect(preview.details).toMatchObject({ endLine: 200 });
    const beforeBytes = await readFile(join(root, info.translatedPath));
    await expect(createReplaceWorkArtifactTool(root, work.id).execute("truncated-replacement", {
      artifactId: artifact.id, content: JSON.stringify({ ...before, segments: before.segments.slice(0, 39) }),
    })).rejects.toMatchObject({ code: "ARTIFACT_STRUCTURE_CHANGED", recovery: { action: "translation__revise_paragraph" } });
    expect(await readFile(join(root, info.translatedPath))).toEqual(beforeBytes);
    expect((await loadWorkManifest(root, work.id)).artifacts).toEqual(work.artifacts);

    const pipeline={createAgentContext:()=>({client:{},model:"fixture"}),runWithAgentContext:(_options:unknown,run:()=>Promise<unknown>)=>run()};
    const revision = await createTranslationRevisionTool(pipeline as never,root,work.id,{createModel:()=>model}).execute("revise-last", { chapterNumber: 1, paragraph: "last", instruction: "Improve rhythm" });
    expect(revision.details).toMatchObject({ paragraphNumber: 41, paragraphCount: 41, sourceSegmentIndex:41, isLastParagraph:true, sourceExcerpt:before.segments.at(-1)!.source, changed: true, reviewRequired: true, exportRequired: true });
    const after = await loadTranslationChapter(root, info.translatedPath);
    expect(after).toEqual({ ...before, segments: before.segments.map(segment => segment.index === 41 ? { ...segment, target: "最后一段的新译文" } : segment) });
    expect(await readFile(join(root, info.sourcePath))).toEqual(originalBytes);
    expect(await readFile(glossaryPath)).toEqual(glossaryBytes);
    expect((await loadTranslationManifest(root, work.id)).chapters[0]!.reviewSummary).toBeUndefined();
    const reviewed = await runTranslationProject(root, work.id, { model });
    expect(reviewed).toMatchObject({ translatedSegments: 0, reviewedChapters: 1, completedSegments: 41, pendingSegments: 0 });
    const exported = await writeTranslationExport(root, work.id, { format: "md" });
    const body = await readFile(exported.outputPath, "utf8");
    for (const segment of after.segments) expect(body).toContain(segment.target);
    expect(body).not.toContain(before.segments.at(-1)!.target);
  });
});
