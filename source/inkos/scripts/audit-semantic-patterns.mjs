#!/usr/bin/env node
import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";

const ROOT = process.cwd();
const SCAN_DIRS = [
  "packages/core/src",
  "packages/studio/src",
  "packages/cli/src",
];

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

const FORBIDDEN_SOURCE_PATHS = [
  "packages/core/src/models/state.ts",
  "packages/core/src/models/genre-profile.ts",
  "packages/core/src/state/memory-db.ts",
  "packages/core/src/interactive-film/memory-link.ts",
  "packages/core/src/agent/llm-stub.ts",
  "packages/cli/src/commands/genre.ts",
];

const FORBIDDEN_ARCHITECTURE_TOKENS = [
  ["audit-failed", "hidden content rejection state"],
  ["review-failed", "hidden content rejection state"],
  ["qualityScore", "host-owned prose score"],
  ["isOutsideHardRange", "host-derived hard length gate"],
  ["isOutsideSoftRange", "host-derived soft length gate"],
  ["lengthWarning", "host-derived length verdict"],
  ["softMin", "host-derived length range"],
  ["hardMin", "host-derived length range"],
  ["SHORT_FICTION_MIN_CHAPTERS", "host-owned creative range"],
  ["SHORT_FICTION_MAX_CHAPTERS", "host-owned creative range"],
  ["INKOS_AGENT_LLM_STUB", "production test-model branch"],
  ["contextRecipes", "unused parallel context abstraction"],
  ["createEditTool", "unregistered generic write surface"],
  ["createWriteFileTool", "unregistered generic write surface"],
  ["plainToAgentMessages", "second conversation-history source"],
  ["InteractionEventSchema", "parallel interaction event ledger"],
  ["AuditIssue", "legacy review issue protocol"],
  ["repairScope", "legacy review issue protocol"],
  ["reviewIssuesAsObservations", "legacy review conversion layer"],
  ["reviewObservations", "legacy review conversion layer"],
  ["reviewIssues", "parallel translation review protocol"],
  ["ValidationWarning", "parallel state-review protocol"],
  ["buildStateReconciliationIssues", "state-review conversion layer"],
  ["loadAllSkillResources", "eager Skill reference loading"],
  ["MAX_SKILL_ACTIVATION_BYTES", "eager Skill reference loading"],
  ["nextActions", "unused speculative ActionResult field"],
  ["fixedIssues", "model-authored revision success claim"],
  ["removeFailedWork", "destructive cleanup of recoverable creation state"],
  ["normalizeStageLabel", "UI stage inferred from human-facing prose"],
  ["stripTrailingLicense", "semantic source text removed by a host heuristic"],
  ["warning.startsWith(\"packaging\")", "observation code inferred from human-facing prose"],
  ["log.startsWith(\"[error]\")", "tool log severity inferred from human-facing prose"],
  ["kind: z.enum([\"hard\", \"soft\"])", "unused host-owned observation severity"],
  ["Type.Literal(\"hard\"), Type.Literal(\"soft\")", "unused host-owned observation severity"],
  ["powerSystem: Type.String({ minLength: 1 })", "genre-specific fanfic canon requirement"],
  ["status.startsWith(\"Error", "UI status inferred from prose"],
  ["content.startsWith(\"\\u2717\")", "UI error state inferred from prose"],
  ["chapterWordCount: z.number().int().min(1000)", "host-owned chapter length floor"],
  ["maximum: 20", "host-owned multi-chapter action ceiling"],
  [".max(20)", "host-owned multi-chapter action ceiling"],
  ["isTerminalProductionToolName", "host-owned production action stop list"],
  ["hasUnansweredTerminalToolResult", "host-owned production action stop list"],
  ["localAssistantStopStream", "host-forced Pi termination after a production action"],
  ["pushToolResultsAsUser", "structured tool results rewritten as user prose"],
  ["appendRestoredHistoryBoundary", "historical control message appended to the user-message stream"],
  ["function suppressManualTextForTool", "tool presentation inferred from an action-name list"],
  ["runWithCliProfileSkills", "legacy CLI-only production wrapper"],
  ["async resyncChapterArtifacts(", "legacy parallel chapter-state repair entry"],
  ["const READ_TOOLS", "capability risk inferred from a parallel tool-name list"],
  ["const DESTRUCTIVE_TOOLS", "capability risk inferred from a parallel tool-name list"],
  ["const CONFIRMED_CREATION_TOOLS", "capability confirmation inferred from a parallel tool-name list"],
  ["function toolRisk(", "capability risk inferred from tool names"],
];

