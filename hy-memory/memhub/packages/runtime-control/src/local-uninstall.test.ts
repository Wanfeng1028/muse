import {
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { applyLocalUninstall, planLocalUninstall } from "./local-install.js";

const applyManagedUninstall = applyLocalUninstall;

async function installed() {
  const home = await mkdtemp(path.join(tmpdir(), "uninstall-"));
  const installRoot = path.join(home, "root");
  const dataDir = path.join(home, "data");
  const version = path.join(installRoot, "versions", "0.0.0-darwin-arm64");
  await mkdir(path.join(version, "bin"), { recursive: true });
  await writeFile(path.join(version, "bin", "one-memory"), "program");
  await symlink(
    path.relative(path.join(installRoot, "versions"), version),
    path.join(installRoot, "versions", "current-link"),
  );
  await symlink(
    "versions/0.0.0-darwin-arm64",
    path.join(installRoot, "current"),
  );
  await mkdir(dataDir, { recursive: true });
  await writeFile(path.join(dataDir, "precious.txt"), "user data");
  const binDirectory = path.join(home, ".local", "bin");
  await mkdir(binDirectory, { recursive: true });
  const cliLink = path.join(binDirectory, "one-memory");
  await symlink(
    path.join(installRoot, "current", "bin", "one-memory"),
    cliLink,
  );
  return { home, installRoot, dataDir, version, cliLink };
}

describe("product uninstall", () => {
  it("removes the program and leaves the data alone", async () => {
    const fixture = await installed();
    const plan = await planLocalUninstall({
      installRoot: fixture.installRoot,
      home: fixture.home,
      dataDir: fixture.dataDir,
      cliLinkPath: fixture.cliLink,
      stopsService: false,
    });
    expect(plan.version_directories).toContain(fixture.version);
    expect(plan.preserved_data_dir).toBe(fixture.dataDir);

    const receipt = await applyManagedUninstall(plan);
    expect(receipt.removed_version_directories).toContain(fixture.version);
    expect(receipt.removed_current_link).toBe(true);
    expect(receipt.removed_cli_link).toBe(true);

    // The program is gone.
    await expect(lstat(fixture.version)).rejects.toThrow();
    await expect(
      lstat(path.join(fixture.installRoot, "current")),
    ).rejects.toThrow();
    await expect(lstat(fixture.cliLink)).rejects.toThrow();
    // The data is not.
    const { readFile } = await import("node:fs/promises");
    await expect(
      readFile(path.join(fixture.dataDir, "precious.txt"), "utf8"),
    ).resolves.toBe("user data");
  });

  it("refuses a version directory outside the install root", async () => {
    const fixture = await installed();
    const plan = await planLocalUninstall({
      installRoot: fixture.installRoot,
      home: fixture.home,
      dataDir: fixture.dataDir,
      cliLinkPath: null,
      stopsService: false,
    });
    // A plan is data: it can be stale or hand-edited, so the path is re-checked
    // at apply time rather than trusted.
    const tampered = { ...plan, version_directories: [fixture.dataDir] };
    await expect(applyManagedUninstall(tampered)).rejects.toThrow(
      "uninstall_path_unsafe",
    );
  });

  it("plans without a cli link when there is none", async () => {
    const fixture = await installed();
    const plan = await planLocalUninstall({
      installRoot: fixture.installRoot,
      home: fixture.home,
      dataDir: null,
      cliLinkPath: null,
      stopsService: false,
    });
    expect(plan.cli_link).toBeNull();
    const receipt = await applyManagedUninstall(plan);
    expect(receipt.removed_cli_link).toBe(false);
  });

  it("never removes a PATH entry it did not create", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-uninstall-foreign-"));
    const installRoot = path.join(home, "runtime");
    const binDirectory = path.join(home, "bin");
    await mkdir(installRoot, { recursive: true });
    await mkdir(binDirectory, { recursive: true });
    // A user file (or another tool's) sitting exactly where our link would go.
    const foreign = path.join(binDirectory, "one-memory");
    await writeFile(foreign, "someone else's tool\n");

    const plan = await planLocalUninstall({
      installRoot,
      home,
      dataDir: null,
      cliLinkPath: foreign,
      stopsService: false,
    });
    const receipt = await applyManagedUninstall(plan);

    expect(receipt.removed_cli_link).toBe(false);
    expect(await readFile(foreign, "utf8")).toBe("someone else's tool\n");
    await rm(home, { recursive: true, force: true });
  });

  it("never removes a PATH symlink that points at another install", async () => {
    const home = await mkdtemp(
      path.join(tmpdir(), "om-uninstall-foreign-link-"),
    );
    const installRoot = path.join(home, "runtime");
    const binDirectory = path.join(home, "bin");
    const other = path.join(
      home,
      "other-install",
      "current",
      "bin",
      "one-memory",
    );
    await mkdir(installRoot, { recursive: true });
    await mkdir(binDirectory, { recursive: true });
    await mkdir(path.dirname(other), { recursive: true });
    await writeFile(other, "other\n");
    const link = path.join(binDirectory, "one-memory");
    await symlink(other, link);

    const plan = await planLocalUninstall({
      installRoot,
      home,
      dataDir: null,
      cliLinkPath: link,
      stopsService: false,
    });
    const receipt = await applyManagedUninstall(plan);

    expect(receipt.removed_cli_link).toBe(false);
    expect((await lstat(link)).isSymbolicLink()).toBe(true);
    await rm(home, { recursive: true, force: true });
  });

  it("refuses to uninstall when the data dir is inside the versions subtree", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "uninstall-data-inside-"));
    const installRoot = path.join(home, "root");
    const dataDir = path.join(installRoot, "versions", "userdata");
    const version = path.join(installRoot, "versions", "0.0.0-darwin-arm64");
    await mkdir(path.join(version, "bin"), { recursive: true });
    await mkdir(dataDir, { recursive: true });
    await writeFile(path.join(dataDir, "PRECIOUS"), "user data\n");

    // Removing versions/ recursively would take the user's data with it, while
    // the plan still advertises preserved_data_dir. Refuse before touching disk.
    await expect(
      planLocalUninstall({
        installRoot,
        home,
        dataDir,
        cliLinkPath: null,
        stopsService: false,
      }),
    ).rejects.toThrow("uninstall_data_inside_install_root");

    // The data must still be there after the refusal.
    expect(await readFile(path.join(dataDir, "PRECIOUS"), "utf8")).toBe(
      "user data\n",
    );
    await rm(home, { recursive: true, force: true });
  });

  it("still allows uninstall when the data dir merely sits under the install root", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "uninstall-data-sibling-"));
    const installRoot = path.join(home, "root");
    const dataDir = path.join(installRoot, "data");
    const version = path.join(installRoot, "versions", "0.0.0-darwin-arm64");
    await mkdir(path.join(version, "bin"), { recursive: true });
    await mkdir(dataDir, { recursive: true });
    await writeFile(path.join(dataDir, "PRECIOUS"), "user data\n");
    await symlink(
      "versions/0.0.0-darwin-arm64",
      path.join(installRoot, "current"),
    );

    // `data/` is a sibling of `versions/`, so the recursive delete cannot reach
    // it. This must keep working: the guard is about the removed subtree only.
    const plan = await planLocalUninstall({
      installRoot,
      home,
      dataDir,
      cliLinkPath: null,
      stopsService: false,
    });
    const receipt = await applyManagedUninstall(plan);

    expect(receipt.preserved_data_dir).toBe(dataDir);
    expect(await readFile(path.join(dataDir, "PRECIOUS"), "utf8")).toBe(
      "user data\n",
    );
    await rm(home, { recursive: true, force: true });
  });

  it("honours an explicit preserve-data-dir override without deleting that directory", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "uninstall-override-"));
    const installRoot = path.join(home, "root");
    const dataDir = path.join(installRoot, "versions", "userdata");
    const version = path.join(installRoot, "versions", "0.0.0-darwin-arm64");
    await mkdir(path.join(version, "bin"), { recursive: true });
    await mkdir(dataDir, { recursive: true });
    await writeFile(path.join(dataDir, "PRECIOUS"), "user data\n");
    await symlink(
      "versions/0.0.0-darwin-arm64",
      path.join(installRoot, "current"),
    );

    // Without the override the guard refuses (covered by the previous test).
    // With it, the plan is built for the caller's stated boundary -- and the
    // data directory must NOT be listed as a managed version, or the same plan
    // would advertise protection while deleting it.
    const plan = await planLocalUninstall({
      installRoot,
      home,
      dataDir,
      cliLinkPath: null,
      stopsService: false,
      preserveDataDir: true,
    });
    expect(plan.preserved_data_dir).toBe(dataDir);
    expect(plan.version_directories).toContain(version);
    expect(plan.version_directories).not.toContain(dataDir);

    const receipt = await applyManagedUninstall(plan);
    expect(receipt.removed_version_directories).toContain(version);
    expect(await readFile(path.join(dataDir, "PRECIOUS"), "utf8")).toBe(
      "user data\n",
    );
    await rm(home, { recursive: true, force: true });
  });
});
