import { createServer, type Server } from "node:http";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createUiSessionRequest } from "./core-client.js";
import { parseUiSessionExchange } from "./ui-session.js";

/** Real socket, real HTTP: proves the CLI sends the bearer only to Core and
 * parses exactly the contract document. */
describe("ui session exchange over HTTP", () => {
  let server: Server;
  let port: number;
  const seen: Array<{ authorization?: string; method?: string; url?: string }> =
    [];
  let status = 200;

  beforeAll(async () => {
    server = createServer((request, response) => {
      seen.push({
        authorization: request.headers.authorization,
        method: request.method,
        url: request.url,
      });
      response.setHeader("content-type", "application/json");
      if (request.url === "/api/v1/ui/session" && request.method === "POST") {
        response.statusCode = status;
        if (status !== 200) {
          response.end(JSON.stringify({ detail: `http_${status}` }));
          return;
        }
        response.end(
          JSON.stringify({
            schema_version: 1,
            exchange_code: "one-time-code",
            expires_in_seconds: 60,
            url: `http://127.0.0.1:${port}/ui/login?code=one-time-code`,
          }),
        );
        return;
      }
      response.statusCode = 404;
      response.end(JSON.stringify({ detail: "not found" }));
    });
    await new Promise<void>((resolve) => {
      server.listen(0, "127.0.0.1", () => resolve());
    });
    const address = server.address();
    if (address === null || typeof address === "string") {
      throw new Error("no port");
    }
    port = address.port;
  });

  afterAll(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it("POSTs the bearer to Core and returns the loopback code URL", async () => {
    const outcome = await createUiSessionRequest({
      host: "127.0.0.1",
      port,
      apiToken: "core-bearer-secret",
      timeoutMs: 3000,
    })();
    expect(outcome.state).toBe("ok");
    if (outcome.state !== "ok") return;
    const parsed = parseUiSessionExchange(outcome.data);
    expect(parsed).toEqual({
      url: `http://127.0.0.1:${port}/ui/login?code=one-time-code`,
      expiresInSeconds: 60,
    });
    // The bearer went to Core; the browser URL carries only the one-time code.
    expect(seen[0]).toMatchObject({
      authorization: "Bearer core-bearer-secret",
      method: "POST",
      url: "/api/v1/ui/session",
    });
    expect(parsed?.url).not.toMatch(/core-bearer-secret/);
  });

  it("maps a missing contract (404) to a distinct HTTP failure", async () => {
    status = 404;
    const outcome = await createUiSessionRequest({
      host: "127.0.0.1",
      port,
      apiToken: "t",
    })();
    expect(outcome).toEqual({ state: "unavailable", code: "http_404" });
  });

  it("does not collapse distinct HTTP statuses into one failure", async () => {
    for (const candidate of [400, 401, 409, 429, 500, 503]) {
      status = candidate;
      const outcome = await createUiSessionRequest({
        host: "127.0.0.1",
        port,
        apiToken: "t",
      })();
      expect(outcome).toEqual(
        candidate === 503
          ? { state: "unavailable", code: "ui_web_assets_unavailable" }
          : { state: "unavailable", code: `http_${candidate}` },
      );
    }
    status = 200;
  });
});
