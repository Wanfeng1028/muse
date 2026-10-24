import { Type, type Static } from "@mariozechner/pi-ai";
import type { AgentTool, AgentToolResult } from "@mariozechner/pi-agent-core";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { executeEditTransaction, type EditRequest } from "../../interaction/edit-controller.js";
import { StateManager } from "../../state/manager.js";
import { assertSafeBookId } from "../../utils/book-id.js";
import { safeChildPath } from "../../utils/path-safety.js";
import { BookRulesDataToolSchema } from "../../agents/architect-tool.js";
import { BookRulesSchema } from "../../models/book-rules.js";
import { commitAtomicFileSet } from "../../utils/atomic-file-set.js";

const SAFE_TRUTH_FLAT_FILE_NAMES = new Set([
  "author_intent.md",
  "current_focus.md",
  "book_rules.md",
  "style_guide.md",
  "parent_canon.md",
  "fanfic_canon.md",
  "current_state.md",
  "pending_hooks.md",
  "chapter_summaries.md",
]);

const SAFE_TRUTH_OUTLINE_FILE_NAMES = new Set([
  "outline/story_frame.md",
  "outline/volume_map.md",
]);

const SAFE_ROLE_TRUTH_FILE_RE = /^roles\/(主要角色|次要角色|major|minor)\/[^/\\]+\.md$/u;

export function assertSafeTruthFileName(fileName: string): string {
  const trimmed = fileName.trim();
  const withExtension = trimmed.endsWith(".md") ? trimmed : `${trimmed}.md`;
  const lower = withExtension.toLowerCase();
  if (
    !trimmed
    || withExtension.startsWith("/")
    || withExtension.includes("\\")
    || withExtension.includes("\0")
    || withExtension.includes("..")
  ) {
    throw new Error(`Invalid truth file name: ${JSON.stringify(fileName)}`);
  }
  if (SAFE_TRUTH_FLAT_FILE_NAMES.has(lower)) return lower;
  if (SAFE_TRUTH_OUTLINE_FILE_NAMES.has(lower)) return lower;
  if (SAFE_ROLE_TRUTH_FILE_RE.test(withExtension)) return withExtension;
  throw new Error(`Invalid truth file name: ${JSON.stringify(fileName)}`);
}

function resolveBookId(toolName: string, requestedBookId: string | undefined, activeBookId: string | null): string {
  const resolved = requestedBookId ?? activeBookId ?? undefined;
  if (!resolved) throw new Error(`${toolName} requires bookId when there is no active Work.`);
  const bookId = assertSafeBookId(resolved, `${toolName}.bookId`);
  if (requestedBookId && activeBookId && bookId !== activeBookId) {
    throw new Error(`${toolName}.bookId must match the active Work.`);
  }
  return bookId;
}

async function withBookLock<T>(state: StateManager, bookId: string, task: () => Promise<T>): Promise<T> {
  const release = await state.acquireBookLock(bookId);
  try {
    return await task();
  } finally {
    await release();
  }
}

function editDeps(state: StateManager) {
  return {
    bookDir: (bookId: string) => state.bookDir(bookId),
    loadChapterIndex: (bookId: string) => state.loadChapterIndex(bookId),
    saveChapterIndex: (bookId: string, index: Awaited<ReturnType<StateManager["loadChapterIndex"]>>) => (
      state.saveChapterIndex(bookId, index)
    ),
  };
}

function textResult<T>(text: string, details: T): AgentToolResult<T> {
  return { content: [{ type: "text", text }], details };
}

const WriteTruthFileParams = Type.Object({
  bookId: Type.Optional(Type.String({ description: "Work ID. Omit to use the active Work." })),
  fileName: Type.String({ description: "Truth file path under story/." }),
  content: Type.String({ description: "Full replacement content for the truth file." }),
  bookRulesData: Type.Optional(BookRulesDataToolSchema),
});

