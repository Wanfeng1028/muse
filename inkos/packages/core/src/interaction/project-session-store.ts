import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { InteractionSessionSchema, type InteractionSession } from "./session.js";
import { listWorkManifests } from "../harness/work-store.js";
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";

const SESSION_DIR = ".inkos";
const SESSION_FILE = "session.json";

export function resolveProjectSessionPath(projectRoot: string): string {
  return join(projectRoot, SESSION_DIR, SESSION_FILE);
}

export function createProjectSession(projectRoot: string): InteractionSession {
  return InteractionSessionSchema.parse({
    sessionId: `${Date.now()}`,
    projectRoot,
    messages: [],
  });
}

export async function loadProjectSession(projectRoot: string): Promise<InteractionSession> {
  try {
    const raw = await readFile(resolveProjectSessionPath(projectRoot), "utf-8");
    return InteractionSessionSchema.parse(JSON.parse(raw));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return createProjectSession(projectRoot);
    throw error;
  }
}

export async function persistProjectSession(
  projectRoot: string,
  session: InteractionSession,
): Promise<void> {
  const parsed = InteractionSessionSchema.parse(session);
  await commitAtomicFileSet({
    rootDir: projectRoot,
    writes: [{ relativePath: join(SESSION_DIR, SESSION_FILE), content: `${JSON.stringify(parsed, null, 2)}\n` }],
  });
}

export async function resolveSessionActiveBook(
  projectRoot: string,
  session: InteractionSession,
): Promise<string | undefined> {
  if (!session.activeBookId) return undefined;
  const work = (await listWorkManifests(projectRoot, "longform-novel"))
    .find((candidate) => candidate.id === session.activeBookId);
  return work?.id;
}
