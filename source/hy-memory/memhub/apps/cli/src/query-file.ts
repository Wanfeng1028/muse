import { Buffer } from "node:buffer";
import { constants, open } from "node:fs/promises";

export const QUERY_MAX_CHARACTERS = 512;

/**
 * Read a query from a regular file without ever buffering more than a query
 * could be. A FIFO would otherwise block forever and a large or device-backed
 * file would be read in full before the length check could reject it, so the
 * size and the file type are settled before any byte is read.
 */
export async function readQueryFile(
  filePath: string,
  maxCharacters = QUERY_MAX_CHARACTERS,
): Promise<string | null> {
  if (!Number.isSafeInteger(maxCharacters) || maxCharacters < 1) return null;
  /** Conservative UTF-8 allowance plus one trailing CRLF. */
  const maxBytes = maxCharacters * 4 + 2;
  let handle: Awaited<ReturnType<typeof open>>;
  try {
    handle = await open(filePath, constants.O_RDONLY | nonBlocking());
  } catch {
    return null;
  }
  try {
    const stats = await handle.stat();
    if (!stats.isFile() || stats.size > maxBytes) return null;
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
    if (bytesRead > maxBytes) return null;
    return parseQuery(buffer.subarray(0, bytesRead), maxCharacters);
  } catch {
    return null;
  } finally {
    await handle.close().catch(() => undefined);
  }
}

function parseQuery(bytes: Buffer, maxCharacters: number): string | null {
  const text = bytes.toString("utf8");
  // Bytes that are not valid UTF-8 become U+FFFD, and a query is text.
  if (text.includes("\uFFFD")) return null;
  const query = text.replace(/\r?\n$/, "");
  if (query.length === 0 || query.length > maxCharacters) return null;
  // One line only: an embedded newline or control byte means this file is not
  // the single query it claims to be.
  // biome-ignore lint/suspicious/noControlCharactersInRegex: that is the point
  return /[\u0000-\u0008\u000A-\u001F\u007F]/.test(query) ? null : query;
}

function nonBlocking(): number {
  return typeof constants.O_NONBLOCK === "number" ? constants.O_NONBLOCK : 0;
}
