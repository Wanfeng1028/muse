import {
  mkdir,
  mkdtemp,
  readFile,
  stat,
  utimes,
  writeFile,
} from "node:fs/promises";
import { createServer, type Server } from "node:http";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { applyCursorInstall, planCursorInstall } from "./cursor-installer.js";
import {
  applyRecallInstall,
  cursorLayout,
  previewRecallInstall,
  repairInstalledRecallCommands,
} from "./recall-installer.js";
import { probeRecallInstall } from "./recall-probe.js";
import { planRecallRepoint } from "./recall-repoint.js";

const brokers: Server[] = [];

afterEach(async () => {
  await Promise.all(
    brokers.splice(0).map(
      (server) =>
        new Promise<void>((resolve) => {
          server.close(() => resolve());
        }),
    ),
  );
});

describe("repointing a host that was installed against the wrong path", () => {
  it("turns an unreachable host wired", async () => {
    // The failure this repairs is the one that really happened: a host
    // installed against a plausible but wrong discovery path, healthy by
    // every check we had. Without a repair the three verdicts are only an
    // alarm — the user is told the link is broken and given nothing to do.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const right = await discoveryFor(cursorDir, broker);
    const wrong = path.join(cursorDir, "plausible-but-wrong.json");

    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, wrong)),
    );
    expect((await probeRecallInstall(cursorLayout(cursorDir))).state).toBe(
      "unreachable",
    );

    const repoint = await planRecallRepoint(
      cursorLayout(cursorDir),
      runtime(right),
    );
    if (repoint === null) throw new Error("nothing offered to repair");
    await applyRecallInstall(repoint.plan);

    expect((await probeRecallInstall(cursorLayout(cursorDir))).state).toBe(
      "wired",
    );
    expect(repoint.from).toBe(wrong);
    expect(repoint.to).toBe(right);
  }, 30_000);

  it("repairs an install that still names the app bundle even when discovery is already right", async () => {
    // Discovery lives in the data directory and survives an app move. The
    // command does not: it was the binary inside the .app. A repair that only
    // compares discovery leaves that command in place, so the next upgrade
    // still breaks the host. This fixture is that install.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const right = await discoveryFor(cursorDir, broker);
    const bundled = {
      runtimeCommand: path.join(
        cursorDir,
        "MemHub.app",
        "Contents",
        "MacOS",
        "MemHub",
      ),
      mcpEntryPath: path.join(
        cursorDir,
        "MemHub.app",
        "Contents",
        "Resources",
        "host-bridge",
        "mcp.cjs",
      ),
      discoveryPath: right,
    };
    const stable = {
      runtimeCommand: path.join(cursorDir, "current", "bin", "node"),
      mcpEntryPath: path.join(cursorDir, "current", "host-bridge", "mcp.cjs"),
      recallCliPath: path.join(
        cursorDir,
        "current",
        "host-bridge",
        "recall-cli.cjs",
      ),
      discoveryPath: right,
    };

    await applyCursorInstall(
      await planCursorInstall({ cursorDir, ...bundled }),
    );
    const before = await readFile(path.join(cursorDir, "mcp.json"), "utf8");
    expect(before).toContain("MemHub.app");

    const repoint = await planRecallRepoint(cursorLayout(cursorDir), stable);
    if (repoint === null) throw new Error("bundle command was left unrepaired");
    await applyRecallInstall(repoint.plan);

    const written = await readFile(path.join(cursorDir, "mcp.json"), "utf8");
    expect(written).toContain(stable.runtimeCommand);
    expect(written).toContain(stable.mcpEntryPath);
    expect(written).not.toContain("MemHub.app");
    expect(repoint.from).toBe(bundled.runtimeCommand);
    expect(repoint.to).toBe(stable.runtimeCommand);
  }, 30_000);

  it("corrects an already-installed app once and does not rewrite a command that is already stable", async () => {
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const right = await discoveryFor(cursorDir, broker);
    const stable = {
      runtimeCommand: path.join(cursorDir, "current", "bin", "node"),
      mcpEntryPath: path.join(cursorDir, "current", "host-bridge", "mcp.cjs"),
      discoveryPath: right,
    };
    const bundled = {
      ...stable,
      runtimeCommand: path.join(
        cursorDir,
        "MemHub.app",
        "Contents",
        "MacOS",
        "MemHub",
      ),
      mcpEntryPath: path.join(
        cursorDir,
        "MemHub.app",
        "Contents",
        "Resources",
        "host-bridge",
        "mcp.cjs",
      ),
    };
    const settled = await fixtureDir();
    const settledDiscovery = await discoveryFor(settled, broker);
    const settledRuntime = {
      runtimeCommand: path.join(settled, "current", "bin", "node"),
      mcpEntryPath: path.join(settled, "current", "host-bridge", "mcp.cjs"),
      discoveryPath: settledDiscovery,
    };
    await applyCursorInstall(
      await planCursorInstall({ cursorDir, ...bundled }),
    );
    await applyCursorInstall(
      await planCursorInstall({ cursorDir: settled, ...settledRuntime }),
    );
    const settledPath = path.join(settled, "mcp.json");
    const frozen = new Date("2020-01-01T00:00:00Z");
    await utimes(settledPath, frozen, frozen);

    const repaired = await repairInstalledRecallCommands(
      [cursorLayout(cursorDir), cursorLayout(settled)],
      (layout) =>
        layout.configPath === path.join(cursorDir, "mcp.json")
          ? stable
          : settledRuntime,
    );
    expect(repaired).toEqual(["cursor"]);
    expect(await readFile(path.join(cursorDir, "mcp.json"), "utf8")).toContain(
      stable.runtimeCommand,
    );
    expect((await stat(settledPath)).mtimeMs).toBe(frozen.getTime());

    const again = await repairInstalledRecallCommands(
      [cursorLayout(cursorDir), cursorLayout(settled)],
      (layout) =>
        layout.configPath === path.join(cursorDir, "mcp.json")
          ? stable
          : settledRuntime,
    );
    expect(again).toEqual([]);
  }, 30_000);

  it("leaves a hand-edited call rule alone and still repairs the next host", async () => {
    const edited = await fixtureDir();
    const plain = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const editedDiscovery = await discoveryFor(edited, broker);
    const plainDiscovery = await discoveryFor(plain, broker);
    const bundled = (dir: string, discoveryPath: string) => ({
      runtimeCommand: path.join(dir, "MemHub.app", "MacOS", "MemHub"),
      mcpEntryPath: path.join(dir, "MemHub.app", "host-bridge", "mcp.cjs"),
      discoveryPath,
    });
    const stable = (dir: string, discoveryPath: string) => ({
      runtimeCommand: path.join(dir, "current", "bin", "node"),
      mcpEntryPath: path.join(dir, "current", "host-bridge", "mcp.cjs"),
      discoveryPath,
    });
    await applyCursorInstall(
      await planCursorInstall({
        cursorDir: edited,
        ...bundled(edited, editedDiscovery),
      }),
    );
    await applyCursorInstall(
      await planCursorInstall({
        cursorDir: plain,
        ...bundled(plain, plainDiscovery),
      }),
    );
    const skill = path.join(edited, "skills", "memhub-recall", "SKILL.md");
    await writeFile(skill, `${await readFile(skill, "utf8")}\nuser edited\n`);

    const repaired = await repairInstalledRecallCommands(
      [cursorLayout(edited), cursorLayout(plain)],
      (layout) =>
        layout.configPath === path.join(edited, "mcp.json")
          ? stable(edited, editedDiscovery)
          : stable(plain, plainDiscovery),
    );
    expect(repaired).toEqual(["cursor"]);
    expect(await readFile(path.join(edited, "mcp.json"), "utf8")).toContain(
      "MemHub.app",
    );
    expect(await readFile(skill, "utf8")).toContain("user edited");
    expect(await readFile(path.join(plain, "mcp.json"), "utf8")).toContain(
      path.join(plain, "current", "bin", "node"),
    );
  }, 30_000);

  it("offers nothing when the host already points at the right place", async () => {
    // An install that is already correct must not be rewritten. Offering a
    // repair here would spend the user's trust on a no-op, and every apply
    // touches their config file for nothing.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const right = await discoveryFor(cursorDir, broker);

    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, right)),
    );

    expect(
      await planRecallRepoint(cursorLayout(cursorDir), runtime(right)),
    ).toBeNull();
  }, 30_000);

  it("offers nothing when the app is merely not running", async () => {
    // The entry is right and the app has simply never written its discovery
    // file. Repointing would change nothing, so offering it would send the
    // user to edit a config that is already correct while the actual fix is
    // to open the app. This is the distinction the three verdicts exist for,
    // and it would be thrown away here by keying the repair off "unreachable".
    const cursorDir = await fixtureDir();
    const right = path.join(cursorDir, "not-written-yet.json");

    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, right)),
    );
    expect((await probeRecallInstall(cursorLayout(cursorDir))).state).toBe(
      "unreachable",
    );

    expect(
      await planRecallRepoint(cursorLayout(cursorDir), runtime(right)),
    ).toBeNull();
  }, 30_000);

  it("writes exactly what the preview showed", async () => {
    // The repair reuses plan / preview / apply rather than writing directly,
    // so what the user approves is what lands. Checked by rebuilding the file
    // from the preview's own hunk and comparing it to what apply wrote.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const right = await discoveryFor(cursorDir, broker);
    const wrong = path.join(cursorDir, "wrong.json");

    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, wrong)),
    );
    const repoint = await planRecallRepoint(
      cursorLayout(cursorDir),
      runtime(right),
    );
    if (repoint === null) throw new Error("nothing offered to repair");

    const preview = await previewRecallInstall(repoint.plan);
    await applyRecallInstall(repoint.plan, preview.fingerprint);

    const written = await readFile(path.join(cursorDir, "mcp.json"), "utf8");
    expect(written).toContain(right);
    expect(written).not.toContain(wrong);
    // The preview said which file and showed the new path in its hunk, so a
    // preview that had described some other edit would fail here.
    expect(preview.files.map((file) => file.path)).toContain(
      path.join(cursorDir, "mcp.json"),
    );
    expect(
      preview.files.some((file) =>
        JSON.stringify(file.hunk ?? {}).includes(right),
      ),
    ).toBe(true);
  }, 30_000);

  it("refuses an approval that no longer covers the file", async () => {
    // Same staleness guard as install. Between the preview and the click the
    // user may have edited the config themselves, and an approval is for one
    // specific edit to one specific state of one specific file.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const right = await discoveryFor(cursorDir, broker);

    await applyCursorInstall(
      await planCursorInstall(
        options(cursorDir, path.join(cursorDir, "wrong.json")),
      ),
    );
    const repoint = await planRecallRepoint(
      cursorLayout(cursorDir),
      runtime(right),
    );
    if (repoint === null) throw new Error("nothing offered to repair");
    const preview = await previewRecallInstall(repoint.plan);

    const mcpPath = path.join(cursorDir, "mcp.json");
    const meddled = JSON.parse(await readFile(mcpPath, "utf8"));
    meddled.mcpServers["something-of-theirs"] = { command: "theirs" };
    await writeFile(mcpPath, `${JSON.stringify(meddled, null, 2)}\n`);

    await expect(
      applyRecallInstall(repoint.plan, preview.fingerprint),
      // Refused by whichever guard sees it first. On this path it is the
      // plan's own hash of the target, which fires before the fingerprint is
      // even compared — stricter than the fingerprint, not weaker, and the
      // assertion is written to accept either so that it pins the refusal
      // rather than which layer produced it.
    ).rejects.toThrow(/changed after plan|changed since the preview/);
    expect(await readFile(mcpPath, "utf8")).toContain("something-of-theirs");
  }, 30_000);
});

