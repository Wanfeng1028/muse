// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  clearPendingModelProbe,
  type PendingModelProbe,
  readPendingModelProbe,
  savePendingModelProbe,
} from "./pending-model-probe";

const KEY = "one-memory.pending-model-probe.v1";
const ERROR = "pending_model_probe_failed";
const ID = "11111111-1111-4111-8111-111111111111";
const PROFILE = "22222222-2222-4222-8222-222222222222";
const OTHER = "33333333-3333-4333-8333-333333333333";
const value: PendingModelProbe = {
  operationId: ID,
  profileId: PROFILE,
  inputRevision: 1,
};
const encode = (item: unknown = value) =>
  JSON.stringify({ schemaVersion: 1, value: item });

function store(raw: string | null = null) {
  let data = raw;
  return {
    getItem: vi.fn((_key: string) => data),
    setItem: vi.fn((_key: string, next: string) => {
      data = next;
    }),
    removeItem: vi.fn((_key: string) => {
      data = null;
    }),
  };
}
afterEach(() => vi.restoreAllMocks());

it("absent read never writes or removes", () => {
  const target = store();
  expect(readPendingModelProbe(target)).toBeNull();
  expect(target.getItem).toHaveBeenCalledExactlyOnceWith(KEY);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it("synchronously saves only metadata and reads back before the caller can post", () => {
  const target = store();
  const post = vi.fn();
  savePendingModelProbe(value, target);
  post();
  expect(target.setItem).toHaveBeenCalledExactlyOnceWith(KEY, encode());
  expect(target.getItem).toHaveBeenCalledTimes(2);
  expect(target.getItem.mock.invocationCallOrder[1]).toBeLessThan(
    post.mock.invocationCallOrder[0],
  );
  expect(readPendingModelProbe(target)).toEqual(value);
});

it("recovers through module reload and default storage accessor", async () => {
  const target = store();
  vi.spyOn(window, "localStorage", "get").mockReturnValue(
    target as unknown as Storage,
  );
  savePendingModelProbe(value);
  vi.resetModules();
  const fresh = await import("./pending-model-probe");
  expect(fresh.readPendingModelProbe()).toEqual(value);
  fresh.clearPendingModelProbe(ID);
  expect(fresh.readPendingModelProbe()).toBeNull();
});

it.each([
  "",
  "null",
  "[]",
  "{",
  JSON.stringify({ schemaVersion: 2, value }),
  JSON.stringify({ schemaVersion: "1", value }),
  JSON.stringify({ value }),
  JSON.stringify({ schemaVersion: 1, value, api_key: "DO_NOT_ECHO" }),
  encode({ ...value, endpoint: "DO_NOT_ECHO" }),
  encode({ operationId: ID }),
])("preserves corrupted data without overwrite or clear (%#)", (raw) => {
  const target = store(raw);
  expect(() => readPendingModelProbe(target)).toThrowError(new Error(ERROR));
  expect(() => savePendingModelProbe(value, target)).toThrowError(
    new Error(ERROR),
  );
  expect(() => clearPendingModelProbe(ID, target)).toThrowError(
    new Error(ERROR),
  );
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
  expect(target.getItem(KEY)).toBe(raw);
});

it.each([
  { operationId: "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB" },
  { profileId: "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB" },
  { operationId: `${ID}\n` },
  { profileId: "not-a-uuid" },
  { operationId: null },
  { profileId: 123 },
  { inputRevision: 0 },
  { inputRevision: -1 },
  { inputRevision: 1.5 },
  { inputRevision: "1" },
  { inputRevision: true },
  { inputRevision: Number.MAX_SAFE_INTEGER + 1 },
  { inputRevision: NaN },
])("rejects invalid IDs or revisions before storage writes (%#)", (patch) => {
  const target = store();
  const invalid = { ...value, ...patch } as PendingModelProbe;
  expect(() => savePendingModelProbe(invalid, target)).toThrowError(ERROR);
  expect(() => readPendingModelProbe(store(encode(invalid)))).toThrowError(
    ERROR,
  );
  expect(target.setItem).not.toHaveBeenCalled();
});

it("supports the maximum safe revision and returns independent data", () => {
  const target = store();
  const maximum = { ...value, inputRevision: Number.MAX_SAFE_INTEGER };
  savePendingModelProbe(maximum, target);
  const read = readPendingModelProbe(target);
  expect(read).toEqual(maximum);
  if (read) read.profileId = OTHER;
  expect(readPendingModelProbe(target)).toEqual(maximum);
});

it("rejects getters, hidden fields and symbols without evaluating them", () => {
  const getter = vi.fn(() => ID);
  const accessor = { ...value };
  Object.defineProperty(accessor, "operationId", { get: getter });
  const hidden = { ...value };
  Object.defineProperty(hidden, "secret", { value: "DO_NOT_ECHO" });
  const symbol = { ...value, [Symbol("secret")]: "DO_NOT_ECHO" };
  for (const candidate of [accessor, hidden, symbol])
    expect(() => savePendingModelProbe(candidate, store())).toThrowError(ERROR);
  expect(getter).not.toHaveBeenCalled();
});

it("same intent save is idempotent; no identity field may change", () => {
  const target = store(encode());
  savePendingModelProbe(value, target);
  expect(target.getItem).toHaveBeenCalledTimes(2);
  for (const patch of [
    { operationId: OTHER },
    { profileId: OTHER },
    { inputRevision: 2 },
  ])
    expect(() =>
      savePendingModelProbe({ ...value, ...patch }, target),
    ).toThrowError(ERROR);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(readPendingModelProbe(target)).toEqual(value);
});

it("matching clear is idempotent and cannot clear another ID", () => {
  const target = store(encode());
  for (const id of [OTHER, "invalid", `${ID}\n`])
    expect(() => clearPendingModelProbe(id, target)).toThrowError(ERROR);
  expect(target.removeItem).not.toHaveBeenCalled();
  clearPendingModelProbe(ID, target);
  clearPendingModelProbe(ID, target);
  expect(target.removeItem).toHaveBeenCalledExactlyOnceWith(KEY);
});

it("enforces inclusive 512 UTF-8 bytes before JSON parsing", () => {
  const raw = encode();
  const exact = raw + " ".repeat(512 - new TextEncoder().encode(raw).length);
  expect(readPendingModelProbe(store(exact))).toEqual(value);
  expect(() => readPendingModelProbe(store(`${exact} `))).toThrowError(ERROR);
  const multibyte = encode({ ...value, extra: "界".repeat(130) });
  expect(multibyte.length).toBeLessThan(512);
  expect(new TextEncoder().encode(multibyte).length).toBeGreaterThan(512);
  expect(() => readPendingModelProbe(store(multibyte))).toThrowError(ERROR);
});

it.each(["getItem", "setItem", "removeItem"] as const)(
  "sanitizes %s errors",
  (method) => {
    const target = store(method === "removeItem" ? encode() : null);
    target[method].mockImplementation(() => {
      throw Error("DO_NOT_ECHO");
    });
    expect(() =>
      method === "getItem"
        ? readPendingModelProbe(target)
        : method === "setItem"
          ? savePendingModelProbe(value, target)
          : clearPendingModelProbe(ID, target),
    ).toThrowError(new Error(ERROR));
  },
);

it("denied default storage never escapes raw errors", () => {
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
    throw Error("DO_NOT_ECHO");
  });
  expect(() => readPendingModelProbe()).toThrowError(new Error(ERROR));
  expect(() => savePendingModelProbe(value)).toThrowError(new Error(ERROR));
  expect(() => clearPendingModelProbe(ID)).toThrowError(new Error(ERROR));
});

