import { afterEach, describe, expect, it } from "vitest";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, sep } from "node:path";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { commitAtomicFileSet, recoverAtomicFileSets } from "../utils/atomic-file-set.js";

describe("commitAtomicFileSet", () => {
  const roots: string[] = [];

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  async function createBookFixture(): Promise<string> {
    const root = await mkdtemp(join(tmpdir(), "inkos-file-set-"));
    roots.push(root);
    await Promise.all([
      mkdir(join(root, "chapters"), { recursive: true }),
      mkdir(join(root, "story"), { recursive: true }),
    ]);
    await Promise.all([
      writeFile(join(root, "chapters", "0001_old.md"), "old chapter", "utf-8"),
      writeFile(join(root, "story", "current_state.md"), "old state", "utf-8"),
      writeFile(join(root, "story", "pending_hooks.md"), "old hooks", "utf-8"),
    ]);
    return root;
  }

  it("commits the complete file set and removes superseded files", async () => {
    const root = await createBookFixture();

    await commitAtomicFileSet({
      rootDir: root,
      writes: [
        { relativePath: "chapters/0001_new.md", content: "new chapter" },
        { relativePath: "story/current_state.md", content: "new state" },
        { relativePath: "story/pending_hooks.md", content: "new hooks" },
      ],
      deletes: ["chapters/0001_old.md"],
    });

    await expect(readFile(join(root, "chapters", "0001_new.md"), "utf-8")).resolves.toBe("new chapter");
    await expect(readFile(join(root, "story", "current_state.md"), "utf-8")).resolves.toBe("new state");
    await expect(readFile(join(root, "story", "pending_hooks.md"), "utf-8")).resolves.toBe("new hooks");
    await expect(readdir(join(root, "chapters"))).resolves.toEqual(["0001_new.md"]);
  });

  it("restores every original file when commit fails after the first replacement", async () => {
    const root = await createBookFixture();
    let stagedRenameCount = 0;

    await expect(commitAtomicFileSet({
      rootDir: root,
      writes: [
        { relativePath: "chapters/0001_new.md", content: "new chapter" },
        { relativePath: "story/current_state.md", content: "new state" },
        { relativePath: "story/pending_hooks.md", content: "new hooks" },
      ],
      deletes: ["chapters/0001_old.md"],
      renameFile: async (from, to) => {
        if (from.includes(`${sep}staged${sep}`)) {
          stagedRenameCount += 1;
          if (stagedRenameCount === 2) {
            throw new Error("injected commit failure");
          }
        }
        await rename(from, to);
      },
    })).rejects.toThrow("injected commit failure");

    await expect(readFile(join(root, "chapters", "0001_old.md"), "utf-8")).resolves.toBe("old chapter");
    await expect(readFile(join(root, "story", "current_state.md"), "utf-8")).resolves.toBe("old state");
    await expect(readFile(join(root, "story", "pending_hooks.md"), "utf-8")).resolves.toBe("old hooks");
    await expect(readdir(join(root, "chapters"))).resolves.toEqual(["0001_old.md"]);
  });

  it("recovers a killed writer before the next action, including deletes and new files", async () => {
    const root = await createBookFixture();
    const moduleUrl = new URL("../utils/atomic-file-set.ts", import.meta.url).href;
    const child = spawn(process.execPath, ["--experimental-strip-types", "--input-type=module", "-e", `
      import { commitAtomicFileSet } from ${JSON.stringify(moduleUrl)};
      import { rename } from 'node:fs/promises';
      await commitAtomicFileSet({rootDir: ${JSON.stringify(root)},
        writes: [{relativePath:'chapters/0001_new.md',content:'new chapter'},
          {relativePath:'story/current_state.md',content:'new state'}],
        deletes:['chapters/0001_old.md'],
        renameFile: async (from,to) => {
          await rename(from,to);
          if (from.includes('staged')) {
            process.send('replaced');
            await new Promise(() => { setInterval(() => {},1000); });
          }
        }
      });
    `], { stdio: ["ignore", "ignore", "pipe", "ipc"] });
    try {
      await Promise.race([
        once(child, "message"),
        once(child, "exit").then(([code]) => { throw new Error(`Writer exited early: ${code}`); }),
      ]);
      expect(await recoverAtomicFileSets(root)).toBe(0);
      const exited = once(child, "exit");
      child.kill("SIGKILL");
      await exited;
      expect(await recoverAtomicFileSets(root)).toBe(1);
      expect(await recoverAtomicFileSets(root)).toBe(0);
      expect(await readFile(join(root, "chapters/0001_old.md"), "utf8")).toBe("old chapter");
      expect(await readFile(join(root, "story/current_state.md"), "utf8")).toBe("old state");
      expect(await readdir(join(root, "chapters"))).toEqual(["0001_old.md"]);
      await commitAtomicFileSet({rootDir: root, writes:[{relativePath:"story/current_state.md",content:"retried"}]});
      expect(await readFile(join(root, "story/current_state.md"), "utf8")).toBe("retried");
    } finally { child.kill("SIGKILL"); }
  });

  it("rejects overlapping paths before mutation and recovers an older overlapping directory journal", async () => {
    const root=await createBookFixture();
    await expect(commitAtomicFileSet({rootDir:root,writes:[{relativePath:'story/current_state.md',content:'new'}],deletes:['story']})).rejects.toMatchObject({code:'ATOMIC_PATH_OVERLAP'});
    expect(await readFile(join(root,'story/current_state.md'),'utf8')).toBe('old state');
    const transaction=join(root,'.inkos-file-txn-legacy');
    await mkdir(join(transaction,'backup/story'),{recursive:true});
    await writeFile(join(transaction,'backup/story/current_state.md'),'old state');
    await writeFile(join(root,'story/current_state.md'),'partly replaced');
    await writeFile(join(transaction,'journal.json'),JSON.stringify({version:1,pid:0,phase:'prepared',entries:[{path:'story/current_state.md',existed:true},{path:'story',existed:true}]}));
    expect(await recoverAtomicFileSets(root)).toBe(1);
    expect(await readFile(join(root,'story/current_state.md'),'utf8')).toBe('old state');
    expect(await readFile(join(root,'story/pending_hooks.md'),'utf8')).toBe('old hooks');
    expect(await recoverAtomicFileSets(root)).toBe(0);
  });
});
