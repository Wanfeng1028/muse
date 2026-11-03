import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HostGrantStore } from "./host-grants.js";
import {
  type SourceChangeNotification,
  SourceNotificationDispatcher,
  SourceNotificationError,
} from "./source-notifications.js";

const roots: string[] = [];
afterEach(async () => {
  vi.restoreAllMocks();
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
function event(id = 1, session = "s1"): SourceChangeNotification {
  return {
    version: 1,
    event_id: id.toString(16).padStart(64, "0"),
    session_id: session,
    event_kind: "source-changed",
  };
}
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
async function fixture(hostId = "claude-code") {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-source-notify-"));
  roots.push(root);
  const store = await HostGrantStore.initialize(path.join(root, "grants"));
  const issued = await store.createInstallation({ hostId });
  const checkSource = vi.fn(async (_sourceId: string) => {});
  const synchronize = vi.fn(
    async (_sourceId: string, _signal: AbortSignal) => {},
  );
  let now = 0;
  const dispatcher = new SourceNotificationDispatcher(
    store,
    { checkSource, synchronize },
    { now: () => now },
  );
  return {
    store,
    issued,
    checkSource,
    synchronize,
    dispatcher,
    advance: (ms: number) => {
      now += ms;
    },
  };
}

describe.skipIf(process.platform === "win32")(
  "bounded source notification dispatch",
  () => {
    it("passes only the authenticated mapped source and a signal to the handler", async () => {
      const f = await fixture();
      expect(await f.dispatcher.dispatch(f.issued.secret, event())).toEqual({
        accepted: true,
      });
      expect(f.checkSource).toHaveBeenCalledWith("claude-code");
      expect(f.synchronize).toHaveBeenCalledExactlyOnceWith(
        "claude-code",
        expect.any(AbortSignal),
      );
      await expect(f.store.authenticate(f.issued.secret)).rejects.toMatchObject(
        { code: "host_grant_not_approved" },
      );
    });

    it("reports written and duplicate hook outcomes without payload content", async () => {
      const f = await fixture();
      const observed: Array<{ outcome: string; reason?: string }> = [];
      const dispatcher = new SourceNotificationDispatcher(
        f.store,
        { checkSource: f.checkSource, synchronize: f.synchronize },
        { observe: (value) => void observed.push(value) },
      );
      await dispatcher.dispatch(f.issued.secret, event());
      await dispatcher.dispatch(f.issued.secret, event());
      expect(observed).toEqual([
        { outcome: "written" },
        { outcome: "skipped", reason: "duplicate" },
      ]);
    });

    it.each([
      null,
      [],
      {},
      { ...event(), path: "/never/read" },
      { ...event(), source_id: "cursor" },
      { ...event(), body: "never send" },
      { ...event(), token: "never send" },
      { ...event(), version: 2 },
      { ...event(), event_id: "A".repeat(64) },
      { ...event(), event_id: `${"a".repeat(64)}\n` },
      { ...event(), session_id: "s1\n" },
      { ...event(), session_id: "s1\u2028" },
      { ...event(), session_id: "../invalid" },
      { ...event(), session_id: "s".repeat(129) },
      { ...event(), event_kind: "process" },
    ])(
      "rejects invalid or expanded payload %j before source work",
      async (input) => {
        const f = await fixture();
        await expect(
          f.dispatcher.dispatch(f.issued.secret, input),
        ).rejects.toMatchObject({
          code: "source_notification_invalid",
          status: 400,
        });
        expect(f.checkSource).not.toHaveBeenCalled();
        expect(f.synchronize).not.toHaveBeenCalled();
      },
    );

    it("denies unmapped hosts even when they have an approved recall grant", async () => {
      const f = await fixture("cursor");
      await f.store.approveGrants({
        installationId: f.issued.receipt.installationId,
        expectedRevision: 1,
        allowedTools: ["om_recall"],
        allowedScopes: ["all-apps"],
      });
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event()),
      ).rejects.toMatchObject({ code: "source_host_unmapped", status: 403 });
      expect(f.checkSource).not.toHaveBeenCalled();
      expect(f.synchronize).not.toHaveBeenCalled();
    });

    it("rechecks current source permission even before returning a cached receipt", async () => {
      const f = await fixture();
      await f.dispatcher.dispatch(f.issued.secret, event());
      f.checkSource.mockClear();
      await f.dispatcher.dispatch(f.issued.secret, event());
      expect(f.checkSource).toHaveBeenCalled();
      expect(f.synchronize).toHaveBeenCalledTimes(1);
      f.checkSource.mockRejectedValueOnce(
        new SourceNotificationError("source_not_authorized", 403),
      );
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event()),
      ).rejects.toMatchObject({ status: 403 });
      expect(f.synchronize).toHaveBeenCalledTimes(1);
    });

    it.each(["before-dispatch", "during-sync", "cached"] as const)(
      "blocks revoked identities %s",
      async (stage) => {
        const f = await fixture();
        const revoke = () =>
          f.store
            .revoke({
              installationId: f.issued.receipt.installationId,
              expectedRevision: 1,
            })
            .then(() => {});
        if (stage === "before-dispatch")
          f.checkSource.mockImplementationOnce(revoke);
        if (stage === "during-sync")
          f.synchronize.mockImplementationOnce(revoke);
        if (stage === "cached") {
          await f.dispatcher.dispatch(f.issued.secret, event());
          await revoke();
        }
        await expect(
          f.dispatcher.dispatch(f.issued.secret, event()),
        ).rejects.toMatchObject({
          code: "host_grant_authentication_failed",
          status: 401,
        });
        expect(f.synchronize).toHaveBeenCalledTimes(
          stage === "before-dispatch" ? 0 : 1,
        );
      },
    );

    it("rejects source revocation after sync instead of caching a successful receipt", async () => {
      const f = await fixture();
      f.synchronize.mockImplementationOnce(async () => {
        f.checkSource.mockRejectedValueOnce(
          new SourceNotificationError("source_not_authorized", 403),
        );
      });
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event()),
      ).rejects.toMatchObject({ status: 403 });
      await f.dispatcher.dispatch(f.issued.secret, event());
      expect(f.synchronize).toHaveBeenCalledTimes(2);
    });

    it("coalesces in-flight duplicates, rejects conflicting sessions, and checks every caller", async () => {
      const f = await fixture();
      const release = deferred();
      f.synchronize.mockImplementationOnce(() => release.promise);
      const first = f.dispatcher.dispatch(f.issued.secret, event());
      await vi.waitFor(() => expect(f.synchronize).toHaveBeenCalledOnce());
      const second = f.dispatcher.dispatch(f.issued.secret, event());
      try {
        await vi.waitFor(() =>
          expect(f.checkSource.mock.calls.length).toBeGreaterThanOrEqual(2),
        );
        await expect(
          f.dispatcher.dispatch(f.issued.secret, event(1, "s2")),
        ).rejects.toMatchObject({
          code: "source_notification_conflict",
          status: 409,
        });
      } finally {
        release.resolve();
      }
      expect(await Promise.all([first, second])).toEqual([
        { accepted: true },
        { accepted: true },
      ]);
      expect(f.synchronize).toHaveBeenCalledOnce();
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event(1, "s2")),
      ).rejects.toMatchObject({ status: 409 });
    });

    it("keeps unrelated installations independent and fences same-installation revisions", async () => {
      const f = await fixture();
      f.checkSource.mockImplementationOnce(async () => {
        await f.store.createInstallation({ hostId: "codex" });
      });
      await f.dispatcher.dispatch(f.issued.secret, event());
      f.checkSource.mockImplementationOnce(async () => {
        await f.store.approveGrants({
          installationId: f.issued.receipt.installationId,
          expectedRevision: 1,
          allowedTools: ["om_recall"],
          allowedScopes: ["all-apps"],
        });
      });
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event(2)),
      ).rejects.toMatchObject({ status: 401 });
      expect(f.synchronize).toHaveBeenCalledOnce();
    });

    it("keeps failed-event session identity pinned while allowing an exact retry", async () => {
      const f = await fixture();
      f.synchronize.mockRejectedValueOnce(
        new SourceNotificationError("source_work_unavailable", 409),
      );
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event()),
      ).rejects.toMatchObject({ code: "source_work_unavailable" });
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event(1, "other-session")),
      ).rejects.toMatchObject({
        code: "source_notification_conflict",
        status: 409,
      });
      expect(f.synchronize).toHaveBeenCalledOnce();
      await f.dispatcher.dispatch(f.issued.secret, event());
      expect(f.synchronize).toHaveBeenCalledTimes(2);
    });

    it("enforces 12 distinct events per rolling minute per installation, not per revision", async () => {
      const f = await fixture();
      for (let id = 1; id <= 12; id++)
        await f.dispatcher.dispatch(f.issued.secret, event(id));
      await f.dispatcher.dispatch(f.issued.secret, event());
      const rotated = await f.store.rotateSecret({
        installationId: f.issued.receipt.installationId,
        expectedRevision: 1,
      });
      await expect(
        f.dispatcher.dispatch(rotated.secret, event(13)),
      ).rejects.toMatchObject({
        code: "source_notification_rate_limited",
        status: 429,
      });
      expect(f.synchronize).toHaveBeenCalledTimes(12);
      const other = await f.store.createInstallation({ hostId: "claude-code" });
      await f.dispatcher.dispatch(other.secret, event(13));
      f.advance(60_001);
      await f.dispatcher.dispatch(rotated.secret, event(13));
      expect(f.synchronize).toHaveBeenCalledTimes(14);
    });

    it("limits global sync concurrency to four and releases capacity after failure", async () => {
      const f = await fixture();
      const release = deferred();
      f.synchronize.mockImplementation(() => release.promise);
      const pending = Array.from({ length: 4 }, (_, index) =>
        f.dispatcher.dispatch(f.issued.secret, event(index + 1)),
      );
      await vi.waitFor(() => expect(f.synchronize).toHaveBeenCalledTimes(4));
      try {
        await expect(
          f.dispatcher.dispatch(f.issued.secret, event(5)),
        ).rejects.toMatchObject({
          code: "source_notification_capacity",
          status: 429,
        });
      } finally {
        release.resolve();
      }
      await Promise.all(pending);
      f.synchronize.mockRejectedValueOnce(
        new Error("private internal failure"),
      );
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event(5)),
      ).rejects.toMatchObject({
        code: "source_notification_unavailable",
        status: 503,
      });
      await f.dispatcher.dispatch(f.issued.secret, event(5));
      expect(f.synchronize).toHaveBeenCalledTimes(6);
    });

    it("bounds successful receipt cache at 256 and expires it after 60 seconds", async () => {
      const f = await fixture();
      const installations = [f.issued];
      for (let i = 1; i < 22; i++)
        installations.push(
          await f.store.createInstallation({ hostId: "claude-code" }),
        );
      for (let i = 0; i < 257; i++)
        await f.dispatcher.dispatch(
          installations[Math.floor(i / 12)].secret,
          event(i + 1),
        );
      expect(f.synchronize).toHaveBeenCalledTimes(257);
      await f.dispatcher.dispatch(installations[21].secret, event(257));
      expect(f.synchronize).toHaveBeenCalledTimes(257);
      await f.dispatcher.dispatch(f.issued.secret, event(1));
      expect(f.synchronize).toHaveBeenCalledTimes(258);
      f.advance(60_001);
      await f.dispatcher.dispatch(installations[21].secret, event(257));
      expect(f.synchronize).toHaveBeenCalledTimes(259);
    });

    it("shutdown aborts, drains the actual handler, and never publishes late success", async () => {
      const f = await fixture();
      const release = deferred();
      f.synchronize.mockImplementation(() => release.promise);
      const pending = f.dispatcher
        .dispatch(f.issued.secret, event())
        .catch((error: unknown) => error);
      await vi.waitFor(() => expect(f.synchronize).toHaveBeenCalledOnce());
      let drained = false;
      const stop = f.dispatcher.shutdown().then(() => {
        drained = true;
      });
      await Promise.resolve();
      expect(f.synchronize.mock.calls[0][1].aborted).toBe(true);
      expect(drained).toBe(false);
      release.resolve();
      expect(await pending).toMatchObject({ status: 503 });
      await stop;
      await expect(
        f.dispatcher.dispatch(f.issued.secret, event(2)),
      ).rejects.toMatchObject({ status: 503 });
    });

    it("normalizes untrusted failures and invalid code/status pairs to a fixed error", () => {
      const error = new SourceNotificationError(
        "private token/path" as never,
        200 as never,
      );
      expect(error).toMatchObject({
        code: "source_notification_unavailable",
        status: 503,
      });
      expect(error.message).not.toContain("private");
      expect(error).not.toHaveProperty("cause");
    });
  },
);
