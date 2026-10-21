import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readlink,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { CliLinkPlan } from "@one-memory/runtime-control";
import { describe, expect, it } from "vitest";
import {
  installManagedCliAlias,
  installManagedCliLink,
  planManagedCliAlias,
  planManagedCliLink,
  removeManagedCliAlias,
  removeManagedCliLink,
  rollbackManagedCliAlias,
  rollbackManagedCliLink,
} from "./managed-cli-link.js";

async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), "memhub-cli-link-"));
  const installRoot = path.join(root, "install");
  const target = path.join(installRoot, "current", "bin", "one-memory");
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, "#!/bin/sh\n", { mode: 0o700 });
  const base: CliLinkPlan = {
    schema_version: 1,
    platform: process.platform,
    home: path.join(root, "home"),
    install_root: installRoot,
    bin_directory: path.join(root, "bin"),
    status: "create",
    blocked_reason: null,
    link_path: path.join(root, "bin", "one-memory"),
    target_path: target,
  };
  return { root, target, base };
}

describe("managed memhub CLI alias", () => {
  it("installs memhub beside the compatibility link", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    const plan = await planManagedCliAlias(f.base);

    const receipt = await installManagedCliAlias(plan);

    expect(path.basename(receipt.link_path)).toBe("memhub");
    expect(await readlink(receipt.link_path)).toBe(f.target);
    expect(receipt.created).toBe(true);
  });

  it("is idempotent when memhub already targets the managed executable", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    const first = await installManagedCliAlias(
      await planManagedCliAlias(f.base),
    );
    const secondPlan = await planManagedCliAlias(f.base);
    const second = await installManagedCliAlias(secondPlan);

    expect(first.created).toBe(true);
    expect(secondPlan.status).toBe("present");
    expect(second.created).toBe(false);
  });

  it("refuses to overwrite an unmanaged memhub entry", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    await mkdir(f.base.bin_directory, { recursive: true });
    const alias = path.join(f.base.bin_directory, "memhub");
    await writeFile(alias, "foreign", "utf8");

    const plan = await planManagedCliAlias(f.base);

    expect(plan.status).toBe("blocked");
    expect(plan.blocked_reason).toBe("cli_alias_unmanaged");
    await expect(readFile(alias, "utf8")).resolves.toBe("foreign");
  });

  it("rolls back only an alias created by this transaction", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    const receipt = await installManagedCliAlias(
      await planManagedCliAlias(f.base),
    );

    await rollbackManagedCliAlias(receipt);

    await expect(lstat(receipt.link_path)).rejects.toMatchObject({
      code: "ENOENT",
    });
  });

  it("removes the exact managed alias during uninstall", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    const plan = await planManagedCliAlias(f.base);
    await installManagedCliAlias(plan);

    await expect(removeManagedCliAlias(plan)).resolves.toBe("removed");
    await expect(lstat(plan.link_path)).rejects.toMatchObject({
      code: "ENOENT",
    });
  });

  // C8 P1 (2026-09-29): `runtime-control.applyLocalUninstall` deletes
  // `versions/` + `current` before the CLI cleans aliases, so the compat
  // `one-memory` symlink is already dangling by then. `planManagedCliLink`
  // classifies a dangling link as `blocked`, and `removeManagedCliLink` used to
  // throw on anything not `present` — the dangling entry then survived.
  it("removes a dangling managed alias instead of leaving it behind", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    await mkdir(f.base.bin_directory, { recursive: true, mode: 0o700 });
    await chmod(f.base.bin_directory, 0o700);
    const oneMemory = path.join(f.base.bin_directory, "one-memory");
    await symlink(f.target, oneMemory, "file");
    const plan = await planManagedCliLink(f.base, "one-memory");
    expect(plan.status).toBe("present");

    // The install tree is torn down first, exactly as `applyLocalUninstall`
    // does. The link is now dangling but still points at the managed target.
    await rm(f.target);
    await expect(removeManagedCliLink(plan)).resolves.toBe("removed");
    await expect(lstat(oneMemory)).rejects.toMatchObject({ code: "ENOENT" });
  });

  // The dangling-link fix must not turn into "delete any symlink": a link that
  // names some other target is still refused.
  it("still refuses to remove a link that points somewhere else", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    await mkdir(f.base.bin_directory, { recursive: true, mode: 0o700 });
    await chmod(f.base.bin_directory, 0o700);
    const foreign = path.join(f.root, "foreign");
    await writeFile(foreign, "#!/bin/sh\n", { mode: 0o700 });
    const oneMemory = path.join(f.base.bin_directory, "one-memory");
    await symlink(foreign, oneMemory, "file");
    const plan = await planManagedCliLink(f.base, "one-memory");
    await expect(removeManagedCliLink(plan)).rejects.toThrow(
      "cli_alias_unmanaged",
    );
    expect(await readlink(oneMemory)).toBe(foreign);
  });

  // H15 shape: runtime-control already created `<bin>/memhub`. The CLI's
  // companion is then the `one-memory` compat link, and it must not throw or
  // touch the package's primary link.
  it("manages the one-memory companion when memhub is already present", async () => {
    if (process.platform === "win32") return;
    const f = await fixture();
    const primary = {
      ...f.base,
      link_path: path.join(f.base.bin_directory, "memhub"),
    };
    await mkdir(f.base.bin_directory, { recursive: true, mode: 0o700 });
    await (await import("node:fs/promises")).chmod(f.base.bin_directory, 0o700);
    await (await import("node:fs/promises")).symlink(
      f.target,
      primary.link_path,
      "file",
    );

    const plan = await planManagedCliLink(f.base, "one-memory");
    // The companion does not exist yet, so it is ours to create; crucially it
    // targets the compat name, not the package's `memhub`.
    expect(plan).toMatchObject({
      status: "create",
      link_path: f.base.link_path,
    });

    // The package's memhub link is untouched.
    expect(await readlink(primary.link_path)).toBe(f.target);

    const receipt = await installManagedCliLink(plan);
    expect(receipt.created).toBe(true);
    expect(await readlink(f.base.link_path)).toBe(f.target);

    await rollbackManagedCliLink(receipt);
    await expect(removeManagedCliLink(plan)).resolves.toBe("not-installed");
  });
});
