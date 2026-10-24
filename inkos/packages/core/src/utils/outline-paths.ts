import { readFile, readdir, access } from "node:fs/promises";
import { join } from "node:path";

/**
 * Whether a book's architect foundation is fully written on disk. A long
 * architect run (especially on a stronger model) can outlive the in-memory
 * create-status tracking — or the server can restart mid-run — leaving the
 * status endpoint with no entry. Checking disk lets create-status answer
 * "ready" truthfully instead of an ambiguous 404 that reads as "failed".
 *
 * "Complete" mirrors the five sections the architect must emit
 * (story_frame / volume_map / book_rules / pending_hooks / roles); a half-built
 * book that is missing any of these is NOT ready.
 */
export async function isBookFoundationComplete(bookDir: string): Promise<boolean> {
  const required = [
    join(bookDir, "book.json"),
    join(bookDir, "story", "outline", "story_frame.md"),
    join(bookDir, "story", "outline", "volume_map.md"),
    join(bookDir, "story", "book_rules.md"),
    join(bookDir, "story", "book_rules.json"),
    join(bookDir, "story", "pending_hooks.md"),
  ];
  for (const path of required) {
    try {
      await access(path);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
      throw error;
    }
  }
  for (const tier of ["主要角色", "major", "次要角色", "minor"]) {
    try {
      const entries = await readdir(join(bookDir, "story", "roles", tier));
      if (entries.some((file) => file.endsWith(".md"))) return true;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  return false;
}

export async function readStoryFrame(bookDir: string): Promise<string> {
  return readFile(join(bookDir, "story", "outline", "story_frame.md"), "utf-8");
}

export async function readVolumeMap(bookDir: string): Promise<string> {
  return readFile(join(bookDir, "story", "outline", "volume_map.md"), "utf-8");
}

export interface RoleCard {
  readonly tier: "major" | "minor";
  readonly name: string;
  readonly content: string;
}

/**
 * Read the canonical roles/ directory.
 */
export async function readRoleCards(bookDir: string): Promise<ReadonlyArray<RoleCard>> {
  const rolesRoot = join(bookDir, "story", "roles");
  const majorDirZh = join(rolesRoot, "主要角色");
  const minorDirZh = join(rolesRoot, "次要角色");
  const majorDirEn = join(rolesRoot, "major");
  const minorDirEn = join(rolesRoot, "minor");

  const cards: RoleCard[] = [];
  await Promise.all([
    collectRoleDir(majorDirZh, "major", cards),
    collectRoleDir(minorDirZh, "minor", cards),
    collectRoleDir(majorDirEn, "major", cards),
    collectRoleDir(minorDirEn, "minor", cards),
  ]);
  return cards;
}

async function collectRoleDir(
  dir: string,
  tier: "major" | "minor",
  out: RoleCard[],
): Promise<void> {
  let entries: string[];
  try {
    entries = await readdir(dir);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
  const reads = entries
    .filter((entry) => entry.endsWith(".md"))
    .map(async (entry) => {
      const content = await readFile(join(dir, entry), "utf-8");
      if (!content.trim()) throw new Error(`Role card is empty: ${join(dir, entry)}`);
      out.push({
        tier,
        name: entry.replace(/\.md$/, ""),
        content,
      });
    });
  await Promise.all(reads);
}

/**
 * Render canonical role cards for model context.
 */
export async function readCharacterContext(bookDir: string): Promise<string> {
  const cards = await readRoleCards(bookDir);
  if (cards.length > 0) {
    const groups: Record<"major" | "minor", RoleCard[]> = { major: [], minor: [] };
    for (const card of cards) groups[card.tier].push(card);

    const render = (tierCards: RoleCard[], heading: string): string => {
      if (tierCards.length === 0) return "";
      const sections = tierCards.map((card) => `### ${card.name}\n\n${card.content.trim()}`);
      return `## ${heading}\n\n${sections.join("\n\n")}`;
    };

    const blocks = [
      render(groups.major, "主要角色 / Major characters"),
      render(groups.minor, "次要角色 / Minor characters"),
    ].filter(Boolean);

    return blocks.join("\n\n");
  }

  throw new Error(`Canonical role cards are missing from: ${join(bookDir, "story", "roles")}`);
}