export function createWriteTruthFileTool(
  projectRoot: string,
  activeBookId: string | null,
): AgentTool<typeof WriteTruthFileParams> {
  return {
    name: "write_truth_file",
    description: "Replace one allowlisted truth/control file under the active long-form Work.",
    label: "Write Truth File",
    parameters: WriteTruthFileParams,
    async execute(_toolCallId, params: Static<typeof WriteTruthFileParams>) {
      const bookId = resolveBookId("write_truth_file", params.bookId, activeBookId);
      const fileName = assertSafeTruthFileName(params.fileName);
      const state = new StateManager(projectRoot);
      await withBookLock(state, bookId, async () => {
        await state.ensureControlDocuments(bookId);
        const targetPath = safeChildPath(join(state.bookDir(bookId), "story"), fileName);
        await mkdir(dirname(targetPath), { recursive: true });
        if (fileName === "book_rules.md") {
          if (!params.bookRulesData) {
            throw new Error("write_truth_file requires bookRulesData when replacing book_rules.md");
          }
          const data = BookRulesSchema.parse({ version: "2", ...params.bookRulesData });
          await commitAtomicFileSet({
            rootDir: state.bookDir(bookId),
            writes: [
              { relativePath: join("story", "book_rules.md"), content: params.content },
              { relativePath: join("story", "book_rules.json"), content: `${JSON.stringify(data, null, 2)}\n` },
            ],
          });
        } else {
          await writeFile(targetPath, params.content, "utf-8");
        }
      });
      return textResult(`Updated "${fileName}" for "${bookId}".`, {
        kind: "truth_file_updated",
        workId: bookId,
        bookId,
        fileName,
      });
    },
  };
}

const RenameEntityParams = Type.Object({
  bookId: Type.Optional(Type.String({ description: "Work ID. Omit to use the active Work." })),
  oldValue: Type.String({ description: "Current entity name." }),
  newValue: Type.String({ description: "New entity name." }),
});

export function createRenameEntityTool(
  projectRoot: string,
  activeBookId: string | null,
): AgentTool<typeof RenameEntityParams> {
  return editTool({
    name: "rename_entity",
    label: "Rename Entity",
    description: "Rename an entity across long-form truth files and chapters.",
    parameters: RenameEntityParams,
    projectRoot,
    activeBookId,
    request: (bookId, params) => ({
      kind: "entity-rename",
      bookId,
      entityType: "character",
      oldValue: params.oldValue,
      newValue: params.newValue,
    }),
  });
}

const PatchChapterTextParams = Type.Object({
  bookId: Type.Optional(Type.String({ description: "Work ID. Omit to use the active Work." })),
  chapterNumber: Type.Number({ description: "Chapter number to patch." }),
  targetText: Type.String({ description: "Exact, unique paragraph text to replace." }),
  replacementText: Type.String({ description: "Replacement text." }),
});

export function createPatchChapterTextTool(
  projectRoot: string,
  activeBookId: string | null,
): AgentTool<typeof PatchChapterTextParams> {
  return editTool({
    name: "patch_chapter_text",
    label: "Patch Chapter",
    description: "Apply one exact, unique local text replacement.",
    parameters: PatchChapterTextParams,
    projectRoot,
    activeBookId,
    request: (bookId, params) => ({
      kind: "chapter-local-edit",
      bookId,
      chapterNumber: params.chapterNumber,
      instruction: `Replace ${params.targetText} with ${params.replacementText}`,
      targetText: params.targetText,
      replacementText: params.replacementText,
    }),
  });
}

const ReplaceChapterTextParams = Type.Object({
  bookId: Type.Optional(Type.String({ description: "Work ID. Omit to use the active Work." })),
  chapterNumber: Type.Number({ description: "Chapter number to replace." }),
  fullText: Type.String({ description: "Complete replacement chapter supplied by the user." }),
});

export function createReplaceChapterTextTool(
  projectRoot: string,
  activeBookId: string | null,
): AgentTool<typeof ReplaceChapterTextParams> {
  return editTool({
    name: "replace_chapter_text",
    label: "Replace Chapter",
    description: "Replace a whole chapter with user-supplied text.",
    parameters: ReplaceChapterTextParams,
    projectRoot,
    activeBookId,
    request: (bookId, params) => ({
      kind: "chapter-replace",
      bookId,
      chapterNumber: params.chapterNumber,
      fullText: params.fullText,
    }),
  });
}

function editTool<TSchema extends typeof RenameEntityParams | typeof PatchChapterTextParams | typeof ReplaceChapterTextParams>(
  input: {
    readonly name: string;
    readonly label: string;
    readonly description: string;
    readonly parameters: TSchema;
    readonly projectRoot: string;
    readonly activeBookId: string | null;
    readonly request: (bookId: string, params: Static<TSchema>) => EditRequest;
  },
): AgentTool<TSchema> {
  return {
    name: input.name,
    label: input.label,
    description: input.description,
    parameters: input.parameters,
    async execute(_toolCallId, params: Static<TSchema>) {
      const bookId = resolveBookId(input.name, params.bookId, input.activeBookId);
      const state = new StateManager(input.projectRoot);
      const execution = await withBookLock(
        state,
        bookId,
        () => executeEditTransaction(editDeps(state), input.request(bookId, params)),
      );
      return textResult(execution.summary, {
        kind: "longform_edit_applied",
        workId: bookId,
        ...execution,
      });
    },
  };
}
