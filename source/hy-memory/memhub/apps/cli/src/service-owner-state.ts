import {
  claimRuntimeServiceForCli,
  type RuntimeServiceOwner,
  readRuntimeServiceOwner,
  removeRuntimeServiceOwner,
  writeRuntimeServiceOwner,
} from "@one-memory/runtime-control";

export async function claimCliServiceOwnership(
  dataDir: string,
): Promise<RuntimeServiceOwner | null> {
  const previous = await readRuntimeServiceOwner(dataDir).catch(() => null);
  await claimRuntimeServiceForCli(dataDir);
  return previous;
}

export async function restoreServiceOwnership(
  dataDir: string,
  previous: RuntimeServiceOwner | null,
): Promise<void> {
  if (previous === null) await removeRuntimeServiceOwner(dataDir);
  else await writeRuntimeServiceOwner(dataDir, previous);
}
