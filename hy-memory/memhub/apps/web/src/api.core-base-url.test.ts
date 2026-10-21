// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

// Captures the request interceptor so the test can drive the *real* request
// path (not just the pure helper): does the resolved bridge port actually reach
// `config.baseURL`?
const fake = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  interceptor: { handler: null as null | ((config: unknown) => unknown) },
}));
vi.mock("axios", () => ({
  default: {
    create: () => ({
      get: fake.get,
      post: fake.post,
      interceptors: {
        request: {
          use: (handler: (config: unknown) => unknown) => {
            fake.interceptor.handler = handler;
          },
        },
      },
    }),
    isAxiosError: () => false,
  },
}));

import { DEFAULT_CORE_URL, getHealth, resolveCoreBaseUrl } from "./api";

afterEach(() => {
  delete (window as unknown as { oneMemory?: unknown }).oneMemory;
  fake.get.mockReset();
});

describe("resolveCoreBaseUrl", () => {
  it("defaults to the fixed local Core when nothing is configured", () => {
    expect(resolveCoreBaseUrl(undefined, undefined)).toBe(DEFAULT_CORE_URL);
    expect(resolveCoreBaseUrl(null, null)).toBe(DEFAULT_CORE_URL);
    expect(DEFAULT_CORE_URL).toBe("http://127.0.0.1:8765");
  });

  it("takes the desktop bridge as the authority for a non-default install root", () => {
    // The desktop main process derived a port for a non-default install root
    // (service-plan hashes the root into 9200-9899) and handed the renderer
    // 9311. The renderer must use exactly that, not the hardcoded default.
    expect(resolveCoreBaseUrl("http://127.0.0.1:9311", undefined)).toBe(
      "http://127.0.0.1:9311",
    );
  });

  it("prefers the bridge over a configured URL, so a stale VITE_CORE_URL cannot win", () => {
    // This is the property that keeps an App on a non-default root off the daily
    // Core: the build-time URL must never override what the main process
    // resolved.
    expect(
      resolveCoreBaseUrl("http://127.0.0.1:9311", "http://127.0.0.1:8765"),
    ).toBe("http://127.0.0.1:9311");
  });

  it("uses the configured URL only when there is no bridge (browser dev)", () => {
    expect(resolveCoreBaseUrl(undefined, "http://127.0.0.1:9311")).toBe(
      "http://127.0.0.1:9311",
    );
  });

  it("ignores an empty bridge value rather than sending requests to an empty base", () => {
    expect(resolveCoreBaseUrl("", "http://127.0.0.1:9311")).toBe(
      "http://127.0.0.1:9311",
    );
    expect(resolveCoreBaseUrl("", undefined)).toBe(DEFAULT_CORE_URL);
  });
});

describe("the request interceptor uses the bridge port", () => {
  function bridge(baseUrl: string) {
    (window as unknown as { oneMemory: unknown }).oneMemory = {
      getApiBaseUrl: vi.fn(async () => baseUrl),
      getApiToken: vi.fn(async () => "token"),
    };
  }

  it("stamps a non-default install root's bridge port onto a real request", async () => {
    bridge("http://127.0.0.1:9311");
    const handler = fake.interceptor.handler;
    expect(
      handler,
      "the interceptor must be registered at import time",
    ).toBeTypeOf("function");
    const config = await handler?.({
      headers: {} as Record<string, string>,
    });
    expect((config as { baseURL?: string }).baseURL).toBe(
      "http://127.0.0.1:9311",
    );
    // The token comes from the same bridge, not from the build-time env.
    expect(
      (config as { headers: Record<string, string> }).headers.Authorization,
    ).toBe("Bearer token");
  });

  it("never lets a bridge-less request read a port from the renderer env", async () => {
    // No bridge => the browser fallback applies. The pure resolver already
    // proves an install-root port cannot be injected from the renderer; this
    // pins that the *request path* consults no other source either.
    fake.get.mockResolvedValue({
      data: {
        status: "ok",
        service: "one-memory-core",
        version: "0.0.0",
        instance_id: "x",
      },
    });
    await getHealth();
    // `config.baseURL` is left as the module default; the bridge is the only
    // per-request override, and there is none here.
    expect(
      (fake.get.mock.calls[0][1] as { baseURL?: string } | undefined)?.baseURL,
    ).toBeUndefined();
  });
});
