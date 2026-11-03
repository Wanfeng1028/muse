import { constants } from "node:fs";
import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  installUserService,
  restartUserService,
  uninstallUserService,
} from "./service-install.js";
import { planUserService, runtimeInstallLayout } from "./service-plan.js";

const injection = vi.hoisted(() => ({
  beforePublish: null as null | ((target: string) => Promise<void>),
  failDirectorySync: false,
  stalePathLinkCount: null as string | null,
  inspectRead: null as
    | null
    | ((handle: fs.FileHandle, flags: number, file: string) => void),
}));
vi.mock("node:fs/promises", async (original) => {
  const real = await original<typeof import("node:fs/promises")>();
  return {
    ...real,
    lstat: async (file: string) => {
      const info = await real.lstat(file);
      if (file !== injection.stalePathLinkCount || info.nlink !== 1)
        return info;
      // CephFS can expose this exact stale view after unlink(temp): the open
      // handle already reports nlink=1 while lstat(target) still says 2.
      const stale = Object.create(Object.getPrototypeOf(info));
      Object.assign(stale, info, { nlink: 2 });
      return stale;
    },
    open: async (file: string, flags: string | number, mode?: number) => {
      const handle = await real.open(file, flags, mode);
      if (
        typeof flags === "number" &&
        (flags & (constants.O_WRONLY | constants.O_RDWR)) === 0 &&
        (flags & constants.O_DIRECTORY) === 0
      ) {
        injection.inspectRead?.(handle, flags, file);
      }
      if (
        typeof flags === "number" &&
        (flags & constants.O_DIRECTORY) !== 0 &&
        injection.failDirectorySync
      ) {
        vi.spyOn(handle, "sync").mockRejectedValueOnce(
          new Error("simulated fsync failure"),
        );
      }
      return handle;
    },
    link: async (from: string, to: string) => {
      await injection.beforePublish?.(to);
      return real.link(from, to);
    },
    rename: async (from: string, to: string) => {
      if (from.endsWith(".tmp")) await injection.beforePublish?.(to);
      return real.rename(from, to);
    },
  };
});
let home: string;
beforeEach(async () => {
  injection.beforePublish = null;
  injection.failDirectorySync = false;
  injection.stalePathLinkCount = null;
  injection.inspectRead = null;
  home = await fs.mkdtemp(path.join(tmpdir(), "service-owned-race-"));
});
afterEach(async () => {
  injection.beforePublish = null;
  injection.failDirectorySync = false;
  injection.stalePathLinkCount = null;
  injection.inspectRead = null;
  await fs.rm(home, { recursive: true, force: true });
});
async function fixture() {
  const layout = runtimeInstallLayout({
    platform: process.platform === "darwin" ? "darwin" : "linux",
    home,
    installRoot: path.join(home, "runtime"),
  });
  for (const file of [
    layout.nodeCommand,
    layout.runtimeEntry,
    layout.coreCommand,
    layout.mcpEntryPath,
    layout.recallCliPath,
    path.join(layout.syncHookAssetsDirectory, "manifest.json"),
  ]) {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, "fixture");
  }
  const options = {
    uid: process.getuid?.(),
    xdgConfigHome: path.join(home, ".config"),
    inspectRegistration: vi.fn(async () => "absent" as const),
    runCommand: vi.fn(async (_command: readonly string[]) => {}),
  };
  const plan = planUserService(layout, options);
  if (!plan.service_file) throw new Error("Fixture platform unsupported");
  const target = plan.service_file.path;
  return { layout, options, plan, target, content: plan.service_file.content };
}

it("does not overwrite or roll back a competing file created just before publication", async () => {
  const f = await fixture();
  injection.beforePublish = async (target) => {
    await fs.writeFile(target, "competitor", { flag: "wx", mode: 0o600 });
  };
  await expect(installUserService(f.layout, f.options)).rejects.toThrow();
  expect(await fs.readFile(f.target, "utf8")).toBe("competitor");
  expect(f.options.runCommand).not.toHaveBeenCalled();
});

