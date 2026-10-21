import { describe, expect, it } from "vitest";

import {
  openBrowser,
  parseUiSessionExchange,
  uiExitCode,
  uiSessionFailure,
} from "./ui-session.js";

describe("memhub ui session wiring", () => {
  it("accepts the contract exchange document and never exposes a token", () => {
    const parsed = parseUiSessionExchange({
      schema_version: 1,
      exchange_code: "opaque-code",
      expires_in_seconds: 60,
      url: "http://127.0.0.1:8765/ui/login?code=opaque-code",
    });
    expect(parsed).toEqual({
      url: "http://127.0.0.1:8765/ui/login?code=opaque-code",
      expiresInSeconds: 60,
    });
    // No bearer/token field is carried through.
    expect(JSON.stringify(parsed)).not.toMatch(/token|bearer|authorization/i);
  });

  it("refuses a non-loopback or non-http URL", () => {
    for (const url of [
      "http://example.com/ui/login?code=x",
      "https://127.0.0.1:8765/ui/login?code=x",
      "http://127.0.0.1.evil.com/ui/login?code=x",
      "file:///tmp/x",
    ]) {
      expect(
        parseUiSessionExchange({
          schema_version: 1,
          exchange_code: "x",
          expires_in_seconds: 60,
          url,
        }),
      ).toBeNull();
    }
  });

  it("refuses a document without a one-time code in the URL", () => {
    for (const doc of [
      null,
      {},
      {
        schema_version: 2,
        exchange_code: "x",
        expires_in_seconds: 60,
        url: "http://127.0.0.1:1/ui/login?code=x",
      },
      { schema_version: 1, exchange_code: "x", expires_in_seconds: 60 },
      {
        schema_version: 1,
        exchange_code: "",
        expires_in_seconds: 60,
        url: "http://127.0.0.1:1/ui/login?code=x",
      },
      {
        schema_version: 1,
        exchange_code: "x",
        expires_in_seconds: 0,
        url: "http://127.0.0.1:1/ui/login?code=x",
      },
      {
        schema_version: 1,
        exchange_code: "x",
        expires_in_seconds: 60,
        url: "http://127.0.0.1:1/",
      },
    ]) {
      expect(parseUiSessionExchange(doc)).toBeNull();
    }
  });

  it("maps failures to the contract codes and exit codes", () => {
    expect(uiSessionFailure("ui_web_assets_unavailable")).toMatchObject({
      code: "ui_web_assets_unavailable",
    });
    expect(
      uiExitCode({
        state: "opened",
        url: "http://127.0.0.1:1/ui/login?code=x",
      }),
    ).toBe(0);
    expect(
      uiExitCode({ state: "blocked", code: "ui_session_contract_unavailable" }),
    ).toBe(4);
    expect(
      uiExitCode({ state: "failed", code: "ui_session_code_invalid" }),
    ).toBe(1);
  });

  it("uses a platform-appropriate opener and reports missing openers", async () => {
    const opened: string[] = [];
    const runner = async (command: string, url: string) => {
      opened.push(`${command} ${url}`);
      return true;
    };
    await expect(
      openBrowser("http://127.0.0.1:1/ui/login?code=x", {
        platform: "darwin",
        run: runner,
      }),
    ).resolves.toBe(true);
    await expect(
      openBrowser("http://127.0.0.1:1/ui/login?code=x", {
        platform: "linux",
        run: runner,
      }),
    ).resolves.toBe(true);
    expect(opened).toEqual([
      "open http://127.0.0.1:1/ui/login?code=x",
      "xdg-open http://127.0.0.1:1/ui/login?code=x",
    ]);
    await expect(
      openBrowser("http://127.0.0.1:1/ui/login?code=x", {
        platform: "win32",
        run: async () => false,
      }),
    ).resolves.toBe(false);
  });
});
