import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { HostGrantStore } from "./host-grants.js";

const roots: string[] = [];
afterEach(async () => {
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
async function fixture() {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "om-notification-identity-"),
  );
  roots.push(root);
  const directory = path.join(root, "grants");
  const store = await HostGrantStore.initialize(directory);
  const issued = await store.createInstallation({ hostId: "claude-code" });
  return {
    store,
    issued,
    directory,
    file: path.join(directory, "host-grants.json"),
  };
}

describe.skipIf(process.platform === "win32")(
  "notification installation identity",
  () => {
    it("authenticates install-only without granting any existing read tool", async () => {
      const f = await fixture();
      const before = await readFile(f.file, "utf8");
      const identity = await f.store.authenticateInstallation(f.issued.secret);
      expect(identity).toMatchObject({
        ...f.issued.receipt,
        status: "install-only",
        allowedTools: [],
        allowedScopes: [],
        storeRevision: 1,
      });
      expect(Object.isFrozen(identity)).toBe(true);
      expect(JSON.stringify(identity)).not.toContain(f.issued.secret);
      await expect(f.store.authenticate(f.issued.secret)).rejects.toMatchObject(
        { code: "host_grant_not_approved" },
      );
      for (const tool of [
        "om_recall",
        "om_ask",
        "om_conversations",
        "om_matters",
      ]) {
        await expect(
          f.store.authorize(f.issued.secret, { tool, scopes: ["all-apps"] }),
        ).rejects.toMatchObject({ code: "host_grant_not_approved" });
      }
      expect(await readFile(f.file, "utf8")).toBe(before);
    });

    it("keeps approved reads intact and invalidates both authentication routes on revoke", async () => {
      const f = await fixture();
      const receipt = await f.store.approveGrants({
        installationId: f.issued.receipt.installationId,
        expectedRevision: 1,
        allowedTools: ["om_recall"],
        allowedScopes: ["all-apps"],
      });
      expect(await f.store.authenticateInstallation(f.issued.secret)).toEqual(
        await f.store.authenticate(f.issued.secret),
      );
      await expect(
        f.store.authorize(f.issued.secret, {
          tool: "om_recall",
          scopes: ["all-apps"],
        }),
      ).resolves.toMatchObject(receipt);
      await f.store.revoke({
        installationId: receipt.installationId,
        expectedRevision: receipt.revision,
      });
      const restarted = await HostGrantStore.open(f.directory);
      for (const reader of [f.store, restarted]) {
        await expect(
          reader.authenticateInstallation(f.issued.secret),
        ).rejects.toMatchObject({ code: "host_grant_authentication_failed" });
        await expect(
          reader.authenticate(f.issued.secret),
        ).rejects.toMatchObject({ code: "host_grant_authentication_failed" });
      }
    });

    it("requires the actual current secret, not a host label or prior rotated secret", async () => {
      const f = await fixture();
      const rotated = await f.store.rotateSecret({
        installationId: f.issued.receipt.installationId,
        expectedRevision: 1,
      });
      for (const value of [
        undefined,
        "claude-code",
        f.issued.receipt.installationId,
        f.issued.secret,
        `omhg_v1_${"a".repeat(43)}`,
      ]) {
        await expect(
          f.store.authenticateInstallation(value as string),
        ).rejects.toMatchObject({ code: "host_grant_authentication_failed" });
      }
      await expect(
        f.store.authenticateInstallation(rotated.secret),
      ).resolves.toMatchObject({ status: "install-only", revision: 2 });
      await expect(f.store.authenticate(rotated.secret)).rejects.toMatchObject({
        code: "host_grant_not_approved",
      });
    });

    it("fails closed on corrupt store and does not leak content", async () => {
      const f = await fixture();
      await writeFile(f.file, `broken ${f.issued.secret}`);
      const error = await f.store
        .authenticateInstallation(f.issued.secret)
        .catch((value: unknown) => value);
      expect(error).toMatchObject({ code: "host_grant_store_corrupt" });
      expect(JSON.stringify(error)).not.toContain(f.issued.secret);
      expect(error).not.toHaveProperty("cause");
    });
  },
);
