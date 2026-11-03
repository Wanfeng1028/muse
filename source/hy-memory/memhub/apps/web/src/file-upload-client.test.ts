// @vitest-environment jsdom
import type {
  FileImportOperationReceipt,
  FileImportReceipt,
} from "@one-memory/contracts";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  reconcileFileUpload,
  recoverableFileUpload,
} from "./file-upload-client";
import {
  readPendingFileUpload,
  savePendingFileUpload,
} from "./pending-file-upload";

const ID = "11111111-1111-4111-8111-111111111111";
const UPLOAD = "22222222-2222-4222-8222-222222222222";
const OTHER = "33333333-3333-4333-8333-333333333333";
const KEY = "one-memory.pending-file-upload.v1";
const file = new File(["PRIVATE BODY"], "private-name.json");
function receipt(
  patch: Partial<FileImportOperationReceipt> = {},
): FileImportOperationReceipt {
  return {
    schema_version: 1,
    operation_id: ID,
    state: "completed",
    upload_id: UPLOAD,
    code: null,
    upload_state: "staged",
    ...patch,
  };
}
const absent = () =>
  receipt({ state: "not_found", upload_id: null, upload_state: null });
function preview(): FileImportReceipt {
  return {
    upload_id: UPLOAD,
    filename: file.name,
    vendor: "generic",
    content_kind: "raw_conversation",
    source_id: "generic-export",
    messages: 1,
    conversations: 1,
    human_messages: 1,
    agent_messages: 0,
    unknown_author_messages: 0,
    skipped_records: 0,
    ignored_files: 0,
    checksum: "a".repeat(64),
    created_at: "2026-09-20T00:00:00Z",
    committed: false,
    preview: [],
  };
}
function transport() {
  return {
    lookup: vi.fn(async (_id: string) => receipt()),
    upload: vi.fn(async (_file: File, _kind: string, _id: string) => receipt()),
    readPreview: vi.fn(async (_id: string) => preview()),
  };
}
beforeEach(() => {
  localStorage.clear();
  vi.spyOn(crypto, "randomUUID").mockReturnValue(ID);
});
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

it("checks capability, journals UUID before POST, reads preview and rechecks operation", async () => {
  const t = transport();
  t.lookup.mockResolvedValueOnce(absent());
  t.upload.mockImplementation(async (sent, kind, id) => {
    expect([sent, kind, id]).toEqual([file, "raw_conversation", ID]);
    expect(readPendingFileUpload()).toBe(ID);
    expect(localStorage.getItem(KEY)).toBe(
      JSON.stringify({ schemaVersion: 1, operationId: ID }),
    );
    return receipt();
  });
  expect(await recoverableFileUpload(file, "raw_conversation", t)).toEqual(
    preview(),
  );
  expect(t.upload).toHaveBeenCalledOnce();
  expect(t.lookup).toHaveBeenCalledTimes(2);
  expect(t.readPreview).toHaveBeenCalledExactlyOnceWith(UPLOAD);
  expect(t.readPreview.mock.invocationCallOrder[0]).toBeLessThan(
    t.lookup.mock.invocationCallOrder[1],
  );
  expect(readPendingFileUpload()).toBeNull();
});

it.each(["transport", "409", "503", "422"])(
  "POST %s loss never permits retransmission, even with a new File",
  async (reason) => {
    const t = transport();
    t.lookup.mockResolvedValueOnce(absent());
    t.upload.mockRejectedValueOnce(Error(`PRIVATE ${reason}`));
    await expect(
      recoverableFileUpload(file, "raw_conversation", t),
    ).rejects.toThrow("file_upload_operation_pending");
    expect(readPendingFileUpload()).toBe(ID);
    expect(
      await recoverableFileUpload(
        new File(["different"], "other.json"),
        "memory_content",
        t,
      ),
    ).toEqual(preview());
    expect(t.upload).toHaveBeenCalledOnce();
    expect(crypto.randomUUID).toHaveBeenCalledOnce();
  },
);

