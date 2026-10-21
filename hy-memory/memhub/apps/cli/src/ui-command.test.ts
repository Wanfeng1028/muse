import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { run } from "./cli.js";

const transport = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("axios", () => ({
  default: { create: vi.fn(() => transport), get: vi.fn() },
}));

const runtime = vi.hoisted(() => ({
  inspectRuntimeStatus: vi.fn(),
  discoverRuntimeAttachment: vi.fn(),
  stopRuntimeProcess: vi.fn(),
  processIsAlive: vi.fn(),
}));

vi.mock("@one-memory/runtime-control", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@one-memory/runtime-control")>()),
  ...runtime,
}));

const ATTACHED = {
  instanceId: "instance-1",
  apiToken: "synthetic-runtime-token",
  host: "127.0.0.1" as const,
  port: 8765,
  servicePid: 4242,
  health: {
    status: "ok",
    service: "one-memory-core",
    version: "1.2.3",
    instanceId: "instance-1",
  },
};

function capture() {
  let value = "";
  const original = process.stdout.write;
  process.stdout.write = ((chunk: string) => {
    value += chunk;
    return true;
  }) as typeof original;
  return {
    value: () => value,
    restore: () => {
      process.stdout.write = original;
    },
  };
}

describe("memhub ui command wiring", () => {
  let directory: string;

  beforeEach(async () => {
    directory = await mkdtemp(path.join(os.tmpdir(), "memhub-ui-"));
    vi.clearAllMocks();
  });

  afterEach(async () => {
    await rm(directory, { recursive: true, force: true });
  });

  it("exchanges a one-time code and opens the returned loopback URL", async () => {
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockResolvedValue({
      status: 200,
      data: {
        schema_version: 1,
        exchange_code: "one-time-code",
        expires_in_seconds: 60,
        url: "http://127.0.0.1:8765/ui/login?code=one-time-code",
      },
    });
    const opened: string[] = [];
    const output = capture();
    let code: number;
    try {
      code = await run(
        ["ui", "--json"],
        {},
        {
          openBrowser: async (url) => {
            opened.push(url);
            return true;
          },
        },
      );
    } finally {
      output.restore();
    }
    expect(code!).toBe(0);
    expect(JSON.parse(output.value())).toMatchObject({
      schema_version: 1,
      product: "memhub",
      command: "ui",
      state: "opened",
      url: "http://127.0.0.1:8765/ui/login?code=one-time-code",
    });
    expect(opened).toEqual([
      "http://127.0.0.1:8765/ui/login?code=one-time-code",
    ]);
    // The bearer token was sent to Core in the request header, never in output.
    expect(output.value()).not.toMatch(/synthetic-runtime-token/);
  });

  it("reports the contract-unavailable block when Core predates the route", async () => {
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockResolvedValue({ status: 404, data: {} });
    const output = capture();
    let code: number;
    try {
      code = await run(["ui", "--json"], {}, { openBrowser: async () => true });
    } finally {
      output.restore();
    }
    expect(code!).toBe(4);
    expect(JSON.parse(output.value())).toMatchObject({
      command: "ui",
      state: "blocked",
      code: "ui_session_contract_unavailable",
    });
  });

  it("reports ui_web_assets_unavailable when Core has no web assets", async () => {
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockResolvedValue({
      status: 503,
      data: { detail: "ui_web_assets_unavailable" },
    });
    const output = capture();
    let code: number;
    try {
      code = await run(["ui", "--json"], {}, { openBrowser: async () => true });
    } finally {
      output.restore();
    }
    expect(code!).toBe(4);
    expect(JSON.parse(output.value())).toMatchObject({
      state: "blocked",
      code: "ui_web_assets_unavailable",
    });
  });

  it("fails without opening a browser when the OS opener is unavailable", async () => {
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    transport.post.mockResolvedValue({
      status: 200,
      data: {
        schema_version: 1,
        exchange_code: "c",
        expires_in_seconds: 60,
        url: "http://127.0.0.1:8765/ui/login?code=c",
      },
    });
    const output = capture();
    let code: number;
    try {
      code = await run(
        ["ui", "--json"],
        {},
        { openBrowser: async () => false },
      );
    } finally {
      output.restore();
    }
    expect(code!).toBe(1);
    expect(JSON.parse(output.value())).toMatchObject({
      state: "failed",
      code: "ui_browser_open_failed",
    });
  });

  it("does not collapse 404, 503 and 500 into the same result", async () => {
    runtime.discoverRuntimeAttachment.mockResolvedValue(ATTACHED);
    const cases = [
      [404, "ui_session_contract_unavailable"],
      [503, "ui_web_assets_unavailable"],
      [500, "ui_session_exchange_failed"],
    ] as const;
    for (const [status, expected] of cases) {
      transport.post.mockResolvedValueOnce({
        status,
        data: status === 503 ? { detail: "ui_web_assets_unavailable" } : {},
      });
      const output = capture();
      let code: number;
      try {
        code = await run(
          ["ui", "--json"],
          {},
          { openBrowser: async () => true },
        );
      } finally {
        output.restore();
      }
      expect(code!).toBe(4);
      expect(JSON.parse(output.value())).toMatchObject({
        command: "ui",
        state: "blocked",
        code: expected,
      });
    }
  });
});
