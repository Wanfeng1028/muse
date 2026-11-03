import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  readCharacterContext,
  readRoleCards,
  readStoryFrame,
  readVolumeMap,
} from "../utils/outline-paths.js";

let bookDir: string;

beforeEach(async () => {
  bookDir = await mkdtemp(join(tmpdir(), "inkos-outline-paths-"));
  await mkdir(join(bookDir, "story"), { recursive: true });
});

afterEach(async () => {
  await rm(bookDir, { recursive: true, force: true });
});

describe("outline-paths", () => {
  it("reads the canonical story frame", async () => {
    await mkdir(join(bookDir, "story", "outline"), { recursive: true });
    await writeFile(join(bookDir, "story", "outline", "story_frame.md"), "Frame prose", "utf-8");

    const content = await readStoryFrame(bookDir);
    expect(content).toBe("Frame prose");
  });

  it("fails when a canonical foundation asset is missing", async () => {
    await expect(readStoryFrame(bookDir)).rejects.toMatchObject({ code: "ENOENT" });
    await expect(readVolumeMap(bookDir)).rejects.toMatchObject({ code: "ENOENT" });
    await expect(readCharacterContext(bookDir)).rejects.toThrow("Canonical role cards are missing");
  });

  it("reads the canonical volume map", async () => {
    await mkdir(join(bookDir, "story", "outline"), { recursive: true });
    await writeFile(join(bookDir, "story", "outline", "volume_map.md"), "Map prose", "utf-8");

    const content = await readVolumeMap(bookDir);
    expect(content).toBe("Map prose");
  });

  it("reads role cards one-file-per-character from both tiers", async () => {
    const majorDir = join(bookDir, "story", "roles", "主要角色");
    const minorDir = join(bookDir, "story", "roles", "次要角色");
    await mkdir(majorDir, { recursive: true });
    await mkdir(minorDir, { recursive: true });
    await writeFile(join(majorDir, "林辞.md"), "主角核心卡", "utf-8");
    await writeFile(join(majorDir, "沈默.md"), "对手卡", "utf-8");
    await writeFile(join(minorDir, "老张.md"), "次要卡", "utf-8");

    const cards = await readRoleCards(bookDir);
    expect(cards).toHaveLength(3);
    const byName = Object.fromEntries(cards.map((card) => [card.name, card]));
    expect(byName["林辞"]?.tier).toBe("major");
    expect(byName["沈默"]?.tier).toBe("major");
    expect(byName["老张"]?.tier).toBe("minor");
  });

  it("composes role cards into character-context prose grouped by tier", async () => {
    const majorDir = join(bookDir, "story", "roles", "主要角色");
    await mkdir(majorDir, { recursive: true });
    await writeFile(join(majorDir, "林辞.md"), "## 核心标签\n沉静的观察者\n", "utf-8");

    const context = await readCharacterContext(bookDir);
    expect(context).toContain("林辞");
    expect(context).toContain("主要角色");
    expect(context).toContain("沉静的观察者");
  });

});
