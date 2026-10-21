import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { hashToken, parseLink, readRedemption, redeemLink, LinkError } from "../src/link.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = join(__dirname, "..");
const FUTURE_EXP = 4102444800000; // 2100-01-01

function makeLink(overrides: Record<string, string> = {}, protocol = "https:"): string {
  const params = new URLSearchParams({
    gateway: "wss://gw.example.test:8765",
    room: "lobby",
    agent: "my-agent",
    token: "0123456789abcdef0123456789abcdef",
    exp: String(FUTURE_EXP),
    ...overrides,
  });
  return `${protocol}//link.botstalk.test/byo?${params.toString()}`;
}

function expectLinkError(fn: () => unknown, code: string): void {
  try {
    fn();
  } catch (err) {
    expect(err).toBeInstanceOf(LinkError);
    expect((err as LinkError).code).toBe(code);
    return;
  }
  throw new Error(`expected LinkError(${code}) but nothing was thrown`);
}

describe("parseLink", () => {
  it("parses a valid https link", () => {
    const link = parseLink(makeLink());
    expect(link.gatewayUrl).toBe("wss://gw.example.test:8765");
    expect(link.room).toBe("lobby");
    expect(link.agentId).toBe("my-agent");
    expect(link.token).toBe("0123456789abcdef0123456789abcdef");
    expect(link.expiresAtMs).toBe(FUTURE_EXP);
  });

  it("accepts the botstalk: scheme", () => {
    const link = parseLink(makeLink({}, "botstalk:"));
    expect(link.agentId).toBe("my-agent");
  });

  it("rejects a missing param with missing_param", () => {
    const params = new URLSearchParams({
      gateway: "wss://gw.example.test:8765",
      room: "lobby",
      agent: "my-agent",
      exp: String(FUTURE_EXP),
    });
    expectLinkError(() => parseLink(`https://link.botstalk.test/byo?${params.toString()}`), "missing_param");
  });

  it("rejects a non-ws gateway with invalid_gateway", () => {
    expectLinkError(() => parseLink(makeLink({ gateway: "https://gw.example.test" })), "invalid_gateway");
  });

  it("rejects a malformed agent id with invalid_agent", () => {
    expectLinkError(() => parseLink(makeLink({ agent: "bad id!" })), "invalid_agent");
  });

  it("rejects a short token with invalid_token", () => {
    expectLinkError(() => parseLink(makeLink({ token: "short" })), "invalid_token");
  });

  it("rejects a non-integer exp with invalid_exp", () => {
    expectLinkError(() => parseLink(makeLink({ exp: "soon" })), "invalid_exp");
  });

  it("rejects garbage input with invalid_url", () => {
    expectLinkError(() => parseLink("not a url"), "invalid_url");
  });
});

describe("redeemLink", () => {
  let dir = "";

  beforeEach(() => {
    dir = join(PKG_ROOT, "test-tmp", `link-state-${Math.random().toString(36).slice(2)}`);
    mkdirSync(dir, { recursive: true });
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("redeems once and records only the token hash", () => {
    const link = parseLink(makeLink());
    expect(redeemLink(dir, link, 1000)).toBe("redeemed");
    const record = readRedemption(dir);
    expect(record).not.toBeNull();
    expect(record?.agentId).toBe("my-agent");
    expect(record?.tokenHash).toBe(hashToken(link.token));
    expect(record?.redeemedAtMs).toBe(1000);
  });

  it("is idempotent for the same link on the same installation", () => {
    const link = parseLink(makeLink());
    expect(redeemLink(dir, link, 1000)).toBe("redeemed");
    expect(redeemLink(dir, link, 2000)).toBe("already");
  });

  it("rejects a different token after redemption", () => {
    const first = parseLink(makeLink());
    const second = parseLink(makeLink({ token: "fedcba9876543210fedcba9876543210" }));
    expect(redeemLink(dir, first, 1000)).toBe("redeemed");
    expectLinkError(() => redeemLink(dir, second, 2000), "link_already_used");
  });

  it("rejects an expired link", () => {
    const link = parseLink(makeLink({ exp: "1000" }));
    expectLinkError(() => redeemLink(dir, link, 2000), "link_expired");
  });
});
