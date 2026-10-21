/** D103: the Reader must start and publish a port the supervisor can use.
 *
 * Covers both halves of the fix against the real Core CLI rather than a
 * stand-in: the supervisor has to spawn `serve --reader` (a bare `--reader`
 * prints usage and exits 2), and Core has to print `reader_port:<n>` on
 * stderr so the supervisor learns the OS-chosen port. Either half missing
 * leaves `readerPort` null, which is the exact regression that shipped --
 * the Reader was attempted on every start and never once ran.
 *
 * Requires the built Core binary; without it the suite reports these as
 * skipped rather than passing, because a Reader test that silently asserts
 * nothing looks like the guard is holding when it is not running at all.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { CoreSupervisor } from "./core-supervisor.js";

const REPO_ROOT = path.resolve(import.meta.dirname, "../../..");
const CORE_BIN = path.join(REPO_ROOT, "apps/core/.venv/bin/one-memory");
const CORE_PYTHON = path.join(REPO_ROOT, "apps/core/.venv/bin/python");

/** `startReader` is private: it is only reachable through `start()`, and the
 * point of this test is the child it spawns. */
type ReaderInternals = {
  activePort: number;
  activeApiToken: string;
  startReader(): Promise<void>;
  stopReader(): Promise<void>;
  readerPort: number | null;
};

const coreAvailable = existsSync(CORE_PYTHON);

describe.skipIf(!coreAvailable)("Reader startup (real Core CLI)", () => {
  let dataDir: string;
  let supervisor: CoreSupervisor | null = null;

  beforeEach(async () => {
    dataDir = await mkdtemp(path.join(tmpdir(), "om-reader-port-"));
    // create_reader_app refuses to start without a database, and it must be
    // a real one: the Reader opens it read-only and reads schema at startup.
    execFileSync(
      CORE_PYTHON,
      [
        "-c",
        "import os\n" +
          "from pathlib import Path\n" +
          "from one_memory.database_access import main_database\n" +
          "with main_database(\n" +
          "    Path(os.environ['ONE_MEMORY_DATA_DIR']) / 'one-memory.sqlite3'\n" +
          ").write() as connection:\n" +
          "    connection.execute('CREATE TABLE t (a INTEGER)')\n",
      ],
      {
        env: {
          ...process.env,
          ONE_MEMORY_DATA_DIR: dataDir,
          PYTHONPATH: path.join(REPO_ROOT, "apps/core/src"),
        },
        stdio: "ignore",
      },
    );
  });

  afterEach(async () => {
    if (supervisor) {
      await (supervisor as unknown as ReaderInternals).stopReader();
      supervisor = null;
    }
    await rm(dataDir, { recursive: true, force: true });
  });

  it("publishes a real port instead of timing out with null", async () => {
    supervisor = new CoreSupervisor({
      launch: { command: CORE_BIN, args: [] },
      dataDir,
      port: 8765,
      apiToken: "test-token",
      readerEnabled: true,
      attempts: 1,
      delayMs: 0,
      probeHealth: async () => ({
        status: "ok",
        service: "one-memory-core",
        version: "0.0.0",
        instance_id: "test",
      }),
    });
    const internals = supervisor as unknown as ReaderInternals;
    // startReader reads these when it builds the child environment.
    internals.activePort = 8765;
    internals.activeApiToken = "test-token";

    await internals.startReader();

    // Not null: that is what a broken launch arg or a missing port report
    // produces, and it is what D103 shipped with.
    expect(internals.readerPort).not.toBeNull();
    expect(internals.readerPort).toBeGreaterThan(0);
  }, 30_000);
});