it("does not delete a competing inode after command failure even with identical content", async () => {
  const f = await fixture();
  let replacementInode: number | undefined;
  f.options.runCommand.mockImplementation(async () => {
    await fs.rename(f.target, `${f.target}.original`);
    await fs.writeFile(f.target, f.content, { mode: 0o600 });
    replacementInode = (await fs.lstat(f.target)).ino;
    throw new Error("command failed");
  });
  await expect(installUserService(f.layout, f.options)).rejects.toThrow();
  expect((await fs.lstat(f.target)).ino).toBe(replacementInode);
  expect(await fs.readFile(f.target, "utf8")).toBe(f.content);
  expect(f.options.runCommand).toHaveBeenCalledOnce();
});

it.each(["contents", "mode", "symlink", "directory"])(
  "preserves changed target %s on rollback",
  async (change) => {
    const f = await fixture();
    f.options.runCommand.mockImplementation(async () => {
      if (change === "contents") await fs.writeFile(f.target, "user edit");
      if (change === "mode") await fs.chmod(f.target, 0o644);
      if (change === "symlink" || change === "directory") {
        await fs.rename(f.target, `${f.target}.original`);
        if (change === "symlink")
          await fs.symlink(`${f.target}.original`, f.target);
        else await fs.mkdir(f.target);
      }
      throw new Error("command failed");
    });
    await expect(installUserService(f.layout, f.options)).rejects.toThrow();
    const stat = await fs.lstat(f.target);
    if (change === "contents")
      expect(await fs.readFile(f.target, "utf8")).toBe("user edit");
    if (change === "mode") expect(stat.mode & 0o777).toBe(0o644);
    if (change === "symlink") expect(stat.isSymbolicLink()).toBe(true);
    if (change === "directory") expect(stat.isDirectory()).toBe(true);
  },
);

it.each(["replace", "chmod"])(
  "rejects parent %s after commands without deleting through changed directory",
  async (change) => {
    const f = await fixture();
    const parent = path.dirname(f.target);
    f.options.runCommand.mockImplementation(async () => {
      if (change === "replace") {
        await fs.rename(parent, `${parent}.original`);
        await fs.mkdir(parent, { mode: 0o700 });
        await fs.writeFile(f.target, "competitor", { mode: 0o600 });
      } else await fs.chmod(parent, 0o777);
    });
    await expect(installUserService(f.layout, f.options)).rejects.toThrow();
    expect(await fs.readFile(f.target, "utf8")).toBe(
      change === "replace" ? "competitor" : f.content,
    );
    expect(f.options.runCommand).toHaveBeenCalledOnce();
  },
);

it("does not report success when a command silently replaces the service file", async () => {
  const f = await fixture();
  f.options.runCommand.mockImplementation(async () => {
    await fs.rename(f.target, `${f.target}.original`);
    await fs.writeFile(f.target, "competitor", { mode: 0o600 });
  });
  await expect(installUserService(f.layout, f.options)).rejects.toThrow();
  expect(await fs.readFile(f.target, "utf8")).toBe("competitor");
});

it("uninstall does not remove a replacement created during its command", async () => {
  const f = await fixture();
  await installUserService(f.layout, f.options);
  f.options.runCommand.mockClear();
  f.options.runCommand.mockImplementation(async () => {
    await fs.rename(f.target, `${f.target}.original`);
    await fs.writeFile(f.target, "competitor", { mode: 0o600 });
  });
  await expect(uninstallUserService(f.layout, f.options)).rejects.toThrow();
  expect(await fs.readFile(f.target, "utf8")).toBe("competitor");
  expect(f.options.runCommand).toHaveBeenCalledOnce();
});

