// Reader-facing labels and projections for canonical Work truth artifacts.

import { getAppLanguage, tr } from "./app-language";

// First non-empty prose paragraph of a body, for an at-a-glance overview. A
// leading markdown heading on the paragraph is dropped so the glance is prose.
export function firstParagraph(text: string): string {
  for (const chunk of text.trim().split(/\n{2,}/)) {
    const withoutHeading = chunk.replace(/^\s*#{1,6}\s+[^\n]*\n?/, "").trim();
    if (withoutHeading) return withoutHeading;
  }
  return "";
}

export interface RoleRef {
  readonly path: string;
  readonly name: string;
  readonly tier: "major" | "minor";
}

// Parse a roles/<tier>/<name>.md truth path (zh or en locale dirs) into a
// character reference. Returns null for any non-role path.
export function roleFromPath(path: string): RoleRef | null {
  const m = path.match(/^roles\/(主要角色|次要角色|major|minor)\/(.+)\.md$/);
  if (!m) return null;
  const tier = m[1] === "主要角色" || m[1] === "major" ? "major" : "minor";
  return { path, name: m[2], tier };
}

// Friendly labels + display order for canonical foundation files. Role cards
// belong to the character roster rather than this list.
export const FOUNDATION_FILE_LABELS: Record<string, string> = {
  "outline/story_frame.md": "故事基石",
  "outline/volume_map.md": "卷纲规划",
  "current_state.md": "当前状态",
  "pending_hooks.md": "伏笔池",
  "book_rules.md": "叙事规则",
};

const FOUNDATION_FILE_LABELS_EN: Record<string, string> = {
  "outline/story_frame.md": "Story Foundation",
  "outline/volume_map.md": "Volume Map",
  "current_state.md": "Current State",
  "pending_hooks.md": "Hook Pool",
  "book_rules.md": "Narrative Rules",
};

// Language-aware display label for a foundation truth file. Returns undefined
// for files that are not part of the foundation list (same qualification as
// FOUNDATION_FILE_LABELS).
export function foundationFileLabel(name: string): string | undefined {
  const zh = FOUNDATION_FILE_LABELS[name];
  if (zh === undefined) return undefined;
  return getAppLanguage() === "en" ? FOUNDATION_FILE_LABELS_EN[name] ?? zh : zh;
}

// --- current_state.md ---------------------------------------------------

export function presentCurrentState(content: string): { readonly isEmpty: boolean; readonly body: string } {
  const body = content.trim();
  return { isEmpty: body.length === 0, body };
}

// --- pending_hooks.md ----------------------------------------------------

export interface PendingHook {
  readonly id: string;
  readonly type: string; // 类型 — 主线伏笔 / 角色前置 / 情感线伏笔 …
  readonly content: string; // 备注 — the actual foreshadow / setup text
  readonly payoff: string;
  readonly status: string;
}

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

// pending_hooks.md is an explicit-state tracking table. Only a few columns are
// reader-facing; parse the table by header name (robust to column reordering)
// and keep the meaningful ones so the UI can render browsable cards instead of
// an unreadable wide table.
export function parsePendingHooks(md: string): ReadonlyArray<PendingHook> {
  const rows = md.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("|"));
  if (rows.length < 2) return [];
  const header = splitTableRow(rows[0]);
  const colOf = (...names: string[]) => header.findIndex((h) => names.includes(h));
  const idIdx = colOf("hook_id", "id");
  const typeIdx = colOf("类型", "type");
  const statusIdx = colOf("状态", "status");
  const payoffIdx = colOf("预期回收", "expected_payoff", "回收卷");
  const contentIdx = colOf("备注", "notes");

  return rows
    .slice(1)
    .filter((line) => !/^\|\s*-{2,}/.test(line)) // drop the | --- | --- | separator
    .map(splitTableRow)
    .filter((cells) => cells.length === header.length)
    .map((cells) => ({
      id: idIdx >= 0 ? cells[idIdx] : "",
      type: typeIdx >= 0 ? cells[typeIdx] : "",
      content: contentIdx >= 0 ? cells[contentIdx] : "",
      payoff: payoffIdx >= 0 ? cells[payoffIdx] : "",
      status: statusIdx >= 0 ? cells[statusIdx] : "",
    }))
    .filter((hook) => hook.content.length > 0 || hook.id.length > 0);
}

export const FOUNDATION_FILE_ORDER: ReadonlyArray<string> = [
  "outline/story_frame.md",
  "outline/volume_map.md",
  "book_rules.md",
  "current_state.md",
  "pending_hooks.md",
];
