import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { loadChaptersFromPath } from "../agent/chapter-import-source.js";

describe("loadChaptersFromPath", () => {
  const roots: string[] = [];

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("loads unpadded chapter files in natural numeric order", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-chapter-import-"));
    roots.push(root);
    const source = join(root, "chapters");
    await mkdir(source);
    await Promise.all([
      writeFile(join(source, "10_终局.md"), "ten"),
      writeFile(join(source, "2_转折.md"), "two"),
      writeFile(join(source, "1_开端.md"), "one"),
    ]);

    const chapters = await loadChaptersFromPath(source);

    expect(chapters.map((chapter) => chapter.title)).toEqual(["开端", "转折", "终局"]);
    expect(chapters.map((chapter) => chapter.content)).toEqual(["one", "two", "ten"]);
  });

  it("treats a non-empty headingless file as one chapter", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-single-chapter-import-"));
    roots.push(root);
    const source = join(root, "harbor-letter.md");
    await writeFile(source, "# The Harbor Letter\n\nAt midnight, the bell rang once.\n", "utf-8");

    await expect(loadChaptersFromPath(source)).resolves.toEqual([{
      title: "The Harbor Letter",
      content: "At midnight, the bell rang once.",
    }]);
  });

  it("keeps a failed explicit split pattern as an error", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-custom-split-import-"));
    roots.push(root);
    const source = join(root, "novel.txt");
    await writeFile(source, "Only body text.", "utf-8");

    await expect(loadChaptersFromPath(source, "^Part\\s+(.+)$"))
      .rejects.toThrow(/No chapters found/);
  });
});
