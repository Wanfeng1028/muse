// @vitest-environment jsdom

import { webcrypto } from "node:crypto";
import type { SourceResponse } from "@one-memory/contracts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  appendIntentRequest,
  assertCheckedConnection,
  connectionFingerprint,
  freezeConnection,
  readIntentRequests,
} from "./connection-intent";

describe("connection intent recovery journal", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("crypto", webcrypto);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("persists only opaque fingerprints and receipt IDs", async () => {
    const key = await connectionFingerprint("checked-private-path");
    const id = crypto.randomUUID();
    appendIntentRequest(key, [], id);
    expect(readIntentRequests(key)).toEqual([id]);
    expect(JSON.stringify(localStorage)).not.toContain("checked-private-path");
  });

  it("preserves the pre-upload identity and fingerprint when no upload is supplied", async () => {
    const checked = freezeConnection(
      [uploadedSource.source_id],
      [uploadedSource],
      false,
    );
    const legacyIdentity = JSON.stringify([
      false,
      [
        {
          source_id: uploadedSource.source_id,
          candidate_root_id: uploadedSource.candidate_root_id,
          candidate_path: uploadedSource.candidate_path,
          candidate_kind: uploadedSource.candidate_kind,
        },
      ],
    ]);
    expect(checked.identity).toBe(legacyIdentity);
    expect(checked).not.toHaveProperty("importUploadId");
    expect(await connectionFingerprint(checked.identity)).toBe(
      await connectionFingerprint(legacyIdentity),
    );
  });

  it("binds custom candidate revision even when A-B-A returns to the same path and root", () => {
    const source = {
      ...uploadedSource,
      source_id: "cursor",
      candidate_kind: "user_selected" as const,
      candidate_revision: 1,
    };
    const checked = freezeConnection([source.source_id], [source], false);
    const replaced = { ...source, candidate_revision: 3 };
    expect(
      freezeConnection([source.source_id], [replaced], false).identity,
    ).not.toBe(checked.identity);
    expect(() => assertCheckedConnection(checked, [replaced])).toThrow(
      /来源位置/,
    );
    expect(() => assertCheckedConnection(checked, [source])).not.toThrow();
  });

  it("starts a new connection after revocation but retains that intent after its grant commits", () => {
    const freeze = (authorized: boolean, grant_revision: number) =>
      freezeConnection(
        [uploadedSource.source_id],
        [{ ...uploadedSource, authorized, grant_revision }],
        false,
      );
    expect(freeze(false, 0).identity).toBe(freeze(true, 1).identity);
    expect(freeze(false, 1).identity).not.toBe(freeze(false, 0).identity);
    expect(freeze(false, 1).identity).toBe(freeze(true, 2).identity);
    expect(freeze(false, 2).identity).not.toBe(freeze(false, 1).identity);
  });

  it("invalidates a frozen connection when its source is revoked during confirmation", () => {
    const active = { ...uploadedSource, authorized: true, grant_revision: 2 };
    const checked = freezeConnection([active.source_id], [active], false);
    expect(() =>
      assertCheckedConnection(checked, [{ ...active, authorized: false }]),
    ).toThrow();
    const revoked = { ...active, authorized: false };
    const regrant = freezeConnection([revoked.source_id], [revoked], false);
    expect(() =>
      assertCheckedConnection(regrant, [{ ...active, grant_revision: 3 }]),
    ).not.toThrow();
  });

  it.each([-1, 1.5, Number.NaN, Number.MAX_SAFE_INTEGER + 1])(
    "rejects an invalid source grant revision %s",
    (grant_revision) => {
      expect(() =>
        freezeConnection(
          [uploadedSource.source_id],
          [{ ...uploadedSource, grant_revision }],
          false,
        ),
      ).toThrow();
    },
  );

  it("freezes upload identity separately from the unchanged directory and journals only its hash", async () => {
    const firstId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const secondId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const freeze = (id?: string) =>
      freezeConnection([uploadedSource.source_id], [uploadedSource], false, id);
    const first = freeze(firstId);
    const duplicate = freeze(firstId);
    const next = freeze(secondId);
    expect(first.importUploadId).toBe(firstId);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.sources)).toBe(true);
    expect(first.identity).toBe(duplicate.identity);
    expect(first.sources).toEqual(next.sources);
    expect(
      new Set([freeze().identity, first.identity, next.identity]).size,
    ).toBe(3);
    const fingerprint = await connectionFingerprint(first.identity);
    const nextFingerprint = await connectionFingerprint(next.identity);
    expect(nextFingerprint).not.toBe(fingerprint);
    appendIntentRequest(fingerprint, [], crypto.randomUUID());
    appendIntentRequest(nextFingerprint, [], crypto.randomUUID());
    const stored = JSON.stringify(localStorage);
    expect(stored).toContain(fingerprint);
    expect(stored).not.toContain(firstId);
    expect(stored).not.toContain(secondId);
    expect(stored).not.toContain(uploadedSource.candidate_path);
    expect(stored).not.toContain("importUploadId");
  });

  it("does not overwrite a concurrently extended retry chain", async () => {
    const key = await connectionFingerprint("checked");
    const id = crypto.randomUUID();
    appendIntentRequest(key, [], id);
    expect(() => appendIntentRequest(key, [], crypto.randomUUID())).toThrow();
    expect(readIntentRequests(key)).toEqual([id]);
  });

  it("refuses a corrupt journal instead of losing an uncertain request", async () => {
    const key = await connectionFingerprint("checked");
    appendIntentRequest(key, [], crypto.randomUUID());
    localStorage.setItem(localStorage.key(0) as string, "{broken");
    expect(() => readIntentRequests(key)).toThrow();
    expect(() => appendIntentRequest(key, [], crypto.randomUUID())).toThrow();
  });

  it("retains prior request IDs when the bounded retry chain fills", async () => {
    const key = await connectionFingerprint("checked");
    const ids: string[] = [];
    for (let i = 0; i < 16; i += 1) {
      const id = crypto.randomUUID();
      appendIntentRequest(key, ids, id);
      ids.push(id);
    }
    expect(() => appendIntentRequest(key, ids, crypto.randomUUID())).toThrow();
    expect(readIntentRequests(key)).toEqual(ids);
  });
});

const uploadedSource: SourceResponse = {
  source_id: "generic-export",
  display_name: "Generic export",
  storage_kinds: ["jsonl"],
  available: true,
  authorized: false,
  detected: null,
  root_label: null,
  candidate_path: "~/data/import-files/ready/generic-export",
  candidate_kind: "default",
  candidate_root_id: "root:v2:ready",
  imported_messages: 0,
  imported_conversations: 0,
  sync_enabled: false,
  sync_completeness: "one_time_snapshot",
  capabilities: {
    historical_import: "implemented",
    incremental_import: "implemented",
    live_sync: "implemented",
    recall: "implemented",
    installer: "implemented",
    verification: "fixture_only",
  },
};
