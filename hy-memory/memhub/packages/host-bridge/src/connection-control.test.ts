import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import axios from "axios";
import { afterEach, expect, it, vi } from "vitest";
import { RecallBroker } from "./recall-broker.js";

const closers: Array<() => Promise<void>> = [];
afterEach(async () => {
  await Promise.all(closers.splice(0).map((close) => close()));
});
async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-control-"));
  const handler = vi.fn(async (_request: unknown) => ({ available: true }));
  const broker = new RecallBroker({
    coreBaseUrl: "http://127.0.0.1:1",
    coreApiToken: "synthetic-admin-token",
    discoveryPath: path.join(root, "broker.json"),
    instanceId: "control-fixture",
    preferredPort: 0,
    connectionControl: handler,
  });
  await broker.start();
  closers.push(() => broker.stop());
  const send = (body: unknown, headers: Record<string, string> = {}) =>
    axios.post(`http://127.0.0.1:${broker.port}/control/connections`, body, {
      headers: { Authorization: "Bearer synthetic-admin-token", ...headers },
      validateStatus: () => true,
    });
  return { handler, send };
}
const request = {
  schema_version: 1,
  instance_id: "control-fixture",
  action: "capability",
  input: {},
};
it("dispatches only an authenticated instance-bound control envelope", async () => {
  const { handler, send } = await setup();
  const result = await send(request);
  expect(result.status).toBe(200);
  expect(result.data).toEqual({
    schema_version: 1,
    instance_id: request.instance_id,
    action: request.action,
    result: { available: true },
  });
  expect(handler).toHaveBeenCalledOnce();
  expect(handler.mock.calls[0][0]).toEqual(request);
  expect(result.headers["cache-control"]).toBe("no-store");
});
it.each([
  { Authorization: "Bearer omhg_v1_untrusted" },
  { Authorization: "Bearer wrong" },
  { Origin: "http://127.0.0.1" },
  { "Sec-Fetch-Site": "same-origin" },
] as Record<string, string>[])(
  "rejects browser/host authorization without dispatch %#",
  async (headers) => {
    const { handler, send } = await setup();
    const result = await send(request, headers);
    expect(result.status).toBe(403);
    expect(handler).not.toHaveBeenCalled();
  },
);
it.each([
  { ...request, instance_id: "other" },
  { ...request, schema_version: 2 },
  { ...request, action: "shell" },
  { ...request, extra: "path" },
  { ...request, input: null },
])("rejects malformed or different-instance input %#", async (body) => {
  const { handler, send } = await setup();
  expect((await send(body)).status).toBe(400);
  expect(handler).not.toHaveBeenCalled();
});
it("contains handler errors without leaking paths or tokens", async () => {
  const { handler, send } = await setup();
  handler.mockRejectedValueOnce(Error("SECRET/private/path"));
  const response = await send(request);
  expect(response.status).toBe(503);
  expect(response.data).toEqual({ error: "connection_control_unavailable" });
});
it("preserves only fixed actionable control errors", async () => {
  const { handler, send } = await setup();
  handler.mockRejectedValueOnce(Error("sync_hook_remove_first"));
  expect((await send(request)).data).toEqual({
    error: "sync_hook_remove_first",
  });
  handler.mockRejectedValueOnce(Error("sync_hook_remove_first: SECRET"));
  expect((await send(request)).data).toEqual({
    error: "connection_control_unavailable",
  });
});