it.each([null, "corrupt", encode({ ...value, operationId: OTHER })])(
  "failed save readback blocks caller POST without cleanup (%#)",
  (raw) => {
    const target = store();
    const post = vi.fn();
    target.getItem.mockReturnValueOnce(null).mockReturnValue(raw);
    expect(() => {
      savePendingModelProbe(value, target);
      post();
    }).toThrowError(ERROR);
    expect(post).not.toHaveBeenCalled();
    expect(target.setItem).toHaveBeenCalledOnce();
    expect(target.removeItem).not.toHaveBeenCalled();
  },
);

it("rechecks same-intent save and absent clear without removing racing data", () => {
  const target = store();
  target.getItem
    .mockReturnValueOnce(encode())
    .mockReturnValue(encode({ ...value, operationId: OTHER }));
  expect(() => savePendingModelProbe(value, target)).toThrowError(ERROR);
  target.getItem.mockReturnValueOnce(null);
  expect(() => clearPendingModelProbe(ID, target)).toThrowError(ERROR);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it.each([encode(), "corrupt", encode({ ...value, operationId: OTHER })])(
  "failed clear readback never retries deletion (%#)",
  (raw) => {
    const target = store();
    target.getItem.mockReturnValueOnce(encode()).mockReturnValue(raw);
    expect(() => clearPendingModelProbe(ID, target)).toThrowError(ERROR);
    expect(target.removeItem).toHaveBeenCalledOnce();
  },
);