it.each(["restart", "uninstall"])(
  "%s refuses broadly readable service declarations before commands",
  async (action) => {
    const f = await fixture();
    await installUserService(f.layout, f.options);
    await fs.chmod(f.target, 0o644);
    f.options.runCommand.mockClear();
    await expect(
      action === "restart"
        ? restartUserService(f.layout, f.options)
        : uninstallUserService(f.layout, f.options),
    ).rejects.toThrow();
    expect(f.options.runCommand).not.toHaveBeenCalled();
  },
);

it("leaves a competing symlink and its referent untouched at publication", async () => {
  const f = await fixture();
  const foreign = path.join(home, "foreign");
  await fs.writeFile(foreign, "competitor");
  injection.beforePublish = async (target) => {
    await fs.symlink(foreign, target);
  };
  await expect(installUserService(f.layout, f.options)).rejects.toThrow();
  expect((await fs.lstat(f.target)).isSymbolicLink()).toBe(true);
  expect(await fs.readFile(foreign, "utf8")).toBe("competitor");
  expect(f.options.runCommand).not.toHaveBeenCalled();
});

it("rejects directory replacement between preparation and publication without traversing it to clean", async () => {
  const f = await fixture();
  const parent = path.dirname(f.target);
  injection.beforePublish = async () => {
    await fs.rename(parent, `${parent}.original`);
    await fs.mkdir(parent, { mode: 0o700 });
    await fs.writeFile(f.target, "competitor", { mode: 0o600 });
  };
  await expect(installUserService(f.layout, f.options)).rejects.toThrow();
  expect(await fs.readFile(f.target, "utf8")).toBe("competitor");
  expect(f.options.runCommand).not.toHaveBeenCalled();
});

it("preserves a published declaration and reports unknown durability after fsync failure", async () => {
  const f = await fixture();
  injection.failDirectorySync = true;
  await expect(installUserService(f.layout, f.options)).rejects.toThrow(
    "runtime_service_durability_unknown",
  );
  expect(await fs.readFile(f.target, "utf8")).toBe(f.content);
  expect(f.options.runCommand).not.toHaveBeenCalled();
  injection.failDirectorySync = false;
  await expect(installUserService(f.layout, f.options)).rejects.toThrow(
    "runtime_service_file_exists",
  );
});

it("accepts stale path link metadata when the retained handle proves ownership", async () => {
  const f = await fixture();
  injection.stalePathLinkCount = f.target;

  await expect(installUserService(f.layout, f.options)).resolves.toEqual(
    f.plan,
  );
  expect(await fs.readFile(f.target, "utf8")).toBe(f.content);
  expect(f.options.runCommand).toHaveBeenCalledTimes(
    f.plan.commands.install.length,
  );
});

it("reports rollback durability as unknown when unlink has happened but directory fsync fails", async () => {
  const f = await fixture();
  f.options.runCommand.mockImplementation(async () => {
    injection.failDirectorySync = true;
    throw new Error("command failed");
  });
  await expect(installUserService(f.layout, f.options)).rejects.toThrow(
    "runtime_service_durability_unknown",
  );
  await expect(fs.lstat(f.target)).rejects.toMatchObject({ code: "ENOENT" });
  expect(f.options.runCommand).toHaveBeenCalledOnce();
});

it.each(["restart", "uninstall"])(
  "%s rejects a declaration with an unexpected hard link",
  async (action) => {
    const f = await fixture();
    await installUserService(f.layout, f.options);
    await fs.link(f.target, `${f.target}.alias`);
    f.options.runCommand.mockClear();
    await expect(
      action === "restart"
        ? restartUserService(f.layout, f.options)
        : uninstallUserService(f.layout, f.options),
    ).rejects.toThrow();
    expect(await fs.readFile(f.target, "utf8")).toBe(f.content);
    expect(f.options.runCommand).not.toHaveBeenCalled();
  },
);

