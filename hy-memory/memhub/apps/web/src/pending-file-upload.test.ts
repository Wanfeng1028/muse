// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  clearPendingFileUpload,
  readPendingFileUpload,
  savePendingFileUpload,
} from "./pending-file-upload";

const KEY = "one-memory.pending-file-upload.v1";
const ERROR = "pending_file_upload_failed";
const ID = "11111111-1111-4111-8111-111111111111";
const OTHER = "22222222-2222-4222-8222-222222222222";
const encode = (operationId = ID) =>
  JSON.stringify({ schemaVersion: 1, operationId });
function store(raw: string | null = null) {
  let data = raw;
  return {
    getItem: vi.fn((_key: string) => data),
    setItem: vi.fn((_key: string, value: string) => {
      data = value;
    }),
    removeItem: vi.fn((_key: string) => {
      data = null;
    }),
  };
}
afterEach(() => vi.restoreAllMocks());

it("reads absent without writes and saves only the UUID with synchronous readback", () => {
  const target = store();
  expect(readPendingFileUpload(target)).toBeNull();
  expect(target.setItem).not.toHaveBeenCalled();
  savePendingFileUpload(ID, target);
  expect(target.setItem).toHaveBeenCalledExactlyOnceWith(KEY, encode());
  expect(target.getItem).toHaveBeenCalledTimes(3);
  expect(readPendingFileUpload(target)).toBe(ID);
});

it("reopens through fresh module and default storage accessor", async () => {
  const target = store();
  vi.spyOn(window, "localStorage", "get").mockReturnValue(
    target as unknown as Storage,
  );
  savePendingFileUpload(ID);
  vi.resetModules();
  const fresh = await import("./pending-file-upload");
  expect(fresh.readPendingFileUpload()).toBe(ID);
  fresh.clearPendingFileUpload(ID);
  expect(fresh.readPendingFileUpload()).toBeNull();
});

it.each([
  "",
  "{",
  "null",
  "[]",
  JSON.stringify({ operationId: ID }),
  JSON.stringify({ schemaVersion: 2, operationId: ID }),
  JSON.stringify({ schemaVersion: "1", operationId: ID }),
  ...["filename", "path", "content", "api_key"].map((key) =>
    JSON.stringify({ schemaVersion: 1, operationId: ID, [key]: "PRIVATE" }),
  ),
])(
  "corrupt envelope %# fails closed without overwrite or automatic deletion",
  (raw) => {
    const target = store(raw);
    expect(() => readPendingFileUpload(target)).toThrowError(new Error(ERROR));
    expect(() => savePendingFileUpload(ID, target)).toThrowError(
      new Error(ERROR),
    );
    expect(() => clearPendingFileUpload(ID, target)).toThrowError(
      new Error(ERROR),
    );
    expect(target.setItem).not.toHaveBeenCalled();
    expect(target.removeItem).not.toHaveBeenCalled();
  },
);

it.each([
  "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB",
  `${ID}\n`,
  "invalid",
  "",
  null,
  1,
  {},
])("rejects invalid UUID %# before any write", (value) => {
  const target = store();
  expect(() => savePendingFileUpload(value as string, target)).toThrowError(
    ERROR,
  );
  expect(() => clearPendingFileUpload(value as string, target)).toThrowError(
    ERROR,
  );
  expect(() =>
    readPendingFileUpload(store(encode(value as string))),
  ).toThrowError(ERROR);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it("same ID is idempotent, different pending cannot be saved or cleared", () => {
  const target = store(encode());
  savePendingFileUpload(ID, target);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(() => savePendingFileUpload(OTHER, target)).toThrowError(ERROR);
  expect(() => clearPendingFileUpload(OTHER, target)).toThrowError(ERROR);
  expect(target.removeItem).not.toHaveBeenCalled();
  clearPendingFileUpload(ID, target);
  clearPendingFileUpload(ID, target);
  expect(target.removeItem).toHaveBeenCalledExactlyOnceWith(KEY);
});

it("enforces 256 UTF-8 bytes including whitespace before parsing", () => {
  const exact = encode() + " ".repeat(256 - encode().length);
  expect(readPendingFileUpload(store(exact))).toBe(ID);
  expect(() => readPendingFileUpload(store(`${exact} `))).toThrowError(ERROR);
  expect(() =>
    readPendingFileUpload(store(encode() + "界".repeat(80))),
  ).toThrowError(ERROR);
});

it.each(["getItem", "setItem", "removeItem"] as const)(
  "sanitizes %s failure",
  (method) => {
    const target = store(method === "removeItem" ? encode() : null);
    target[method].mockImplementation(() => {
      throw Error("PRIVATE");
    });
    expect(() =>
      method === "getItem"
        ? readPendingFileUpload(target)
        : method === "setItem"
          ? savePendingFileUpload(ID, target)
          : clearPendingFileUpload(ID, target),
    ).toThrowError(new Error(ERROR));
  },
);

it("denied default storage is not silently absent", () => {
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
    throw Error("PRIVATE");
  });
  for (const action of [
    () => readPendingFileUpload(),
    () => savePendingFileUpload(ID),
    () => clearPendingFileUpload(ID),
  ])
    expect(action).toThrowError(new Error(ERROR));
});

it.each([null, "{", encode(OTHER)])(
  "save readback %# prevents subsequent POST",
  (raw) => {
    const target = store();
    target.getItem.mockReturnValueOnce(null).mockReturnValue(raw);
    const post = vi.fn();
    expect(() => {
      savePendingFileUpload(ID, target);
      post();
    }).toThrowError(ERROR);
    expect(post).not.toHaveBeenCalled();
    expect(target.removeItem).not.toHaveBeenCalled();
  },
);

it("rechecks idempotent save and absent clear for races without deleting the replacement", () => {
  const target = store();
  target.getItem.mockReturnValueOnce(encode()).mockReturnValue(encode(OTHER));
  expect(() => savePendingFileUpload(ID, target)).toThrowError(ERROR);
  target.getItem.mockReturnValueOnce(null);
  expect(() => clearPendingFileUpload(ID, target)).toThrowError(ERROR);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it.each([encode(), encode(OTHER), "{"])(
  "clear readback %# fails without retrying deletion",
  (raw) => {
    const target = store();
    target.getItem.mockReturnValueOnce(encode()).mockReturnValue(raw);
    expect(() => clearPendingFileUpload(ID, target)).toThrowError(ERROR);
    expect(target.removeItem).toHaveBeenCalledOnce();
  },
);