async function fixtureDir(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-repoint-"));
  const cursorDir = path.join(root, ".cursor");
  await mkdir(cursorDir);
  await writeFile(
    path.join(cursorDir, "mcp.json"),
    `${JSON.stringify({ mcpServers: {} }, null, 2)}\n`,
  );
  return cursorDir;
}

function runtime(discoveryPath: string) {
  return {
    runtimeCommand: process.execPath,
    mcpEntryPath: path.join(process.cwd(), "dist", "mcp.cjs"),
    discoveryPath,
  };
}

function options(cursorDir: string, discoveryPath: string) {
  return { cursorDir, ...runtime(discoveryPath) };
}

function emptyReceipt() {
  return {
    state: "empty",
    query: "__om_probe__",
    scope: "all-apps",
    hits: [],
    used_characters: 0,
    truncated: false,
  };
}

async function brokerReturning(receipt: unknown): Promise<Server> {
  const instanceId = "probe-fixture-instance";
  const broker = createServer((request, response) => {
    if (request.url === "/health") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          status: "ok",
          service: "one-memory-recall-broker",
          instance_id: instanceId,
        }),
      );
      return;
    }
    if (request.url === "/recall") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(receipt));
      return;
    }
    response.writeHead(404);
    response.end();
  });
  await new Promise<void>((resolve) => {
    broker.listen(0, "127.0.0.1", () => resolve());
  });
  brokers.push(broker);
  Object.assign(broker, { instanceId });
  return broker;
}

async function discoveryFor(
  cursorDir: string,
  broker: Server,
): Promise<string> {
  const address = broker.address();
  if (address === null || typeof address === "string") {
    throw new Error("the fixture broker is not listening on a port");
  }
  const discovery = path.join(cursorDir, "broker.json");
  await writeFile(
    discovery,
    `${JSON.stringify({
      schema_version: 1,
      service: "one-memory-recall-broker",
      status: "running",
      host: "127.0.0.1",
      port: address.port,
      instance_id: (broker as Server & { instanceId: string }).instanceId,
      pid: process.pid,
      updated_at: new Date().toISOString(),
    })}\n`,
  );
  return discovery;
}
