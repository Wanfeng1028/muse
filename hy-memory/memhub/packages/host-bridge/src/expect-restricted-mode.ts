import { access, constants, stat } from "node:fs/promises";
import { expect } from "vitest";

/**
 * On POSIX we insist the file is owner-readable/writable only (0o600).
 * On Windows, `chmod` only flips the read-only bit — owner-only is an ACL
 * concern, and asserting `mode & 0o777 === 0o600` is a false failure that
 * would block a Windows CI run for a property the platform does not express
 * that way. There we only require the file to exist and be readable.
 */
export async function expectRestrictedFileMode(
  targetPath: string,
): Promise<void> {
  if (process.platform === "win32") {
    await access(targetPath, constants.R_OK);
    return;
  }
  expect((await stat(targetPath)).mode & 0o777).toBe(0o600);
}
