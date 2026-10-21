// Adapted from MemTensor Claude SkillTarget installation (MIT). See PROVENANCE.md.

import { constants } from "node:fs";
import { access, lstat } from "node:fs/promises";
import path from "node:path";
import {
  type ClaudeInstallPlan,
  type ClaudeTargetOptions,
  type FileSnapshot,
  type InstallationJournal,
  JOURNAL,
  MANAGED_FILES,
  parseJournal,
  planFingerprint,
  renderInstallPlan,
  renderUninstallPlan,
} from "./install-plan.js";
import {
  assertNoSymlinks,
  readText,
  removeFile,
  withDirectoryLock,
  writeText,
} from "./private-files.js";
import { absolutePath, ClaudeAdapterError } from "./runtime-config.js";

export function createClaudeCodeTarget(options: ClaudeTargetOptions) {
  return createTarget(options.claudeDirectory, options);
}

export function createClaudeCodeRemovalTarget(claudeDirectory: string) {
  const { planUninstall, applyUninstall, verify } =
    createTarget(claudeDirectory);
  return { planUninstall, applyUninstall, verify };
}

function createTarget(claudeDirectory: string, options?: ClaudeTargetOptions) {
  const root = absolutePath(claudeDirectory);
  const filePath = (name: string) => path.join(root, name);
  const journalPath = filePath(JOURNAL);
  const ensure = async () => {
    if (process.platform === "win32" || typeof process.getuid !== "function")
      throw new ClaudeAdapterError("platform_unsupported");
    await assertNoSymlinks(root);
    if (!(await lstat(root)).isDirectory())
      throw new ClaudeAdapterError("host_directory_unavailable");
  };
  const credentialMetadata = async () => {
    try {
      if (!options) throw new ClaudeAdapterError("invalid_install_plan");
      await assertNoSymlinks(options.config.credentialFile);
      const info = await lstat(options.config.credentialFile);
      const parent = await lstat(path.dirname(options.config.credentialFile));
      if (
        !info.isFile() ||
        info.nlink !== 1 ||
        info.uid !== process.getuid?.() ||
        (info.mode & 0o7777) !== 0o600 ||
        info.size < 51 ||
        info.size > 52 ||
        !parent.isDirectory() ||
        parent.uid !== process.getuid?.() ||
        (parent.mode & 0o7777) !== 0o700
      )
        throw new Error();
      await access(options.nodeExecutable, constants.X_OK);
    } catch {
      throw new ClaudeAdapterError("credential_unavailable");
    }
  };
  const observe = async (): Promise<FileSnapshot[]> => {
    const files: FileSnapshot[] = [];
    for (const name of MANAGED_FILES) {
      const content = await readText(filePath(name));
      const mode =
        content === null ? 0o600 : (await lstat(filePath(name))).mode & 0o777;
      files.push({ path: name, content, mode });
    }
    return files;
  };
  const planInstall = async () => {
    if (!options) throw new ClaudeAdapterError("invalid_install_plan");
    await ensure();
    await credentialMetadata();
    return renderInstallPlan(
      options,
      await observe(),
      await readText(journalPath, 8 * 1024 * 1024),
    );
  };
  const planUninstall = async () => {
    await ensure();
    const raw = await readText(journalPath, 8 * 1024 * 1024);
    if (raw === null) throw new ClaudeAdapterError("not_installed");
    return renderUninstallPlan(await observe(), raw);
  };
  const apply = async (plan: ClaudeInstallPlan, approved: string) => {
    await ensure();
    if (typeof approved !== "string" || approved !== plan.fingerprint)
      throw new ClaudeAdapterError("preview_stale");
    await withDirectoryLock(
      path.join(root, ".one-memory-mh-c01.lock"),
      async () => {
        const current =
          plan.operation === "install"
            ? await planInstall()
            : await planUninstall();
        if (current.fingerprint !== approved)
          throw new ClaudeAdapterError("preview_stale");
        const { fingerprint: _fingerprint, ...body } = plan;
        if (planFingerprint(body) !== approved)
          throw new ClaudeAdapterError("preview_stale");
        const journal = plan.journalAfter ?? parseJournal(plan.journalBefore);
        if (!journal)
          throw new ClaudeAdapterError("invalid_installation_journal");
        const changed: typeof plan.files = [];
        await writeText(
          journalPath,
          `${JSON.stringify({ ...journal, phase: "applying" })}\n`,
        );
        try {
          for (const file of current.files) {
            if (file.content === file.after) continue;
            if ((await readText(filePath(file.path))) !== file.content)
              throw new ClaudeAdapterError("preview_stale");
            if (file.after === null) await removeFile(filePath(file.path));
            else
              await writeText(
                filePath(file.path),
                file.after,
                file.content === null ? 0o600 : file.mode,
              );
            changed.push(file);
          }
          if (plan.journalAfter)
            await writeText(
              journalPath,
              `${JSON.stringify(plan.journalAfter)}\n`,
            );
          else await removeFile(journalPath);
        } catch (error) {
          let recovered = true;
          for (const file of changed.reverse()) {
            try {
              if ((await readText(filePath(file.path))) !== file.after) {
                recovered = false;
                continue;
              }
              if (file.content === null) await removeFile(filePath(file.path));
              else
                await writeText(filePath(file.path), file.content, file.mode);
            } catch {
              recovered = false;
            }
          }
          if (recovered) {
            if (plan.journalBefore === null) await removeFile(journalPath);
            else await writeText(journalPath, plan.journalBefore);
          }
          throw error;
        }
      },
    );
  };
  return {
    targetId: "claude-code" as const,
    planInstall,
    planUninstall,
    async applyInstall(plan: ClaudeInstallPlan, approved: string) {
      if (plan.operation !== "install")
        throw new ClaudeAdapterError("invalid_install_plan");
      await apply(plan, approved);
    },
    async applyUninstall(plan: ClaudeInstallPlan, approved: string) {
      if (plan.operation !== "uninstall")
        throw new ClaudeAdapterError("invalid_install_plan");
      await apply(plan, approved);
    },
    async verify(): Promise<{
      state: "not-installed" | "candidate-installed";
      permissionEffect: "none";
    }> {
      await ensure();
      const raw = await readText(journalPath, 8 * 1024 * 1024);
      if (raw === null)
        return { state: "not-installed", permissionEffect: "none" };
      const journal = parseJournal(raw) as InstallationJournal;
      if (journal.phase !== "installed")
        throw new ClaudeAdapterError("installation_recovery_required");
      // Uninstall planning validates that every managed artifact/entry remains intact.
      await planUninstall();
      if (options) await credentialMetadata();
      return { state: "candidate-installed", permissionEffect: "none" };
    },
  };
}
