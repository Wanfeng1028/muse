import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import {
  applyCursorInstall,
  planCursorInstall,
  verifyCursorInstall,
} from "./cursor-installer.js";
import { cursorLayout } from "./recall-installer.js";
import { probeRecallInstall } from "./recall-probe.js";

const brokers: Server[] = [];

afterEach(async () => {
  await Promise.all(
    brokers.splice(0).map(
      (broker) =>
        new Promise<void>((resolve) => {
          broker.close(() => resolve());
        }),
    ),
  );
});

describe("recall link probe", () => {
  // A-24: expected to fail until the receipt shape is settled with M-09.
  // `.fails()` rather than `.skip()` on purpose: it asserts that this case
  // still fails, so whoever fixes the error propagation gets told immediately
  // instead of leaving a test that is silently excluded forever. A skip is a
  // false-green generator, which is the one thing this repo keeps guarding
  // against. Recovery conditions are in OPEN-ITEMS A-24.
  it.fails("reports unreachable where verify reports healthy", async () => {
    // The recorded blind spot, reproduced. Verify compares our files against
    // what we wrote and finds them intact; the host handshake succeeds too,
    // because the stdio server starts and lists its tool without ever needing
    // the app. Three hosts were installed this way and looked perfectly
    // healthy while recalling nothing.
    const cursorDir = await fixtureDir();
    const missing = path.join(cursorDir, "nowhere", "broker.json");
    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, missing)),
    );

    // Healthy, as recorded. This is the defect, not an oversight in the test.
    await expect(verifyCursorInstall(cursorDir)).resolves.toBeUndefined();

    const probe = await probeRecallInstall(cursorLayout(cursorDir));

    expect(probe.state).toBe("unreachable");
    expect(probe.discoveryPresent).toBe(false);
    // Asserted on the words the broker itself produced, so this case cannot
    // pass without the recall call having actually been made. Without it the
    // verdict alone would still read unreachable — the discovery file is
    // missing either way — and this test would go on passing against a probe
    // that only handshakes, which is the very thing it exists to rule out.
    expect(probe.detail).toContain("broker discovery is unavailable");
  }, 30_000);

  it("reports wired against a broker with nothing to say", async () => {
    // A library with no confirmed memories yet is the normal state of a fresh
    // install, and this machine's really is empty for the global scope. A
    // probe that called that "not wired" would cry wolf on every new install.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const discovery = await discoveryFor(cursorDir, broker);
    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );

    const probe = await probeRecallInstall(cursorLayout(cursorDir));

    expect(probe.state).toBe("wired");
    expect(probe.discoveryPresent).toBe(true);
  }, 30_000);

  it("tells a host that cannot reach the app from one that never could", async () => {
    // Two failures that look the same from the outside and are not the same
    // to act on: the app is simply not running (nothing to fix, wait for it),
    // against the entry pointing somewhere the app will never write (a wrong
    // install, fix by repointing). The first must not offer to repoint.
    const cursorDir = await fixtureDir();
    const discovery = path.join(cursorDir, "broker.json");
    await writeFile(
      discovery,
      `${JSON.stringify({
        schema_version: 1,
        service: "one-memory-recall-broker",
        status: "running",
        host: "127.0.0.1",
        // Nothing is listening here. Written as running, which is what a
        // discovery file left behind by a crash says.
        port: 1,
        instance_id: "no-such-instance",
        pid: 1,
        updated_at: new Date().toISOString(),
      })}\n`,
    );
    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );

    const probe = await probeRecallInstall(cursorLayout(cursorDir));

    expect(probe.state).toBe("reachable_but_blind");
    expect(probe.discoveryPresent).toBe(true);
  }, 30_000);

  it("does not call a broker that answers nonsense wired", async () => {
    // The verdict is "a structurally valid receipt came back", not "something
    // came back". Accepting any JSON would report wired against a broker that
    // is answering but not answering this, which is the second of the two
    // things this probe exists to tell apart.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning({ ok: true, memories: [] });
    const discovery = await discoveryFor(cursorDir, broker);
    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );

    const probe = await probeRecallInstall(cursorLayout(cursorDir));

    expect(probe.state).toBe("reachable_but_blind");
  }, 30_000);

  it("runs the command line the host has on disk, not one of its own", async () => {
    // A second implementation of the launch is free to drift from what
    // actually landed, and then the probe reports on a link nobody uses. So
    // it is read back from the host's own config: edited there, the probe
    // must follow the edit.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const discovery = await discoveryFor(cursorDir, broker);
    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );

    const mcpPath = path.join(cursorDir, "mcp.json");
    const config = JSON.parse(await readFile(mcpPath, "utf8"));
    config.mcpServers["one-memory"].args = [
      path.join(process.cwd(), "dist", "no-such-entry.cjs"),
    ];
    await writeFile(mcpPath, `${JSON.stringify(config, null, 2)}\n`);

    const probe = await probeRecallInstall(cursorLayout(cursorDir));

    // The entry it now names does not exist, so the server cannot start. A
    // probe that had built its own command line would have reported wired.
    expect(probe.state).toBe("unreachable");
  }, 30_000);

  it("reports an immediately exiting server without an unhandled EPIPE", async () => {
    const cursorDir = await fixtureDir();
    const discovery = path.join(cursorDir, "broker.json");
    await writeFile(discovery, "{}\n");
    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );
    const exitImmediately = path.join(cursorDir, "exit-immediately.sh");
    await writeFile(exitImmediately, "#!/bin/sh\nexit 0\n");
    await chmod(exitImmediately, 0o700);
    const mcpPath = path.join(cursorDir, "mcp.json");
    const config = JSON.parse(await readFile(mcpPath, "utf8"));
    config.mcpServers["one-memory"].command = exitImmediately;
    config.mcpServers["one-memory"].args = [];
    await writeFile(mcpPath, `${JSON.stringify(config, null, 2)}\n`);

    const probe = await probeRecallInstall(cursorLayout(cursorDir));

    expect(probe.state).toBe("unreachable");
    expect(probe.detail).toMatch(
      /closed before|did not complete the handshake/,
    );
  });

  it("records a self-check in the journal of every fresh install", async () => {
    // Without this the probe is a function nobody calls: it would only run
    // when someone thought to ask, which is never, and the blind spot it
    // exists for would go on being invisible exactly as before. This
    // repository already has three features that exist and are never called,
    // so the wiring is the deliverable, not the function.
    const cursorDir = await fixtureDir();
    const broker = await brokerReturning(emptyReceipt());
    const discovery = await discoveryFor(cursorDir, broker);

    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );

    const journal = JSON.parse(
      await readFile(
        path.join(cursorDir, ".one-memory", "recall-install.json"),
        "utf8",
      ),
    );
    expect(journal.self_check.state).toBe("wired");
    expect(Date.parse(journal.self_check.probed_at)).not.toBeNaN();
  }, 30_000);

  it("still installs when the self-check cannot reach the app", async () => {
    // The install itself succeeded; the app merely is not running. Rolling it
    // back would make a working install impossible to perform before first
    // launch, so the verdict is recorded and the install stands.
    const cursorDir = await fixtureDir();
    const discovery = path.join(cursorDir, "no-such-broker.json");

    await applyCursorInstall(
      await planCursorInstall(options(cursorDir, discovery)),
    );

    const journal = JSON.parse(
      await readFile(
        path.join(cursorDir, ".one-memory", "recall-install.json"),
        "utf8",
      ),
    );
    expect(journal.self_check.state).toBe("unreachable");
    await expect(verifyCursorInstall(cursorDir)).resolves.toBeUndefined();
  }, 30_000);

  it("does not record a pending authorization as a blind link", async () => {
    const { journalSelfCheckFromProbe, recordInstallSelfCheck, cursorLayout } =
      await import("./recall-installer.js");
    const pending = {
      hostId: "cursor",
      state: "reachable_but_blind" as const,
      discoveryPath: "/tmp/broker.json",
      discoveryPresent: true,
      detail:
        "MemHub host authorization is required or has changed. Review this installation in MemHub.",
      probedAt: "2026-09-14T17:14:28.320Z",
    };
    expect(
      journalSelfCheckFromProbe(pending, { omitAuthorizationPending: true }),
    ).toBeUndefined();
    expect(journalSelfCheckFromProbe(pending)?.state).toBe(
      "reachable_but_blind",
    );

    const cursorDir = await fixtureDir();
    const journalPath = path.join(
      cursorDir,
      ".one-memory",
      "recall-install.json",
    );
    await mkdir(path.dirname(journalPath), { recursive: true });
    await writeFile(
      journalPath,
      `${JSON.stringify({ schema_version: 1, installed_at: pending.probedAt }, null, 2)}\n`,
    );
    await recordInstallSelfCheck(cursorLayout(cursorDir), {
      ...pending,
      state: "wired",
      detail: "recalled 1 memories for the self-check",
    });
    const updated = JSON.parse(await readFile(journalPath, "utf8"));
    expect(updated.self_check.state).toBe("wired");
  });
});

async function fixtureDir(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-probe-fixture-"));
  const cursorDir = path.join(root, ".cursor");
  await mkdir(cursorDir);
  await writeFile(
    path.join(cursorDir, "mcp.json"),
    `${JSON.stringify({ mcpServers: {} }, null, 2)}\n`,
  );
  return cursorDir;
}

function options(cursorDir: string, discoveryPath: string) {
  return {
    cursorDir,
    // The real install names the app binary and runs it as Node. Here the
    // probe has to be able to actually start it, so it is Node directly.
    runtimeCommand: process.execPath,
    mcpEntryPath: path.join(process.cwd(), "dist", "mcp.cjs"),
    discoveryPath,
  };
}

/** What core really answers with when it has nothing to offer.
 *
 * The shape matters: a probe that accepted any JSON would report wired
 * against a broker answering nonsense, which is one of the two things it
 * exists to catch.
 */
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
