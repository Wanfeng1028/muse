import { appendFile, chmod, mkdir, rename, rm, stat } from "node:fs/promises";
import path from "node:path";

/**
 * Bounded, owner-only capture of the Runtime's own stdout/stderr.
 *
 * Why the Runtime writes these instead of launchd: with
 * `StandardOutPath`/`StandardErrorPath` in the plist, launchd holds the file
 * descriptor. Rotation then cannot work -- renaming the file leaves launchd
 * writing to the renamed inode, and truncating it loses data without bound.
 * Measured on macOS: the redirect grew a login-start daemon's log by ~654 bytes
 * per `status` call (Core's HTTP access log) with no cap.
 *
 * So the plist no longer redirects, and the Runtime captures its own streams
 * into rotating files. Bounds deliberately match the diagnostic logger
 * (`DIAGNOSTIC_MAX_FILE_BYTES`): 4 MiB per file, up to 3 rotated copies, so a
 * service log family is capped at ~16 MiB no matter how long the daemon runs.
 */
export const SERVICE_LOG_MAX_FILE_BYTES = 4 * 1024 * 1024;
const SERVICE_LOG_KEEP_FILES = 3;
const SERVICE_LOG_DIRECTORY_MODE = 0o700;
const SERVICE_LOG_FILE_MODE = 0o600;

export interface ServiceLogCapture {
  /** Append a stdout chunk, rotating first when it would exceed the cap. */
  writeStdout(chunk: string): Promise<void>;
  /** Append a stderr chunk, rotating first when it would exceed the cap. */
  writeStderr(chunk: string): Promise<void>;
  /** Resolve once every queued chunk has been written. */
  flush(): Promise<void>;
}

/** Rotate `<target>` to `.1`, shifting `.1`->`.2`, `.2`->`.3`, dropping `.3`. */
async function rotate(target: string): Promise<void> {
  await rm(`${target}.${SERVICE_LOG_KEEP_FILES}`, { force: true });
  for (let index = SERVICE_LOG_KEEP_FILES - 1; index >= 1; index -= 1) {
    await rename(`${target}.${index}`, `${target}.${index + 1}`).catch(
      (error: NodeJS.ErrnoException) => {
        if (error.code !== "ENOENT") throw error;
      },
    );
  }
  await rename(target, `${target}.1`).catch((error: NodeJS.ErrnoException) => {
    if (error.code !== "ENOENT") throw error;
  });
}

/** Append one chunk, rotating when the chunk would cross the per-file cap.
 *
 * Writes are serialized by the caller's queue so a slow disk cannot interleave
 * two chunks or race a rotation.
 */
async function appendBounded(target: string, chunk: string): Promise<void> {
  const current = await stat(target).catch(() => null);
  if (
    current &&
    current.size + Buffer.byteLength(chunk) > SERVICE_LOG_MAX_FILE_BYTES
  ) {
    await rotate(target);
  }
  await appendFile(target, chunk, {
    encoding: "utf8",
    mode: SERVICE_LOG_FILE_MODE,
  });
  await chmod(target, SERVICE_LOG_FILE_MODE);
}

/** Capture the Runtime's stdout/stderr into bounded files under `dataDir`.
 *
 * Returns null when `dataDir` is unusable, so a capture failure can never stop
 * the Runtime from starting: the whole point is diagnosability, not a new
 * failure mode.
 */
export async function createServiceLogCapture(
  dataDir: string,
): Promise<ServiceLogCapture | null> {
  const directory = path.join(dataDir, "logs");
  try {
    await mkdir(directory, {
      recursive: true,
      mode: SERVICE_LOG_DIRECTORY_MODE,
    });
    await chmod(directory, SERVICE_LOG_DIRECTORY_MODE);
  } catch {
    return null;
  }
  const stdoutPath = path.join(directory, "service.log");
  const stderrPath = path.join(directory, "service-error.log");
  // Serialize every append: rotation must not interleave with another write.
  let tail: Promise<void> = Promise.resolve();
  let failed = false;
  const enqueue = (target: string, chunk: string): void => {
    if (failed) return;
    tail = tail
      .then(() => appendBounded(target, chunk))
      .catch(() => {
        // Never let a logging problem take down the Runtime; stop trying so a
        // full or read-only disk cannot produce an unbounded retry loop.
        failed = true;
      });
  };
  return {
    writeStdout(chunk) {
      enqueue(stdoutPath, chunk);
      return tail;
    },
    writeStderr(chunk) {
      enqueue(stderrPath, chunk);
      return tail;
    },
    async flush() {
      await tail;
    },
  };
}
