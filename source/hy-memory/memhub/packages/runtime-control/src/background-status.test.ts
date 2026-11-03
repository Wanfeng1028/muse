import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { inspectBackgroundRegistration } from "./background-status.js";
import { planUserService, runtimeInstallLayout } from "./service-plan.js";

const dirs: string[] = [];
afterEach(async () => {
  for (const dir of dirs.splice(0))
    await rm(dir, { recursive: true, force: true });
});
async function fixture(write = true) {
  const home = await mkdtemp(path.join(os.tmpdir(), "om-bg-status-"));
  dirs.push(home);
  const layout = runtimeInstallLayout({
    platform: "darwin",
    home,
    installRoot: path.join(home, "runtime/current"),
  });
  const plan = planUserService(layout, { uid: 501 });
  const file = plan.service_file;
  if (!file) throw new Error("test_service_plan_missing");
  if (write) {
    await mkdir(path.dirname(file.path), { recursive: true, mode: 0o700 });
    await writeFile(file.path, file.content, { mode: 0o600 });
  }
  return { layout, file };
}
describe("background registration inspection", () => {
  it("does not call a file registered or running without OS observation", async () => {
    const { layout, file } = await fixture();
    const before = await readFile(file.path, "utf8");
    expect(
      await inspectBackgroundRegistration(layout, {
        uid: 501,
        legacy: "not_registered",
      }),
    ).toMatchObject({
      file: "managed",
      registration: "unknown",
      runtime: "not_checked",
    });
    expect(await readFile(file.path, "utf8")).toBe(before);
  });
  it("reports absent without creating directories or reading Core", async () => {
    const { layout, file } = await fixture(false);
    expect(
      await inspectBackgroundRegistration(layout, {
        uid: 501,
        legacy: "not_registered",
      }),
    ).toMatchObject({ file: "absent", registration: "unknown" });
    await expect(readFile(file.path)).rejects.toMatchObject({ code: "ENOENT" });
  });
  it.each(["disabled_by_system", "requires_approval", "registered"] as const)(
    "retains OS %s without repair",
    async (registration) => {
      const { layout } = await fixture();
      const expected = planUserService(layout, { uid: 501 }).service_id;
      const observe = vi.fn(async () => registration);
      expect(
        await inspectBackgroundRegistration(layout, {
          uid: 501,
          legacy: "not_registered",
          observe,
        }),
      ).toMatchObject({
        file: "managed",
        registration,
        runtime: "not_checked",
      });
      expect(observe).toHaveBeenCalledExactlyOnceWith(expected);
    },
  );
  it.each(["enabled", "requires_approval"] as const)(
    "treats legacy %s as a conflict",
    async (legacy) => {
      const { layout } = await fixture();
      const observe = vi.fn();
      expect(
        await inspectBackgroundRegistration(layout, {
          uid: 501,
          legacy,
          observe,
        }),
      ).toMatchObject({
        registration: "conflict",
        reason: "legacy_registration_conflict",
      });
      expect(observe).not.toHaveBeenCalled();
    },
  );
  it("missing legacy observation cannot permit a new registration", async () => {
    const { layout } = await fixture();
    expect(
      await inspectBackgroundRegistration(layout, { uid: 501 }),
    ).toMatchObject({
      registration: "unknown",
      reason: "legacy_registration_unknown",
    });
  });
  it("rejects changed files without mutation or OS action", async () => {
    const { layout, file } = await fixture();
    await writeFile(file.path, "foreign definition");
    const observe = vi.fn();
    expect(
      await inspectBackgroundRegistration(layout, {
        uid: 501,
        legacy: "not_registered",
        observe,
      }),
    ).toMatchObject({ file: "conflict", registration: "conflict" });
    expect(observe).not.toHaveBeenCalled();
    expect(await readFile(file.path, "utf8")).toBe("foreign definition");
  });
  it("rejects symlink or broadly writable declarations", async () => {
    const { layout, file } = await fixture();
    await chmod(file.path, 0o666);
    expect(
      (await inspectBackgroundRegistration(layout, { uid: 501 })).file,
    ).toBe("conflict");
    await rm(file.path);
    await symlink(path.join(layout.home, "missing"), file.path);
    expect(
      (await inspectBackgroundRegistration(layout, { uid: 501 })).file,
    ).toBe("conflict");
  });
  it("does not leak observer errors or promote unknown to absent", async () => {
    const { layout } = await fixture();
    const status = await inspectBackgroundRegistration(layout, {
      uid: 501,
      legacy: "not_registered",
      observe: async () => {
        throw Error("secret path");
      },
    });
    expect(status.registration).toBe("unknown");
    expect(JSON.stringify(status)).not.toContain("secret path");
  });
  it("OS registered without the managed declaration is a conflict", async () => {
    const { layout } = await fixture(false);
    expect(
      await inspectBackgroundRegistration(layout, {
        uid: 501,
        legacy: "not_registered",
        observe: async () => "registered",
      }),
    ).toMatchObject({ file: "absent", registration: "conflict" });
  });
  it("does not infer still absent if a declaration appears during observation", async () => {
    const { layout, file } = await fixture(false);
    const result = await inspectBackgroundRegistration(layout, {
      uid: 501,
      legacy: "not_registered",
      observe: async () => {
        await mkdir(path.dirname(file.path), { recursive: true, mode: 0o700 });
        await writeFile(file.path, file.content, { mode: 0o600 });
        return "absent";
      },
    });
    expect(result.registration).toBe("unknown");
    expect(result.reason).toBe("service_declaration_changed");
  });
});
