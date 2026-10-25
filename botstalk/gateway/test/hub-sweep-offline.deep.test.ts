import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WebSocket } from "ws";
import { OFFLINE_AFTER_MS, SeqTracker, GapRateLimiter } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import type { Conn } from "../src/hub.js";
import { openDb, getPresence } from "../src/db.js";
import type { Db } from "../src/db.js";

const NOW_MS = 1_000_000;

function makeConn(
  adapterId: string,
  lastFrameAtMs: number,
  terminate: ReturnType<typeof vi.fn>,
): Conn {
  return {
    ws: { terminate } as unknown as WebSocket,
    adapterId,
    room: "lobby",
    lastFrameAtMs,
    maxSeenSeq: 0,
    seqTracker: new SeqTracker(),
    gapLimiter: new GapRateLimiter(),
    capabilities: { intents: ["chat"] },
    capabilityVersion: 1,
    capabilitySkills: [],
    capabilityTags: [],
    usageIn: 0,
    usageOut: 0,
    online: true,
  };
}

describe("Hub.sweep heartbeat offline boundary", () => {
  let tmpDir: string;
  let db: Db;
  let hub: Hub;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "botstalk-hub-sweep-"));
    db = openDb(tmpDir);
    hub = new Hub(db);
  });

  afterEach(() => {
    db.close();
    rmSync(tmpDir, { recursive: true, force: true });
    vi.restoreAllMocks();
  });

  it("keeps conn when idle exactly OFFLINE_AFTER_MS", () => {
    const terminate = vi.fn();
    hub.conns.set(
      "edge-eq",
      makeConn("edge-eq", NOW_MS - OFFLINE_AFTER_MS, terminate),
    );

    hub.sweep(NOW_MS);

    expect(hub.conns.has("edge-eq")).toBe(true);
    expect(terminate).toHaveBeenCalledTimes(0);
  });

  it("kicks conn when idle OFFLINE_AFTER_MS + 1", () => {
    const terminate = vi.fn();
    hub.conns.set(
      "edge-plus",
      makeConn("edge-plus", NOW_MS - OFFLINE_AFTER_MS - 1, terminate),
    );

    hub.sweep(NOW_MS);

    expect(hub.conns.has("edge-plus")).toBe(false);
    expect(terminate).toHaveBeenCalledTimes(1);
  });

  it("keeps conn when idle OFFLINE_AFTER_MS - 1", () => {
    const terminate = vi.fn();
    hub.conns.set(
      "edge-minus",
      makeConn("edge-minus", NOW_MS - OFFLINE_AFTER_MS + 1, terminate),
    );

    hub.sweep(NOW_MS);

    expect(hub.conns.has("edge-minus")).toBe(true);
    expect(terminate).toHaveBeenCalledTimes(0);
  });

  it("kicked conn presence set to offline in db", () => {
    const terminate = vi.fn();
    hub.conns.set(
      "sweep-off",
      makeConn("sweep-off", NOW_MS - OFFLINE_AFTER_MS - 1, terminate),
    );

    hub.sweep(NOW_MS);

    const row = getPresence(db, "sweep-off");
    expect(row).toBeDefined();
    expect(row?.status).toBe("offline");
    expect(row?.adapter_id).toBe("sweep-off");
    expect(row?.last_seen_ms).toBe(NOW_MS);
  });

  it("terminate called exactly once on kick", () => {
    const terminate = vi.fn();
    hub.conns.set(
      "once-off",
      makeConn("once-off", NOW_MS - OFFLINE_AFTER_MS - 1, terminate),
    );

    hub.sweep(NOW_MS);
    expect(terminate).toHaveBeenCalledTimes(1);

    hub.sweep(NOW_MS);
    expect(terminate).toHaveBeenCalledTimes(1);
    expect(hub.conns.has("once-off")).toBe(false);
  });

  it("mixed conns: only the timed-out one is kicked", () => {
    const terminateTimeout = vi.fn();
    const terminateAlive = vi.fn();
    hub.conns.set(
      "mix-timeout",
      makeConn("mix-timeout", NOW_MS - OFFLINE_AFTER_MS - 100, terminateTimeout),
    );
    hub.conns.set(
      "mix-alive",
      makeConn("mix-alive", NOW_MS - 1000, terminateAlive),
    );

    hub.sweep(NOW_MS);

    expect(hub.conns.has("mix-timeout")).toBe(false);
    expect(hub.conns.has("mix-alive")).toBe(true);
    expect(terminateTimeout).toHaveBeenCalledTimes(1);
    expect(terminateAlive).toHaveBeenCalledTimes(0);
  });
});
