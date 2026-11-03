import {
  mkdir,
  mkdtemp,
  readFile,
  readlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { installCliLink, planCliLink, rollbackCliLink } from "./cli-link.js";

describe("public CLI link", () => {
  it("creates memhub plus an idempotent one-memory compatibility link", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-cli-link-"));
    const installRoot = path.join(home, "runtime");
    const target = path.join(installRoot, "current", "bin", "one-memory");
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, "launcher");
    const plan = await planCliLink({ home, installRoot });

    const receipt = await installCliLink(plan);

    expect(await readlink(plan.link_path)).toBe(plan.target_path);
    expect(plan.link_path.endsWith("/memhub")).toBe(true);
    expect(plan.compat_link_path?.endsWith("/one-memory")).toBe(true);
    expect(await readlink(plan.compat_link_path!)).toBe(
      plan.compat_target_path,
    );
    expect((await planCliLink({ home, installRoot })).status).toBe("present");
    await rollbackCliLink(receipt);
    await expect(readFile(plan.link_path)).rejects.toThrow();
    await expect(readFile(plan.compat_link_path!)).rejects.toThrow();
  });

  it("can install only the memhub command for a packaged App", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-cli-link-"));
    const installRoot = path.join(home, "runtime");
    const target = path.join(installRoot, "current", "bin", "one-memory");
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, "launcher");

    const plan = await planCliLink({
      home,
      installRoot,
      includeCompatibilityAlias: false,
    });
    await installCliLink(plan);

    expect(await readlink(plan.link_path)).toBe(target);
    expect(plan.compat_link_path).toBeUndefined();
    await expect(
      readFile(path.join(home, ".local", "bin", "one-memory")),
    ).rejects.toThrow();
  });

  it("does not overwrite an unmanaged command", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-cli-link-"));
    const command = path.join(home, ".local", "bin", "memhub");
    await mkdir(path.dirname(command), { recursive: true });
    await writeFile(command, "another product");

    const plan = await planCliLink({
      home,
      installRoot: path.join(home, "runtime"),
    });

    expect(plan.status).toBe("blocked");
    await expect(installCliLink(plan)).rejects.toThrow("cli_link_unmanaged");
    expect(await readFile(command, "utf8")).toBe("another product");
  });

  it("does not overwrite an unmanaged compatibility command", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-cli-link-"));
    const command = path.join(home, ".local", "bin", "one-memory");
    await mkdir(path.dirname(command), { recursive: true });
    await writeFile(command, "another product");

    const plan = await planCliLink({
      home,
      installRoot: path.join(home, "runtime"),
    });

    expect(plan.status).toBe("blocked");
    await expect(installCliLink(plan)).rejects.toThrow("cli_link_unmanaged");
    expect(await readFile(command, "utf8")).toBe("another product");
  });

  it("does not create a dangling public command", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-cli-link-"));
    const plan = await planCliLink({
      home,
      installRoot: path.join(home, "runtime"),
    });

    await expect(installCliLink(plan)).rejects.toThrow(
      "cli_link_target_missing",
    );
    await expect(readFile(plan.link_path)).rejects.toThrow();
  });
});
