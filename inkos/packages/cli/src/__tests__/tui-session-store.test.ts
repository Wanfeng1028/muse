import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createWorkManifest, saveWorkManifest, workDirectory } from "@actalk/inkos-core";
import {
  createProjectSession,
  loadProjectSession,
  persistProjectSession,
  resolveSessionActiveBook,
} from "../tui/session-store.js";

let projectRoot: string;

async function createBookWork(root: string, bookId: string): Promise<void> {
  await saveWorkManifest(root, createWorkManifest({
    id: bookId,
    title: bookId,
    profileId: "longform-novel",
    language: "en",
  }));
  const sourceDir = join(workDirectory(root, bookId), "source");
  await mkdir(sourceDir, { recursive: true });
  await writeFile(join(sourceDir, "book.json"), JSON.stringify({ id: bookId }), "utf-8");
}

describe("tui session store", () => {
  beforeAll(async () => {
    projectRoot = await mkdtemp(join(tmpdir(), "inkos-tui-session-"));
  });

  afterAll(async () => {
    // no cleanup needed, tmpdir
  });

  it("creates a default project session", () => {
    const session = createProjectSession(projectRoot);
    expect(session.projectRoot).toBe(projectRoot);
    expect(session.messages).toEqual([]);
  });

  it("persists and reloads the session", async () => {
    const session = {
      ...createProjectSession(projectRoot),
      activeBookId: "night-harbor",
    };

    await persistProjectSession(projectRoot, session);
    const reloaded = await loadProjectSession(projectRoot);

    expect(reloaded.activeBookId).toBe("night-harbor");
  });

  it("resolves active book from session when it still exists", async () => {
    await createBookWork(projectRoot, "night-harbor");

    const session = {
      ...createProjectSession(projectRoot),
      activeBookId: "night-harbor",
    };

    expect(await resolveSessionActiveBook(projectRoot, session)).toBe("night-harbor");
  });

  it("does not infer an active book from the project catalog", async () => {
    const singleRoot = await mkdtemp(join(tmpdir(), "inkos-tui-single-"));
    await createBookWork(singleRoot, "single-book");

    const session = createProjectSession(singleRoot);
    expect(await resolveSessionActiveBook(singleRoot, session)).toBeUndefined();
  });
});
