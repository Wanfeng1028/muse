import { Buffer } from "node:buffer";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QUERY_MAX_CHARACTERS, readQueryFile } from "./query-file.js";

const handle = vi.hoisted(() => ({
  stat: vi.fn(),
  read: vi.fn(),
  close: vi.fn(async () => undefined),
}));
const fs = vi.hoisted(() => ({ open: vi.fn(async () => handle) }));

vi.mock("node:fs/promises", async (importOriginal) => ({
  ...(await importOriginal<typeof import("node:fs/promises")>()),
  ...fs,
}));

function regular(size: number) {
  return { isFile: () => true, size };
}

function fifo(size = 0) {
  return { isFile: () => false, size };
}

function serve(text: string) {
  const payload = Buffer.from(text, "utf8");
  handle.read.mockImplementation(
    async (
      buffer: Buffer,
      offset: number,
      length: number,
      position: number,
    ) => {
      const bytesRead = payload.copy(
        buffer,
        offset,
        position,
        Math.min(position + length, payload.length),
      );
      return { bytesRead, buffer };
    },
  );
  return payload;
}

beforeEach(() => {
  vi.clearAllMocks();
  fs.open.mockResolvedValue(handle);
});

describe("query file reading", () => {
  it("returns the query and always closes the handle", async () => {
    handle.stat.mockResolvedValue(regular(64));
    serve("部署脚本\n");
    expect(await readQueryFile("/tmp/query.txt")).toBe("部署脚本");
    expect(handle.close).toHaveBeenCalledTimes(1);
  });

  // Main's READ-REVIEW: the old code called readFile() and only then checked
  // the 512-character bound, so the whole file was buffered first.
  it("refuses an oversized file without reading it", async () => {
    handle.stat.mockResolvedValue(regular(64 * 1024 * 1024));
    expect(await readQueryFile("/tmp/huge.bin")).toBeNull();
    expect(handle.read).not.toHaveBeenCalled();
    expect(handle.close).toHaveBeenCalledTimes(1);
  });

  it("refuses anything that is not a regular file without reading it", async () => {
    handle.stat.mockResolvedValue(fifo());
    expect(await readQueryFile("/tmp/pipe")).toBeNull();
    expect(handle.read).not.toHaveBeenCalled();
    expect(handle.close).toHaveBeenCalledTimes(1);
  });

  it("caps the read even when stat under-reports the size", async () => {
    handle.stat.mockResolvedValue(regular(8));
    serve("x".repeat(64 * 1024));
    expect(await readQueryFile("/tmp/lying.txt")).toBeNull();
    const [, , length] = handle.read.mock.calls[0] as [Buffer, number, number];
    expect(length).toBeLessThanOrEqual(QUERY_MAX_CHARACTERS * 4 + 3);
  });

  it("continues bounded partial reads instead of accepting a prefix", async () => {
    const payload = Buffer.from("分段读取", "utf8");
    handle.stat.mockResolvedValue(regular(payload.length));
    handle.read.mockImplementation(
      async (
        buffer: Buffer,
        offset: number,
        _length: number,
        position: number,
      ) => {
        const bytesRead = payload.copy(
          buffer,
          offset,
          position,
          Math.min(position + 2, payload.length),
        );
        return { bytesRead, buffer };
      },
    );
    expect(await readQueryFile("/tmp/partial.txt")).toBe("分段读取");
    expect(handle.read.mock.calls.length).toBeGreaterThan(1);
  });

  it("refuses an overlong query, an empty one and embedded control characters", async () => {
    for (const text of [
      "x".repeat(QUERY_MAX_CHARACTERS + 1),
      "",
      "\n",
      "第一行\n第二行",
      "带\u0000空字节",
    ]) {
      handle.stat.mockResolvedValue(regular(Buffer.byteLength(text)));
      serve(text);
      expect(await readQueryFile("/tmp/query.txt")).toBeNull();
    }
  });

  it("refuses bytes that are not valid UTF-8", async () => {
    handle.stat.mockResolvedValue(regular(3));
    handle.read.mockImplementation(async (buffer: Buffer, offset: number) => {
      const bytes = Buffer.from([0xff, 0xfe, 0xfd]);
      return {
        bytesRead: offset === 0 ? bytes.copy(buffer, 0) : 0,
        buffer,
      };
    });
    expect(await readQueryFile("/tmp/binary")).toBeNull();
  });

  it("closes the handle when stat or read throws", async () => {
    handle.stat.mockRejectedValue(new Error("EIO"));
    expect(await readQueryFile("/tmp/query.txt")).toBeNull();
    expect(handle.close).toHaveBeenCalledTimes(1);

    handle.stat.mockResolvedValue(regular(8));
    handle.read.mockRejectedValue(new Error("EIO"));
    expect(await readQueryFile("/tmp/query.txt")).toBeNull();
    expect(handle.close).toHaveBeenCalledTimes(2);
  });

  it("reports a file it cannot open instead of throwing", async () => {
    fs.open.mockRejectedValue(new Error("ENOENT"));
    expect(await readQueryFile("/tmp/absent")).toBeNull();
    expect(handle.close).not.toHaveBeenCalled();
  });
});
