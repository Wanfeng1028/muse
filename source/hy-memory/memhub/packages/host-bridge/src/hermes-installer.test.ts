import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  hermesLayout,
  mcpConfigPath,
  planRecallInstall,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

/** A config in the shape Hermes leaves behind once it has been configured.
 *
 * Taken from this machine after `hermes config set`: an already-populated
 * document with no `mcp_servers` section yet, and a comment block belonging to
 * the section that follows.
 */
const HOST_WRITTEN = `model:
  default: qwen-plus
  provider: custom
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
gateway:
  platforms:
    telegram:
      - hermes-telegram

# \u2500\u2500 Security \u2500\u2500
# security:
#   redact_secrets: true
`;

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "hermes-"));
  const hermesDir = path.join(root, ".hermes");
  await mkdir(hermesDir, { recursive: true });
  const layout = hermesLayout(hermesDir);
  const runtime = {
    runtimeCommand: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    mcpEntryPath: "/Applications/MemHub.app/Contents/Resources/mcp.cjs",
    discoveryPath: path.join(root, "discovery.json"),
  };
  return { root, hermesDir, layout, runtime };
}

describe("hermes recall installer", () => {
  it("merges into the settings document without touching the rest of it", async () => {
    const { hermesDir, layout, runtime } = await fixture();
    await writeFile(mcpConfigPath(layout), HOST_WRITTEN, { encoding: "utf8" });

    const plan = await planRecallInstall(layout, runtime);
    await applyRecallInstall(plan);

    const written = await readFile(mcpConfigPath(layout), "utf8");
    // Everything the host owns survives, comments included.
    expect(written).toContain("  default: qwen-plus");
    expect(written).toContain("      - hermes-telegram");
    expect(written).toContain("# \u2500\u2500 Security \u2500\u2500");
    expect(written).toContain("#   redact_secrets: true");
    // And the entry is in the dialect this host reads.
    expect(written).toContain("mcp_servers:");
    expect(written).toContain("  one-memory:");
    expect(written).toContain("ELECTRON_RUN_AS_NODE: '1'");

    const verification = await verifyRecallInstall(layout);
    expect(verification.hostId).toBe("hermes");
    expect(verification.discoveryPath).toBe(runtime.discoveryPath);
    // The app writes that file when it first runs, so absent is not a failure.
    expect(verification.discoveryPresent).toBe(false);

    expect(path.dirname(path.dirname(layout.skillPath ?? ""))).toBe(
      path.join(hermesDir, "skills"),
    );
    await expect(readFile(layout.skillPath ?? "", "utf8")).resolves.toContain(
      "one-memory",
    );
  });

  it("recognises its own entry instead of installing a second one", async () => {
    const { layout, runtime } = await fixture();
    await writeFile(mcpConfigPath(layout), HOST_WRITTEN, { encoding: "utf8" });
    await applyRecallInstall(await planRecallInstall(layout, runtime));

    const again = await planRecallInstall(layout, runtime);

    expect(again.actions).toContain("merge-mcp");
    await applyRecallInstall(again);
    const written = await readFile(mcpConfigPath(layout), "utf8");
    expect(written.match(/one-memory:/g)).toHaveLength(1);
  });

  it("gives the document back, though not the same bytes", async () => {
    const { layout, runtime } = await fixture();
    await writeFile(mcpConfigPath(layout), HOST_WRITTEN, { encoding: "utf8" });

    const plan = await planRecallInstall(layout, runtime);
    await applyRecallInstall(plan);
    await rollbackRecallInstall(layout);

    const restored = await readFile(mcpConfigPath(layout), "utf8");
    // Uninstalling takes the whole section, since `mcp_servers:` with nothing
    // under it reads as null rather than as the empty map a host would write.
    expect(restored).not.toContain("mcp_servers");
    expect(restored).not.toContain("one-memory");
    expect(restored).toContain("  default: qwen-plus");
    expect(restored).toContain("# \u2500\u2500 Security \u2500\u2500");
  });

  it("leaves a neighbouring server and the section alone", async () => {
    const { layout, runtime } = await fixture();
    await writeFile(
      mcpConfigPath(layout),
      `${HOST_WRITTEN}mcp_servers:\n  other-tool:\n    command: npx\n    args:\n      - other\n    enabled: true\n`,
      { encoding: "utf8" },
    );

    await applyRecallInstall(await planRecallInstall(layout, runtime));
    await rollbackRecallInstall(layout);

    const restored = await readFile(mcpConfigPath(layout), "utf8");
    expect(restored).toContain("  other-tool:");
    expect(restored).toContain("    command: npx");
    expect(restored).not.toContain("one-memory");
    // The section stays, because it was not ours to remove.
    expect(restored).toContain("mcp_servers:");
  });

  it("refuses a foreign entry of the same name unless told to take over", async () => {
    const { layout, runtime } = await fixture();
    await writeFile(
      mcpConfigPath(layout),
      `${HOST_WRITTEN}mcp_servers:\n  one-memory:\n    command: /somebody/else\n    enabled: true\n`,
      { encoding: "utf8" },
    );

    await expect(planRecallInstall(layout, runtime)).rejects.toThrow(
      /takeover|already/i,
    );

    const plan = await planRecallInstall(layout, runtime, { takeover: true });
    await applyRecallInstall(plan);
    await rollbackRecallInstall(layout);

    const restored = await readFile(mcpConfigPath(layout), "utf8");
    // Restored by value, not by byte: one YAML entry has no self-contained
    // text span to hand back untouched.
    expect(restored).toContain("command: /somebody/else");
  });
});
