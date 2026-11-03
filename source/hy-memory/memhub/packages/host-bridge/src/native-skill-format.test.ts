import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  claudeCodeLayout,
  codexLayout,
  cursorLayout,
  piLayout,
  planRecallInstall,
  type RecallRuntime,
  renderSkillContent,
  SKILL_MARKER,
  workbuddyLayout,
} from "./recall-installer.js";
import { skillFilePath } from "./skill-drift.js";

const roots: string[] = [];

afterEach(async () => {
  for (const root of roots.splice(0)) {
    await rm(root, { recursive: true, force: true });
  }
});

function runtime(root: string): RecallRuntime {
  return {
    runtimeCommand: path.join(root, "not-installed-runtime"),
    mcpEntryPath: path.join(root, "mcp.cjs"),
    discoveryPath: path.join(root, "discovery.json"),
    recallCliPath: path.join(root, "recall-cli.cjs"),
  };
}

// This is the emitted two-scalar metadata contract, not a general YAML parser
// or a native-host run. Matching only the first block catches the loader bug.
function readNativeMetadata(text: string) {
  const match = /^---\nname: ([a-z0-9-]+)\ndescription: (\S[^\n]*)\n---\n/.exec(
    text,
  );
  if (match === null || text.match(/^---$/gm)?.length !== 2) {
    throw new Error(
      "expected one leading YAML frontmatter with name and description",
    );
  }
  return {
    name: match[1],
    description: match[2],
    body: text.slice(match[0].length),
  };
}

function expectNativeSkill(text: string) {
  const metadata = readNativeMetadata(text);
  expect(metadata.name).toBe("memhub-recall");
  expect(metadata.description).toMatch(/^Recall from the local MemHub app /);
  expect(metadata.description).toContain("past decisions");
  expect(metadata.body).toMatch(
    new RegExp(`^\\n?${SKILL_MARKER}\\n\\n# MemHub Recall\\n`),
  );
  expect(text.match(/<!-- one-memory-managed[^\n]*-->/g)).toEqual([
    SKILL_MARKER,
  ]);
}

describe("native Skill frontmatter contract", () => {
  it.each(["mcp", "cli"] as const)(
    "%s rendering starts with complete metadata before the sole ownership marker",
    (channel) => {
      expectNativeSkill(renderSkillContent(channel, runtime("/fixture")));
    },
  );

  it.each([
    { name: "Codex", layout: codexLayout },
    { name: "Cursor", layout: cursorLayout },
    {
      name: "Claude Code",
      layout: (root: string) =>
        claudeCodeLayout({
          claudeDir: root,
          configPath: path.join(root, "claude.json"),
        }),
    },
    { name: "WorkBuddy plugin", layout: workbuddyLayout },
    { name: "CLI-only Pi", layout: piLayout },
  ])(
    "reads name and description from the installed $name file",
    async ({ layout }) => {
      const root = await mkdtemp(
        path.join(tmpdir(), "om-native-skill-format-"),
      );
      roots.push(root);
      const host = layout(path.join(root, "host"));
      const fixtureRuntime = runtime(root);
      const runtimeTargets = [
        fixtureRuntime.runtimeCommand,
        fixtureRuntime.mcpEntryPath,
        ...(fixtureRuntime.recallCliPath ? [fixtureRuntime.recallCliPath] : []),
      ];
      for (const target of runtimeTargets) {
        await writeFile(target, "#!/bin/sh\nexit 0\n");
        await chmod(target, 0o700);
      }
      await applyRecallInstall(await planRecallInstall(host, fixtureRuntime));
      const installedPath = skillFilePath(host);
      if (installedPath === null)
        throw new Error("expected an installed Skill");
      const installed = await readFile(installedPath, "utf8");
      expectNativeSkill(installed);
      expect(installed).toBe(renderSkillContent(host.channel, fixtureRuntime));
    },
  );

  const valid =
    "---\nname: memhub-recall\ndescription: Recall prior decisions.\n---\n";
  it("has a positive reader control independent of the generated template", () => {
    expect(readNativeMetadata(`${valid}\n# Skill\n`)).toEqual({
      name: "memhub-recall",
      description: "Recall prior decisions.",
      body: "\n# Skill\n",
    });
  });

  it.each([
    ["versioned marker before YAML", `${SKILL_MARKER}\n${valid}`],
    ["legacy marker before YAML", `<!-- one-memory-managed:v1 -->\n${valid}`],
    ["body-only metadata", `# Skill\n${valid}`],
    ["incomplete frontmatter", valid.slice(0, -4)],
    ["missing name", valid.replace("name: memhub-recall\n", "")],
    [
      "missing description",
      valid.replace("description: Recall prior decisions.\n", ""),
    ],
    ["empty description", valid.replace("Recall prior decisions.", "")],
    ["duplicate frontmatter", `${valid}${valid}`],
  ])("rejects %s even when other Skill content is present", (_name, text) => {
    expect(() => readNativeMetadata(text)).toThrow(/leading YAML frontmatter/);
  });
});
