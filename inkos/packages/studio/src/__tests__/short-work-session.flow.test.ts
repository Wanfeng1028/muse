import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { createInitialWorkManifestWrite, commitAtomicFileSet } from "@actalk/inkos-core";
import { createStudioServer } from "../api/server.js";

it("runs a book-route session against a short Work with no long-form book.json", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-short-session-"));
  let calls = 0;
  const releases: Array<() => void> = [];
  const upstream = createServer(async (req, res) => {
    for await (const _chunk of req) { /* Consume the real request. */ }
    calls += 1;
    await new Promise<void>(resolve => releases.push(resolve));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ id: "fixture-response", choices: [{ message: { role: "assistant", tool_calls: [{ id: `finish-${calls}`, type: "function", function: { name: "finish_turn", arguments: JSON.stringify({ status: "answered", message: "Ready." }) } }] }, finish_reason: "tool_calls" }], usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } }));
  });
  try {
    upstream.listen(0, "127.0.0.1"); await once(upstream, "listening");
    const baseUrl = `http://127.0.0.1:${(upstream.address() as { port: number }).port}/v1`;
    await mkdir(join(root, ".inkos"));
    await writeFile(join(root, "inkos.json"), JSON.stringify({ name: "fixture", version: "0.1.0", language: "en", llm: {
      defaultModel: "fixture-model", services: [{ service: "custom", name: "fixture", baseUrl, apiFormat: "chat", stream: false, models: ["fixture-model"] }],
    } }));
    await writeFile(join(root, ".inkos/secrets.json"), JSON.stringify({ services: { "custom:fixture": { apiKey: "fixture" } } }));
    const writes = [{ relativePath: "works/short/source/brief.md", content: "A short story." }];
    const initial = createInitialWorkManifestWrite({ workId: "short", title: "Short", profileId: "short-fiction", language: "en", writes });
    await commitAtomicFileSet({ rootDir: root, writes: [...writes, initial.write] });
    const app = createStudioServer({} as never, root);
    const sessionResponse = await app.request("/api/v1/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bookId: "short", workId: "short", sessionKind: "book", modelOverride: "fixture-model", serviceOverride: "custom:fixture" }) });
    expect(sessionResponse.status).toBe(200);
    const { session } = await sessionResponse.json();
    const payload =  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ instruction: "Say you are ready; do not create or edit anything.", activeBookId: "short", workId: "short", profileId: "short-fiction", sessionKind: "book", sessionId: session.sessionId, service: "custom:fixture", model: "fixture-model" }) };
    const run = app.request("/api/v1/agent", payload);
    await expect.poll(() => calls).toBe(1);
    const detail = await (await app.request(`/api/v1/sessions/${session.sessionId}`)).json();
    expect(detail.chatRequest).toMatchObject({ sessionId: session.sessionId, status: "running" });
    const duplicate = await app.request("/api/v1/agent", payload);
    expect(duplicate.status).toBe(409);
    expect(await duplicate.json()).toMatchObject({ error: { code: "CHAT_REQUEST_ALREADY_RUNNING" } });
    expect(calls).toBe(1);
    releases.shift()!();
    const response = await run;
    const body = await response.json();
    expect(response.status, JSON.stringify(body)).toBe(200);
    expect(body.session).toMatchObject({ workId: "short", profileId: "short-fiction" });
    expect((await (await app.request(`/api/v1/sessions/${session.sessionId}`)).json()).chatRequest.status).toBe("completed");
    const secondRun = app.request("/api/v1/agent", payload);
    await expect.poll(() => calls).toBe(2);
    const abort = await app.request(`/api/v1/sessions/${session.sessionId}/abort`, { method: "POST" });
    expect(await abort.json()).toMatchObject({ aborted: true });
    await secondRun;
    expect((await (await app.request(`/api/v1/sessions/${session.sessionId}`)).json()).chatRequest.status).toBe("cancelled");
  } finally {
    for (const release of releases) release();
    upstream.closeAllConnections();
    if (upstream.listening) await new Promise<void>((resolve, reject) => upstream.close(error => error ? reject(error) : resolve()));
    await rm(root, { recursive: true, force: true });
  }
}, 20000);
