import { createServer } from "node:http";
import { once } from "node:events";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { readTranscriptEvents } from "@actalk/inkos-core";
import { createStudioServer } from "../api/server.js";
import { ChatRequestStore } from "../api/chat-request-store.js";

it("retains a failed submission across server recreation and exposes an interrupted request without replaying it", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-chat-recovery-"));
  let calls = 0;
  const upstream = createServer(async (req, res) => {
    for await (const _chunk of req) { /* Exercise the actual HTTP adapter. */ }
    calls++;
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { code: "fixture_unavailable", message: "Fixture rejected the request." } }));
  });
  try {
    upstream.listen(0, "127.0.0.1"); await once(upstream, "listening");
    const baseUrl = `http://127.0.0.1:${(upstream.address() as { port: number }).port}/v1`;
    await mkdir(join(root, ".inkos"));
    await writeFile(join(root, "inkos.json"), JSON.stringify({ name: "fixture", version: "0.1.0", language: "en", llm: {
      defaultModel: "fixture-model", services: [{ service: "custom", name: "fixture", baseUrl, apiFormat: "chat", stream: false, models: ["fixture-model"] }],
    } }));
    await writeFile(join(root, ".inkos/secrets.json"), JSON.stringify({ services: { "custom:fixture": { apiKey: "fixture" } } }));
    const app = createStudioServer({} as never, root);
    const post = (body: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const { session } = await (await app.request("/api/v1/sessions", post({ sessionKind: "chat" }))).json();
    const instruction = "Summarize the attached note.";
    const attachments = [{ id: "note", filename: "note.txt", mediaType: "text/plain", size: 5, dataUrl: "data:text/plain;base64,aGVsbG8=" }];
    const response = await app.request("/api/v1/agent", post({ instruction, sessionId: session.sessionId, clientRequestId: "recovery-request",
      sessionKind: "chat", requestedSkills: [], disabledSkills: ["inkos-story-review"], attachments,
      service: "custom:fixture", model: "fixture-model" }));
    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(calls).toBe(1);
    const transcript = await readTranscriptEvents(root, session.sessionId);
    const userEvent = transcript.find(event => event.type === "message" && event.role === "user");
    expect(userEvent?.type === "message" && userEvent.display?.userInput).toEqual({
      text: instruction, language: "en", attachments: [{ filename: "note.txt" }],
    });
    const rawUserMessage = JSON.stringify(userEvent?.type === "message" ? userEvent.message : null);
    const recreated = createStudioServer({} as never, root);
    const detail = await (await recreated.request(`/api/v1/sessions/${session.sessionId}`)).json();
    expect(detail.chatRequest).toMatchObject({ requestId: "recovery-request", status: "failed",
      error: { code: "AGENT_LLM_ERROR" }, retry: { text: instruction, options: { attachments, disabledSkills: ["inkos-story-review"] } } });
    expect(calls).toBe(1);
    expect(detail.session.messages[0].content.split("\n")[0]).toBe(instruction);
    const restoredTranscript = await readTranscriptEvents(root, session.sessionId);
    const restoredUser = restoredTranscript.find(event => event.type === "message" && event.role === "user");
    expect(JSON.stringify(restoredUser?.type === "message" ? restoredUser.message : null)).toBe(rawUserMessage);

    // A process can disappear after saving its submission but before terminal persistence.
    const store = new ChatRequestStore(root);
    await store.save({ ...detail.chatRequest, status: "running", completedAt: undefined, error: undefined });
    const restarted = createStudioServer({} as never, root);
    const interrupted = await (await restarted.request(`/api/v1/sessions/${session.sessionId}`)).json();
    expect(interrupted.chatRequest).toMatchObject({ status: "failed", error: { code: "CHAT_REQUEST_INTERRUPTED" }, retry: detail.chatRequest.retry });
    expect(calls).toBe(1);
    await restarted.request(`/api/v1/sessions/${session.sessionId}`, { method: "DELETE" });
    expect(await store.load(session.sessionId)).toBeNull();
  } finally {
    upstream.closeAllConnections();
    if (upstream.listening) await new Promise<void>((resolve, reject) => upstream.close(error => error ? reject(error) : resolve()));
    await rm(root, { recursive: true, force: true });
  }
}, 20000);
