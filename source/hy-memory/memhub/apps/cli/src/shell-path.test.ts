import { mkdtemp, readFile, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyShellPath,
  planShellPath,
  removeShellPath,
} from "./shell-path.js";

async function home(): Promise<string> {
  return mkdtemp(path.join(tmpdir(), "memhub-shell-path-"));
}

describe("managed shell PATH block", () => {
  it("adds a single marked block to a profile that lacks the directory", async () => {
    const root = await home();
    const profile = path.join(root, ".zprofile");
    await writeFile(profile, "# existing\nexport EDITOR=vim\n");

    const plan = await planShellPath({
      binDirectory: path.join(root, ".local/bin"),
      home: root,
      platform: "darwin",
    });
    expect(plan).toMatchObject({ status: "create" });

    const receipt = await applyShellPath(plan);
    expect(receipt.created).toBe(true);
    const content = await readFile(profile, "utf8");
    expect(content).toContain("# >>> memhub PATH >>>");
    expect(content).toContain(path.join(root, ".local/bin"));
    // Existing content is preserved, not rewritten.
    expect(content).toContain("export EDITOR=vim");
  });

  it("creates a missing home directory before writing the profile", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "memhub-shell-path-"));
    const missingHome = path.join(root, "new-user-home");
    const binDirectory = path.join(missingHome, ".local", "bin");
    const plan = await planShellPath({
      binDirectory,
      home: missingHome,
      platform: "darwin",
    });

    expect(plan.status).toBe("create");
    await expect(applyShellPath(plan)).resolves.toMatchObject({
      created: true,
    });
    const content = await readFile(path.join(missingHome, ".zprofile"), "utf8");
    expect(content).toContain("# >>> memhub PATH >>>");
    expect(content).toContain(binDirectory);
  });

  it("is idempotent: a second plan sees the block as present", async () => {
    const root = await home();
    const profile = path.join(root, ".zprofile");
    const binDirectory = path.join(root, ".local/bin");
    await applyShellPath(
      await planShellPath({ binDirectory, home: root, platform: "darwin" }),
    );
    const again = await planShellPath({
      binDirectory,
      home: root,
      platform: "darwin",
    });
    expect(again.status).toBe("present");
    const applied = await applyShellPath(again);
    expect(applied.created).toBe(false);
    // Exactly one block, still.
    const content = await readFile(profile, "utf8");
    expect(content.match(/# >>> memhub PATH >>>/g)).toHaveLength(1);
  });

  it("leaves a user-managed PATH entry alone", async () => {
    const root = await home();
    const profile = path.join(root, ".zprofile");
    const binDirectory = path.join(root, ".local/bin");
    await writeFile(profile, `export PATH="${binDirectory}:$PATH"\n`);

    const plan = await planShellPath({
      binDirectory,
      home: root,
      platform: "darwin",
    });
    expect(plan).toMatchObject({ status: "present", block: null });
    const receipt = await applyShellPath(plan);
    expect(receipt.created).toBe(false);
    expect(await readFile(profile, "utf8")).toBe(
      `export PATH="${binDirectory}:$PATH"\n`,
    );
  });

  it("does not match a directory that is only a prefix of the entry", async () => {
    const root = await home();
    const profile = path.join(root, ".zprofile");
    const binDirectory = path.join(root, ".local/bin");
    await writeFile(profile, `export PATH="${binDirectory}-extra:$PATH"\n`);

    const plan = await planShellPath({
      binDirectory,
      home: root,
      platform: "darwin",
    });
    expect(plan.status).toBe("create");
  });

  it("removes exactly the block it wrote, keeping the rest", async () => {
    const root = await home();
    const profile = path.join(root, ".zprofile");
    const binDirectory = path.join(root, ".local/bin");
    await writeFile(profile, "export A=1\n");
    const plan = await planShellPath({
      binDirectory,
      home: root,
      platform: "darwin",
    });
    await applyShellPath(plan);
    const result = await removeShellPath(plan);
    expect(result).toBe("removed");
    const content = await readFile(profile, "utf8");
    expect(content).toBe("export A=1\n");
  });

  it("blocks writing outside the user's home", async () => {
    const root = await home();
    const plan = await planShellPath({
      binDirectory: path.join(root, ".local/bin"),
      home: root,
      platform: "darwin",
      profilePath: "/etc/profile",
    });
    expect(plan).toMatchObject({
      status: "blocked",
      blocked_reason: "profile_outside_home",
    });
  });

  it("blocks an unusable bin directory instead of writing it", async () => {
    const root = await home();
    for (const bad of ["relative/bin", "/tmp/with\nnewline"]) {
      const plan = await planShellPath({
        binDirectory: bad,
        home: root,
        platform: "darwin",
      });
      expect(plan).toMatchObject({
        status: "blocked",
        blocked_reason: "bin_directory_unusable",
      });
    }
  });

  // C8 74a7c9e / [BLOCK C8 -> C6 CLI] install-must-not-edit-host-shell:
  // `--no-shell-path` must produce a plan that writes nothing, so an isolated
  // install never edits the login profile even when binDir is not on PATH.
  it("writes nothing at all when the caller opts out with disabled", async () => {
    const directory = await home();
    const binDirectory = path.join(directory, "bin");
    const plan = await planShellPath({
      binDirectory,
      home: directory,
      platform: "darwin",
      disabled: true,
    });
    expect(plan.status).toBe("present");
    expect(plan.block).toBeNull();
    const receipt = await applyShellPath(plan);
    expect(receipt.created).toBe(false);
    await expect(
      readFile(path.join(directory, ".zprofile"), "utf8"),
    ).rejects.toThrow();
  });

  it("stays blocked on Windows rather than guessing a PATH story", async () => {
    const root = await home();
    const plan = await planShellPath({
      binDirectory: "C:\\Users\\Example\\.local\\bin",
      home: root,
      platform: "win32",
    });
    expect(plan.status).toBe("blocked");
  });

  // O-19 (2026-09-29 acceptance): `--home` may point at a directory that does
  // not exist yet (a fresh profile). Writing the temp `.zprofile` file then
  // failed with a raw ENOENT. The installer must create the home first.
  it("creates the home directory when it does not exist yet", async () => {
    const root = await home();
    const freshHome = path.join(root, "brand-new-home");
    const binDirectory = path.join(root, ".local/bin");
    // The home does not exist at plan time.
    await expect(stat(freshHome)).rejects.toMatchObject({ code: "ENOENT" });

    const plan = await planShellPath({
      binDirectory,
      home: freshHome,
      platform: "darwin",
    });
    expect(plan).toMatchObject({ status: "create" });

    const receipt = await applyShellPath(plan);
    expect(receipt.created).toBe(true);
    const content = await readFile(path.join(freshHome, ".zprofile"), "utf8");
    expect(content).toContain("# >>> memhub PATH >>>");
    expect(content).toContain(binDirectory);
  });
});
