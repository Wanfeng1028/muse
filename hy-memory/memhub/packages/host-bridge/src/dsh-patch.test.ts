import { describe, expect, it } from "vitest";

import {
  DSH_ROW_ID,
  hasUnmanagedRow,
  putDshServer,
  readDshServer,
  removeDshServer,
} from "./dsh-patch.js";

/** The user layer as dsh 0.1.2-rc.1 creates it, byte for byte.
 *
 * Note what the host's own header promises the user: `!!js` expressions are
 * allowed in this file.
 */
const PRISTINE = `# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; \`!!js\` expressions allowed).
[]
`;

/** A user layer that took the host up on that offer.
 *
 * Shaped after rows in the installed \`dsh-base\` bundle patch and the
 * \`dsh-mcp-client\` reference, both of which pass secrets by expression rather
 * than by value.
 */
const WITH_JS = `- id: llm-pi-ai
  config:
    providers:
      bailian:
        apiKeyEnv: bailian_apikey

- insert:
    - id: mcp-github
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: github
        transport: stdio
        command: npx
        args: ['-y', '@modelcontextprotocol/server-github']
        env:
          GITHUB_TOKEN: !!js process.env.GITHUB_TOKEN

- id: tool-bash
  disabled: !!js process.platform === 'win32'
`;

const SERVER = {
  command: "/Applications/MemHub.app/Contents/MacOS/MemHub",
  args: ["/Applications/MemHub.app/Contents/Resources/mcp.cjs"],
  env: {
    ELECTRON_RUN_AS_NODE: "1",
    ONE_MEMORY_MANAGED_BY: "one-memory",
  },
};

describe("dsh patch editing", () => {
  it("replaces the empty list rather than appending after it", () => {
    const written = putDshServer(PRISTINE, SERVER);

    // `[]` followed by a block item is two nodes in one document, which the
    // host refuses to load — so installing that way would break dsh outright.
    expect(written).not.toContain("[]");
    expect(written).toContain("- insert:");
    expect(written).toContain(`    - id: ${DSH_ROW_ID}`);
    // The host's own header is not ours to remove.
    expect(written).toContain("# Your patch layer for this dsh profile");
    expect(readDshServer(written)).toEqual(SERVER);
  });

  it("never reads the rest of the document as YAML", () => {
    const written = putDshServer(WITH_JS, SERVER);

    // A YAML loader without `!!js` registered rejects this file; one that
    // loads it loosely evaluates or drops the tag. Both are unacceptable in a
    // tool that was asked only to add a server, so these bytes survive intact.
    expect(written).toContain("GITHUB_TOKEN: !!js process.env.GITHUB_TOKEN");
    expect(written).toContain("disabled: !!js process.platform === 'win32'");
    expect(written).toContain("        apiKeyEnv: bailian_apikey");
    expect(readDshServer(written)).toEqual(SERVER);
  });

  it("keeps a number-like value a string", () => {
    const written = putDshServer(PRISTINE, SERVER);

    // Harness merges `env` into the child process environment, where an
    // unquoted 1 is a number and therefore not a value at all.
    expect(written).toContain("ELECTRON_RUN_AS_NODE: '1'");
    expect(readDshServer(written)?.env.ELECTRON_RUN_AS_NODE).toBe("1");
  });

  it("gives the pristine file back on uninstall", () => {
    const written = putDshServer(PRISTINE, SERVER);

    expect(removeDshServer(written)).toBe(PRISTINE);
  });

  it("leaves other rows alone on uninstall", () => {
    const written = putDshServer(WITH_JS, SERVER);

    const removed = removeDshServer(written);

    expect(removed).toBe(WITH_JS);
    expect(readDshServer(removed)).toBeNull();
  });

  it("reinstalling replaces the block instead of stacking a second one", () => {
    const once = putDshServer(PRISTINE, SERVER);
    const twice = putDshServer(once, {
      ...SERVER,
      command: "/opt/new/MemHub",
    });

    // Two rows with one id is a load error in Harness.
    expect(twice.match(new RegExp(`id: ${DSH_ROW_ID}`, "g"))).toHaveLength(1);
    expect(readDshServer(twice)?.command).toBe("/opt/new/MemHub");
  });

  it("spots a row of ours that no sentinel can remove", () => {
    const byHand = `- insert:\n    - id: ${DSH_ROW_ID}\n      name: '@deepseek-ai/dsh-mcp-client'\n`;

    // Installing over this would leave two rows sharing one id, so the caller
    // has to be told rather than allowed to proceed.
    expect(hasUnmanagedRow(byHand)).toBe(true);
    expect(hasUnmanagedRow(putDshServer(PRISTINE, SERVER))).toBe(false);
    expect(hasUnmanagedRow(WITH_JS)).toBe(false);
  });

  it("reads a path with a quote in it back unchanged", () => {
    const awkward = {
      ...SERVER,
      command: "/Users/o'brien/MemHub.app/Contents/MacOS/MemHub",
      args: ["/Users/o'brien/mcp.cjs"],
    };

    const written = putDshServer(PRISTINE, awkward);

    expect(readDshServer(written)).toEqual(awkward);
  });
});