const FORBIDDEN_ENTRY_CALLS = [
  "pipeline.initBook(",
  "pipeline.writeNextChapter(",
  "pipeline.writeChapters(",
  "pipeline.reviseDraft(",
  "pipeline.reviseFoundation(",
  "pipeline.resyncChapter",
  "pipeline.importChapters(",
  "pipeline.importCanon(",
  "pipeline.importFanficCanon(",
  "pipeline.generateStyleGuide(",
  "runShortFictionProduction(",
  "runScriptCreation(",
  "runStoryboardCreation(",
  "runInteractiveFilmCreation(",
];

const HARNESS_ENTRY_PATHS = [
  "packages/cli/src/commands/",
  "packages/studio/src/api/server.ts",
];

const AGENT_CONSTRUCTION_PATHS = new Set([
  "packages/core/src/agent/agent-session.ts",
  "packages/core/src/agent/worker-agent.ts",
]);

const ACTION_SURFACE_PATHS = [
  "packages/core/src/agent/",
  "packages/core/src/interaction/",
  "packages/studio/src/api/server.ts",
  "packages/studio/src/pages/BookCreate.tsx",
  "packages/cli/src/commands/agent.ts",
  "packages/cli/src/tui/",
];

const SEMANTIC_HINTS = [
  "instruction",
  "intent",
  "requestedIntent",
  "actionSource",
  "free-text",
  "continue",
  "write next",
  "create book",
  "edit",
  "rewrite",
  "revise",
  "play",
  "short",
  "fanfic",
  "spinoff",
  "imitation",
  "续写",
  "继续",
  "建书",
  "短篇",
  "互动",
  "番外",
  "仿写",
  "同人",
];

const PATTERN_TOKENS = [
  ".match(",
  ".test(",
  ".includes(",
  ".startsWith(",
  ".endsWith(",
  "new RegExp(",
];

function hasAny(text, words) {
  const lower = text.toLowerCase();
  return words.some((word) => lower.includes(word.toLowerCase()));
}

function isActionSurface(path) {
  const rel = path.replace(`${ROOT}/`, "");
  return ACTION_SURFACE_PATHS.some((prefix) => rel.startsWith(prefix));
}

