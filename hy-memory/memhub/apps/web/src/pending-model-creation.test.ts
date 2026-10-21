// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  clearPendingModelCreation,
  readPendingModelCreation,
  savePendingModelCreation,
} from "./pending-model-creation";

const KEY = "one-memory.pending-model-creation.v1";
const ERROR = "pending_model_creation_failed";
const ID = "d306b9d7-8dd5-4894-b5aa-dfe1e5c57ab9";
const OTHER = "bdb0b477-c9f1-42b7-aabd-6d52ebc5fdce";
const encode = (operationId = ID) =>
  JSON.stringify({ schemaVersion: 1, operationId });
function storage(raw: string | null = null) {
  let value = raw;
  return {
    getItem: vi.fn((_key: string) => value),
    setItem: vi.fn((_key: string, next: string) => {
      value = next;
    }),
    removeItem: vi.fn((_key: string) => {
      value = null;
    }),
  };
}
afterEach(() => vi.restoreAllMocks());

it("returns null only when absent, without writing", () => {
  const target = storage();
  expect(readPendingModelCreation(target)).toBeNull();
  expect(target.getItem).toHaveBeenCalledExactlyOnceWith(KEY);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it("persists only the version and ID across module reload with default storage mocked", async () => {
  const target = storage();
  vi.spyOn(window, "localStorage", "get").mockReturnValue(
    target as unknown as Storage,
  );
  savePendingModelCreation(ID);
  expect(target.setItem).toHaveBeenCalledExactlyOnceWith(KEY, encode());
  vi.resetModules();
  const fresh = await import("./pending-model-creation");
  expect(fresh.readPendingModelCreation()).toBe(ID);
  expect(target.setItem).toHaveBeenCalledOnce();
  fresh.clearPendingModelCreation(ID);
  expect(fresh.readPendingModelCreation()).toBeNull();
});

it.each([
  "",
  "null",
  "[]",
  "{",
  JSON.stringify({ schemaVersion: 2, operationId: ID }),
  JSON.stringify({ schemaVersion: "1", operationId: ID }),
  JSON.stringify({ operationId: ID }),
  JSON.stringify({ schemaVersion: 1 }),
  JSON.stringify({ schemaVersion: 1, operationId: ID, api_key: "DO_NOT_ECHO" }),
  JSON.stringify({
    schemaVersion: 1,
    operationId: ID,
    endpoint: "DO_NOT_ECHO",
    name: "DO_NOT_ECHO",
  }),
])(
  "refuses corrupt or extra-field data without overwriting or deleting it (%#)",
  (raw) => {
    const target = storage(raw);
    expect(() => readPendingModelCreation(target)).toThrowError(
      new Error(ERROR),
    );
    expect(() => savePendingModelCreation(ID, target)).toThrowError(
      new Error(ERROR),
    );
    expect(() => clearPendingModelCreation(ID, target)).toThrowError(
      new Error(ERROR),
    );
    expect(target.setItem).not.toHaveBeenCalled();
    expect(target.removeItem).not.toHaveBeenCalled();
    expect(target.getItem(KEY)).toBe(raw);
  },
);

it.each([
  ID.toUpperCase(),
  ID.replaceAll("-", ""),
  ` ${ID}`,
  `${ID}\n`,
  "",
  "not-a-uuid",
  123,
  null,
])("requires canonical string UUIDs on every entry point (%#)", (invalid) => {
  const target = storage();
  expect(() =>
    savePendingModelCreation(invalid as string, target),
  ).toThrowError(ERROR);
  expect(() =>
    clearPendingModelCreation(invalid as string, target),
  ).toThrowError(ERROR);
  expect(() =>
    readPendingModelCreation(
      storage(JSON.stringify({ schemaVersion: 1, operationId: invalid })),
    ),
  ).toThrowError(ERROR);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it("enforces the inclusive 256 UTF-8 byte limit before JSON parsing", () => {
  const exact =
    encode() + " ".repeat(256 - new TextEncoder().encode(encode()).length);
  expect(readPendingModelCreation(storage(exact))).toBe(ID);
  expect(() => readPendingModelCreation(storage(`${exact} `))).toThrowError(
    ERROR,
  );
  const oversized = JSON.stringify({
    schemaVersion: 1,
    operationId: ID,
    raw: "界".repeat(70),
  });
  expect(oversized.length).toBeLessThan(256);
  expect(new TextEncoder().encode(oversized).length).toBeGreaterThan(256);
  expect(() => readPendingModelCreation(storage(oversized))).toThrowError(
    ERROR,
  );
});

it("same ID is idempotent and another ID cannot overwrite or clear it", () => {
  const target = storage(encode());
  savePendingModelCreation(ID, target);
  expect(target.getItem).toHaveBeenCalledTimes(2);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(() => savePendingModelCreation(OTHER, target)).toThrowError(ERROR);
  expect(() => clearPendingModelCreation(OTHER, target)).toThrowError(ERROR);
  expect(target.removeItem).not.toHaveBeenCalled();
  clearPendingModelCreation(ID, target);
  clearPendingModelCreation(ID, target);
  expect(target.removeItem).toHaveBeenCalledExactlyOnceWith(KEY);
  expect(readPendingModelCreation(target)).toBeNull();
});

it.each(["getItem", "setItem", "removeItem"] as const)(
  "sanitizes %s failures",
  (method) => {
    const target = storage(method === "removeItem" ? encode() : null);
    target[method].mockImplementation(() => {
      throw new Error("DO_NOT_ECHO");
    });
    const action =
      method === "getItem"
        ? () => readPendingModelCreation(target)
        : method === "setItem"
          ? () => savePendingModelCreation(ID, target)
          : () => clearPendingModelCreation(ID, target);
    expect(action).toThrowError(new Error(ERROR));
  },
);

it("sanitizes a denied default-storage accessor for read, save and clear", () => {
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
    throw new Error("DO_NOT_ECHO");
  });
  expect(() => readPendingModelCreation()).toThrowError(new Error(ERROR));
  expect(() => savePendingModelCreation(ID)).toThrowError(new Error(ERROR));
  expect(() => clearPendingModelCreation(ID)).toThrowError(new Error(ERROR));
});

it.each([null, encode(OTHER), "corrupt"])(
  "rejects divergent write readback without cleanup (%#)",
  (readback) => {
    const target = storage();
    target.getItem.mockReturnValueOnce(null).mockReturnValue(readback);
    expect(() => savePendingModelCreation(ID, target)).toThrowError(ERROR);
    expect(target.setItem).toHaveBeenCalledOnce();
    expect(target.removeItem).not.toHaveBeenCalled();
  },
);

it("rechecks idempotent save and absent clear without touching a competing intent", () => {
  const target = storage();
  target.getItem.mockReturnValueOnce(encode()).mockReturnValue(encode(OTHER));
  expect(() => savePendingModelCreation(ID, target)).toThrowError(ERROR);
  target.getItem.mockReturnValueOnce(null);
  expect(() => clearPendingModelCreation(ID, target)).toThrowError(ERROR);
  expect(target.setItem).not.toHaveBeenCalled();
  expect(target.removeItem).not.toHaveBeenCalled();
});

it.each([encode(), encode(OTHER), "corrupt"])(
  "rejects failed or raced deletion readback without deleting again (%#)",
  (readback) => {
    const target = storage(encode());
    target.getItem.mockReturnValueOnce(encode()).mockReturnValue(readback);
    expect(() => clearPendingModelCreation(ID, target)).toThrowError(ERROR);
    expect(target.removeItem).toHaveBeenCalledOnce();
  },
);

it.each(["save", "clear"])("sanitizes %s readback failure", (action) => {
  const target = storage();
  target.getItem
    .mockReturnValueOnce(action === "save" ? null : encode())
    .mockImplementation(() => {
      throw new Error("DO_NOT_ECHO");
    });
  expect(() =>
    action === "save"
      ? savePendingModelCreation(ID, target)
      : clearPendingModelCreation(ID, target),
  ).toThrowError(new Error(ERROR));
});