it("reopens and reconciles without a File or any automatic POST", async () => {
  savePendingFileUpload(ID);
  vi.resetModules();
  const fresh = await import("./file-upload-client");
  const t = transport();
  expect(await fresh.reconcileFileUpload(t)).toEqual(preview());
  expect(t.upload).not.toHaveBeenCalled();
  expect(crypto.randomUUID).not.toHaveBeenCalled();
});

it("absent reconcile does not request capability or upload", async () => {
  const t = transport();
  expect(await reconcileFileUpload(t)).toBeNull();
  expect(t.lookup).not.toHaveBeenCalled();
  expect(t.upload).not.toHaveBeenCalled();
});

it.each([
  {},
  { ...absent(), schema_version: 2 },
  { ...absent(), operation_id: OTHER },
  receipt(),
  { ...absent(), filename: "PRIVATE" },
])("invalid fresh capability %# does not store or upload", async (value) => {
  const t = transport();
  t.lookup.mockResolvedValue(value as FileImportOperationReceipt);
  await expect(
    recoverableFileUpload(file, "raw_conversation", t),
  ).rejects.toThrow("file_upload_capability_unavailable");
  expect(readPendingFileUpload()).toBeNull();
  expect(t.upload).not.toHaveBeenCalled();
});

it.each([
  absent(),
  receipt({ state: "pending", upload_id: null, upload_state: null }),
  receipt({ upload_state: "unknown" }),
])(
  "unresolved recovery %# retains ID and never reads preview or POSTs",
  async (value) => {
    savePendingFileUpload(ID);
    const t = transport();
    t.lookup.mockResolvedValue(value);
    await expect(reconcileFileUpload(t)).rejects.toThrow(
      "file_upload_operation_pending",
    );
    expect(readPendingFileUpload()).toBe(ID);
    expect(t.upload).not.toHaveBeenCalled();
    expect(t.readPreview).not.toHaveBeenCalled();
  },
);

it.each(["404", "422", "503"])(
  "GET %s is not evidence of absent upload",
  async (code) => {
    savePendingFileUpload(ID);
    const t = transport();
    t.lookup.mockRejectedValue(Error(`PRIVATE ${code}`));
    await expect(reconcileFileUpload(t)).rejects.toThrow(
      "file_upload_operation_pending",
    );
    expect(readPendingFileUpload()).toBe(ID);
    expect(t.upload).not.toHaveBeenCalled();
  },
);

it.each([
  [
    receipt({
      state: "failed",
      upload_id: null,
      upload_state: null,
      code: "import_upload_invalid",
    }),
    "file_upload_invalid",
  ],
  [receipt({ upload_state: "missing" }), "file_upload_missing"],
] as const)(
  "only authoritative terminal %# clears with safe error",
  async (value, error) => {
    savePendingFileUpload(ID);
    const t = transport();
    t.lookup.mockResolvedValue(value);
    await expect(reconcileFileUpload(t)).rejects.toThrow(error);
    expect(readPendingFileUpload()).toBeNull();
    expect(t.upload).not.toHaveBeenCalled();
    expect(t.readPreview).not.toHaveBeenCalled();
  },
);

it.each([
  { operation_id: OTHER },
  { code: "PRIVATE" },
  { upload_id: "invalid" },
  { upload_state: null },
  { stale: true },
  { state: "discarded" },
])("bad receipt %# cannot release the pending fence", async (patch) => {
  savePendingFileUpload(ID);
  const t = transport();
  t.lookup.mockResolvedValue({
    ...receipt(),
    ...patch,
  } as FileImportOperationReceipt);
  await expect(reconcileFileUpload(t)).rejects.toThrow(
    "file_upload_operation_unavailable",
  );
  expect(readPendingFileUpload()).toBe(ID);
  expect(t.upload).not.toHaveBeenCalled();
});

it.each([
  { upload_id: OTHER },
  { committed: "false" },
  { checksum: "wrong" },
  { endpoint: "PRIVATE" },
])("invalid preview %# never clears", async (patch) => {
  savePendingFileUpload(ID);
  const t = transport();
  t.readPreview.mockResolvedValue({
    ...preview(),
    ...patch,
  } as FileImportReceipt);
  await expect(reconcileFileUpload(t)).rejects.toThrow(
    "file_upload_operation_unavailable",
  );
  expect(readPendingFileUpload()).toBe(ID);
});

