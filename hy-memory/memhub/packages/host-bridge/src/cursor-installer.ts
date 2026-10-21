import {
  applyRecallInstall,
  cursorLayout,
  planRecallInstall,
  type RecallInstallPlan,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

export interface CursorInstallOptions {
  cursorDir: string;
  runtimeCommand: string;
  mcpEntryPath: string;
  discoveryPath: string;
}

export type CursorInstallPlan = RecallInstallPlan;

export async function planCursorInstall(
  options: CursorInstallOptions,
): Promise<CursorInstallPlan> {
  if (!options.cursorDir) {
    throw new Error("All Cursor installer paths are required");
  }
  return planRecallInstall(cursorLayout(options.cursorDir), options);
}

export async function applyCursorInstall(
  plan: CursorInstallPlan,
): Promise<void> {
  await applyRecallInstall(plan);
}

export async function verifyCursorInstall(cursorDir: string): Promise<void> {
  await verifyRecallInstall(cursorLayout(cursorDir));
}

export async function rollbackCursorInstall(cursorDir: string): Promise<void> {
  await rollbackRecallInstall(cursorLayout(cursorDir));
}
