import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { evictAgentCache } from "@actalk/inkos-core";
import { createStudioServer } from "../api/server.js";

it("keeps answered and blocked outcomes distinct through API delivery and session reload", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-api-completion-"));
  const outcomes = [{ status: "answered", message: "A concise answer." }, { status: "blocked", message: "The requested source is unavailable." }];
  let calls = 0;
  let sessionId: string | undefined;
  const upstream = createServer(async (request, response) => {
    for await (const _chunk of request) {}
    const outcome = outcomes[calls++];
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ choices: [{ finish_reason: "tool_calls", message: { role: "assistant", tool_calls: [{ id: `finish-${calls}`, type: "function",
      function: { name: "finish_turn", arguments: JSON.stringify(outcome) } }] } }] }));
  });
  upstream.listen(0, "127.0.0.1"); await once(upstream, "listening");
  try {
    const baseUrl = `http://127.0.0.1:${(upstream.address() as { port: number }).port}/v1`;
    await mkdir(join(root, ".inkos"));
    await writeFile(join(root, "inkos.json"), JSON.stringify({ name: "fixture", version: "0.1.0", language: "en", llm: {
      defaultModel: "fixture-model", services: [{ service: "custom", name: "fixture", baseUrl, apiFormat: "chat", stream: false, models: ["fixture-model"] }],
    } }));
    await writeFile(join(root, ".inkos/secrets.json"), JSON.stringify({ services: { "custom:fixture": { apiKey: "fixture" } } }));
    const app = createStudioServer({} as never, root);
    const post = (body: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const { session } = await (await app.request("/api/v1/sessions", post({ sessionKind: "chat" }))).json();
    sessionId = session.sessionId;
    const first = await app.request("/api/v1/agent", post({ sessionId: session.sessionId, instruction: "Explain a scene.", model: "fixture-model", service: "custom:fixture" }));
    expect(first.status).toBe(200);
    expect(await first.json()).toMatchObject({ completionStatus: "answered", response: outcomes[0].message });
    const second = await app.request("/api/v1/agent", post({ sessionId: session.sessionId, instruction: "Use the missing source.", model: "fixture-model", service: "custom:fixture" }));
    expect(second.status).toBe(422);
    expect(await second.json()).toMatchObject({ completionStatus: "blocked", error: { code: "AGENT_TASK_INCOMPLETE" } });
    const detail = await (await app.request(`/api/v1/sessions/${session.sessionId}`)).json();
    expect(detail.chatRequest).toMatchObject({ status: "failed", completionStatus: "blocked", error: { code: "AGENT_TASK_INCOMPLETE" }, retry: { text: "Use the missing source." } });
    expect(detail.session.messages.filter((m: { role: string }) => m.role === "assistant").map((m: { content: string }) => m.content)).toEqual(outcomes.map(x => x.message));
    expect(calls).toBe(2);
  } finally {
    if (sessionId) evictAgentCache(sessionId);
    upstream.closeAllConnections(); await new Promise<void>((resolve, reject) => upstream.close(error => error ? reject(error) : resolve()));
    await rm(root, { recursive: true, force: true });
  }
}, 15000);
