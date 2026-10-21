import type { MemoryDetail, SourceResponse } from "@one-memory/contracts";
import { describe, expect, it } from "vitest";
import {
  draftForScenario,
  guideDetailAvailable,
  guideHosts,
  sameGuideMemory,
} from "./first-use-model";
import type { RecallHostStatus } from "./global";

function guideDetail(
  overrides: Partial<MemoryDetail["memory"]> = {},
): MemoryDetail {
  return {
    memory: {
      memory_id: "m1",
      user_id: "local",
      content: "周会不安排在周五",
      kind: "chat",
      status: "confirmed",
      origin: "extracted",
      scopes: ["workspace:project-a"],
      tags: ["项目周会"],
      evidence_ids: ["e1"],
      revision: 1,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      deleted_at: null,
      ...overrides,
    },
    evidence: [
      {
        evidence_id: "e1",
        source_id: "cursor",
        written_by: "person",
        role: "user",
        created_at: null,
        verbatim: "周五我有其他安排，周会避开周五。",
        available: true,
      },
    ],
    history: [],
    index_sync: null,
  };
}
const hosts = [
  { hostId: "cursor", label: "Cursor", present: true, installed: true },
  { hostId: "codex", label: "Codex", present: true, installed: false },
  { hostId: "workbuddy", label: "WorkBuddy", present: false, installed: true },
] as RecallHostStatus[];
describe("first use evidence and draft boundaries", () => {
  it("requires current, available citations instead of trusting a confirmed flag alone", () => {
    expect(guideDetailAvailable(guideDetail(), [])).toBe(true);
    expect(
      guideDetailAvailable(guideDetail({ status: "superseded" }), []),
    ).toBe(false);
    expect(guideDetailAvailable(guideDetail({ evidence_ids: [] }), [])).toBe(
      false,
    );
    expect(guideDetailAvailable({ ...guideDetail(), evidence: [] }, [])).toBe(
      false,
    );
    expect(
      guideDetailAvailable(
        {
          ...guideDetail(),
          evidence: [{ ...guideDetail().evidence[0], available: false }],
        },
        [],
      ),
    ).toBe(false);
    expect(
      guideDetailAvailable(guideDetail(), [
        { source_id: "cursor", authorized: false },
      ] as SourceResponse[]),
    ).toBe(false);
  });
  it("keeps same-app, cross-app and user-chosen new-tool destinations distinct", () => {
    expect(
      guideHosts("same", guideDetail(), hosts).map((h) => h.hostId),
    ).toEqual(["cursor"]);
    expect(
      guideHosts("switch", guideDetail(), hosts).map((h) => h.hostId),
    ).toEqual(["codex"]);
    expect(
      guideHosts("new", guideDetail(), hosts).map((h) => h.hostId),
    ).toEqual(["cursor", "codex"]);
  });
  it.each(["same", "switch", "new"] as const)(
    "does not leak the expected answer into a %s recall trial",
    (scene) => {
      const text = draftForScenario(
        scene,
        "query",
        "项目周会",
        guideDetail(),
        "Cursor",
      );
      expect(text).toContain("MemHub");
      expect(text).toContain("项目周会");
      expect(text).not.toContain("周五");
      expect(text).not.toContain("m1");
    },
  );
  it("manual transfer retains full background and warns against invented personal profiles", () => {
    const long = "不自动扩大授权。".repeat(1000);
    const text = draftForScenario(
      "new",
      "context",
      "协作",
      guideDetail({ content: long }),
      "Cursor",
    );
    expect(text).toContain(long);
    expect(text).toContain("[m1 · v1]");
    expect(text).toContain("不代表完整个人画像");
    expect(text).toContain("workspace:project-a");
  });
  it("invalidates changed revision, content, scope, citation or status", () => {
    const original = guideDetail();
    expect(sameGuideMemory(original, guideDetail())).toBe(true);
    for (const update of [
      { revision: 2 },
      { content: "已改" },
      { scopes: ["all-apps"] },
      { evidence_ids: ["e2"] },
      { status: "deleted" as const },
    ]) {
      expect(sameGuideMemory(original, guideDetail(update))).toBe(false);
    }
  });
});
