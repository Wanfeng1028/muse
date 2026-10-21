import { constants } from "node:fs";
import { type FileHandle, open } from "node:fs/promises";

/** Read one regular, non-symlinked file without ever buffering past maxBytes. */
export async function readBoundedFile(
  filePath: string,
  maxBytes: number,
  options: { ownerOnly?: boolean } = {},
): Promise<Buffer | null> {
  if (
    !Number.isSafeInteger(maxBytes) ||
    maxBytes < 1 ||
    maxBytes > 1024 * 1024
  ) {
    return null;
  }
  let handle: FileHandle;
  try {
    handle = await open(
      filePath,
      constants.O_RDONLY |
        (constants.O_NONBLOCK ?? 0) |
        (constants.O_NOFOLLOW ?? 0),
    );
  } catch {
    return null;
  }
  try {
    const stats = await handle.stat();
    if (
      !stats.isFile() ||
      stats.nlink !== 1 ||
      stats.size > maxBytes ||
      (options.ownerOnly &&
        ((stats.mode & 0o077) !== 0 ||
          (process.getuid !== undefined && stats.uid !== process.getuid())))
    )
      return null;
    const buffer = Buffer.alloc(maxBytes + 1);
    let bytesRead = 0;
    while (bytesRead < buffer.length) {
      const chunk = await handle.read(
        buffer,
        bytesRead,
        buffer.length - bytesRead,
        bytesRead,
      );
      if (chunk.bytesRead === 0) break;
      bytesRead += chunk.bytesRead;
    }
    if (bytesRead > maxBytes || bytesRead !== stats.size) return null;
    return buffer.subarray(0, bytesRead);
  } catch {
    return null;
  } finally {
    await handle.close().catch(() => undefined);
  }
}

export async function readBoundedJson(
  filePath: string,
  maxBytes = 64 * 1024,
): Promise<unknown | null> {
  const bytes = await readBoundedFile(filePath, maxBytes);
  if (!bytes) return null;
  const text = bytes.toString("utf8");
  if (text.includes("\uFFFD")) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
