import { randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { lstat, mkdir, open, rename, rmdir, unlink } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { absolutePath, ClaudeAdapterError } from "./runtime-config.js";

export function missing(error: unknown): boolean {
  return (
    !!error &&
    typeof error === "object" &&
    "code" in error &&
    error.code === "ENOENT"
  );
}

export async function assertNoSymlinks(target: string): Promise<void> {
  absolutePath(target);
  let current = path.parse(target).root;
  for (const part of target
    .slice(current.length)
    .split(path.sep)
    .filter(Boolean)) {
    current = path.join(current, part);
    try {
      if ((await lstat(current)).isSymbolicLink())
        throw new ClaudeAdapterError("symlink_not_allowed");
    } catch (error) {
      if (!missing(error)) throw error;
    }
  }
}

export async function readText(
  target: string,
  limit = 2 * 1024 * 1024,
): Promise<string | null> {
  await assertNoSymlinks(target);
  try {
    const handle = await open(
      target,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
    );
    try {
      const info = await handle.stat();
      if (!info.isFile() || info.nlink !== 1 || info.size > limit)
        throw new ClaudeAdapterError("unsafe_file");
      const data = Buffer.alloc(limit + 1);
      let offset = 0;
      while (offset < data.length) {
        const { bytesRead } = await handle.read(
          data,
          offset,
          data.length - offset,
          offset,
        );
        if (!bytesRead) break;
        offset += bytesRead;
      }
      if (offset > limit) throw new ClaudeAdapterError("file_too_large");
      return new TextDecoder("utf-8", { fatal: true }).decode(
        data.subarray(0, offset),
      );
    } finally {
      await handle.close();
    }
  } catch (error) {
    if (missing(error)) return null;
    throw error;
  }
}

export async function writeText(
  target: string,
  content: string,
  mode = 0o600,
): Promise<void> {
  await assertNoSymlinks(target);
  await mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
  const temporary = path.join(
    path.dirname(target),
    `.mh-c01-${randomUUID()}.tmp`,
  );
  let created = false;
  try {
    const handle = await open(temporary, "wx", mode);
    created = true;
    try {
      await handle.chmod(mode);
      await handle.writeFile(content, "utf8");
      await handle.sync();
    } finally {
      await handle.close();
    }
    await assertNoSymlinks(target);
    await rename(temporary, target);
    created = false;
  } finally {
    if (created) await unlink(temporary);
  }
}

export async function removeFile(target: string): Promise<void> {
  await assertNoSymlinks(target);
  await unlink(target);
}

export async function withDirectoryLock<T>(
  lock: string,
  body: () => Promise<T>,
): Promise<T> {
  await assertNoSymlinks(lock);
  const deadline = Date.now() + 2000;
  for (;;) {
    try {
      await mkdir(lock, { mode: 0o700 });
      break;
    } catch (error) {
      if (
        !error ||
        typeof error !== "object" ||
        !("code" in error) ||
        error.code !== "EEXIST"
      )
        throw error;
      if (Date.now() >= deadline) throw new ClaudeAdapterError("state_busy");
      await assertNoSymlinks(lock);
      await delay(10);
    }
  }
  try {
    return await body();
  } finally {
    await rmdir(lock);
  }
}