it("missing preview GET alone remains unresolved", async () => {
  savePendingFileUpload(ID);
  const t = transport();
  t.readPreview.mockRejectedValue(Error("404 PRIVATE"));
  await expect(reconcileFileUpload(t)).rejects.toThrow(
    "file_upload_operation_pending",
  );
  expect(readPendingFileUpload()).toBe(ID);
});

it.each(["missing", "unknown", "committed"] as const)(
  "post-preview %s change cannot release stale staged preview",
  async (state) => {
    savePendingFileUpload(ID);
    const t = transport();
    t.lookup
      .mockResolvedValueOnce(receipt())
      .mockResolvedValue(receipt({ upload_state: state }));
    await expect(reconcileFileUpload(t)).rejects.toThrow(
      state === "missing"
        ? "file_upload_missing"
        : "file_upload_operation_pending",
    );
    expect(readPendingFileUpload()).toBe(state === "missing" ? null : ID);
    expect(t.upload).not.toHaveBeenCalled();
  },
);

it("committed receipt is returned as committed without any commit action", async () => {
  savePendingFileUpload(ID);
  const t = transport();
  t.lookup.mockResolvedValue(receipt({ upload_state: "committed" }));
  t.readPreview.mockResolvedValue({ ...preview(), committed: true });
  expect((await reconcileFileUpload(t))?.committed).toBe(true);
  expect(t.upload).not.toHaveBeenCalled();
});

it.each(["corrupt", "write", "readback"])(
  "storage %s prevents POST",
  async (kind) => {
    const t = transport();
    t.lookup.mockResolvedValueOnce(absent());
    if (kind === "corrupt") localStorage.setItem(KEY, "{");
    else
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        if (kind === "write") throw Error("PRIVATE");
      });
    await expect(
      recoverableFileUpload(file, "raw_conversation", t),
    ).rejects.toThrow("pending_file_upload_failed");
    expect(t.upload).not.toHaveBeenCalled();
  },
);

it("another operation appearing during capability lookup blocks upload", async () => {
  const t = transport();
  t.lookup.mockImplementation(async () => {
    savePendingFileUpload(OTHER);
    return absent();
  });
  await expect(
    recoverableFileUpload(file, "raw_conversation", t),
  ).rejects.toThrow("pending_file_upload_failed");
  expect(t.upload).not.toHaveBeenCalled();
  expect(readPendingFileUpload()).toBe(OTHER);
});

it("clear failure cannot expose preview as recovered success", async () => {
  savePendingFileUpload(ID);
  const t = transport();
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw Error("PRIVATE");
  });
  await expect(reconcileFileUpload(t)).rejects.toThrow(
    "pending_file_upload_failed",
  );
  expect(readPendingFileUpload()).toBe(ID);
});

it("single-flight rejects another upload or reconcile while checking capability", async () => {
  const t = transport();
  let release!: (value: FileImportOperationReceipt) => void;
  t.lookup.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const first = recoverableFileUpload(file, "raw_conversation", t);
  try {
    await expect(reconcileFileUpload(t)).rejects.toThrow(
      "file_upload_in_flight",
    );
    await expect(
      recoverableFileUpload(file, "raw_conversation", t),
    ).rejects.toThrow("file_upload_in_flight");
  } finally {
    release(absent());
    await first;
  }
  expect(t.upload).toHaveBeenCalledOnce();
});

it.each([
  receipt({ state: "failed", upload_id: null, upload_state: null, code: null }),
  receipt({ state: "failed", code: "import_upload_invalid" }),
  receipt({ state: "pending" }),
  { ...absent(), upload_state: "missing" },
])(
  "inconsistent terminal or pending receipt %# retains the fence",
  async (value) => {
    savePendingFileUpload(ID);
    const t = transport();
    t.lookup.mockResolvedValue(value as FileImportOperationReceipt);
    await expect(reconcileFileUpload(t)).rejects.toThrow(
      "file_upload_operation_unavailable",
    );
    expect(readPendingFileUpload()).toBe(ID);
    expect(t.readPreview).not.toHaveBeenCalled();
    expect(t.upload).not.toHaveBeenCalled();
  },
);

