import { describe, expect, it, vi } from "vitest";
import { processMcpLine } from "./mcp-protocol.js";
import { McpSession } from "./mcp-session.js";

const FOUND = {
  hits: [
    {
      evidence_id: "ev-1",
      conversation_id: "conv-1",
      source_id: "cursor",
      workspace: null,
      project: null,
      created_at: "2026-08-20T10:00:00Z",
      excerpt: "我们说好这个任务先做导入不阻塞",
    },
  ],
  empty_reason: null,
  imported_messages: 4210,
};

function session(search = vi.fn().mockResolvedValue(FOUND)) {
  return {
    search,
    instance: new McpSession(
      "/fixture/discovery.json",
      undefined,
      undefined,
      undefined,
      search,
    ),
  };
}

async function call(
  instance: McpSession,
  args: unknown,
  name = "om_conversations",
) {
  return JSON.parse(
    (await processMcpLine(
      instance,
      JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: { name, arguments: args },
      }),
    )) ?? "",
  );
}

describe("om_conversations", () => {
  it("把原始对话原话连同来自哪个 App、什么时候一起交回去", async () => {
    const { search, instance } = session();

    const response = await call(instance, {
      query: "导入不阻塞",
      limit: 5,
    });

    expect(search).toHaveBeenCalledWith("/fixture/discovery.json", {
      query: "导入不阻塞",
      limit: 5,
    });
    const hit = response.result.structuredContent.hits[0];
    expect(hit.source_id).toBe("cursor");
    expect(hit.created_at).toBe("2026-08-20T10:00:00Z");
    expect(hit.excerpt).toContain("导入不阻塞");
  });

  it("工具说明写清楚它和 om_recall 的分工", async () => {
    const { instance } = session();

    const listed = JSON.parse(
      (await processMcpLine(
        instance,
        JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" }),
      )) ?? "",
    );
    const tool = listed.result.tools.find(
      (item: { name: string }) => item.name === "MemHub_conversations",
    );

    // 宿主的模型只凭这段字判断要不要调它。含糊一点，
    // 「你记得我在 Cursor 聊的那个任务吗」就不会触发。
    expect(tool.description).toContain("another app");
    expect(tool.description).toContain("MemHub_recall");
    expect(tool.annotations.readOnlyHint).toBe(true);
  });

  it("只读，不接受任何写入意图的参数", async () => {
    const { search, instance } = session();

    const response = await call(instance, {
      query: "x",
      scope: "*",
    });

    expect(response.error.message).toContain("unknown arguments");
    expect(search).not.toHaveBeenCalled();
  });

  it("超出范围的 limit 被挡下来，不会传给 Core", async () => {
    const { search, instance } = session();

    const response = await call(instance, { query: "x", limit: 500 });

    expect(response.error.message).toContain("1 to 50");
    expect(search).not.toHaveBeenCalled();
  });

  it("范围内的 limit 会传下去", async () => {
    // 上一条的正面对照：否则「永远不调用」也能让它通过。
    const { search, instance } = session();

    await call(instance, { query: "x", limit: 50 });

    expect(search).toHaveBeenCalledWith("/fixture/discovery.json", {
      query: "x",
      limit: 50,
    });
  });

  it("MemHub 没开的时候明说，而不是回一个空结果", async () => {
    const { instance } = session(
      vi.fn().mockRejectedValue(new Error("MemHub is not running")),
    );

    const response = await call(instance, { query: "x" });

    expect(response.result.isError).toBe(true);
    expect(response.result.content[0].text).toContain("not running");
  });
});
