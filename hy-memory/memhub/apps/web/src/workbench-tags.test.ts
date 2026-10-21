import type { GovernedMemory } from "@one-memory/contracts";
import { describe, expect, it } from "vitest";

import { singletonTags, tagCounts } from "./workbench-tags";

function memory(
  id: string,
  tags: string[],
  overrides: Partial<GovernedMemory> = {},
): GovernedMemory {
  return {
    memory_id: id,
    user_id: "local",
    kind: "chat",
    status: "confirmed",
    content: `记忆 ${id}`,
    scopes: ["all-apps"],
    evidence_ids: [`ev-${id}`],
    origin: "extracted",
    tags,
    revision: 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    deleted_at: null,
    ...overrides,
  };
}

describe("主题标签的用量", () => {
  it("按用得多的排在前面，一样多就按名字定序", () => {
    const counted = tagCounts([
      memory("a", ["排期", "工作习惯"]),
      memory("b", ["排期"]),
      memory("c", ["前端"]),
    ]);

    expect(counted).toEqual([
      ["排期", 2],
      ["前端", 1],
      ["工作习惯", 1],
    ]);
  });

  it("删掉和被取代的记忆不给标签撑数", () => {
    const counted = tagCounts([
      memory("a", ["排期"]),
      memory("b", ["排期"], { status: "deleted" }),
      memory("c", ["排期"], { status: "superseded" }),
      memory("d", ["前端"]),
    ]);

    expect(counted).toEqual([
      ["前端", 1],
      ["排期", 1],
    ]);
  });

  it("只用过一次的挑出来，这是度量不是判决", () => {
    expect(
      singletonTags([memory("a", ["排期", "工作习惯"]), memory("b", ["排期"])]),
    ).toEqual(["工作习惯"]);
  });

  it("一条标签都没有的库不报任何东西", () => {
    expect(tagCounts([memory("a", [])])).toEqual([]);
    expect(singletonTags([])).toEqual([]);
  });
});