it.each(["wrong-upload", "lookup-loss", "not_found"])(
  "final lookup %s cannot clear pending or return preview",
  async (kind) => {
    savePendingFileUpload(ID);
    const t = transport();
    t.lookup.mockResolvedValueOnce(receipt());
    if (kind === "lookup-loss")
      t.lookup.mockRejectedValueOnce(Error("PRIVATE"));
    else
      t.lookup.mockResolvedValueOnce(
        kind === "not_found" ? absent() : receipt({ upload_id: OTHER }),
      );
    await expect(reconcileFileUpload(t)).rejects.toThrow(
      "file_upload_operation_pending",
    );
    expect(readPendingFileUpload()).toBe(ID);
    expect(t.upload).not.toHaveBeenCalled();
  },
);

it("competing pending during preview cannot be removed or returned as success", async () => {
  savePendingFileUpload(ID);
  const t = transport();
  t.readPreview.mockImplementation(async () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({ schemaVersion: 1, operationId: OTHER }),
    );
    return preview();
  });
  await expect(reconcileFileUpload(t)).rejects.toThrow(
    "pending_file_upload_failed",
  );
  expect(readPendingFileUpload()).toBe(OTHER);
  expect(t.upload).not.toHaveBeenCalled();
});

it("fresh lookup HTTP failure cannot authorize a legacy upload fallback", async () => {
  const t = transport();
  t.lookup.mockRejectedValue(Error("PRIVATE 404"));
  await expect(
    recoverableFileUpload(file, "raw_conversation", t),
  ).rejects.toThrow("file_upload_capability_unavailable");
  expect(readPendingFileUpload()).toBeNull();
  expect(t.upload).not.toHaveBeenCalled();
});

it.each([
  "",
  "export.csv",
  "export",
  "folder/export.json",
  "folder\\export.json",
  "export.json/",
  "export.json\n",
  "export.json ",
  `${"a".repeat(196)}.json`,
  `${"\u{1f600}".repeat(196)}.json`,
])(
  "fresh invalid filename %# fails before capability, storage or upload",
  async (name) => {
    const t = transport();
    const write = vi.spyOn(Storage.prototype, "setItem");
    await expect(
      recoverableFileUpload(new File(["fixture"], name), "raw_conversation", t),
    ).rejects.toThrow("file_upload_input_invalid");
    expect(t.lookup).not.toHaveBeenCalled();
    expect(t.upload).not.toHaveBeenCalled();
    expect(t.readPreview).not.toHaveBeenCalled();
    expect(crypto.randomUUID).not.toHaveBeenCalled();
    expect(write).not.toHaveBeenCalled();
    expect(readPendingFileUpload()).toBeNull();
  },
);

it.each([
  "export.zip",
  "export.JSON",
  "export.Md",
  "export.txt",
  ".md",
  `${"a".repeat(195)}.json`,
  `${"\u{1f600}".repeat(195)}.json`,
])(
  "Core-compatible filename %# supports normal upload and preview",
  async (name) => {
    const input = new File(["fixture"], name);
    const t = transport();
    t.lookup.mockResolvedValueOnce(absent());
    t.readPreview.mockResolvedValue({ ...preview(), filename: name });
    expect(
      (await recoverableFileUpload(input, "raw_conversation", t)).filename,
    ).toBe(name);
    expect(t.upload).toHaveBeenCalledExactlyOnceWith(
      input,
      "raw_conversation",
      ID,
      undefined,
    );
    expect(readPendingFileUpload()).toBeNull();
  },
);

it("invalid new filename does not bypass an existing unresolved operation", async () => {
  savePendingFileUpload(ID);
  const t = transport();
  t.lookup.mockResolvedValue(absent());
  await expect(
    recoverableFileUpload(
      new File(["different"], "bad.csv"),
      "raw_conversation",
      t,
    ),
  ).rejects.toThrow("file_upload_operation_pending");
  expect(t.lookup).toHaveBeenCalledExactlyOnceWith(ID);
  expect(t.upload).not.toHaveBeenCalled();
  expect(crypto.randomUUID).not.toHaveBeenCalled();
  expect(readPendingFileUpload()).toBe(ID);
});
