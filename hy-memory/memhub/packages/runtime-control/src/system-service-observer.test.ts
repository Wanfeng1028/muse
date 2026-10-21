import { execFile } from "node:child_process";
import os from "node:os";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { observeSystemService } from "./system-service-observer.js";

vi.mock("node:child_process", () => ({ execFile: vi.fn() }));

describe("system service eligibility observer", () => {
  const input = {
    helperPath: "/fixture/artifact/service-observer",
    home: "/Users/fixture",
    uid: 501,
  };
  let stdout: string;
  let stderr: string;
  let failure: Error | null;
  beforeEach(() => {
    stdout = JSON.stringify({
      schemaVersion: 1,
      systemEligibility: "registered",
    });
    stderr = "";
    failure = null;
    vi.spyOn(process, "platform", "get").mockReturnValue("darwin");
    vi.spyOn(process, "getuid").mockReturnValue(501);
    vi.spyOn(process, "geteuid").mockReturnValue(501);
    vi.spyOn(os, "homedir").mockReturnValue(input.home);
    vi.spyOn(os, "userInfo").mockReturnValue({
      uid: 501,
      gid: 20,
      username: "fixture",
      homedir: input.home,
      shell: "/bin/zsh",
    });
    vi.mocked(execFile).mockImplementation((...args: unknown[]) => {
      const callback = args.at(-1) as (
        error: Error | null,
        out: string,
        err: string,
      ) => void;
      callback(failure, stdout, stderr);
      return {} as ReturnType<typeof execFile>;
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(execFile).mockReset();
  });

  it.each(["registered", "requires_approval", "not_registered", "unknown"])(
    "accepts only eligibility %s",
    async (systemEligibility) => {
      stdout = JSON.stringify({ schemaVersion: 1, systemEligibility });
      expect(await observeSystemService(input)).toEqual({
        schemaVersion: 1,
        systemEligibility,
        code:
          systemEligibility === "unknown"
            ? "system_eligibility_unknown"
            : "system_eligibility_observed",
      });
      expect(execFile).toHaveBeenCalledOnce();
    },
  );

  it("executes only the fixed status argument with bounded clean environment", async () => {
    await observeSystemService(input);
    expect(execFile).toHaveBeenCalledWith(
      input.helperPath,
      ["--status"],
      {
        encoding: "utf8",
        timeout: 2000,
        maxBuffer: 4096,
        killSignal: "SIGKILL",
        shell: false,
        env: {
          HOME: input.home,
          PATH: "/usr/bin:/bin",
          LANG: "C",
          LC_ALL: "C",
        },
      },
      expect.any(Function),
    );
  });

  it.each([
    { uid: 502 },
    { uid: 0 },
    { uid: 501.5 },
    { home: "/Users/other" },
    { home: "/Users/fixture/" },
    { helperPath: "relative/helper" },
    { helperPath: "/tmp/helper\n--status" },
    { helperPath: "/tmp/../helper" },
  ])("rejects mismatched/invalid caller before exec %j", async (patch) => {
    expect(
      (await observeSystemService({ ...input, ...patch })).systemEligibility,
    ).toBe("unknown");
    expect(execFile).not.toHaveBeenCalled();
  });

  it("does not trust an environment-overridden home", async () => {
    vi.mocked(os.userInfo).mockReturnValue({
      ...os.userInfo(),
      homedir: "/Users/real-account",
    });
    expect((await observeSystemService(input)).code).toBe(
      "system_observer_identity_mismatch",
    );
    expect(execFile).not.toHaveBeenCalled();
  });
  it("rejects effective uid mismatch", async () => {
    vi.spyOn(process, "geteuid").mockReturnValue(0);
    expect((await observeSystemService(input)).code).toBe(
      "system_observer_identity_mismatch",
    );
    expect(execFile).not.toHaveBeenCalled();
  });
  it("fails closed if account lookup fails", async () => {
    vi.mocked(os.userInfo).mockImplementation(() => {
      throw Error("private account data");
    });
    expect((await observeSystemService(input)).code).toBe(
      "system_observer_identity_mismatch",
    );
    expect(execFile).not.toHaveBeenCalled();
  });
  it("unsupported platform never invokes the helper", async () => {
    vi.spyOn(process, "platform", "get").mockReturnValue("linux");
    expect((await observeSystemService(input)).code).toBe(
      "system_observer_unsupported",
    );
    expect(execFile).not.toHaveBeenCalled();
  });

  it.each([
    "",
    "{}",
    "[]",
    "null",
    "1",
    "partial{",
    "{}\n{}",
    '{"schemaVersion":2,"systemEligibility":"registered"}',
    '{"schemaVersion":1,"systemEligibility":"disabled_by_system"}',
    '{"schemaVersion":1,"systemEligibility":"registered","token":"secret"}',
    '{"schemaVersion":1,"systemEligibility":"registered","schemaVersion":1}',
    "x".repeat(4097),
  ])("rejects invalid helper output %#", async (text) => {
    stdout = text;
    expect(await observeSystemService(input)).toEqual({
      schemaVersion: 1,
      systemEligibility: "unknown",
      code: "system_observer_invalid_response",
    });
  });
  it("rejects stderr even when process exits zero", async () => {
    stderr = "private error details";
    expect((await observeSystemService(input)).code).toBe(
      "system_observer_invalid_response",
    );
  });
  it.each(["ENOENT", "ETIMEDOUT", "ERR_CHILD_PROCESS_STDIO_MAXBUFFER", "1"])(
    "sanitizes process failure %s even with plausible stdout",
    async (code) => {
      failure = Object.assign(Error("private details"), { code });
      expect(await observeSystemService(input)).toEqual({
        schemaVersion: 1,
        systemEligibility: "unknown",
        code: "system_observer_unavailable",
      });
    },
  );
});
