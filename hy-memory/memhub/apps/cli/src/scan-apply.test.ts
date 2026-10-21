/**
 * `scan` is now wired to Runtime's `POST /api/v1/sources/{id}/sync`.
 *
 * These pin the contract that matters, verified against a real running Core:
 * the endpoint returns 200 with a job, or 409 `live_sync_unavailable`. The CLI
 * must turn 409 into "this source cannot be synced" — NOT into "the command
 * failed", because the caller's next action differs.
 */

import http from "node:http";
import { describe, expect, it } from "vitest";
import { submitBackup, submitScan } from "./core-client.js";

function serveOnce(
  status: number,
  body: unknown,
): Promise<{ host: string; port: number; close: () => void }> {
  return new Promise((resolve) => {
    const server = http.createServer((_request, response) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    });
    server.listen(0, "127.0.0.1", () => {
      const address = server.address() as { address: string; port: number };
      resolve({
        host: address.address,
        port: address.port,
        close: () => server.close(),
      });
    });
  });
}

describe("submitScan", () => {
  it("returns the job Runtime started", async () => {
    const server = await serveOnce(200, {
      job_id: "job-1",
      source_id: "cursor",
      status: "running",
    });
    try {
      const job = await submitScan({ ...server, apiToken: "t" }, "cursor");
      expect(job).toEqual({
        job_id: "job-1",
        source_id: "cursor",
        status: "running",
      });
    } finally {
      server.close();
    }
  });

  it("maps 409 to null: the source cannot be synced, not a command failure", async () => {
    const server = await serveOnce(409, { detail: "live_sync_unavailable" });
    try {
      const job = await submitScan({ ...server, apiToken: "t" }, "cursor");
      expect(job).toBeNull();
    } finally {
      server.close();
    }
  });

  it("surfaces other errors rather than swallowing them", async () => {
    const server = await serveOnce(500, {});
    try {
      await expect(
        submitScan({ ...server, apiToken: "t" }, "cursor"),
      ).rejects.toThrow(/scan_rejected/);
    } finally {
      server.close();
    }
  });
});

describe("submitBackup", () => {
  it("reports the path Runtime chose, not the argument as typed", async () => {
    const server = await serveOnce(200, {
      target: "/data/home/backups/my.sqlite3",
      bytes: 536_576,
    });
    try {
      const result = await submitBackup(
        { ...server, apiToken: "t" },
        "my.sqlite3",
      );
      expect(result).toEqual({
        target: "/data/home/backups/my.sqlite3",
        bytes: 536_576,
      });
    } finally {
      server.close();
    }
  });

  it("names a refused target distinctly so the user can fix the argument", async () => {
    const server = await serveOnce(422, {
      detail: "backup_target_outside_data_dir",
    });
    try {
      await expect(
        submitBackup({ ...server, apiToken: "t" }, "/etc/passwd"),
      ).rejects.toThrow(/backup_target_outside_data_dir/);
    } finally {
      server.close();
    }
  });
});