it("restart rejects a replacement returned by the runner rather than reporting success", async () => {
  const f = await fixture();
  await installUserService(f.layout, f.options);
  f.options.runCommand.mockClear();
  f.options.runCommand.mockImplementation(async () => {
    await fs.rename(f.target, `${f.target}.original`);
    await fs.writeFile(f.target, f.content, { mode: 0o600 });
  });
  await expect(restartUserService(f.layout, f.options)).rejects.toThrow();
  expect(await fs.readFile(f.target, "utf8")).toBe(f.content);
  expect(f.options.runCommand).toHaveBeenCalledOnce();
});

it("concurrent installers publish exactly once and the loser does not erase the winner", async () => {
  const f = await fixture();
  let entered = 0;
  let release!: () => void;
  const ready = new Promise<void>((resolve) => {
    release = resolve;
  });
  injection.beforePublish = async () => {
    entered += 1;
    if (entered === 2) release();
    await ready;
  };
  const results = await Promise.allSettled([
    installUserService(f.layout, f.options),
    installUserService(f.layout, f.options),
  ]);
  expect(
    results.filter((result) => result.status === "fulfilled"),
  ).toHaveLength(1);
  expect(results.filter((result) => result.status === "rejected")).toHaveLength(
    1,
  );
  expect(await fs.readFile(f.target, "utf8")).toBe(f.content);
  expect(f.options.runCommand).toHaveBeenCalledTimes(
    f.plan.commands.install.length,
  );
  expect(
    (await fs.readdir(path.dirname(f.target))).filter((name) =>
      name.endsWith(".tmp"),
    ),
  ).toEqual([]);
});

it("does not chmod a pre-existing unsafe service directory into an acceptable one", async () => {
  const f = await fixture();
  const parent = path.dirname(f.target);
  await fs.mkdir(parent, { recursive: true });
  await fs.chmod(parent, 0o777);
  await expect(installUserService(f.layout, f.options)).rejects.toThrow(
    "runtime_service_directory_unsafe",
  );
  expect((await fs.lstat(parent)).mode & 0o777).toBe(0o777);
  expect(f.options.runCommand).not.toHaveBeenCalled();
});

it("opens verification nonblocking and bounds reads when a checked file grows", async () => {
  const f = await fixture();
  await installUserService(f.layout, f.options);
  f.options.runCommand.mockClear();
  const lengths: number[] = [];
  injection.inspectRead = (handle, flags, file) => {
    expect(flags & constants.O_NONBLOCK).not.toBe(0);
    expect(flags & constants.O_NOFOLLOW).not.toBe(0);
    vi.spyOn(handle, "readFile").mockRejectedValue(
      new Error("unbounded read forbidden"),
    );
    const original = handle.read.bind(handle);
    vi.spyOn(handle, "read").mockImplementation(
      async (...args: Parameters<typeof handle.read>) => {
        const buffer = args[0]?.buffer;
        if (!Buffer.isBuffer(buffer))
          throw new Error("expected bounded buffer");
        lengths.push(buffer.length);
        await fs.appendFile(file, "x".repeat(8192));
        return original(...args);
      },
    );
  };
  await expect(restartUserService(f.layout, f.options)).rejects.toThrow(
    "runtime_service_file_unmanaged",
  );
  expect(lengths).toEqual([Buffer.byteLength(f.content) + 1]);
  expect(f.options.runCommand).not.toHaveBeenCalled();
});

it("sanitizes injected command errors without exposing secret text or causes", async () => {
  const f = await fixture();
  f.options.runCommand.mockRejectedValue(new Error("SECRET_STDERR_BODY"));
  const error = await installUserService(f.layout, f.options).catch(
    (reason: unknown) => reason,
  );
  expect(error).toEqual(new Error("runtime_service_command_failed"));
  expect(error).not.toHaveProperty("cause");
  await expect(fs.lstat(f.target)).rejects.toMatchObject({ code: "ENOENT" });
});