function isLikelySemanticDecision(path, line, windowText) {
  if (!isActionSurface(path)) return false;
  if (!PATTERN_TOKENS.some((token) => line.includes(token))) return false;
  if (!hasAny(`${line}\n${windowText}`, SEMANTIC_HINTS)) return false;
  if (line.includes("CHAT_EDIT_TEXT_EXTENSIONS")) return false;
  if (line.includes("SAFE_ROLE_TRUTH_FILE_RE")) return false;
  if (path.endsWith("agent-tools.ts") && line.includes("current.includes(")) return false;
  if (path.endsWith("skill-tool.ts") && line.includes("body.includes(\"\\0\")")) return false;
  if (line.includes("RUNTIME_DIAGNOSTIC_FILE_RE")) return false;
  if (line.includes("runtimeDiagnostic")) return false;
  if (line.includes("startsWith(\"scene-turn-\")")) return false;
  if (line.includes("PlannerParseError") && line.includes(".test(text)")) return false;
  if (line.includes("CODE_FENCE_RE") || line.includes("DIRECTIVE_CLOSE_RE")) return false;
  if (line.includes("safeSessionId")) return false;
  if (line.includes("genreId")) return false;
  if (line.includes("relPath") || line.includes("targetPath") || line.includes("requestedPath")) return false;
  if (line.includes("entry.name") || line.includes("base.includes") || line.includes("escapeRegExp")) return false;
  if (line.includes("raw.includes(\"/\")") || line.includes("raw.includes(\"\\\\\")")) return false;
  if (line.includes("Manual text edit requires review")) return false;
  if (path.endsWith("project-tools.ts") && line.includes("includes(")) return false;
  if (path.endsWith("i18n.ts")) return false;
  if (line.includes("rel || rel.startsWith")) return false;
  if (line.includes("trimmed.match(/^([A-Za-z_]")) return false;
  if (line.includes("file.includes(\"/\")")) return false;
  if (line.includes("startsWith(\"[Tool results]\")")) return false;
  if (line.includes("already processing") || line.includes("prompt.*queue")) return false;
  if (line.includes("trimmed.startsWith(\"#\")")) return false;
  if (line.includes("actionSource") && line.includes("startsWith(\"/\")")) return false;
  if (line.includes("startsWith(\"/\")")) return false;
  // Explicit slash-command grammar and Pi tool namespaces are protocols, not
  // natural-language intent inference.
  if (path.endsWith("agent-input.ts") && line.includes("/^\\/")) return false;
  if ((path.endsWith("agent-session.ts") || path.endsWith("session-transcript-restore.ts"))
    && line.includes("includes(\"__\")")) return false;
  if (line.includes("endsWith(") && !hasAny(windowText, ["instruction", "intent"])) return false;
  return true;
}

async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "dist" || entry.name === "__tests__") continue;
      out.push(...await walk(path));
    } else if (SOURCE_EXTENSIONS.has(path.slice(path.lastIndexOf(".")))) {
      out.push(path);
    }
  }
  return out;
}

const files = [];
for (const dir of SCAN_DIRS) {
  files.push(...await walk(join(ROOT, dir)));
}

const findings = [];
for (const path of FORBIDDEN_SOURCE_PATHS) {
  try {
    await readFile(join(ROOT, path), "utf-8");
    findings.push({ file: path, line: 1, text: "forbidden 1.x source remains" });
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}
for (const file of files) {
  const content = await readFile(file, "utf-8");
  const lines = content.split(/\r?\n/);
  const relativeFile = relative(ROOT, file);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const windowText = lines.slice(Math.max(0, index - 4), Math.min(lines.length, index + 5)).join("\n");
    for (const [token, reason] of FORBIDDEN_ARCHITECTURE_TOKENS) {
      if (line.includes(token)) {
        findings.push({
          file: relative(ROOT, file),
          line: index + 1,
          text: `${reason}: ${line.trim()}`,
        });
      }
    }
    if (isLikelySemanticDecision(file, line, windowText)) {
      findings.push({
        file: relative(ROOT, file),
        line: index + 1,
        text: line.trim(),
      });
    }
    if (
      HARNESS_ENTRY_PATHS.some((prefix) => relativeFile.startsWith(prefix))
      && FORBIDDEN_ENTRY_CALLS.some((token) => line.includes(token))
    ) {
      findings.push({
        file: relativeFile,
        line: index + 1,
        text: `production entry bypasses Harness capability: ${line.trim()}`,
      });
    }
    if (line.includes("new Agent(") && !AGENT_CONSTRUCTION_PATHS.has(relativeFile)) {
      findings.push({
        file: relativeFile,
        line: index + 1,
        text: `parallel Agent construction outside the shared main/worker kernels: ${line.trim()}`,
      });
    }
  }
}

if (process.argv.includes("--json")) {
  console.log(JSON.stringify({ findings }, null, 2));
} else {
  console.log(`Semantic/template-pattern audit candidates: ${findings.length}`);
  for (const finding of findings) {
    console.log(`${finding.file}:${finding.line}  ${finding.text}`);
  }
}

if (findings.length > 0) process.exitCode = 1;
