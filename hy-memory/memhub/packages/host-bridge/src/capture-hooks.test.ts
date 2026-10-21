import { execFile, execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it } from "vitest";

import { failOpenHookCommand } from "./capture-hooks.js";
import {
  applyRecallInstall,
  applyRecallUninstall,
  claudeCodeLayout,
  codexLayout,
  cursorLayout,
  opencodeLayout,
  piLayout,
  planRecallInstall,
  planRecallUninstall,
  type RecallRuntime,
} from "./recall-installer.js";

async function root(): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), "one-memory-capture-"));
}

function runtime(home: string): RecallRuntime {
  return {
    runtimeCommand: "/opt/memhub/bin/node",
    mcpEntryPath: "/opt/memhub/host-bridge/mcp.cjs",
    discoveryPath: path.join(home, "cursor-broker.json"),
    captureCommand: "/opt/memhub/core/one-memory",
    recallCliPath: "/opt/memhub/host-bridge/recall-cli.cjs",
  };
}

describe("capture hooks installed with recall", () => {
  it("adds Cursor commands and removes only those on uninstall", async () => {
    const home = await root();
    const dir = path.join(home, ".cursor");
    await mkdir(dir);
    const hooksPath = path.join(dir, "hooks.json");
    await writeFile(
      hooksPath,
      JSON.stringify({
        version: 1,
        hooks: {
          beforeSubmitPrompt: [{ command: "other-tool" }],
        },
      }),
    );
    const layout = cursorLayout(dir);
    await applyRecallInstall(await planRecallInstall(layout, runtime(home)));
    const installed = JSON.parse(await readFile(hooksPath, "utf8")) as {
      hooks: Record<string, Array<{ command: string }>>;
    };
    const capture = failOpenHookCommand(
      "/opt/memhub/core/one-memory",
      "capture cursor",
      "silent",
    );
    expect(
      installed.hooks.beforeSubmitPrompt.map((entry) => entry.command),
    ).toEqual(["other-tool", capture]);
    expect(installed.hooks.afterAgentResponse[0].command).toBe(capture);
    await writeFile(
      hooksPath,
      JSON.stringify({
        ...installed,
        hooks: {
          ...installed.hooks,
          stop: [{ command: "added-after" }],
        },
      }),
    );
    await applyRecallUninstall(await planRecallUninstall(layout));
    const removed = JSON.parse(await readFile(hooksPath, "utf8")) as {
      hooks: Record<string, Array<{ command: string }>>;
    };
    expect(removed.hooks.beforeSubmitPrompt).toEqual([
      { command: "other-tool" },
    ]);
    expect(removed.hooks.afterAgentResponse).toBeUndefined();
    expect(removed.hooks.stop).toEqual([{ command: "added-after" }]);
  });

  it("replaces stale One Memory capture commands instead of accumulating them", async () => {
    const home = await root();
    const dir = path.join(home, ".cursor");
    await mkdir(dir);
    const hooksPath = path.join(dir, "hooks.json");
    await writeFile(
      hooksPath,
      JSON.stringify({
        version: 1,
        hooks: {
          beforeSubmitPrompt: [
            { command: "other-tool" },
            {
              command:
                "sh -c 'ONE_MEMORY_DATA_DIR='\\''/old-data'\\'' '\\''/old/core/one-memory'\\'' capture cursor >/dev/null 2>&1; exit 0'",
            },
            {
              command:
                "sh -c 'ONE_MEMORY_DATA_DIR='\\''/older-data'\\'' '\\''/older/core/one-memory'\\'' capture cursor >/dev/null 2>&1; exit 0'",
            },
          ],
        },
      }),
    );
    const layout = cursorLayout(dir);

    await applyRecallInstall(await planRecallInstall(layout, runtime(home)));

    const installed = JSON.parse(await readFile(hooksPath, "utf8")) as {
      hooks: { beforeSubmitPrompt: Array<{ command: string }> };
    };
    const commands = installed.hooks.beforeSubmitPrompt.map(
      (entry) => entry.command,
    );
    expect(commands).toHaveLength(2);
    expect(commands[0]).toBe("other-tool");
    expect(
      commands.filter((command) => command.includes("capture cursor")),
    ).toHaveLength(1);
  });

  it("merges Claude Code and Codex hook groups", async () => {
    const home = await root();
    const claude = path.join(home, ".claude");
    const codex = path.join(home, ".codex");
    await mkdir(claude);
    await mkdir(codex);
    await applyRecallInstall(
      await planRecallInstall(
        claudeCodeLayout({
          claudeDir: claude,
          configPath: path.join(home, ".claude.json"),
        }),
        runtime(home),
      ),
    );
    await applyRecallInstall(
      await planRecallInstall(codexLayout(codex), runtime(home)),
    );
    const claudeHooks = JSON.parse(
      await readFile(path.join(claude, "settings.json"), "utf8"),
    ) as {
      hooks: Record<string, Array<{ hooks: Array<{ command: string }> }>>;
    };
    expect(claudeHooks.hooks.UserPromptSubmit[0].hooks[0].command).toBe(
      failOpenHookCommand(
        "/opt/memhub/core/one-memory",
        "capture claude-code",
        "silent",
      ),
    );
    expect(claudeHooks.hooks.Stop[0].hooks[0].command).toContain(
      "capture claude-code",
    );
    expect(claudeHooks.hooks.SubagentStop[0].hooks[0].command).toContain(
      "capture claude-code",
    );
    const codexHooks = JSON.parse(
      await readFile(path.join(codex, "hooks.json"), "utf8"),
    ) as {
      hooks: Record<string, Array<{ hooks: Array<{ command: string }> }>>;
    };
    expect(Object.keys(codexHooks.hooks).sort()).toEqual([
      "Stop",
      "UserPromptSubmit",
    ]);
    expect(codexHooks.hooks.Stop[0].hooks[0].command).toBe(
      failOpenHookCommand(
        "/opt/memhub/core/one-memory",
        "capture codex",
        "silent",
      ),
    );
  });

  it.each([
    ["claude-code", "UserPromptSubmit"],
    ["codex", "UserPromptSubmit"],
  ] as const)(
    "replaces stale %s capture groups instead of accumulating them",
    async (hostId, event) => {
      const home = await root();
      const dir = path.join(home, hostId === "codex" ? ".codex" : ".claude");
      await mkdir(dir);
      const hooksPath = path.join(hostId === "codex" ? dir : dir, "hooks.json");
      if (hostId === "claude-code") {
        await writeFile(
          path.join(dir, "settings.json"),
          JSON.stringify({
            hooks: {
              [event]: [
                {
                  matcher: "",
                  hooks: [{ type: "command", command: "other-tool" }],
                },
                {
                  matcher: "",
                  hooks: [
                    {
                      type: "command",
                      command:
                        "sh -c 'ONE_MEMORY_DATA_DIR='\\''/old-data'\\'' '\\''/old/core/one-memory'\\'' capture claude-code >/dev/null 2>&1; exit 0'",
                    },
                  ],
                },
                {
                  matcher: "",
                  hooks: [
                    {
                      type: "command",
                      command:
                        "sh -c 'ONE_MEMORY_DATA_DIR='\\''/older-data'\\'' '\\''/older/core/one-memory'\\'' capture claude-code >/dev/null 2>&1; exit 0'",
                    },
                  ],
                },
              ],
            },
          }),
        );
      } else {
        await writeFile(
          hooksPath,
          JSON.stringify({
            hooks: {
              [event]: [
                {
                  matcher: "",
                  hooks: [{ type: "command", command: "other-tool" }],
                },
                {
                  matcher: "",
                  hooks: [
                    {
                      type: "command",
                      command:
                        "sh -c 'ONE_MEMORY_DATA_DIR='\\''/old-data'\\'' '\\''/old/core/one-memory'\\'' capture codex >/dev/null 2>&1; exit 0'",
                    },
                  ],
                },
                {
                  matcher: "",
                  hooks: [
                    {
                      type: "command",
                      command:
                        "sh -c 'ONE_MEMORY_DATA_DIR='\\''/older-data'\\'' '\\''/older/core/one-memory'\\'' capture codex >/dev/null 2>&1; exit 0'",
                    },
                  ],
                },
              ],
            },
          }),
        );
      }
      const layout =
        hostId === "codex"
          ? codexLayout(dir)
          : claudeCodeLayout({
              claudeDir: dir,
              configPath: path.join(home, ".claude.json"),
            });

      await applyRecallInstall(await planRecallInstall(layout, runtime(home)));

      const target =
        hostId === "codex" ? hooksPath : path.join(dir, "settings.json");
      const document = JSON.parse(await readFile(target, "utf8")) as {
        hooks: Record<string, Array<{ hooks: Array<{ command: string }> }>>;
      };
      const commands = document.hooks[event].flatMap((entry) =>
        entry.hooks.map((hook) => hook.command),
      );
      expect(
        commands.filter((command) => command === "other-tool"),
      ).toHaveLength(1);
      expect(
        commands.filter((command) => command.includes(`capture ${hostId}`)),
      ).toHaveLength(1);
    },
  );

  it("tells capture which database the running app is using", async () => {
    const home = await root();
    const dataDir = path.join(home, "trial-data");
    const seen = path.join(home, "seen-data-dir");
    const binary = path.join(home, "one-memory");
    await writeFile(
      binary,
      "#!/bin/sh\nprintf '%s' \"$ONE_MEMORY_DATA_DIR\" > '" +
        seen.replaceAll("'", "'\\''") +
        "'\nexit 0\n",
    );
    await chmod(binary, 0o755);
    const dir = path.join(home, ".cursor");
    await mkdir(dir);
    await applyRecallInstall(
      await planRecallInstall(cursorLayout(dir), {
        ...runtime(home),
        captureCommand: binary,
        dataDir,
      }),
    );
    const installed = JSON.parse(
      await readFile(path.join(dir, "hooks.json"), "utf8"),
    ) as { hooks: { beforeSubmitPrompt: Array<{ command: string }> } };
    const command = installed.hooks.beforeSubmitPrompt[0].command;
    expect(command).toContain("ONE_MEMORY_DATA_DIR=");
    execFileSync("sh", ["-c", command], {
      input: "{}",
      timeout: 5000,
    });
    expect(await readFile(seen, "utf8")).toBe(dataDir);
  });

  it("still lets the prompt through when the capture program rejects the command", async () => {
    const home = await root();
    const binary = path.join(home, "one-memory");
    await writeFile(
      binary,
      "#!/bin/sh\necho 'Usage: one-memory [serve|status [--json]|doctor [--json]]'\nexit 2\n",
    );
    await chmod(binary, 0o755);
    const dir = path.join(home, ".cursor");
    await mkdir(dir);
    const layout = cursorLayout(dir);
    await applyRecallInstall(
      await planRecallInstall(layout, {
        ...runtime(home),
        captureCommand: binary,
      }),
    );
    const installed = JSON.parse(
      await readFile(path.join(dir, "hooks.json"), "utf8"),
    ) as { hooks: { beforeSubmitPrompt: Array<{ command: string }> } };
    const command = installed.hooks.beforeSubmitPrompt[0].command;
    const result = await promisify(execFile)("sh", ["-c", command], {
      timeout: 5000,
    });
    expect(result.stdout).toBe("");
    const boundary = await promisify(execFile)(
      "sh",
      ["-c", failOpenHookCommand(binary, "boundary", "context")],
      { timeout: 5000 },
    );
    // Hosts read a reply without hookSpecificOutput as context text.
    expect(boundary.stdout).toBe("");
  });

  it("passes a boundary's reply through when it has one", async () => {
    const home = await root();
    const binary = path.join(home, "one-memory");
    const reply = '{"hookSpecificOutput": {"additionalContext": "x"}}';
    await writeFile(binary, `#!/bin/sh\nprintf '%s\\n' '${reply}'\n`);
    await chmod(binary, 0o755);
    const boundary = await promisify(execFile)(
      "sh",
      ["-c", failOpenHookCommand(binary, "boundary", "context")],
      { timeout: 5000 },
    );
    expect(boundary.stdout).toBe(`${reply}\n`);
  });

  it("writes a Pi extension and an OpenCode plugin that call the core binary", async () => {
    const home = await root();
    const pi = path.join(home, ".pi", "agent");
    const opencode = path.join(home, ".config", "opencode");
    await mkdir(pi, { recursive: true });
    await mkdir(opencode, { recursive: true });
    await applyRecallInstall(
      await planRecallInstall(piLayout(pi), runtime(home)),
    );
    await applyRecallInstall(
      await planRecallInstall(opencodeLayout(opencode), runtime(home)),
    );
    const extension = await readFile(
      path.join(pi, "extensions", "one-memory-capture.js"),
      "utf8",
    );
    expect(extension).toContain('"/opt/memhub/core/one-memory"');
    expect(extension).toContain("before_agent_start");
    expect(extension).toContain("turn_end");
    expect(extension).not.toContain("toolResults");
    const plugin = await readFile(
      path.join(opencode, "plugin", "one-memory-capture.js"),
      "utf8",
    );
    expect(plugin).toContain("session.idle");
    expect(plugin).toContain('type: "text"');
    await applyRecallUninstall(await planRecallUninstall(piLayout(pi)));
    await expect(
      readFile(path.join(pi, "extensions", "one-memory-capture.js"), "utf8"),
    ).rejects.toThrow();
  });
});

