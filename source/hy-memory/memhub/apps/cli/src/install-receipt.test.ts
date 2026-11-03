import {
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { resolveEntryDiagnostics } from "./entry-diagnostics.js";
import {
  defaultInstallReceiptPath,
  readInstallReceipt,
  removeInstallReceipt,
  resolveDiagnosticsDataDir,
  resolveInstalledDataDir,
  writeInstallReceipt,
} from "./install-receipt.js";

async function root(): Promise<string> {
  return mkdtemp(path.join(tmpdir(), "memhub-install-receipt-"));
}

describe("managed install receipt", () => {
  // C8 P1 isolated-cli-session-writes-home: with only an isolated HOME set,
  // `stop` etc. resolved their data dir to `<HOME>/.one-memory` and wrote
  // `logs/diagnostic-cli.jsonl` into a HOME the caller meant as an isolation
  // root. Entry diagnostics must be skipped in that case.
  describe("entry diagnostics under an isolated HOME", () => {
    it("skips the diagnostic file for an isolated HOME with no data dir", () => {
      const decision = resolveEntryDiagnostics({
        arguments_: ["stop", "--json"],
        home: "/tmp/definitely-not-the-account-home/some-root",
        accountHome: "/Users/somebody",
        environmentDataDir: undefined,
      });
      expect(decision).toEqual({ kind: "skip", reason: "isolated_home" });
    });

    it("keeps diagnostics for the real account home", () => {
      const decision = resolveEntryDiagnostics({
        arguments_: ["stop", "--json"],
        home: "/Users/somebody",
        accountHome: "/Users/somebody",
        environmentDataDir: undefined,
      });
      expect(decision).toEqual({ kind: "log" });
    });

    const accountHome = path.resolve("/Users/somebody");
    it.each([
      `${accountHome}${path.sep}`,
      path.join(accountHome, "."),
      path.join(accountHome, ".", ""),
      path.join(accountHome, "nested", ".."),
    ])("treats %s as the real account home", (home) => {
      // `HOME` can name the real home with redundant path syntax. A
      // lexical-only comparison drops diagnostics for the same directory.
      const decision = resolveEntryDiagnostics({
        arguments_: ["stop", "--json"],
        home,
        accountHome,
        environmentDataDir: undefined,
      });
      expect(decision).toEqual({ kind: "log" });
    });

    it("keeps a parent path isolated even though it shares a lexical prefix", () => {
      // The parent of the account home is not the account home. Do not satisfy
      // a string-shaped approximation by logging outside HOME.
      const accountHome = path.resolve("/Users/somebody");
      const decision = resolveEntryDiagnostics({
        arguments_: ["stop", "--json"],
        home: path.join(accountHome, ".."),
        accountHome,
        environmentDataDir: undefined,
      });
      expect(decision).toEqual({ kind: "skip", reason: "isolated_home" });
    });

    it("keeps diagnostics when an explicit data dir is named", () => {
      const decision = resolveEntryDiagnostics({
        arguments_: ["stop", "--data-dir", "/tmp/isolated/data", "--json"],
        home: "/tmp/definitely-not-the-account-home/some-root",
        accountHome: "/Users/somebody",
        environmentDataDir: undefined,
      });
      expect(decision).toEqual({ kind: "log" });
    });

    it("keeps diagnostics when ONE_MEMORY_DATA_DIR is set", () => {
      const decision = resolveEntryDiagnostics({
        arguments_: ["stop", "--json"],
        home: "/tmp/definitely-not-the-account-home/some-root",
        accountHome: "/Users/somebody",
        environmentDataDir: "/tmp/isolated/data",
      });
      expect(decision).toEqual({ kind: "log" });
    });
  });

  it("round-trips the selected data dir and install root", async () => {
    const home = await root();
    const receiptPath = defaultInstallReceiptPath(home);
    await writeInstallReceipt({
      path: receiptPath,
      dataDir: "/tmp/custom data",
      installRoot: "/tmp/memhub install",
      home,
    });
    const receipt = await readInstallReceipt(receiptPath);
    expect(receipt).toMatchObject({
      schema_version: 1,
      data_dir: "/tmp/custom data",
      install_root: "/tmp/memhub install",
      home,
    });
  });

  it("returns null for a missing or malformed receipt instead of guessing", async () => {
    const home = await root();
    const receiptPath = defaultInstallReceiptPath(home);
    expect(await readInstallReceipt(receiptPath)).toBeNull();
    await mkdir(path.dirname(receiptPath), { recursive: true });
    await writeFile(receiptPath, "not json\n");
    expect(await readInstallReceipt(receiptPath)).toBeNull();
    await writeFile(receiptPath, JSON.stringify({ schema_version: 2 }));
    expect(await readInstallReceipt(receiptPath)).toBeNull();
  });

  it("rejects relative or unsafe data dirs", async () => {
    const home = await root();
    const receiptPath = defaultInstallReceiptPath(home);
    for (const dataDir of ["relative/data", "/tmp/a\nb", ""]) {
      await expect(
        writeInstallReceipt({
          path: receiptPath,
          dataDir,
          installRoot: path.join(home, "install"),
          home,
        }),
      ).rejects.toThrow("install_receipt_data_dir_invalid");
    }
  });

  it("removes only the receipt file it owns", async () => {
    const home = await root();
    const receiptPath = defaultInstallReceiptPath(home);
    await writeInstallReceipt({
      path: receiptPath,
      dataDir: path.join(home, "data"),
      installRoot: path.join(home, "install"),
      home,
    });
    expect(await removeInstallReceipt(receiptPath)).toBe("removed");
    expect(await readInstallReceipt(receiptPath)).toBeNull();
    expect(await removeInstallReceipt(receiptPath)).toBe("not-present");
  });

  it("is idempotent: repeated writes leave exactly one receipt", async () => {
    const home = await root();
    const receiptPath = defaultInstallReceiptPath(home);
    await writeInstallReceipt({
      path: receiptPath,
      dataDir: path.join(home, "data"),
      installRoot: path.join(home, "install"),
      home,
      now: "2026-09-29T00:00:00.000Z",
    });
    await writeInstallReceipt({
      path: receiptPath,
      dataDir: path.join(home, "data"),
      installRoot: path.join(home, "install"),
      home,
      now: "2026-09-29T01:00:00.000Z",
    });
    const entries = await readdir(path.dirname(receiptPath));
    expect(entries.filter((name) => name.includes("cli-install"))).toEqual([
      "cli-install.json",
    ]);
    expect((await readInstallReceipt(receiptPath))?.created_at).toBe(
      "2026-09-29T01:00:00.000Z",
    );
  });

  it("resolves data dir by precedence: env > receipt > undefined", async () => {
    const home = await root();
    const installed = path.join(home, "installed data");
    await writeInstallReceipt({
      path: defaultInstallReceiptPath(home),
      dataDir: installed,
      installRoot: path.join(home, "install"),
      home,
    });
    // No HOME: never consults the receipt (and never reads the real home).
    expect(await resolveInstalledDataDir({})).toBeUndefined();
    expect(await resolveInstalledDataDir({ HOME: home })).toBe(installed);
    // Explicit env wins over the receipt.
    expect(
      await resolveInstalledDataDir({
        HOME: home,
        ONE_MEMORY_DATA_DIR: "/tmp/explicit",
      }),
    ).toBe("/tmp/explicit");
  });

  it("diagnostics resolution prefers an explicit --data-dir flag", async () => {
    const home = await root();
    await writeInstallReceipt({
      path: defaultInstallReceiptPath(home),
      dataDir: path.join(home, "receipt data"),
      installRoot: path.join(home, "install"),
      home,
    });
    // Explicit flag beats env, receipt, and default.
    expect(
      await resolveDiagnosticsDataDir(
        ["install", "--data-dir", "/tmp/flag data"],
        { HOME: home, ONE_MEMORY_DATA_DIR: "/tmp/env data" },
      ),
    ).toBe("/tmp/flag data");
    // Env beats receipt.
    expect(
      await resolveDiagnosticsDataDir(["install"], {
        HOME: home,
        ONE_MEMORY_DATA_DIR: "/tmp/env data",
      }),
    ).toBe("/tmp/env data");
    // Receipt beats default.
    expect(await resolveDiagnosticsDataDir(["install"], { HOME: home })).toBe(
      path.join(home, "receipt data"),
    );
    // Invalid explicit flag must not silently fall back to the receipt.
    expect(
      await resolveDiagnosticsDataDir(
        ["install", "--data-dir", "relative/data"],
        { HOME: home },
      ),
    ).toBeNull();
  });

  it("keeps the receipt inside the user home", async () => {
    const home = await root();
    const receiptPath = defaultInstallReceiptPath(home);
    await writeInstallReceipt({
      path: receiptPath,
      dataDir: path.join(home, "data"),
      installRoot: path.join(home, "install"),
      home,
    });
    const raw = JSON.parse(await readFile(receiptPath, "utf8")) as {
      home: string;
    };
    expect(raw.home).toBe(home);
    await rm(home, { recursive: true, force: true });
  });
});
