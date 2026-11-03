import { mkdtemp, readdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  createServiceLogCapture,
  SERVICE_LOG_MAX_FILE_BYTES,
} from "./service-log.js";

describe("service log capture", () => {
  it("rotates once the per-file cap would be crossed and stays bounded", async () => {
    const dataDir = await mkdtemp(path.join(tmpdir(), "om-service-log-"));
    const capture = await createServiceLogCapture(dataDir);
    expect(capture).not.toBeNull();
    // Two chunks that individually fit but together exceed one file. This is
    // the property launchd's StandardOutPath could not provide: the writer owns
    // the file, so it can rotate before crossing the cap.
    const chunk = "x".repeat(SERVICE_LOG_MAX_FILE_BYTES - 10);
    await capture?.writeStdout(chunk);
    await capture?.writeStdout("y".repeat(200));
    await capture?.flush();

    const logs = path.join(dataDir, "logs");
    const entries = (await readdir(logs)).sort();
    expect(entries).toContain("service.log");
    expect(entries).toContain("service.log.1");
    for (const entry of entries) {
      const info = await stat(path.join(logs, entry));
      expect(info.size).toBeLessThanOrEqual(SERVICE_LOG_MAX_FILE_BYTES);
      // Owner-only, like every other credential-adjacent file.
      expect(info.mode & 0o777).toBe(0o600);
    }
    await rm(dataDir, { recursive: true, force: true });
  });

  it("keeps at most three rotated copies so the family is bounded", async () => {
    const dataDir = await mkdtemp(path.join(tmpdir(), "om-service-log-"));
    const capture = await createServiceLogCapture(dataDir);
    const chunk = "z".repeat(SERVICE_LOG_MAX_FILE_BYTES - 10);
    for (let i = 0; i < 6; i += 1) {
      await capture?.writeStdout(chunk);
    }
    await capture?.flush();
    const entries = (await readdir(path.join(dataDir, "logs"))).filter((name) =>
      name.startsWith("service.log"),
    );
    // service.log + .1 + .2 + .3 -- never unbounded.
    expect(entries.length).toBeLessThanOrEqual(4);
    await rm(dataDir, { recursive: true, force: true });
  });
});