describe("uninstall recognises our capture however it is spelled", () => {
  type Hooks = { hooks: Record<string, Array<{ command: string }>> };

  async function installedCursor() {
    const home = await root();
    const dir = path.join(home, ".cursor");
    await mkdir(dir);
    const layout = cursorLayout(dir);
    await applyRecallInstall(await planRecallInstall(layout, runtime(home)));
    const hooksPath = path.join(dir, "hooks.json");
    return { layout, hooksPath };
  }

  async function rewriteCommands(
    hooksPath: string,
    change: (command: string) => string,
  ) {
    const document = JSON.parse(await readFile(hooksPath, "utf8")) as Hooks;
    for (const entries of Object.values(document.hooks))
      for (const entry of entries) entry.command = change(entry.command);
    await writeFile(hooksPath, JSON.stringify(document));
  }

  it("removes a command whose only difference is whitespace", async () => {
    const { layout, hooksPath } = await installedCursor();
    await rewriteCommands(hooksPath, (command) =>
      command
        .replace("sh -c", "sh  \t-c")
        .replaceAll("capture cursor", "capture \t cursor"),
    );
    expect(await readFile(hooksPath, "utf8")).not.toContain("capture cursor");
    await applyRecallUninstall(await planRecallUninstall(layout));
    const left = await readFile(hooksPath, "utf8").catch(() => null);
    const commands =
      left === null
        ? []
        : Object.values((JSON.parse(left) as Partial<Hooks>).hooks ?? {})
            .flat()
            .map((entry) => entry.command);
    expect(
      commands.filter((command) => /capture\s+cursor/.test(command)),
    ).toEqual([]);
  });

  it("asks for a person when a capture command of another spelling remains", async () => {
    const { layout, hooksPath } = await installedCursor();
    await rewriteCommands(hooksPath, (command) =>
      command.replace("/opt/memhub/core/one-memory", "/elsewhere/one-memory"),
    );
    const before = await readFile(hooksPath, "utf8");
    const plan = await planRecallUninstall(layout);
    expect(plan.files).toEqual([]);
    expect(plan.review).toContainEqual({
      path: hooksPath,
      where: "hooks.beforeSubmitPrompt[0].command",
    });
    await expect(applyRecallUninstall(plan)).rejects.toThrow(
      "host_uninstall_needs_review",
    );
    expect(await readFile(hooksPath, "utf8")).toBe(before);
  });

  it("asks for a person when the hook file cannot be parsed", async () => {
    const { layout, hooksPath } = await installedCursor();
    await writeFile(hooksPath, "{ not json");
    const plan = await planRecallUninstall(layout);
    expect(plan.files).toEqual([]);
    expect(plan.review).toEqual([
      { path: hooksPath, where: expect.stringContaining("JSON") },
    ]);
  });

  it("asks for a person when Pi's capture extension was edited after install", async () => {
    const home = await root();
    const pi = path.join(home, ".pi", "agent");
    await mkdir(pi, { recursive: true });
    const layout = piLayout(pi);
    await applyRecallInstall(await planRecallInstall(layout, runtime(home)));
    const extension = path.join(pi, "extensions", "one-memory-capture.js");
    const edited = `${await readFile(extension, "utf8")}\n// mine\n`;
    await writeFile(extension, edited);
    const plan = await planRecallUninstall(layout);
    expect(plan.files).toEqual([]);
    expect(plan.review).toEqual([
      { path: extension, where: expect.any(String) },
    ]);
    await expect(applyRecallUninstall(plan)).rejects.toThrow(
      "host_uninstall_needs_review",
    );
    expect(await readFile(extension, "utf8")).toBe(edited);
  });
});
